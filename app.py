from PIL import Image, ImageDraw, ImageFont
import streamlit as st
import os
from openai import OpenAI
from main import build_prompt, evaluate_macro_value, evaluate_lane_trade, diagnose_player
import urllib.parse
import subprocess
import cv2
import os
import base64

def extract_frames(video_path, output_dir="frames", interval=3):
    os.makedirs(output_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    count = 0
    saved = []

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        if fps == 0:
            break

        if count % (fps * interval) == 0:
            sec = int(count / fps)
            timestamp = f"{sec//60:02d}:{sec%60:02d}"

            path = f"{output_dir}/frame_{count}_{timestamp}.jpg"

            cv2.putText(
                frame,
                f"{timestamp}",
                (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2,
                cv2.LINE_AA
            )

            cv2.imwrite(path, frame)
            saved.append(path)

        count += 1

    cap.release()
    return saved

def trim_video(input_path, start, end, output_path):
    import shutil
    shutil.copy(input_path, output_path)

def analyze_frames_with_gpt(frame_paths, client):
    descriptions = []

    for path in frame_paths[:3]:
        with open(path, "rb") as f:
            img_bytes = f.read()

        img_base64 = base64.b64encode(img_bytes).decode()

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "LoLの試合画面。この状況を具体的に説明しろ（HP状況・位置・人数差・危険度）"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}}
                    ]
                }
            ]
        )

        descriptions.append(response.choices[0].message.content)

    return "\n".join(descriptions)

def create_share_image(img_path, comments, diagnosis, output_path="share.png"):

    img = Image.open(img_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    width, height = img.size

    # 半透明黒背景
    overlay_height = int(height * 0.4)
    overlay = Image.new("RGBA", (width, overlay_height), (0, 0, 0, 180))
    img.paste(overlay, (0, height - overlay_height), overlay)

    draw = ImageDraw.Draw(img)

    # フォント
    try:
        title_font = ImageFont.truetype("arial.ttf", 40)
        font = ImageFont.truetype("arial.ttf", 32)
    except:
        title_font = ImageFont.load_default()
        font = ImageFont.load_default()

    # 👇 診断テキスト
    diagnosis_text = f"🧠 {diagnosis}"

    # 👇 コメント
    comment_text = "\n".join([
        f"① {comments[0]}",
        f"② {comments[1]}",
        f"③ {comments[2]}"
    ])

    # 👇 描画（診断）
    draw.text(
        (20, height - overlay_height + 10),
        diagnosis_text,
        fill=(255, 100, 100),
        font=title_font
    )

    # 👇 描画（コメント）
    draw.multiline_text(
        (20, height - overlay_height + 60),
        comment_text,
        fill=(255, 255, 255),
        font=font,
        spacing=10
    )

    img.save(output_path)
    return output_path

def pick_worst_frame(frame_paths, client):

    descriptions = []

    for i, path in enumerate(frame_paths[:3]):
        with open(path, "rb") as f:
            img_bytes = f.read()

        img_base64 = base64.b64encode(img_bytes).decode()

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"""
これはLoLの試合のフレーム{i}です。
このシーンのミスの重大度を10点満点で評価し、理由を一言で述べろ。

出力形式:
score:数字
reason:一言
"""},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}}
                    ]
                }
            ]
        )

        text = response.choices[0].message.content

        try:
            score = int(text.split("score:")[1].split("\n")[0])
        except:
            score = 0

        descriptions.append((score, path, text))

    worst = max(descriptions, key=lambda x: x[0])

    return worst[1], worst[2]

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

st.set_page_config(page_title="LOLコーチング", layout="centered")
st.title("🔥 ちくちくコーチングAI 🔥")

if "event" not in st.session_state:
    st.session_state.event = None
if "history" not in st.session_state:
    st.session_state.history = []
if "frames" not in st.session_state:
    st.session_state.frames = []

total = len(st.session_state.history)

video_file = st.file_uploader(
    "動画ファイルをアップロード",
    type=["mp4", "webm"],
    key="video_uploader"
)
if video_file:
    st.video(video_file)

st.divider()

st.subheader("状況入力")
st.subheader("⏱ シーン指定")

start_time = st.text_input("開始時間 (例: 00:01:40)")
end_time = st.text_input("終了時間 (例: 00:01:55)")

lane = st.selectbox(
    "レーン",
    ["top", "jg", "mid", "adc", "sup"],
    key="lane_select"
)

st.subheader("イベント選択")

event = st.radio(
    "イベントを選択",
    ["トレードした", "デスした", "ガンクされた", "キルした", "集団戦した"],
    key="event_radio"
)

