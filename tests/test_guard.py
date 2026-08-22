from __future__ import annotations

from engine.self_guard import AsyncGuard, SyncGuard
from engine.story_state import StoryState
from models.backend import MockBackend


def test_intrusion_detected(rulebook):
    guard = SyncGuard()
    state = StoryState()
    result = guard.check("窓の外から見知らぬ男が現れた。", state, rulebook, "今日は楽しかったね")
    assert not result.ok
    assert result.issues[0].type == "intrusion"


def test_clean_output_passes(rulebook):
    guard = SyncGuard()
    state = StoryState(location="主人公の家")
    result = guard.check("Aliceは微笑んだ。「今日は楽しかったね」", state, rulebook, "うん。また来よう")
    assert result.ok


def test_escalation_blocked_when_calm(rulebook):
    guard = SyncGuard()
    state = StoryState(story_tension=0.1)
    result = guard.check("突然、遠くで銃声が響いた。", state, rulebook, "のんびりしよう")
    assert not result.ok
    assert result.issues[0].type == "escalation"


def test_escalation_allowed_when_user_wants_it(rulebook):
    guard = SyncGuard()
    state = StoryState(story_tension=0.1, user_wants_escalation=True)
    result = guard.check("突然、遠くで銃声が響いた。", state, rulebook, "スリルが欲しいな")
    assert result.ok


def test_escalation_allowed_when_tension_high(rulebook):
    guard = SyncGuard()
    state = StoryState(story_tension=0.9)
    result = guard.check("悲鳴が聞こえた。", state, rulebook, "どうする？")
    assert result.ok


def test_async_guard_parses_verdict(rulebook):
    backend = MockBackend(responses=['{"ok": false, "violations": [{"type": "intrusion", "detail": "第三者が登場"}]}'])
    guard = AsyncGuard(backend)
    result = guard.analyze("こんにちは", "謎の人物が現れた", StoryState(), rulebook)
    assert not result.ok
    assert len(result.issues) == 1
    assert result.issues[0].type == "intrusion"


def test_async_guard_fail_open_on_garbage():
    backend = MockBackend(responses=["判定できませんでした。"])
    guard = AsyncGuard(backend)
    from tests.conftest import make_rulebook

    result = guard.analyze("こんにちは", "穏やかな一日だった", StoryState(), make_rulebook())
    assert result.ok
