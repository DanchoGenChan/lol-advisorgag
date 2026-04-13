from PIL import Image, ImageDraw, ImageFont
import streamlit as st
import os
from openai import OpenAI
from main import build_prompt
import urllib.parse
import subprocess
import cv2
import os
import base64  # 👈 追加

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
    # ffmpeg使えない環境用：そのままコピー
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

def create_share_image(img_path, comments, output_path="share.png"):

    img = Image.open(img_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    width, height = img.size

    # 半透明黒背景
    overlay_height = int(height * 0.35)
    overlay = Image.new("RGBA", (width, overlay_height), (0, 0, 0, 180))
    img.paste(overlay, (0, height - overlay_height), overlay)

    draw = ImageDraw.Draw(img)

    # フォント
    try:
        font = ImageFont.truetype("arial.ttf", 32)
    except:
        font = ImageFont.load_default()

    # テキスト
    text = "\n".join([
        f"① {comments[0]}",
        f"② {comments[1]}",
        f"③ {comments[2]}"
    ])

    # 描画
    draw.multiline_text(
        (20, height - overlay_height + 20),
        text,
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

# =========================
# 動画
# =========================
video_file = st.file_uploader(
    "動画ファイルをアップロード",
    type=["mp4", "webm"],
    key="video_uploader"
)
if video_file:
    st.video(video_file)

st.divider()

# =========================
# 入力
# =========================
st.subheader("状況入力")
st.subheader("⏱ シーン指定")

start_time = st.text_input("開始時間 (例: 00:01:40)")
end_time = st.text_input("終了時間 (例: 00:01:55)")

lane = st.selectbox(
    "レーン",
    ["top", "jg", "mid", "adc", "sup"],
    key="lane_select"
)


# =========================
# イベント選択
# =========================
st.subheader("イベント選択")

event = st.radio(
    "イベントを選択",
    ["トレードした", "デスした", "ガンクされた", "キルした", "集団戦した"],
    key="event_radio"
)

st.session_state.event = event

# =========================
# 実行ボタン
# =========================
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

            st.write(f"抽出フレーム数: {len(frames)}")

            if len(frames) > 0:
                best_frame, vision_context = pick_worst_frame(frames, client)
                st.session_state.best_frame = best_frame

        with st.spinner("考え中..."):
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": build_prompt(
                            lane,
                            f"{start_time}〜{end_time}",
                            st.session_state.event
                        ) + f"""【重要：以下は実際の画面分析】
                                   {vision_context}
                             この情報を必ず使って具体的に指摘、改善案の提示をしろ
                             """
                    }
                ]
            )

        raw = response.choices[0].message.content

        outputs = [line for line in raw.strip().split("\n") if line.strip()]
        while len(outputs) < 3:
            outputs.append("（出力不足）")
        outputs = outputs[:3]

        st.session_state.history.append({
            "event": st.session_state.event,
            "outputs": outputs,
            "ratings": [None, None, None]
        })

        st.session_state.history = st.session_state.history[-3:]

# =========================
# 👇 常に表示されるエリア（ここが重要）
# =========================
if len(st.session_state.history) > 0:

    last = st.session_state.history[-1]
    frames = st.session_state.frames

if "best_frame" in st.session_state:
    st.image(
        st.session_state.best_frame,
        caption="🔥 一番ヤバいシーン",
        use_container_width=True
    )
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
                if last.get("ratings") is None:
                    last["ratings"] = [None, None, None]
                last["ratings"][i] = "good"
                st.toast(f"{i+1}個目：👍 保存")

        with col2:
            if st.button(
                f"よくないちくちく👎",
                key=f"bad_{len(st.session_state.history)}_{i}"
            ):
                if last.get("ratings") is None:
                    last["ratings"] = [None, None, None]
                last["ratings"][i] = "bad"
                st.toast(f"{i+1}個目：👎 保存")

        if last.get("ratings") and last["ratings"][i]:
            if last["ratings"][i] == "good":
                st.success("→ 👍 評価済み")
            else:
                st.error("→ 👎 評価済み")

        st.divider()

    combined = "\n".join(last["outputs"])

    st.code(combined)

    if st.button("🔥 コピー用", key=f"copy_latest_{len(st.session_state.history)}"):
        st.toast("下のテキストをコピー！（Ctrl+C）")

    url_link = "https://lol-coaching-chiku-chiku-ai.streamlit.app/"

    share_text = f"""ちくちくコーチングAIからのフィードバック

st.link_button("🔥 Xでシェア", url)
# =========================
# 👇 画像生成＆ダウンロード
# =========================
if "best_frame" in st.session_state:

    if st.button("📸 シェア画像を作成"):

        share_img = create_share_image(
            st.session_state.best_frame,
            last["outputs"]
        )

        with open(share_img, "rb") as f:
            st.download_button(
                "📥 画像をダウンロード",
                f,
                file_name="lol_coaching.png"
            )

{last['outputs'][0]}
{last['outputs'][1]}
{last['outputs'][2]}

#LOL #LeagueOfLegends #ちくちく #コーチング

👇君もちくちくされてみないか
{url_link}
"""

    tweet = urllib.parse.quote(share_text)
    url = f"https://twitter.com/intent/tweet?text={tweet}"

    st.link_button("🔥 Xでシェア", url)

if len(st.session_state.history) > 0:

    st.subheader("これまでのちくちく")

    for i, item in enumerate(reversed(st.session_state.history)):

        st.markdown(f"### {i+1}回目（{item['event']}）")

        for j, line in enumerate(item["outputs"]):
            st.write(f"{j+1}. {line}")

            if item.get("ratings") and item["ratings"][j]:
                if item["ratings"][j] == "good":
                    st.write("→ 👍")
                else:
                    st.write("→ 👎")

        share_text = f"""ちくちくコーチングAIからのフィードバック

{item["outputs"][0]}
{item["outputs"][1]}
{item["outputs"][2]}

#LOL #LeagueOfLegends #ちくちく #コーチング
👇君もちくちくされてみないか
{url_link}
"""

        tweet = urllib.parse.quote(share_text)
        url = f"https://twitter.com/intent/tweet?text={tweet}"

        st.link_button("🔥 この回をXでシェア", url)

        st.divider()

st.divider()
st.markdown("🚩初心者～中級者向けのマジで使えるアプリ目指して改良中です🚩")
st.markdown("👇よかったら作業中の1杯奢ってくださいな！👇")
st.link_button("☕ コーヒー奢る", "https://buymeacoffee.com/egg_plant")