st.session_state.event = event

vision_context = ""
macro_eval = ""
lane_eval = ""
diagnosis = ""

if st.button("🔥 着火　🔥", key="start_button"):

    

    if st.session_state.event is None:
        st.warning("イベントを選択して")
    else:

        

        vision_context = ""

        if video_file is not None and start_time and end_time:

            

            video_bytes = video_file.getvalue()

            with open("input.mp4", "wb") as f:
                f.write(video_bytes)

            trim_video("input.mp4", start_time, end_time, "clip.mp4")

            frames = extract_frames("clip.mp4")
            st.session_state.frames = frames

            if len(frames) > 0:
                best_frame, vision_context = pick_worst_frame(frames, client)
                st.session_state.best_frame = best_frame
                

        # 👇 診断ロジック（ここで1回だけ）
        macro_eval = evaluate_macro_value(st.session_state.event, vision_context)
        lane_eval = evaluate_lane_trade(vision_context)
        diagnosis = diagnose_player(macro_eval, lane_eval)

        

        with st.spinner("考え中..."):

            # 👇 contentは1回だけ作る（上書き禁止）
            content = build_prompt(
                lane,
                f"{start_time}〜{end_time}",
                st.session_state.event
            ) + f"""

【画面分析】
{vision_context}

【内部評価】
{macro_eval}
{lane_eval}

【診断】
{diagnosis}

【ルール】
・数値（点数）は絶対に出すな
・初心者にもわかる言葉で言え
・詰問口調で
・改善案を出せ
"""

            

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": content}]
            )

            

            # 👇 これが無かったのが今回のクラッシュ原因
            raw = response.choices[0].message.content

        # 👇 APIの外で処理
        outputs = [line for line in raw.strip().split("\n") if line.strip()]
        while len(outputs) < 3:
            outputs.append("（出力不足）")
        outputs = outputs[:3]

        st.session_state.history.append({
            "event": st.session_state.event,
            "outputs": outputs,
            "ratings": [None, None, None],
            "diagnosis": diagnosis
        })

        st.session_state.history = st.session_state.history[-3:]


# =========================
# 👇 常に表示されるエリア（修正版）
# =========================
if len(st.session_state.history) > 0:

    last = st.session_state.history[-1]
    frames = st.session_state.frames

    # 👇 best_frameなくても動くようにする
    if "best_frame" in st.session_state:
        st.image(
            st.session_state.best_frame,
            caption="🔥 一番ヤバいシーン",
            use_container_width=True
        )

    # 👇 診断
    if "diagnosis" in last:
        st.subheader(f"🧠 診断結果：{last['diagnosis']}")

    st.subheader("🔥ちくちく一言🔥")

    for i, text in enumerate(last["outputs"]):

        col_img, col_text = st.columns([1, 2])

        with col_img:
            if i < len(frames):
                st.image(frames[i], use_container_width=True)

        with col_text:
            st.success(text)

        col1, col2 = st.columns(2)

        with col1:
            if st.button(
                f"いいちくちく👍",
                key=f"good_{len(st.session_state.history)}_{i}"
            ):
                last["ratings"][i] = "good"
                st.toast(f"{i+1}個目：👍 保存")

        with col2:
            if st.button(
                f"よくないちくちく👎",
                key=f"bad_{len(st.session_state.history)}_{i}"
            ):
                last["ratings"][i] = "bad"
                st.toast(f"{i+1}個目：👎 保存")

        if last["ratings"][i]:
            if last["ratings"][i] == "good":
                st.success("→ 👍 評価済み")
            else:
                st.error("→ 👎 評価済み")

        st.divider()

    # 👇 コピー用
    combined = "\n".join(last["outputs"])
    st.code(combined)

    if st.button("🔥 コピー用"):
        st.toast("コピーして使え")

    # =========================
    # 👇 画像生成＆ダウンロード
    # =========================
    if "best_frame" in st.session_state:

        st.info("👇 画像を保存してツイートに貼れ")

        if st.button("📸 シェア画像を作成"):

            share_img = create_share_image(
                st.session_state.best_frame,
                last["outputs"],
                last["diagnosis"]
            )

            with open(share_img, "rb") as f:
                st.download_button(
                    "📥 画像をダウンロード",
                    f,
                    file_name="lol_coaching.png"
                )

    # =========================
    # 👇 シェア
    # =========================
    url_link = "https://lol-coaching-chiku-chiku-ai.streamlit.app/"

    share_text = f"""ちくちくAIからのフィードバック

🧠 診断：{last['diagnosis']}

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