from PIL import Image, ImageDraw, ImageFont
import streamlit as st
import os
from openai import OpenAI
from main import build_prompt, evaluate_macro_value, evaluate_lane_trade, diagnose_player
import urllib.parse
import subprocess
import cv2
import base64

# =========================
# 🎯 時間文字列 → 秒
# =========================
def time_to_seconds(t):
    try:
        parts = list(map(int, t.split(":")))
        if len(parts) == 3:
            return parts[0]*3600 + parts[1]*60 + parts[2]
        elif len(parts) == 2:
            return parts[0]*60 + parts[1]
    except:
        return 0
    return 0

# =========================
# 🎯 動画トリミング（完全版）
# =========================
def trim_video(input_path, start, end, output_path):
    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-ss", start,
        "-to", end,
        "-c", "copy",
        output_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# =========================
# 🎯 フレーム抽出（時間範囲前提）
# =========================
def extract_frames(video_path, output_dir="frames", max_frames=3):
    os.makedirs(output_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames == 0:
        return []

    interval = max(total_frames // max_frames, 1)

    frames = []
    count = 0
    saved = 0

    while cap.isOpened() and saved < max_frames:
        ret, frame = cap.read()
        if not ret:
            break

        if count % interval == 0:
            path = os.path.join(output_dir, f"frame_{saved}.png")
            cv2.imwrite(path, frame)
            frames.append(path)
            saved += 1

        count += 1

    cap.release()
    return frames

# =========================
# 🎯 最悪フレーム選定
# =========================
def pick_worst_frame(frame_paths, client):
    scored = []

    for i, path in enumerate(frame_paths):
        with open(path, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode()

        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": f"""
このLoLのシーンのミスの重大度を10点満点で評価しろ。
score:数字 だけ返せ
"""},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}}
                ]
            }]
        )

        text = res.choices[0].message.content

        try:
            score = int(text.split("score:")[1].strip())
        except:
            score = 0

        scored.append((score, path))

    if len(scored) == 0:
        return None, ""

    worst = max(scored, key=lambda x: x[0])
    return worst[1], "最もミスが大きいシーン"

# =========================
# 🎯 画像生成
# =========================
def create_share_image(img_path, comments, diagnosis, output_path="share.png"):
    img = Image.open(img_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    w, h = img.size

    overlay_top = Image.new("RGBA", (w, 100), (0,0,0,180))
    img.paste(overlay_top, (0,0), overlay_top)

    try:
        font_big = ImageFont.truetype("arial.ttf", 40)
        font = ImageFont.truetype("arial.ttf", 28)
    except:
        font_big = ImageFont.load_default()
        font = ImageFont.load_default()

    draw.text((20,20), f"診断: {diagnosis}", fill=(255,255,255), font=font_big)

    overlay_h = int(h*0.35)
    overlay = Image.new("RGBA", (w, overlay_h), (0,0,0,180))
    img.paste(overlay, (0, h-overlay_h), overlay)

    text = "\n".join([
        f"① {comments[0]}",
        f"② {comments[1]}",
        f"③ {comments[2]}"
    ])

    draw.multiline_text((20, h-overlay_h+20), text, fill=(255,255,255), font=font)

    img.save(output_path)
    return output_path

# =========================
# UI
# =========================
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

st.set_page_config(page_title="LOLコーチング", layout="centered")
st.title("🔥 ちくちくコーチングAI 🔥")

if "history" not in st.session_state:
    st.session_state.history = []
if "best_frame" not in st.session_state:
    st.session_state.best_frame = None

video_file = st.file_uploader("動画アップロード", type=["mp4","webm"])

if video_file:
    st.video(video_file)

st.subheader("⏱ シーン指定")
start_time = st.text_input("開始時間", "00:00:05")
end_time = st.text_input("終了時間", "00:00:10")

lane = st.selectbox("レーン", ["top","jg","mid","adc","sup"])
event = st.radio("イベント", ["トレードした","デスした","ガンクされた","キルした","集団戦した"])

# =========================
# 実行
# =========================
if st.button("🔥 着火"):

    if not video_file:
        st.error("動画なし")
        st.stop()

    with open("input.mp4", "wb") as f:
        f.write(video_file.getvalue())

    # ✅ 時間切り出し
    #trim_video("input.mp4", start_time, end_time, "clip.mp4")


    # ✅ 抽出（ここが今回の本質）
    frames = extract_frames("clip.mp4")

    if len(frames) == 0:
        st.error("フレーム抽出失敗")
        st.stop()

    # ✅ 最悪シーン取得
    best_frame, vision_context = pick_worst_frame(frames, client)
    st.session_state.best_frame = best_frame

    # =========================
    # GPT生成
    # =========================
    content = build_prompt(lane, f"{start_time}〜{end_time}", event)

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":content}]
    )

    raw = res.choices[0].message.content

    outputs = [l for l in raw.split("\n") if l.strip()]
    while len(outputs) < 3:
        outputs.append("（出力不足）")

    st.session_state.history.append({
        "outputs": outputs[:3],
        "diagnosis": "思考停止マン"
    })

# =========================
# 表示
# =========================
if len(st.session_state.history) > 0:

    last = st.session_state.history[-1]

    if st.session_state.best_frame:
        st.image(st.session_state.best_frame, caption="🔥 最悪シーン")

    st.subheader("🔥ちくちく🔥")

    for t in last["outputs"]:
        st.success(t)

    if st.button("📸 画像生成"):
        path = create_share_image(
            st.session_state.best_frame,
            last["outputs"],
            last["diagnosis"]
        )
        with open(path,"rb") as f:
            st.download_button("DL", f, "lol.png")
    # =========================
    # 👇 Xシェア
    # =========================
    url_link = "https://lol-coaching-chiku-chiku-ai.streamlit.app/"

    share_text = f"""ちくちくAIからのフィードバック

【診断】
{last.get("diagnosis", "")}

【ちくちく】
{last['outputs'][0]}
{last['outputs'][1]}
{last['outputs'][2]}

#LOL #LeagueOfLegends #ちくちく #コーチング

👇君は褒めてもらえるかな？
{url_link}
"""

    tweet = urllib.parse.quote(share_text)
    url = f"https://twitter.com/intent/tweet?text={tweet}"

    st.link_button("🔥 Xでシェア", url)