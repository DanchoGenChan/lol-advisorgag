from PIL import Image, ImageDraw, ImageFont
import streamlit as st
import os
import json
import base64
import textwrap
import urllib.parse
import cv2
from openai import OpenAI

from main import (
    build_prompt,
    evaluate_macro_value,
    evaluate_lane_trade,
    diagnose_player,
    normalize_outputs,
)


def wrap_text(text, width=18):
    return "\n".join(textwrap.wrap(text or "", width=width))


def parse_time_to_sec(t):
    parts = (t or "").strip().split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    if len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(parts[0])


def extract_frames(video_path, output_dir="frames", max_frames=3):
    os.makedirs(output_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        cap.release()
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
            frame_path = os.path.join(output_dir, f"frame_{saved}.png")
            cv2.imwrite(frame_path, frame)
            frames.append(frame_path)
            saved += 1

        count += 1

    cap.release()
    return frames


def trim_video(input_path, start, end, output_path):
    start_sec = parse_time_to_sec(start)
    end_sec = parse_time_to_sec(end)

    if end_sec <= start_sec:
        raise ValueError("終了時間は開始時間より後にしてください")

    cap = cv2.VideoCapture(input_path)
    fps = cap.get(cv2.CAP_PROP_FPS)

    if fps <= 0:
        cap.release()
        raise ValueError("動画のFPS取得に失敗")

    start_frame = int(start_sec * fps)
    end_frame = int(end_sec * fps)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = None
    current = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        if current == start_frame:
            h, w, _ = frame.shape
            out = cv2.VideoWriter(output_path, fourcc, fps, (w, h))

        if out is not None and start_frame <= current <= end_frame:
            out.write(frame)

        if current > end_frame:
            break

        current += 1

    cap.release()
    if out:
        out.release()


def build_feedback_from_history(history):
    good = 0
    bad = 0

    for item in history:
        for r in item.get("ratings", []):
            if r == "good":
                good += 1
            elif r == "bad":
                bad += 1

    return {"good": good, "bad": bad, "total": good + bad}


def pick_worst_frame_and_context(frame_paths, client):
    if not frame_paths:
        return None, "", ""

    content = [
        {
            "type": "text",
            "text": """
3枚のLoLフレームを比較し、最もミスが重い1枚を選べ。
JSONのみで返答せよ。余計な文章は禁止。

{
  "worst_index": 0,
  "vision_context": "HP状況/位置/人数差/危険度/オブジェクト状況を短文で",
  "reason": "重大なミス理由を一言"
}
""",
        }
    ]

    for path in frame_paths[:3]:
        with open(path, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode()
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img_base64}"},
            }
        )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": content}],
    )

    try:
        data = json.loads(response.choices[0].message.content)
        worst_index = int(data.get("worst_index", 0))
        worst_index = max(0, min(worst_index, min(2, len(frame_paths) - 1)))
        vision_context = data.get("vision_context", "")
        reason = data.get("reason", "")
        return frame_paths[worst_index], vision_context, reason
    except Exception:
        return frame_paths[0], "", "json parse failed"


