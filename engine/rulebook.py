from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Character:
    name: str
    personality: list[str] = field(default_factory=list)
    relationships: dict[str, str] = field(default_factory=dict)
    notes: str = ""

    def render(self) -> str:
        lines = [f"◆ {self.name}"]
        if self.personality:
            lines.append("性格: " + "・".join(self.personality))
        if self.relationships:
            relations = ", ".join(f"{key}={value}" for key, value in self.relationships.items())
            lines.append(f"関係性: {relations}")
        if self.notes:
            lines.append(f"備考: {self.notes}")
        return "\n".join(lines)


@dataclass
class Rulebook:
    characters: list[Character] = field(default_factory=list)
    world: dict[str, Any] = field(default_factory=dict)
    rules: list[str] = field(default_factory=list)

    @property
    def character_names(self) -> list[str]:
        return [character.name for character in self.characters if character.name]

    def mentioned_characters(self, text: str) -> list[Character]:
        return [character for character in self.characters if character.name and character.name in text]

    def render_characters(self, names: list[str] | None = None) -> str:
        targets = self.characters if names is None else [c for c in self.characters if c.name in names]
        return "\n\n".join(character.render() for character in targets)

    def render_world(self) -> str:
        if not self.world:
            return ""
        lines = [f"- {key}: {value}" for key, value in self.world.items() if str(value).strip()]
        return "\n".join(lines)

    def render_rules(self) -> str:
        return "\n".join(f"- {rule}" for rule in self.rules)

    @classmethod
    def from_dict(cls, data: dict | None) -> "Rulebook":
        data = data or {}
        characters = []
        for item in data.get("characters") or []:
            characters.append(
                Character(
                    name=str(item.get("name") or "").strip(),
                    personality=[str(p) for p in (item.get("personality") or [])],
                    relationships={str(k): str(v) for k, v in (item.get("relationships") or {}).items()},
                    notes=str(item.get("notes") or ""),
                )
            )
        return cls(
            characters=characters,
            world={str(k): v for k, v in (data.get("world") or {}).items()},
            rules=[str(r) for r in (data.get("rules") or [])],
        )

    @classmethod
    def load_yaml(cls, path: str | Path) -> "Rulebook":
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(raw)
