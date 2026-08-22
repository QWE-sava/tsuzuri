from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from models.backend import GenParams, ModelBackend

from .jsonparse import extract_json_array

_TOKEN_SPLIT = re.compile(r"[、。！？!?\s「」『』（）()・,:;、.]+")

SUMMARY_SYSTEM = (
    "あなたは物語会話の記録係です。与えられた会話を要約してください。"
    "キャラクターの関係性・重要な出来事・約束・所有物・場所と時刻の変化を失わないでください。"
    "挨拶や相槌は省略します。出力は日本語の要約本文のみです。"
)

FACT_SYSTEM = (
    "あなたは物語会話の記録係です。"
    "会話から長期記憶として保持すべき事実だけを抽出してください。"
    "対象: 人物関係・性格の発覚・約束・重要な物品・場所の移動・未解決の出来事。"
    "挨拶・相槌・一時的な感情表現は対象外です。"
)


@dataclass
class Fact:
    id: str
    text: str
    kind: str = "fact"
    turn: int = 0
    tags: list[str] = field(default_factory=list)


def tokenize(text: str) -> set[str]:
    tokens = set()
    for token in _TOKEN_SPLIT.split((text or "").lower()):
        token = token.strip()
        if len(token) >= 2:
            tokens.add(token)
    return tokens


def char_ngrams(text: str) -> tuple[set[str], set[str]]:
    cleaned = _TOKEN_SPLIT.sub("", (text or "").lower())
    unigrams = set(cleaned)
    bigrams = {cleaned[i : i + 2] for i in range(len(cleaned) - 1)}
    return unigrams, bigrams


class Memory:
    def __init__(self) -> None:
        self.facts: list[Fact] = []
        self.summary: str = ""
        self.summarized_until: int = 0

    def add_fact(self, text: str, kind: str = "fact", turn: int = 0, tags: list[str] | None = None) -> Fact | None:
        text = (text or "").strip()
        if not text:
            return None
        for existing in self.facts:
            if existing.text == text:
                return existing
        fact = Fact(id=uuid.uuid4().hex[:8], text=text, kind=kind, turn=turn, tags=list(tags or []))
        self.facts.append(fact)
        return fact

    def events(self) -> list[str]:
        return [fact.text for fact in self.facts if fact.kind == "event"]

    def relevant_facts(self, query: str, k: int = 10) -> list[Fact]:
        query_unigrams, query_bigrams = char_ngrams(query)
        query_tokens = tokenize(query)
        scored: list[tuple[float, int, Fact]] = []
        total = max(len(self.facts), 1)
        for index, fact in enumerate(self.facts):
            fact_unigrams, fact_bigrams = char_ngrams(fact.text + " ".join(fact.tags))
            fact_tokens = tokenize(fact.text) | set(fact.tags)
            bigram_overlap = len(query_bigrams & fact_bigrams)
            unigram_overlap = len(query_unigrams & fact_unigrams)
            token_overlap = len(query_tokens & fact_tokens)
            score = 2.0 * bigram_overlap + 1.0 * unigram_overlap + 3.0 * token_overlap
            score += (index / total) * 0.5
            if score > 0:
                scored.append((score, index, fact))
        scored.sort(key=lambda item: (-item[0], item[1]))
        selected = [fact for _, _, fact in scored[:k]]
        if not selected:
            selected = self.facts[-k:]
        return selected

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "summarized_until": self.summarized_until,
            "facts": [asdict(fact) for fact in self.facts],
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "Memory":
        memory = cls()
        if not data:
            return memory
        memory.summary = str(data.get("summary") or "")
        memory.summarized_until = int(data.get("summarized_until") or 0)
        for item in data.get("facts") or []:
            memory.facts.append(
                Fact(
                    id=str(item.get("id") or uuid.uuid4().hex[:8]),
                    text=str(item.get("text") or ""),
                    kind=str(item.get("kind") or "fact"),
                    turn=int(item.get("turn") or 0),
                    tags=[str(tag) for tag in item.get("tags") or []],
                )
            )
        return memory

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Memory":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def format_dialogue(messages: list[dict]) -> str:
    role_names = {"user": "ユーザー", "assistant": "応答"}
    return "\n".join(f"{role_names.get(m['role'], m['role'])}: {m['content']}" for m in messages)


def summarize_turns(
    backend: ModelBackend,
    previous_summary: str,
    dialogue_messages: list[dict],
    params: GenParams | None = None,
) -> str:
    params = params or GenParams(temperature=0.3, max_tokens=500)
    user_content = (
        f"既存の要約:\n{previous_summary or '（まだありません）'}\n\n"
        f"新しく対象になる会話:\n{format_dialogue(dialogue_messages)}\n\n"
        "既存の要約に統合した新しい要約だけを出力してください。"
    )
    messages = [
        {"role": "system", "content": SUMMARY_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    output = backend.generate(messages, params)
    return output.strip()


def extract_facts(backend: ModelBackend, dialogue_messages: list[dict], params: GenParams | None = None) -> list[str]:
    params = params or GenParams(temperature=0.2, max_tokens=400)
    user_content = (
        f"会話:\n{format_dialogue(dialogue_messages)}\n\n"
        'JSON配列形式で出力してください。例: ["Aliceは猫が苦手", "二人は来週映画に行く予定"]\n'
        "重要な事実がない場合は空配列 [] のみを出力してください。JSON配列以外は出力しないでください。"
    )
    messages = [
        {"role": "system", "content": FACT_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    output = backend.generate(messages, params)
    parsed = extract_json_array(output)
    if not parsed:
        return []
    facts: list[str] = []
    for item in parsed:
        text = str(item).strip()
        if text:
            facts.append(text)
    return facts[:6]