def create_share_image(img_path, comments, diagnosis, output_path="share.png"):
    img = Image.open(img_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    width, height = img.size

    top_overlay = Image.new("RGBA", (width, 100), (0, 0, 0, 180))
    img.paste(top_overlay, (0, 0), top_overlay)

    try:
        font_big = ImageFont.truetype("arial.ttf", 40)
        font = ImageFont.truetype("arial.ttf", 28)
    except Exception:
        font_big = ImageFont.load_default()
        font = ImageFont.load_default()

    draw.text((20, 20), f"診断: {diagnosis}", fill=(255, 255, 255), font=font_big)

    overlay_height = int(height * 0.35)
    overlay = Image.new("RGBA", (width, overlay_height), (0, 0, 0, 180))
    img.paste(overlay, (0, height - overlay_height), overlay)

    safe_comments = comments[:3]
    if len(safe_comments) < 3:
        safe_comments += ["", "", ""]
        safe_comments = safe_comments[:3]

    text = "\n".join(
        [
            f"① {wrap_text(safe_comments[0])}",
            f"② {wrap_text(safe_comments[1])}",
            f"③ {wrap_text(safe_comments[2])}",
        ]
    )

    draw.multiline_text(
        (20, height - overlay_height + 20),
        text,
        fill=(255, 255, 255),
        font=font,
        spacing=10,
    )

    img.save(output_path)
    return output_path


# -------------------------
# App
# -------------------------
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    st.error("OPENAI_API_KEY が未設定です")
    st.stop()

client = OpenAI(api_key=api_key)

st.set_page_config(page_title="LOLコーチング", layout="centered")
st.title("🔥 ちくちくコーチングAI 🔥")

if "event" not in st.session_state:
    st.session_state.event = None
if "history" not in st.session_state:
    st.session_state.history = []
if "frames" not in st.session_state:
    st.session_state.frames = []
if "best_frame" not in st.session_state:
    st.session_state.best_frame = None
if "share_img_path" not in st.session_state:
    st.session_state.share_img_path = None

video_file = st.file_uploader(
    "動画ファイルをアップロード",
    type=["mp4", "webm"],
    key="video_uploader",
)

if video_file is not None:
    with open("temp.mp4", "wb") as f:
        f.write(video_file.read())

    frames = extract_frames("temp.mp4")
    st.session_state.frames = frames

    if len(frames) == 0:
        st.error("❌ フレーム抽出失敗")
        st.session_state.best_frame = None
    else:
        st.success(f"✅ {len(frames)}枚抽出")
        st.session_state.best_frame = frames[0]

if video_file:
    st.video(video_file)

st.divider()
st.subheader("状況入力")
st.subheader("⏱ シーン指定")

start_time = st.text_input("開始時間 (例: 00:01:40)")
end_time = st.text_input("終了時間 (例: 00:01:55)")

lane = st.selectbox("レーン", ["top", "jg", "mid", "adc", "sup"], key="lane_select")

st.subheader("イベント選択")
event = st.radio(
    "イベントを選択",
    ["トレードした", "デスした", "ガンクされた", "キルした", "集団戦した"],
    key="event_radio",
)
st.session_state.event = event

if st.button("🔥 着火　🔥", key="start_button"):
    if st.session_state.event is None:
        st.warning("イベントを選択して")
    else:
        vision_context = ""
        worst_reason = ""

        if video_file is not None and start_time and end_time:
            try:
                video_bytes = video_file.getvalue()
                with open("input.mp4", "wb") as f:
                    f.write(video_bytes)

                trim_video("input.mp4", start_time, end_time, "clip.mp4")
                frames = extract_frames("clip.mp4")
                st.session_state.frames = frames

                if len(frames) > 0:
                    best_frame, vision_context, worst_reason = pick_worst_frame_and_context(frames, client)
                    st.session_state.best_frame = best_frame
            except Exception as e:
                st.error(f"動画処理エラー: {e}")

        feedback = build_feedback_from_history(st.session_state.history)
        macro_eval = evaluate_macro_value(st.session_state.event, vision_context)
        lane_eval = evaluate_lane_trade(vision_context)
        diagnosis = diagnose_player(macro_eval, lane_eval)

        with st.spinner("考え中..."):
            content = build_prompt(
                lane,
                f"{start_time}〜{end_time}",
                st.session_state.event,
                feedback=feedback,
                vision_context=vision_context,
            ) + f"""

【補足】
worst_reason: {worst_reason}
内部評価: {macro_eval} / {lane_eval}
診断: {diagnosis}

【ルール】
・数値（点数）は絶対に出すな
・初心者にもわかる言葉で言え
・詰問口調で
・改善案を出せ
"""

            outputs = [
                "出力失敗",
                "GPTの応答がおかしい",
                "プロンプト見直せ",
            ]
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": content}],
                )
                raw = response.choices[0].message.content if response and response.choices else ""
                outputs = normalize_outputs(raw)
            except Exception:
                outputs = normalize_outputs("")

        st.session_state.history.append(
            {
                "event": st.session_state.event,
                "outputs": outputs,  # 常にlen=3
                "ratings": [None, None, None],
                "diagnosis": diagnosis,
            }
        )
        st.session_state.history = st.session_state.history[-3:]


# -------------------------
# 表示エリア
# -------------------------
best_frame = st.session_state.get("best_frame", None)
frames = st.session_state.get("frames", [])
history = st.session_state.get("history", [])

if len(history) > 0:
    last = history[-1]
    last_outputs = normalize_outputs("\n".join(last.get("outputs", [])))

    if st.session_state.get("best_frame") is not None:
        st.image(st.session_state.best_frame, caption="🔥 一番ヤバいシーン", use_container_width=True)

    if "diagnosis" in last:
        st.subheader(f"🧠 診断結果：{last['diagnosis']}")

    st.subheader("🔥ちくちく一言🔥")

    for i, text in enumerate(last_outputs):
        col_img, col_text = st.columns([1, 2])

        with col_img:
            if i < len(frames):
                st.image(frames[i], use_container_width=True)

        with col_text:
            st.success(text)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("いいちくちく👍", key=f"good_{len(history)}_{i}"):
                last["ratings"][i] = "good"
                st.toast(f"{i+1}個目：👍 保存")

        with col2:
            if st.button("よくないちくちく👎", key=f"bad_{len(history)}_{i}"):
                last["ratings"][i] = "bad"
                st.toast(f"{i+1}個目：👎 保存")

        if last["ratings"][i]:
            if last["ratings"][i] == "good":
                st.success("→ 👍 評価済み")
            else:
                st.error("→ 👎 評価済み")

        st.divider()

    combined = "\n".join(last_outputs)
    st.code(combined)

    if st.button("🔥 コピー用"):
        st.toast("コピーして使え")

    if best_frame is not None:
        if st.button("📸 シェア画像を作成"):
            share_img = create_share_image(
                best_frame,
                last_outputs,
                last.get("diagnosis", "診断なし"),
            )
            st.session_state.share_img_path = share_img
            st.toast("画像を生成した")

        share_img_path = st.session_state.get("share_img_path")
        if share_img_path and os.path.exists(share_img_path):
            with open(share_img_path, "rb") as f:
                st.download_button(
                    "📥 画像をダウンロード",
                    data=f.read(),
                    file_name="lol_coaching.png",
                    mime="image/png",
                )

    url_link = "https://lol-coaching-chiku-chiku-ai.streamlit.app/"
    share_text = f"""ちくちくAIからのフィードバック

【診断】
{last.get("diagnosis", "")}

【ちくちく】
{last_outputs[0]}
{last_outputs[1]}
{last_outputs[2]}

#LOL #LeagueOfLegends #ちくちく #コーチング

👇君は褒めてもらえるかな？
{url_link}
"""
    tweet = urllib.parse.quote(share_text)
    url = f"https://twitter.com/intent/tweet?text={tweet}"
    st.link_button("🔥 Xでシェア", url)