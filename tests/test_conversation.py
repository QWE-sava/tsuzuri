from __future__ import annotations

from engine.conversation import ConversationCore
from tests.conftest import make_rulebook

GOOD_REPLY = "Aliceは静かに微笑んだ。「うん、また一緒に来よう」。窓の外では雨が降り続いている。"
INTRUSION_REPLY = "突然、見知らぬ男が部屋に入ってきて銃声が響いた。"


def _collect(generator) -> str:
    return "".join(chunk for chunk in generator)


def test_send_appends_history_and_schedules_background(config, mock_backend_factory):
    backend = mock_backend_factory([GOOD_REPLY])
    core = ConversationCore(config, backend, make_rulebook())
    output = _collect(core.send("今日は楽しかったね"))
    assert GOOD_REPLY in output
    assert len(core.history) == 2
    assert core.history[-1]["role"] == "assistant"

    core.wait_background(timeout=30)
    assert core.state.turn == 1
    facts = [fact.text for fact in core.memory.facts]
    assert "Aliceは猫が苦手" in facts


def test_sync_guard_triggers_regeneration(config, mock_backend_factory):
    config.guard.max_retry = 1
    backend = mock_backend_factory([INTRUSION_REPLY, GOOD_REPLY])
    core = ConversationCore(config, backend, make_rulebook())
    output = _collect(core.send("のんびり過ごそう"))
    assert "再生成" in output
    assert INTRUSION_REPLY not in "".join(entry["content"] for entry in core.history)
    assistant_entries = [entry for entry in core.history if entry["role"] == "assistant"]
    assert len(assistant_entries) == 1
    assert assistant_entries[0]["content"] == GOOD_REPLY


def test_regenerate_removes_previous_reply(config, mock_backend_factory):
    config.guard.max_retry = 0
    backend = mock_backend_factory(["一回目の応答。", "二回目の応答。"])
    core = ConversationCore(config, backend, make_rulebook())
    _collect(core.send("こんにちは"))
    output = _collect(core.regenerate())
    assert "二回目の応答。" in output
    contents = [entry["content"] for entry in core.history]
    assert "一回目の応答。" not in contents
    assert contents.count("二回目の応答。") == 1


def test_state_update_job_applies_patch(config, mock_backend_factory):
    config.memory.facts_enabled = False
    config.guard.async_judge = False
    backend = mock_backend_factory([GOOD_REPLY])
    core = ConversationCore(config, backend, make_rulebook())
    _collect(core.send("喫茶店でおしゃべり"))
    core.wait_background(timeout=30)
    assert core.state.location == "喫茶店"


def test_new_session_resets_everything(config, mock_backend_factory):
    config.guard.async_judge = False
    config.memory.facts_enabled = False
    backend = mock_backend_factory([GOOD_REPLY])
    core = ConversationCore(config, backend, make_rulebook())
    _collect(core.send("こんにちは"))
    core.start_new_session()
    assert core.history == []
    assert core.state.turn == 0
    assert core.session_dir.name.startswith("session-")
