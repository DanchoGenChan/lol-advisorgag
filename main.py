def normalize_outputs(raw_text: str):
    lines = [line.strip() for line in (raw_text or "").splitlines() if line.strip()]

    if len(lines) >= 3:
        return lines[:3]

    fallback = [
        "画面情報が薄い、判断ミスが特定しきれてない",
        "HPと人数差を先に見ろ、なんでノールックで入った？",
        "次はちゃんと見てから動け",
    ]
    lines.extend(fallback[len(lines):])
    return lines[:3]


def build_prompt(lane, time, situation, feedback=None, vision_context=""):
    macro_rules = """
【マクロ評価ルール】

このゲームはネクサス破壊が最終目的であり、全ての行動はその価値で評価する。

■ オブジェクト価値（目安）
ネクサス: 100
エルダー: 90
バロン: 70
ドラゴンソウル: 75
ドラゴン1体: 15
ヘラルド: 35
ミッド1stタワー: 50
サイドタワー: 20

■ 判断ルール
・常に「どちらが価値が高いか」で判断すること
・トレード（交換）時は必ず価値差を意識すること
・バロンはタワー取得が前提なら価値が上がる
・ソウルやエルダー前は戦闘リソース（ウルト・サモスペ）の価値が上がる
・価値の低いオブジェクトのために高価値を捨てるのは明確なミス

■ 出力ルール
・数値（点数）は絶対に出すな（内部思考のみで使う）
・感覚ではなく、理由を明確にすること
"""

    feedback_text = ""
    if feedback:
        good = feedback.get("good", 0)
        bad = feedback.get("bad", 0)
        total = feedback.get("total", 0)

        if total > 0:
            feedback_text = f"""
過去の評価傾向:
- good: {good}
- bad: {bad}
- total: {total}

指示:
- good > bad: 今の厳しさを維持
- bad >= good: 指摘をより具体化し、改善手順を短く明確に
"""

    style_rules = """
あなたはLOLの上級者プレイヤーです。
初心者のプレイを見て、少しイラつきながらコーチングしてください。

▼基本スタイル
・軽くキレてる
・短い
・断定する
・無駄な説明なし
・LOL経験者が「分かる」と思う内容

▼絶対にやること
・実際のプレイミスを具体的に指摘する
・必ず改善案を出す
・「なんでそれやった？」系の詰問を入れる

▼禁止
・ふわっとした指摘
・一般論
・説明口調
・丁寧語
・出力不足
・1行40字以上の長文
・「ミスの指摘」などの抽象ワード
・期待してるなど、直接的な応援

▼出力（重要）
3行で出力：

1行目：ミスの指摘（何がダメか）
2行目：改善＋詰問（どうすべきだったか＋なんでやらない？）
3行目：雑な応援（少し呆れつつ一言）
"""

    return f"""
あなたはLoLのプロコーチです。

{macro_rules}

{style_rules}

{feedback_text}

状況:
- レーン: {lane}
- 時間: {time}
- 出来事: {situation}

画面分析:
{vision_context if vision_context else "情報不足"}

この状況を見て、上のルールに従って3行でコメントしろ。

【出力フォーマット（絶対厳守）】
・必ず3行で出力
・1行＝1文で書け
・改行で区切れ（同じ行に複数文書くな）
・3行未満は失敗とみなす

【出力内容ルール】
1行目：具体的なミスを指摘しろ（抽象禁止）
2行目：改善案＋詰問を入れろ
3行目：雑に一言で締めろ（短く）
"""


def evaluate_macro_value(event, vision_context):
    text = vision_context or ""

    if any(k in text for k in ["人数不利", "人数差-1", "人数差-2"]):
        return "人数不利でオブジェクト判断が遅い"

    if "バロン" in text and any(k in text for k in ["視界なし", "ノーワード", "暗い川"]):
        return "バロン周辺の視界管理が甘い"

    if "ドラゴン" in text and any(k in text for k in ["レーン押し負け", "ウェーブ不利"]):
        return "ドラゴン前のレーン準備が不足"

    if any(k in text for k in ["タワー前で孤立", "サイド深追い"]):
        return "低価値行動でリスクを背負っている"

    return "オブジェクト価値の判断が曖昧"


def evaluate_lane_trade(vision_context):
    text = vision_context or ""

    if any(k in text for k in ["HP不利", "HP差不利"]):
        return "HP不利なのにトレード継続している"

    if any(k in text for k in ["ミニオン不利", "敵ウェーブ大"]):
        return "ミニオン状況を無視して仕掛けている"

    if any(k in text for k in ["スキル落ち", "サモスペ無し", "CD中"]):
        return "重要CD中の判断が雑"

    return "トレード判断が甘い"


def diagnose_player(macro_eval, lane_eval):
    text = f"{macro_eval} / {lane_eval}"

    if "曖昧" in text:
        return "思考停止マン"

    if "低価値" in text:
        return "一生アイテムそろわない人"

    if "HP不利" in text:
        return "チキンでもなく無謀でもある"

    if "遅い" in text or "不足" in text:
        return "準備不足ファイター"

    return "ggwp"