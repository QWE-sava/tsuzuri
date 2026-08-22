from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from engine.config import TsuzuriConfig
from engine.rulebook import Rulebook
from models.backend import MockBackend


def make_rulebook() -> Rulebook:
    return Rulebook.from_dict(
        {
            "characters": [
                {"name": "Alice", "personality": ["優しい", "人見知り"], "relationships": {"user": "恋人"}},
            ],
            "world": {"technology": "modern", "supernatural": False},
            "rules": ["明示されていない第三者を勝手に登場させない"],
        }
    )


def job_responder(story_replies: list[str]):
    queue = list(story_replies)

    def respond(messages):
        joined = "\n".join(m["content"] for m in messages)
        if "JSONパッチ" in joined:
            return '{"location": "喫茶店", "story_tension": 0.2}'
        if "JSON配列" in joined:
            return '["Aliceは猫が苦手"]'
        if "検査官" in joined:
            return '{"ok": true, "violations": []}'
        if "要約" in joined:
            return "統合されたあらすじ。"
        if queue:
            return queue.pop(0)
        return "Aliceは微笑んで頷いた。"

    return respond


@pytest.fixture
def rulebook() -> Rulebook:
    return make_rulebook()


@pytest.fixture
def config(tmp_path) -> TsuzuriConfig:
    cfg = TsuzuriConfig()
    cfg.saves_dir = tmp_path / "saves"
    cfg.session_id = "test-session"
    return cfg


@pytest.fixture
def mock_backend_factory():
    def factory(responses: list[str] | None = None):
        return MockBackend(responder=job_responder(responses or []))

    return factory
