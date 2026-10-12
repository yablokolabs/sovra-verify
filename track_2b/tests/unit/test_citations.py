"""Citation resolution: spans, quote derivation and rejection of fabricated evidence.

Quotes must be sliced from canonical text at the recorded offsets. A quote
string a model supplies is never trusted.
"""

from __future__ import annotations

import pytest

from sovra.citations import (
    MAX_QUOTE_CHARS,
    WINDOW_TOLERANCE,
    resolve_all,
    resolve_span,
)
from sovra.models import Passage

PART_A = "Agreement clause 7.2: payment within 30 days of the invoice date. " * 8
PART_B = "Policy 4.1: all supplier invoices are settled within 60 days. " * 8
CANONICAL = PART_A + "\n\n" + PART_B
FIRST_END = len(PART_A)
SECOND_START = FIRST_END + 2
SECOND_END = len(CANONICAL)


@pytest.fixture
def passages() -> dict[str, Passage]:
    return {
        "doc-a-p0": Passage(
            id="doc-a-p0",
            document_id="doc-a",
            page=1,
            text=CANONICAL[0:FIRST_END],
            start_offset=0,
            end_offset=FIRST_END,
            paragraph_index=0,
        ),
        "doc-b-p0": Passage(
            id="doc-b-p0",
            document_id="doc-b",
            page=2,
            text=CANONICAL[SECOND_START:SECOND_END],
            start_offset=SECOND_START,
            end_offset=SECOND_END,
            paragraph_index=0,
        ),
    }


def test_valid_span_resolves_and_quote_is_the_canonical_slice(passages) -> None:
    result = resolve_span(
        passage_id="doc-a-p0",
        start_offset=0,
        end_offset=40,
        passages_by_id=passages,
        canonical_text=CANONICAL,
    )
    assert result.resolved is True
    assert result.citation is not None
    assert result.citation.quote == CANONICAL[0:40]
    assert result.citation.page == 1
    assert result.citation.document_id == "doc-a"
    assert result.citation.start_offset == 0


def test_span_past_end_of_canonical_text_is_rejected(passages) -> None:
    result = resolve_span(
        passage_id="doc-a-p0",
        start_offset=0,
        end_offset=len(CANONICAL) + 25,
        passages_by_id=passages,
        canonical_text=CANONICAL,
    )
    assert result.resolved is False
    assert "past the end" in result.reason


def test_inverted_offsets_are_rejected(passages) -> None:
    result = resolve_span(
        passage_id="doc-a-p0",
        start_offset=120,
        end_offset=40,
        passages_by_id=passages,
        canonical_text=CANONICAL,
    )
    assert result.resolved is False
    assert "inverted" in result.reason or "empty" in result.reason


def test_negative_start_offset_is_rejected(passages) -> None:
    result = resolve_span(
        passage_id="doc-a-p0",
        start_offset=-5,
        end_offset=40,
        passages_by_id=passages,
        canonical_text=CANONICAL,
    )
    assert result.resolved is False


def test_unknown_passage_id_is_rejected(passages) -> None:
    result = resolve_span(
        passage_id="does-not-exist",
        start_offset=0,
        end_offset=40,
        passages_by_id=passages,
        canonical_text=CANONICAL,
    )
    assert result.resolved is False
    assert "unknown passage id" in result.reason


def test_span_far_outside_its_passage_is_rejected_as_fabricated(passages) -> None:
    """A span pointing into a different document region must not become evidence."""
    start = passages["doc-a-p0"].end_offset + WINDOW_TOLERANCE + 200
    result = resolve_span(
        passage_id="doc-a-p0",
        start_offset=start,
        end_offset=start + 40,
        passages_by_id=passages,
        canonical_text=CANONICAL,
    )
    assert result.resolved is False
    assert "does not overlap" in result.reason


def test_span_ending_inside_another_passage_is_rejected(passages) -> None:
    start = SECOND_START
    result = resolve_span(
        passage_id="doc-a-p0",
        start_offset=start,
        end_offset=start + 30,
        passages_by_id=passages,
        canonical_text=CANONICAL,
    )
    assert result.resolved is False


