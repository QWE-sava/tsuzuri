from __future__ import annotations

from dataclasses import dataclass, field

from .config import GuardConfig
from .jsonparse import extract_json_object
from .prompt import judge_messages
from .rulebook import Rulebook
from .story_state import StoryState
from models.backend import GenParams, ModelBackend


@dataclass
class GuardIssue:
    type: str
    detail: str


@dataclass
class GuardResult:
    ok: bool = True
    issues: list[GuardIssue] = field(default_factory=list)


class SyncGuard:
    name = "sync"

    def __init__(self, config: GuardConfig | None = None) -> None:
        self.config = config or GuardConfig()

    def check(self, output: str, state: StoryState, rulebook: Rulebook, user_input: str) -> GuardResult:
        issues: list[GuardIssue] = []
        for marker in self.config.intruder_markers:
            if marker in output:
                issues.append(GuardIssue(type="intrusion", detail=f"新規人物の登場を示す表現「{marker}」が含まれています"))
                break
        if not state.user_wants_escalation and state.story_tension < self.config.tension_threshold:
            for keyword in self.config.escalation_keywords:
                if keyword in output:
                    issues.append(
                        GuardIssue(
                            type="escalation",
                            detail=f"ユーザーが加速を望んでいないのに不穏な要素「{keyword}」が含まれています",
                        )
                    )
                    break
        return GuardResult(ok=len(issues) == 0, issues=issues)


class AsyncGuard:
    name = "async-judge"

    def __init__(self, backend: ModelBackend, config: GuardConfig | None = None) -> None:
        self.backend = backend
        self.config = config or GuardConfig()

    def analyze(self, user_text: str, assistant_text: str, state: StoryState, rulebook: Rulebook) -> GuardResult:
        rulebook_summary = "\n".join(f"- {rule}" for rule in rulebook.rules[:10])
        messages = judge_messages(state.to_prompt(), rulebook_summary, user_text, assistant_text)
        params = GenParams(temperature=0.1, max_tokens=300)
        raw = self.backend.generate(messages, params)
        parsed = extract_json_object(raw)
        if parsed is None:
            return GuardResult(ok=True)
        violations = parsed.get("violations") or []
        issues: list[GuardIssue] = []
        for item in violations:
            if isinstance(item, dict):
                issue_type = str(item.get("type") or "unknown")
                detail = str(item.get("detail") or "")
                issues.append(GuardIssue(type=issue_type, detail=detail))
        return GuardResult(ok=(not issues and parsed.get("ok") is not False), issues=issues)
