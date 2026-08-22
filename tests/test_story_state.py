from __future__ import annotations

from engine.story_state import MAX_RECENT_EVENTS, StoryState


def test_defaults():
    state = StoryState()
    assert state.location == "不明"
    assert state.story_tension == 0.1
    assert state.user_wants_escalation is False


def test_apply_patch_updates_fields():
    state = StoryState()
    applied = state.apply_patch({"location": "喫茶店", "time": "昼", "current_activity": "コーヒーを飲む"})
    assert state.location == "喫茶店"
    assert state.time == "昼"
    assert state.current_activity == "コーヒーを飲む"
    assert "location" in applied


def test_float_clamping():
    state = StoryState()
    state.apply_patch({"story_tension": 5.0, "story_activity": -3})
    assert state.story_tension == 1.0
    assert state.story_activity == 0.0


def test_recent_events_capped():
    state = StoryState()
    events = [f"イベント{i}" for i in range(30)]
    state.apply_patch({"recent_events": events})
    assert len(state.recent_events) == MAX_RECENT_EVENTS


def test_escalation_flag_recorded():
    state = StoryState()
    applied = state.apply_patch({"story_tension": 0.9, "user_wants_escalation": True})
    assert state.story_tension == 0.9
    assert state.user_wants_escalation is True
    assert applied["user_wants_escalation"] is True


def test_patch_mirrors_reality_without_clamp():
    state = StoryState()
    state.apply_patch({"story_tension": 0.9})
    assert state.story_tension == 0.9
    assert state.user_wants_escalation is False


def test_save_load_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    state = StoryState(location="公園", characters=["Alice"], story_tension=0.4)
    state.save(path)
    loaded = StoryState.load(path)
    assert loaded.location == "公園"
    assert loaded.characters == ["Alice"]
    assert abs(loaded.story_tension - 0.4) < 1e-9


def test_to_prompt_contains_key_fields():
    state = StoryState(location="海", time="夕方")
    text = state.to_prompt()
    assert "海" in text
    assert "夕方" in text
    assert "展開加速" in text
