from __future__ import annotations

import json


def _find_block(text: str, open_char: str, close_char: str) -> str | None:
    start = -1
    depth = 0
    in_string = False
    escape = False
    for index, char in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == open_char:
            if depth == 0:
                start = index
            depth += 1
        elif char == close_char and depth > 0:
            depth -= 1
            if depth == 0 and start >= 0:
                return text[start : index + 1]
    return None


def extract_json_object(text: str) -> dict | None:
    block = _find_block(text or "", "{", "}")
    if block is None:
        return None
    try:
        parsed = json.loads(block)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def extract_json_array(text: str) -> list | None:
    block = _find_block(text or "", "[", "]")
    if block is None:
        return None
    try:
        parsed = json.loads(block)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) else None
