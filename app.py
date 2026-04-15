from PIL import Image, ImageDraw, ImageFont
import streamlit as st
import os
from openai import OpenAI
from main import build_prompt, evaluate_macro_value, evaluate_lane_trade, diagnose_player
import urllib.parse
import cv2
import base64

# =========================
# 🔥 時間変換関数（追加）
# =========================
def time_to_seconds(t):
    parts = t.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h)*3600 + int(m)*60 + int(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m)*60 + int(s)
    else:
        return int(parts[0])

# =========================
# 🔥 フレーム抽出（完全置き換え）
# =========================
def extract_frames(video_path, start_sec=None, end_sec=None, output_dir="frames", max_frames=3):
    os.makedirs(output_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print("❌ 動画開けない")
        return []

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    start_frame = int(start_sec * fps) if start_sec else 0
    end_frame = int(end_sec * fps) if end_sec else total_frames

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    interval = max((end_frame - start_frame) // max_frames, 1)

    frames = []
    count = start_frame
    saved = 0

    while cap.isOpened() and count < end_frame and saved < max_frames:
        ret, frame = cap.read()
        if not ret:
            break

        if (count - start_frame) % interval == 0:
            frame_path = os.path.join(output_dir, f"frame_{saved}.png")
            cv2.imwrite(frame_path, frame)
            frames.append(frame_path)
            saved += 1

        count += 1

    cap.release()
    print(f"✅ 抽出成功: {len(frames)}枚")
    return frames

# =========================
# 他の関数はそのまま
# =========================



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

if "event" not in st.session_state:
    st.session_state.event = None
if "history" not in st.session_state:
    st.session_state.history = []
if "frames" not in st.session_state:
    st.session_state.frames = []

video_file = st.file_uploader(
    "動画ファイルをアップロード",
    type=["mp4", "webm"],
    key="video_uploader"
)

if video_file is not None:
    with open("temp.mp4", "wb") as f:
        f.write(video_file.read())

if video_file:
    st.video(video_file)

st.divider()

start_time = st.text_input("開始時間 (例: 00:01:40)")
end_time = st.text_input("終了時間 (例: 00:01:55)")

lane = st.selectbox("レーン", ["top", "jg", "mid", "adc", "sup"])

event = st.radio(
    "イベントを選択",
    ["トレードした", "デスした", "ガンクされた", "キルした", "集団戦した"]
)

st.session_state.event = event

if st.button("🔥 着火　🔥", key="start_button"):
    st.write("DEBUG: ボタン押された")


    st.write("DEBUG:",
         "video_file:", video_file is not None,
         "start_time:", start_time,
         "end_time:", end_time)
    
    if video_file is not None:

        with open("input.mp4", "wb") as f:
            f.write(video_file.getvalue())

        # 🔥 時間変換
        start_sec = time_to_seconds(start_time)
        end_sec = time_to_seconds(end_time)


        st.write("DEBUG start_sec:", start_sec, "end_sec:", end_sec)
        # 🔥 フレーム抽出
        frames = extract_frames(
            "input.mp4",
            start_sec=start_sec,
            end_sec=end_sec
        )
        st.write("DEBUG frames:", len(frames))

        st.session_state.frames = frames

        if len(frames) > 0:
            best_frame = frames[0]
            st.session_state.best_frame = best_frame
            if len(frames) > 0:
                try:
                    st.write("DEBUG: GPT解析開始")

                    best_frame, vision_context = pick_worst_frame(frames, client)

                    st.write("DEBUG: GPT解析成功")
                    st.write("DEBUG vision:", vision_context[:100])

                    st.session_state.best_frame = best_frame

                except Exception as e:
                    st.error(f"❌ GPTエラー: {e}")
                    st.stop()

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