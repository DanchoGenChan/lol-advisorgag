import streamlit as st
import os
from openai import OpenAI
from main import build_prompt
import urllib.parse


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

st.set_page_config(page_title="LOLコーチング", layout="centered")
st.title("🔥 ちくちくコーチングAI 🔥")

# セッション状態
if "event" not in st.session_state:
    st.session_state.event = None
if "history" not in st.session_state:
    st.session_state.history = []

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

lane = st.selectbox(
    "レーン",
    ["top", "jg", "mid", "adc", "sup"],
    key="lane_select"
)

time = st.text_input(
    "時間（例: 8:30）",
    key="time_input"
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
        with st.spinner("考え中..."):
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": build_prompt(
                            lane,
                            time,
                            st.session_state.event
                        )
                    }
                ]
            )

        raw = response.choices[0].message.content

        outputs = [line for line in raw.strip().split("\n") if line.strip()]
        # 👇 足りなかったら補完
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

    # 👇 表示
    st.subheader("🔥ちくちく一言🔥")

    for i, text in enumerate(last["outputs"]):

        st.success(f"{i+1}. {text}")

        col1, col2 = st.columns(2)

        # 👍
        with col1:
            if st.button(
                f"いいちくちく👍",
                key=f"good_{len(st.session_state.history)}_{i}"
            ):
                if last.get("ratings") is None:
                    last["ratings"] = [None, None, None]
                last["ratings"][i] = "good"
                st.toast(f"{i+1}個目：👍 保存")

        # 👎
        with col2:
            if st.button(
                f"よくないちくちく👎",
                key=f"bad_{len(st.session_state.history)}_{i}"
            ):
                if last.get("ratings") is None:
                    last["ratings"] = [None, None, None]
                last["ratings"][i] = "bad"
                st.toast(f"{i+1}個目：👎 保存")

        # 評価表示
        if last.get("ratings") and last["ratings"][i]:
            if last["ratings"][i] == "good":
                st.success("→ 👍 評価済み")
            else:
                st.error("→ 👎 評価済み")

        st.divider()

    # =========================
    # 👇 ここもこのブロック内に入れる
    # =========================
    combined = "\n".join(
        [f"{i+1}. {t}" for i, t in enumerate(last["outputs"])]
    )

    st.code(combined)

    # コピー用
    if st.button("🔥 コピー用", key=f"copy_latest_{len(st.session_state.history)}"):
        st.toast("下のテキストをコピー！（Ctrl+C）")

    # Xシェア
    url_link = "https://your-app-url.com"  # 後で変更

    share_text = f"""ちくちくコーチングAIからのフィードバック


{last['outputs'][0]}
{last['outputs'][1]}
{last['outputs'][2]}

#LOL #LeagueOfLegends #ちくちく #コーチング

👇自己責任でどうぞ
{url_link}
"""

    tweet = urllib.parse.quote(share_text)
    url = f"https://twitter.com/intent/tweet?text={tweet}"

    st.link_button("🔥 Xでシェア", url)
# =========================
# 履歴表示（修正版）
# =========================
if len(st.session_state.history) > 0:

    st.subheader("これまでのちくちく")

    for i, item in enumerate(reversed(st.session_state.history)):

        st.markdown(f"### {i+1}回目（{item['event']}）")

        for j, line in enumerate(item["outputs"]):
            st.write(f"{j+1}. {line}")

            # 👇 評価表示（ここが重要：ratingsに対応）
            if item.get("ratings") and item["ratings"][j]:
                if item["ratings"][j] == "good":
                    st.write("→ 👍")
                else:
                    st.write("→ 👎")

        # 👇 各履歴シェア
        share_text = f"""ちくちくコーチングAIからのフィードバック

{item["outputs"][0]}
{item["outputs"][1]}
{item["outputs"][2]}

#LOL #LeagueOfLegends #ちくちく #コーチング
👇自己責任でどうぞ
{url_link}
"""

        tweet = urllib.parse.quote(share_text)
        url = f"https://twitter.com/intent/tweet?text={tweet}"

        st.link_button("🔥 この回をXでシェア", url)

        st.divider()

st.divider()
st.markdown("🚩初心者～中級者向けの普通のコーチングアプリ作ってます🚩")
st.markdown("👇作業中の１杯はこちらから👇")
st.link_button("☕ コーヒー奢る", "https://buymeacoffee.com/egg_plant")