"""Model-output JSON parsing: fences, prose, truncation and coercion."""

from __future__ import annotations

import pytest

from sovra.jsonio import (
    coerce_int,
    coerce_str,
    parse_json_object,
    repair_instruction,
)


def test_plain_json_object_parses() -> None:
    result = parse_json_object('{"relation": "consistent"}')
    assert result.ok is True
    assert result.payload == {"relation": "consistent"}
    assert result.truncated is False


def test_fenced_json_parses() -> None:
    result = parse_json_object('Here you go:\n```json\n{"a": 1}\n```\n')
    assert result.ok is True
    assert result.payload == {"a": 1}


def test_json_embedded_in_prose_is_extracted() -> None:
    result = parse_json_object('Sure! {"a": {"b": 2}} and that is my answer.')
    assert result.ok is True
    assert result.payload == {"a": {"b": 2}}


def test_json_array_is_wrapped_not_discarded() -> None:
    result = parse_json_object('[{"a": 1}]')
    assert result.ok is True
    assert result.payload == {"items": [{"a": 1}]}


def test_empty_output_fails_cleanly() -> None:
    result = parse_json_object("")
    assert result.ok is False
    assert result.payload is None
    assert "empty" in result.error


def test_malformed_json_fails_without_a_payload() -> None:
    result = parse_json_object("this is not json at all")
    assert result.ok is False
    assert result.payload is None


def test_truncated_output_is_flagged_and_yields_no_payload() -> None:
    """A truncated response is a failed extraction, never an empty result set."""
    result = parse_json_object('{"claims": [{"passage_id": "doc-p0"', finish_reason="length")
    assert result.ok is False
    assert result.payload is None
    assert result.truncated is True


def test_unbalanced_object_without_length_finish_is_not_flagged_truncated() -> None:
    result = parse_json_object('{"claims": [', finish_reason="stop")
    assert result.ok is False
    assert result.truncated is False


def test_repair_instruction_mentions_the_error_and_stays_bounded() -> None:
    instruction = repair_instruction("x" * 5000, "model output was not a JSON object")
    assert "not a JSON object" in instruction
    assert len(instruction) < 2000


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, "unknown"), ("", "unknown"), ("  ", "unknown"), (7, "7"), (True, "True")],
)
def test_coerce_str_defaults_on_missing_values(value, expected: str) -> None:
    assert coerce_str(value) == expected


def test_coerce_str_truncates_long_values() -> None:
    assert len(coerce_str("z" * 900, limit=10)) == 10


@pytest.mark.parametrize(
    ("value", "expected"),
    [(5, 5), (5.0, 5), ("5", 5), (" 12 ", 12), (None, None), (True, None), ("x", None), (5.5, None)],
)
def test_coerce_int_is_strict_about_booleans_and_floats(value, expected) -> None:
    assert coerce_int(value) == expected
