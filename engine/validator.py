from __future__ import annotations

import re

from .self_guard import GuardResult

_META_PATTERN = re.compile(r"(システムとして|AIとして|言語モデル|プロンプト|Story State)")


def validate_output(text: str, guard_result: GuardResult | None = None, min_chars: int = 2) -> tuple[bool, list[str]]:
    issues: list[str] = []
    stripped = (text or "").strip()
    if len(stripped) < min_chars:
        issues.append("出力が空または短すぎます")
    if len(stripped) > 30 and len(set(stripped)) <= 3:
        issues.append("出力が同一文字の繰り返しです")
    if _META_PATTERN.search(stripped):
        issues.append("メタな説明が含まれています")
    if guard_result is not None:
        for issue in guard_result.issues:
            issues.append(f"{issue.type}: {issue.detail}")
    return (len(issues) == 0, issues)
