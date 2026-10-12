"""Bounded JSON parsing for model output.

Model text is data. It is parsed, never executed, and never used to choose a
provider, URL or file path. One repair attempt is allowed and counted; after
that the caller must abstain rather than invent a result. A truncated response
is a failed extraction, not an empty finding set.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


@dataclass(slots=True)
class ParseResult:
    payload: Any | None
    ok: bool
    repaired: bool = False
    error: str = ""
    truncated: bool = False


def _strip_fence(text: str) -> str:
    match = _FENCE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()


def _balanced_candidate(text: str, opener: str, closer: str) -> str | None:
    start = text.find(opener)
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def parse_json_object(text: str, *, finish_reason: str = "") -> ParseResult:
    """Parse a single JSON object out of model output."""
    if not text or not text.strip():
        return ParseResult(None, False, error="empty model output")

    truncated = finish_reason == "length"
    raw = _strip_fence(text)

    for candidate in (raw, _balanced_candidate(raw, "{", "}") or ""):
        if not candidate:
            continue
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return ParseResult(value, True, truncated=False)
        if isinstance(value, list):
            return ParseResult({"items": value}, True, truncated=False)

    return ParseResult(
        None,
        False,
        error="model output was not a JSON object",
        truncated=truncated,
    )


def repair_instruction(previous_output: str, error: str) -> str:
    """One bounded repair prompt. Contains no credentials and no document text."""
    return (
        "Your previous answer could not be parsed as JSON "
        f"({error}). Reply with a single JSON object and nothing else. "
        "Do not add commentary, markdown fences or trailing text.\n"
        "Previous answer (truncated to 1500 characters):\n"
        f"{previous_output[:1500]}"
    )


def coerce_str(value: Any, default: str = "unknown", limit: int = 200) -> str:
    if value is None:
        return default
    if isinstance(value, (int, float, bool)):
        return str(value)[:limit]
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned[:limit] if cleaned else default
    return default


def coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None
