from __future__ import annotations

from engine.config import ContextConfig
from engine.context import ContextManager
from engine.memory import Memory
from engine.rulebook import Rulebook
from engine.story_state import StoryState


def make_rulebook() -> Rulebook:
    return Rulebook.from_dict(
        {
            "characters": [{"name": "Alice", "personality": ["優しい"]}],
            "world": {"technology": "modern"},
            "rules": ["第三者を勝手に登場させない"],
        }
    )


def test_bundle_contains_core_layers():
    manager = ContextManager(ContextConfig(token_budget=4000))
    state = StoryState(location="喫茶店")
    memory = Memory()
    memory.add_fact("Aliceは猫が苦手")
    bundle = manager.build(state, memory, make_rulebook(), [], "猫の話をしよう")
    rules_text = bundle.block_text("rules")
    state_text = bundle.block_text("state")
    assert "物語ルール" in rules_text
    assert "Alice" in rules_text
    assert "喫茶店" in state_text
    assert bundle.user_input == "猫の話をしよう"
    assert any(name == "memory" for name, _ in bundle.blocks)


def test_budget_trims_recent_messages():
    manager = ContextManager(ContextConfig(token_budget=1200))
    state = StoryState()
    memory = Memory()
    rulebook = make_rulebook()
    history = [
        {"role": "user", "content": f"履歴メッセージ{i}。" + "あ" * 200}
        for i in range(20)
    ]
    bundle = manager.build(state, memory, rulebook, history, "最新の入力")
    assert len(bundle.recent_messages) < len(history)
    assert bundle.recent_messages[-1]["content"].endswith("あ" * 200)
    assert bundle.user_input == "最新の入力"


def test_summary_block_included():
    manager = ContextManager(ContextConfig(token_budget=4000))
    memory = Memory()
    memory.summary = "これまでのあらすじです。"
    bundle = manager.build(StoryState(), memory, make_rulebook(), [], "こんにちは")
    assert "これまでのあらすじ" in bundle.block_text("summary")


def test_total_tokens_positive():
    manager = ContextManager()
    bundle = manager.build(StoryState(), Memory(), make_rulebook(), [], "入力")
    assert bundle.total_tokens > 0
