import random

def build_prompt(lane, time, situation, feedback=None):

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
        total = feedback.get("total", 0)

        if total > 0:
            feedback_text = f"""
過去の評価傾向:
- good率: {good}/{total}

指示:
- goodが多い → 今のスタイル維持
- badがある → もっと自然で辛口に
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

▼出力（重要）
3行で出力：

1行目：ミスの指摘（何がダメか）
2行目：改善＋詰問（どうすべきだったか＋なんでやらない？）
3行目：雑な応援（少し呆れつつ一言）

▼例のニュアンス（コピペ禁止）
・「そのHPで前出るの普通に意味わからん」
・「ウェーブ見てから動けよ、なんで突っ込んだ？」
・「これから上手くなるといいね」
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

この状況を見て、上のルールに従って3行でコメントしろ。
"""


def evaluate_macro_value(event, vision_context):
    """
    オブジェクト価値ベースで判断する
    """

    values = {
        "nexus": 100,
        "elder": 90,
        "baron": 70,
        "soul": 75,
        "dragon": 15,
        "mid_tower": 50,
        "side_tower": 20,
        "herald": 35,
        "voidgrub": 10
    }

    # 超簡易ロジック（あとで強化可能）
    if "ドラゴン" in vision_context:
        return "ドラゴンの価値を無視している"
    if "バロン" in vision_context:
        return "バロンへの対応が遅れている"
    if "タワー" in vision_context:
        return "低価値オブジェクトに固執している"

    return "オブジェクト価値の判断が曖昧"


def evaluate_lane_trade(vision_context):
    """
    レーン戦ロジック
    """

    if "HP差" in vision_context and "負け" in vision_context:
        return "ダメトレ負けてるのに殴り返してない"

    if "CS" in vision_context:
        return "CS取るタイミングでプレッシャーかけれてない"

    return "トレード判断が甘い"

def diagnose_player(macro_eval, lane_eval):
    """
    プレイヤー診断
    """

    text = f"{macro_eval} / {lane_eval}"

    if "曖昧" in text:
        return "思考停止してる"

    if "低価値" in text:
        return "一生アイテムそろわない人"

    if "殴り返してない" in text:
        return "チキン野郎"

    if "遅れている" in text:
        return "鱗滝さんに殴られる"

    return "ggwp"