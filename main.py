import streamlit as st
import os
from openai import OpenAI
import random

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
st.title("ちくちくコーチングbot")

video_file = st.file_uploader("動画ファイルをアップロード", type=["mp4", "webm"])

if video_file is not None:
    st.video(video_file)

st.divider()

st.subheader("状況入力")
lane = st.selectbox("レーン", ["top", "jg", "mid", "adc", "sup"])
time = st.text_input("時間（例: 8:30）")

# イベントUI
st.subheader("イベント選択")

event = None

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    if st.button("トレードした"):
        event = "トレードした"

with col2:
    if st.button("デスした"):
        event = "デスした"

with col3:
    if st.button("ガンクされた"):
        event = "ガンクされた"

with col4:
    if st.button("キルした"):
        event = "キルした"

with col5:
    if st.button("集団戦した"):
        event = "集団戦した"

# プロンプト関数
def build_prompt(lane, time, situation):
    import random

    emotion_patterns = [
        "呆れ気味",
        "ちょっとキレ気味",
        "冷静に見下す感じ",
        "イライラしてる感じ",
        "理解できないって感じ",
    ]

    selected = random.sample(emotion_patterns, 3)

    style = """あなたはLOL配信者のらいじんです。

特徴：
・基本辛口
・短くてキレのある一言
・少し雑でリアルな話し方

重要ルール：
・毎回言い回しを変える（同じ単語を使い回さない）
・「普通に」を多用しない
・口調に揺らぎを出す（敬語NG）
・「いや」「え？」「は？」「なんで？」などを自然に使う
・1〜2文で短く

例：
「おかしい人が2人もいると集団戦には勝てない」
「クソ雑魚の考え、発想がゴミ」
「あぁ、それ戦ってたんだ」
「今絶対死なない方がいい。これ死ぬのマジトロール」
「謝りながらファームしてほしい」
「上手くなると良いね」
「チッ、もう、キモ」
「論外の雑魚だな」

このスタイルを完全に再現してください。
"""

    return f"""
{style}

状況:
- レーン: {lane}
- 時間: {time}
- 出来事: {situation}

以下の3つの感情で、それぞれ1コメントずつ作ってください。

1. {selected[0]}
2. {selected[1]}
3. {selected[2]}

【厳守ルール】
・各コメントは1文のみ
・20〜40文字
・改行して3行で出力
・それぞれ全く違う言い回しにする
・同じ単語や表現は禁止
・説明は禁止

【出力形式】
コメント
コメント
コメント
"""

# 生成
if event:
    situation = event

    with st.spinner("考え中..."):
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": build_prompt(lane, time, situation)}
            ],
            n=1
        )

    # 👇 ここで3行に分解
    raw_output = response.choices[0].message.content
    outputs = raw_output.strip().split("\n")

    st.subheader("🔥ちくちく一言🔥")

    # 👇 表示
    for i, text in enumerate(outputs):
        st.success(f"{i+1}. {text}")

    # 👇 コピー用まとめ
    combined_text = "\n".join([f"{i+1}. {text}" for i, text in enumerate(outputs)])

    st.divider()
    st.code(combined_text, language="text")

    if st.button("🔥 3つまとめてコピー"):
        st.toast("下のテキストをコピー！（Ctrl+C）")

    # 👇 Xシェア
    import urllib.parse

    share_text = "\n".join(outputs)
    tweet_text = urllib.parse.quote(f"らいじんコーチング\n{share_text}\n#LOL #コーチング")

    tweet_url = f"https://twitter.com/intent/tweet?text={tweet_text}"

    st.link_button("🔥 Xでシェア", tweet_url)