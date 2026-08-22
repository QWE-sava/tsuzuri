from __future__ import annotations

import json

from .context import ContextBundle

BASE_SYSTEM = """あなたは物語会話エンジン「TSUZURI」の物語コアです。ユーザーと協力して物語を進めます。

以下の厳守ルールに従ってください。
1. Rulebookに明示されていない第三者・キャラクターを勝手に登場させない。新しい人物を登場させてよいのは、ユーザーが要求した場合だけである。
2. キャラクターの性格・関係性・口調を勝手に変更しない。
3. 平穏な展開は停滞ではない。活動度が低いことを理由に事件やトラブルを発生させない。
4. 「ユーザーが展開加速を望んでいる: いいえ」の場合、急展開・不穏化・災害・事件を発生させない。日常の穏やかなやり取りを続けること。
5. Story Stateの場所・時刻・天候・登場人物と矛盾しない。勝手に場所を移動させたり時間を大きく進めたりしない。
6. 過去に起きた出来事を再発させない。長期記憶や過去イベントと矛盾する内容を出力しない。
7. メタな説明（設定解説・AIである旨など）をせず、物語本文のみを出力する。
8. ユーザーの発言を勝手に書き換えたり無視したりしない。ユーザーの意図に沿って応答する。

出力形式: 日本語。地の文とセリフで構成する。"""


def build_system_message(bundle: ContextBundle, corrections: list[str] | None = None) -> str:
    parts: list[str] = [BASE_SYSTEM]
    summary = bundle.block_text("summary")
    if summary:
        parts.append(summary)
    events = bundle.block_text("events")
    if events:
        parts.append(events)
    memory = bundle.block_text("memory")
    if memory:
        parts.append(memory)
    rules = bundle.block_text("rules")
    if rules:
        parts.append(rules)
    state = bundle.block_text("state")
    parts.append("【現在のStory State】\n" + state)
    if corrections:
        parts.append(
            "【直前の出力への修正指示】\n前回の出力には以下の問題がありました。これらを必ず修正した上で応答してください。\n"
            + "\n".join(f"- {issue}" for issue in corrections)
        )
    return "\n\n".join(parts)


def build_messages(bundle: ContextBundle, corrections: list[str] | None = None) -> list[dict]:
    messages: list[dict] = [{"role": "system", "content": build_system_message(bundle, corrections)}]
    messages.extend(bundle.recent_messages)
    messages.append({"role": "user", "content": bundle.user_input})
    return messages


def state_update_prompt(state_dict: dict, user_text: str, assistant_text: str) -> str:
    return (
        "現在のStory State(JSON)と最新のやり取りを与えます。"
        "やり取りによって変化があった項目のみを含むJSONパッチを出力してください。\n\n"
        "ルール:\n"
        "- 変化がない項目は含めない\n"
        "- 活動度(activity)が低いことを理由に新しい出来事を作らない\n"
        "- user_wants_escalation はユーザーが明示的に加速を要求した場合のみ true にする\n"
        "- 出力はJSONオブジェクトのみ。説明文は書かない\n\n"
        f"現在のState:\n{json.dumps(state_dict, ensure_ascii=False, indent=2)}\n\n"
        f"最新のやり取り:\nユーザー: {user_text}\n応答: {assistant_text}\n\n"
        "JSONパッチ:"
    )


GUARD_JUDGE_PROMPT = (
    "あなたは物語会話の検査官です。直近のやり取りが、Story State・Rulebook・以下の検査項目に違反していないか判定します。\n\n"
    "検査項目:\n"
    "1. キャラクター性格・関係性の矛盾\n"
    "2. 世界設定との矛盾\n"
    "3. 時系列矛盾\n"
    "4. 場所矛盾\n"
    "5. 不要な第三者登場（Rulebook外の人物）\n"
    "6. 不要なイベント発生（平穏なのに事件が起きた等）\n"
    "7. 不穏化（ユーザーが加速を望んでいないのに不穏になった）\n"
    "8. 既出イベントの重複\n\n"
    "出力は次のJSON形式のみ:\n"
    '{"ok": true/false, "violations": [{"type": "項目名", "detail": "簡潔な説明"}]}\n'
)

FALLBACK_NOTE = (
    "これは最終フォールバック生成です。上記の修正指示を最優先し、安全で穏やかな応答のみを行ってください。"
)


def judge_messages(state_prompt: str, rulebook_summary: str, user_text: str, assistant_text: str) -> list[dict]:
    return [
        {"role": "system", "content": GUARD_JUDGE_PROMPT},
        {
            "role": "user",
            "content": (
                f"【Story State】\n{state_prompt}\n\n"
                f"【Rulebook 要約】\n{rulebook_summary or 'なし'}\n\n"
                f"【判定対象のやり取り】\nユーザー: {user_text}\n応答: {assistant_text}"
            ),
        },
    ]
