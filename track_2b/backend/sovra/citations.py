"""Deterministic citation resolution.

A model may nominate a passage id and an offset pair. It may never supply the
quote text that ends up in a report. Quotes are always sliced from canonical
extracted text at the offsets it nominated, and any span that does not resolve
against canonical text rejects the whole finding. A plausible-sounding model
explanation cannot rescue a fabricated citation.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Citation, Passage

MIN_QUOTE_CHARS = 8
#: How far outside a nominated paragraph a span may reach before it is rejected.
#: Keeps a model from "citing" a whole document.
MAX_QUOTE_CHARS = 600
WINDOW_TOLERANCE = 120


@dataclass(slots=True)
class Resolution:
    citation: Citation | None
    resolved: bool
    reason: str = ""


def resolve_span(
    *,
    passage_id: str,
    start_offset: int | None,
    end_offset: int | None,
    passages_by_id: dict[str, Passage],
    canonical_text: str,
) -> Resolution:
    """Resolve one nominated span to a validated citation.

    ``canonical_text`` must be the canonical text of *this passage's own
    document*. Offsets are per document, so resolving them against a string
    built from several documents would silently quote the wrong text.
    """
    passage = passages_by_id.get(passage_id)
    if passage is None:
        return Resolution(None, False, f"unknown passage id '{passage_id}'")

    start = passage.start_offset if start_offset is None else int(start_offset)
    end = passage.end_offset if end_offset is None else int(end_offset)

    if start < 0 or end <= start:
        return Resolution(None, False, "offsets are empty or inverted")
    if end > len(canonical_text):
        return Resolution(None, False, "span runs past the end of canonical text")

    # The span must overlap the paragraph it claims to come from.
    if end <= passage.start_offset - WINDOW_TOLERANCE or start >= passage.end_offset + WINDOW_TOLERANCE:
        return Resolution(
            None,
            False,
            "span does not overlap the passage it cites (possible fabricated location)",
        )

    # Clamp to a paragraph window so a citation stays reviewable in the UI.
    lo = max(0, passage.start_offset - WINDOW_TOLERANCE)
    hi = min(len(canonical_text), passage.end_offset + WINDOW_TOLERANCE)
    start = max(start, lo)
    end = min(end, hi)
    if end - start > MAX_QUOTE_CHARS:
        end = start + MAX_QUOTE_CHARS

    quote = canonical_text[start:end]
    meaningful = sum(1 for ch in quote if not ch.isspace())
    if meaningful < MIN_QUOTE_CHARS:
        return Resolution(None, False, "span is too short to support a finding")
    if not passage_contains(passage, start, end, quote):
        return Resolution(None, False, "derived quote is not a substring of its passage")

    return Resolution(
        Citation(
            passage_id=passage.id,
            document_id=passage.document_id,
            page=passage.page,
            start_offset=start,
            end_offset=end,
            quote=quote,
            resolved=True,
            reason="",
        ),
        True,
    )


def passage_contains(passage: Passage, start: int, end: int, quote: str) -> bool:
    """The derived quote must be readable as part of the passage's own text."""
    if not passage.text:
        return False
    if quote.strip() and quote.strip() in passage.text:
        return True
    # Allow a partial overlap at the paragraph boundary (window tolerance).
    overlap_start = max(start, passage.start_offset)
    overlap_end = min(end, passage.end_offset)
    if overlap_end - overlap_start < MIN_QUOTE_CHARS:
        return False
    offset_in_passage = overlap_start - passage.start_offset
    length = overlap_end - overlap_start
    return passage.text[offset_in_passage : offset_in_passage + length].strip() != ""


def resolve_all(
    *,
    nominations: list[dict],
    passages_by_id: dict[str, Passage],
    canonical_by_document: dict[str, str],
    limit: int = 6,
) -> tuple[list[Citation], list[str]]:
    """Resolve a model's nominated spans. Returns (citations, rejection reasons).

    Each span is resolved against its own document's canonical text, so a
    citation from the second document can never be sliced out of the first.
    """
    citations: list[Citation] = []
    reasons: list[str] = []
    seen: set[tuple[str, int, int]] = set()
    for item in nominations[:limit]:
        if not isinstance(item, dict):
            reasons.append("citation entry was not an object")
            continue
        passage_id = str(item.get("passage_id") or item.get("evidence_id") or "")
        passage = passages_by_id.get(passage_id)
        if passage is None:
            reasons.append(f"unknown passage id '{passage_id}'")
            continue
        canonical_text = canonical_by_document.get(passage.document_id)
        if canonical_text is None:
            reasons.append(f"no canonical text available for document '{passage.document_id}'")
            continue
        start = item.get("start_offset")
        end = item.get("end_offset")
        result = resolve_span(
            passage_id=passage_id,
            start_offset=start if isinstance(start, int) else None,
            end_offset=end if isinstance(end, int) else None,
            passages_by_id=passages_by_id,
            canonical_text=canonical_text,
        )
        if result.resolved and result.citation is not None:
            key = (
                result.citation.document_id,
                result.citation.start_offset,
                result.citation.end_offset,
            )
            if key in seen:
                continue
            seen.add(key)
            citations.append(result.citation)
        else:
            reasons.append(result.reason)
    return citations, reasons
