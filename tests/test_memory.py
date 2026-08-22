from __future__ import annotations

from engine.memory import Memory, extract_facts, summarize_turns
from models.backend import MockBackend


def test_add_fact_and_dedupe():
    memory = Memory()
    first = memory.add_fact("Aliceは猫が苦手", turn=1)
    second = memory.add_fact("Aliceは猫が苦手", turn=2)
    assert first is not None
    assert second is first
    assert len(memory.facts) == 1


def test_relevant_search_ranks_by_overlap():
    memory = Memory()
    memory.add_fact("Aliceは猫が苦手")
    memory.add_fact("二人は先週映画館へ行った")
    memory.add_fact("ユーザーはコーヒーが好き")
    hits = memory.relevant_facts("猫の話をしよう", k=2)
    assert hits[0].text == "Aliceは猫が苦手"


def test_events_filter():
    memory = Memory()
    memory.add_fact("Aliceは猫が苦手", kind="fact")
    memory.add_fact("二人は映画館へ行った", kind="event")
    assert memory.events() == ["二人は映画館へ行った"]


def test_save_load_roundtrip(tmp_path):
    path = tmp_path / "memory.json"
    memory = Memory()
    memory.summary = "あらすじ"
    memory.summarized_until = 4
    memory.add_fact("事実A", turn=2)
    memory.save(path)
    loaded = Memory.load(path)
    assert loaded.summary == "あらすじ"
    assert loaded.summarized_until == 4
    assert [f.text for f in loaded.facts] == ["事実A"]


def test_summarize_turns_uses_backend():
    backend = MockBackend(responses=["統合後の要約"])
    result = summarize_turns(backend, "旧要約", [{"role": "user", "content": "こんにちは"}, {"role": "assistant", "content": "元気だよ"}])
    assert result == "統合後の要約"
    joined = "\n".join(m["content"] for m in backend.calls[0])
    assert "旧要約" in joined


def test_extract_facts_parses_array():
    backend = MockBackend(responses=['["Aliceは猫が苦手", "来週デートの予定", ""]'])
    facts = extract_facts(backend, [{"role": "user", "content": "猫、苦手だよね"}, {"role": "assistant", "content": "うん…"}])
    assert facts == ["Aliceは猫が苦手", "来週デートの予定"]


def test_extract_facts_garbage_returns_empty():
    backend = MockBackend(responses=["特に抽出できるものはありません。"])
    facts = extract_facts(backend, [{"role": "user", "content": "そうなんだ"}, {"role": "assistant", "content": "うん"}])
    assert facts == []
