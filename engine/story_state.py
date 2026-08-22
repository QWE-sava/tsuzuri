from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

MAX_RECENT_EVENTS = 10
MAX_LIST_ITEMS = 20


@dataclass
class StoryState:
    location: str = "不明"
    time: str = "不明"
    weather: str = "不明"
    characters: list[str] = field(default_factory=list)
    current_activity: str = ""
    recent_events: list[str] = field(default_factory=list)
    important_objects: list[str] = field(default_factory=list)
    active_conflicts: list[str] = field(default_factory=list)
    story_tension: float = 0.1
    story_activity: float = 0.3
    user_wants_escalation: bool = False
    turn: int = 0

    def apply_patch(self, patch: dict) -> dict:
        applied: dict = {}
        if patch.get("user_wants_escalation") is not None:
            self.user_wants_escalation = bool(patch["user_wants_escalation"])
        for spec in fields(self):
            key = spec.name
            if key == "user_wants_escalation":
                continue
            if key not in patch or patch[key] is None:
                continue
            value = patch[key]
            if key in ("story_tension", "story_activity"):
                try:
                    number = max(0.0, min(1.0, float(value)))
                except (TypeError, ValueError):
                    continue
                setattr(self, key, number)
                applied[key] = number
            elif key == "user_wants_escalation":
                self.user_wants_escalation = bool(value)
                applied[key] = self.user_wants_escalation
            elif key == "turn":
                try:
                    self.turn = int(value)
                    applied[key] = self.turn
                except (TypeError, ValueError):
                    continue
            elif isinstance(getattr(self, key), list):
                items = [str(item).strip() for item in value if str(item).strip()]
                cap = MAX_RECENT_EVENTS if key == "recent_events" else MAX_LIST_ITEMS
                setattr(self, key, items[:cap])
                applied[key] = items[:cap]
            elif isinstance(getattr(self, key), str):
                setattr(self, key, str(value).strip())
                applied[key] = getattr(self, key)
        if "user_wants_escalation" in patch and patch["user_wants_escalation"] is not None:
            applied["user_wants_escalation"] = self.user_wants_escalation
        return applied

    def to_prompt(self) -> str:
        characters = "、".join(self.characters) if self.characters else "なし"
        events = "\n".join(f"  - {event}" for event in self.recent_events[-5:]) or "  - なし"
        objects = "、".join(self.important_objects) if self.important_objects else "なし"
        conflicts = "、".join(self.active_conflicts) if self.active_conflicts else "なし"
        escalation = "はい" if self.user_wants_escalation else "いいえ"
        return (
            f"- 場所: {self.location}\n"
            f"- 時刻: {self.time}\n"
            f"- 天候: {self.weather}\n"
            f"- 登場中のキャラクター: {characters}\n"
            f"- 現在の行動: {self.current_activity or '特になし'}\n"
            f"- 最近の出来事:\n{events}\n"
            f"- 重要な物品: {objects}\n"
            f"- 未解決の対立: {conflicts}\n"
            f"- 緊張度(tension): {self.story_tension:.2f} / 活動度(activity): {self.story_activity:.2f}\n"
            f"- ユーザーが展開加速を望んでいる: {escalation}"
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "StoryState":
        state = cls()
        if data:
            state.apply_patch(data)
        return state

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "StoryState":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