def test_too_short_span_is_rejected(passages) -> None:
    result = resolve_span(
        passage_id="doc-a-p0",
        start_offset=0,
        end_offset=3,
        passages_by_id=passages,
        canonical_text=CANONICAL,
    )
    assert result.resolved is False
    assert "too short" in result.reason


def test_long_span_is_clamped_to_the_reviewable_maximum(passages) -> None:
    result = resolve_span(
        passage_id="doc-a-p0",
        start_offset=0,
        end_offset=FIRST_END,
        passages_by_id=passages,
        canonical_text=CANONICAL,
    )
    assert result.resolved is True
    assert result.citation is not None
    assert result.citation.end_offset - result.citation.start_offset <= MAX_QUOTE_CHARS


def test_none_offsets_fall_back_to_the_whole_passage(passages) -> None:
    result = resolve_span(
        passage_id="doc-b-p0",
        start_offset=None,
        end_offset=None,
        passages_by_id=passages,
        canonical_text=CANONICAL,
    )
    assert result.resolved is True
    assert result.citation is not None
    assert result.citation.quote == passages["doc-b-p0"].text


# -- resolve_all -----------------------------------------------------------
def test_resolve_all_ignores_a_model_supplied_quote_string(passages) -> None:
    nominations = [
        {
            "passage_id": "doc-a-p0",
            "start_offset": 0,
            "end_offset": 40,
            "quote": "FABRICATED TEXT THAT IS NOT IN THE DOCUMENT",
            "text": "FABRICATED TEXT THAT IS NOT IN THE DOCUMENT",
        }
    ]
    citations, reasons = resolve_all(
        nominations=nominations, passages_by_id=passages,
        canonical_by_document={"doc-a": CANONICAL, "doc-b": CANONICAL},
    )
    assert reasons == []
    assert len(citations) == 1
    assert citations[0].quote == CANONICAL[0:40]
    assert "FABRICATED" not in citations[0].quote


def test_resolve_all_deduplicates_identical_spans(passages) -> None:
    nomination = {"passage_id": "doc-a-p0", "start_offset": 0, "end_offset": 40}
    citations, reasons = resolve_all(
        nominations=[nomination, dict(nomination), dict(nomination)],
        passages_by_id=passages,
        canonical_by_document={"doc-a": CANONICAL, "doc-b": CANONICAL},
    )
    assert len(citations) == 1
    assert reasons == []


def test_resolve_all_collects_reasons_for_rejected_spans(passages) -> None:
    citations, reasons = resolve_all(
        nominations=[
            {"passage_id": "doc-a-p0", "start_offset": 0, "end_offset": 40},
            {"passage_id": "nope", "start_offset": 0, "end_offset": 40},
            {"passage_id": "doc-a-p0", "start_offset": 5, "end_offset": 5},
        ],
        passages_by_id=passages,
        canonical_by_document={"doc-a": CANONICAL, "doc-b": CANONICAL},
    )
    assert len(citations) == 1
    assert len(reasons) == 2
    assert any("unknown passage id" in reason for reason in reasons)


def test_resolve_all_honours_its_limit(passages) -> None:
    nominations = [
        {"passage_id": "doc-a-p0", "start_offset": i, "end_offset": i + 30} for i in range(10, 50, 5)
    ]
    citations, _ = resolve_all(
        nominations=nominations, passages_by_id=passages, limit=2,
        canonical_by_document={"doc-a": CANONICAL, "doc-b": CANONICAL},
    )
    assert len(citations) <= 2


def test_resolve_all_skips_non_object_entries(passages) -> None:
    citations, reasons = resolve_all(
        nominations=["not-an-object", 42],
        passages_by_id=passages,
        canonical_by_document={"doc-a": CANONICAL, "doc-b": CANONICAL},
    )
    assert citations == []
    assert len(reasons) == 2
