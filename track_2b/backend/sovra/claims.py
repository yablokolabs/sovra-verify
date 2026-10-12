"""Claim identification.

Apertus reads the passages and nominates typed claims. Everything it returns is
validated: unknown passage ids, inverted offsets and out-of-range spans produce
an ``unresolved`` claim (visible in the UI) rather than a plausible-looking
record. A deterministic rule extractor runs alongside as a baseline and as a
safety net when inference is unavailable.
"""

from __future__ import annotations

import hashlib
import re

from .citations import resolve_span
from .config import Settings
from .jsonio import coerce_int, coerce_str, parse_json_object, repair_instruction
from .models import Claim, ExtractionStatus, Passage, ProviderRun
from .normalize import (
    normalize_date,
    normalize_predicate,
    normalize_subject,
    normalize_unit,
    normalize_value,
)
from .prompts import CLAIM_SYSTEM, CLAIM_USER_TEMPLATE, UNTRUSTED_PREAMBLE, render_passages
from .providers import ProviderRouter

MAX_CLAIMS_PER_DOCUMENT = 40
BATCH_PASSAGE_LIMIT = 8

_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
#: A real monetary amount. Bare integers are deliberately excluded: clause
#: numbers ("4.1", "7.2") are not amounts and pairing them produces pure noise.
_AMOUNT_RE = re.compile(
    r"\b(CHF|EUR|USD|GBP)\s?([0-9][0-9'\u2019]*(?:[.,][0-9]{2})?)\b"
    r"|\b([0-9][0-9,'\u2019]{0,12}\.[0-9]{2})\b"
)
_CLAUSE_PREFIX_RE = re.compile(
    r"(clause|section|paragraph|article|policy|annex|appendix|schedule|item|annex|ref)\s*$", re.IGNORECASE
)
#: Clause numbering such as '4.1', '7.2', '11.2.3'. Components are at most two
#: digits, so a real decimal amount ('250.00') is never mistaken for a clause.
_CLAUSE_NUMBER_RE = re.compile(r"^\d{1,2}(?:\.\d{1,2}){1,3}$")
_DAYS_RE = re.compile(r"\b(\d{1,4})\s*(?:calendar\s+|working\s+)?days?\b", re.IGNORECASE)
_PERCENT_RE = re.compile(r"\b(\d{1,3}(?:\.\d+)?)\s*%")
_ENTITY_RE = re.compile(r"\b([A-Z][A-Za-z0-9&.\-]*(?:\s+[A-Z][A-Za-z0-9&.\-]*){1,3}\s(?:AG|Ltd|LTD|GmbH|SA|SE|Inc|LLC|BV|Sàrl|SARL))\b")

#: Predicates where two values with no stated unit are not comparable evidence.
UNIT_REQUIRED_PREDICATES = {"amount", "rate", "quantity", "payment_period"}


class _Amount:
    __slots__ = ("currency", "value")

    def __init__(self, currency: str, value: str):
        self.currency = currency
        self.value = value


def find_amount(text: str) -> _Amount | None:
    """Find a currency-qualified or decimal amount, ignoring clause numbers."""
    for match in _AMOUNT_RE.finditer(text):
        prefix = text[max(0, match.start() - 24) : match.start()]
        if _CLAUSE_PREFIX_RE.search(prefix):
            continue
        currency = match.group(1) or ""
        value = match.group(2) or match.group(3) or ""
        if not value:
            continue
        if not currency and _CLAUSE_NUMBER_RE.match(value.replace(",", "")):
            continue
        return _Amount(currency, value)
    return None


def looks_like_clause_number(value: str, passage_text: str) -> bool:
    """True when a value is a clause reference such as '4.1' rather than a quantity."""
    cleaned = (value or "").strip().strip(".,;")
    if not _CLAUSE_NUMBER_RE.match(cleaned):
        return False
    return bool(
        re.search(
            r"(clause|section|paragraph|article|policy|annex|appendix|schedule)\s*" + re.escape(cleaned),
            passage_text,
            re.IGNORECASE,
        )
    )


def with_normalized_keys(claim: Claim, *, origin: str | None = None) -> Claim:
    """Attach comparable keys without touching the raw wording."""
    unit = normalize_unit(claim.unit)
    claim.unit_normalized = unit
    claim.predicate_normalized = normalize_predicate(claim.predicate)
    claim.value_normalized = normalize_value(claim.value, unit)
    claim.subject_normalized = normalize_subject(claim.subject)
    claim.effective_date = normalize_date(claim.effective_date) if claim.effective_date else "unknown"
    if origin:
        claim.origin = origin
    return claim


def _document_name_of(passage: Passage, names: dict[str, str]) -> str:
    return names.get(passage.document_id, passage.document_id)


def claims_from_rules(passages: list[Passage], document_names: dict[str, str]) -> list[Claim]:
    """Deterministic baseline: one claim per passage that states a number or date."""
    claims: list[Claim] = []
    for passage in passages:
        text = passage.text
        if find_amount(text) is None and _DATE_RE.search(text) is None and not _DAYS_RE.search(text):
            continue
        days = _DAYS_RE.search(text)
        percent = _PERCENT_RE.search(text)
        date = _DATE_RE.search(text)
        amount = find_amount(text)

        if days:
            # Keep the unit in the value so a rule claim and a model claim that
            # state the same fact normalise to the same comparable value.
            value, unit, predicate = f"{days.group(1)} days", "days", "payment_period"
        elif percent:
            value, unit, predicate = percent.group(1), "percent", "rate"
        elif amount is not None:
            value = f"{amount.currency} {amount.value}".strip()
            unit = amount.currency or "unknown"
            predicate = "amount"
        elif date:
            value, unit, predicate = date.group(1), "date", "effective_date"
        else:  # pragma: no cover - guarded above
            continue

        entity = _ENTITY_RE.search(text)
        claims.append(
            with_normalized_keys(
                Claim(
                    id=f"{passage.document_id}-rule-{passage.paragraph_index}",
                    document_id=passage.document_id,
                    subject=entity.group(1) if entity else "unknown",
                    predicate=predicate,
                    value=value,
                    unit=unit,
                    scope="unknown",
                    effective_date=date.group(1) if date else "unknown",
                    source_passage_id=passage.id,
                    quote_start=passage.start_offset,
                    quote_end=passage.end_offset,
                    quote=text[:400],
                    extraction_status=ExtractionStatus.OK,
                    notes="deterministic rule baseline",
                    origin="rules",
                )
            )
        )
    return claims


class ClaimExtractor:
    def __init__(self, router: ProviderRouter, settings: Settings):
        self.router = router
        self.settings = settings

    def extract(
        self,
        *,
        passages: list[Passage],
        document_names: dict[str, str],
        max_claims: int = MAX_CLAIMS_PER_DOCUMENT,
    ) -> tuple[list[Claim], list[str]]:
        """Return (claims, limitations). Raises ProviderError if inference fails."""
        limitations: list[str] = []
        if not passages:
            return [], ["no passages were extracted, so no claims could be identified"]

        by_id = {p.id: p for p in passages}
        # Offsets are per document, so canonical text is looked up per document.
        canonical_by_document: dict[str, str] = getattr(self, "_canonical_by_document", {}) or {}

        claims: list[Claim] = []
        for batch_start in range(0, len(passages), BATCH_PASSAGE_LIMIT):
            batch = passages[batch_start : batch_start + BATCH_PASSAGE_LIMIT]
            rows = [
                {
                    "id": p.id,
                    "document_name": _document_name_of(p, document_names),
                    "page": p.page,
                    "start_offset": p.start_offset,
                    "end_offset": p.end_offset,
                    "text": p.text[: self.settings.max_chunk_chars],
                }
                for p in batch
            ]
            user = CLAIM_USER_TEMPLATE.format(
                preamble=UNTRUSTED_PREAMBLE,
                max_claims=min(max_claims, len(batch) * 3),
                document_name=document_names.get(batch[0].document_id, batch[0].document_id),
                passages=render_passages(rows),
            )
            payload_text, run, error = self._call(system=CLAIM_SYSTEM, user=user, mode="claims", payload_source=user)
            if run is not None and run.status != "ok":
                limitations.append(
                    f"claim extraction batch {batch_start // BATCH_PASSAGE_LIMIT} failed "
                    f"({run.error_class}); those passages have no model-derived claims"
                )
                continue
            if payload_text is None:
                limitations.append(f"claim extraction batch returned no usable JSON ({error})")
                continue

            items = payload_text.get("claims")
            if not isinstance(items, list):
                limitations.append("claim extraction returned no 'claims' array")
                continue

            for item in items:
                if not isinstance(item, dict):
                    continue
                claim = self._validate_claim(
                    item=item,
                    by_id=by_id,
                    canonical_by_document=canonical_by_document,
                    document_names=document_names,
                    counter=len(claims),
                )
                claims.append(claim)
                if len(claims) >= max_claims:
                    break
            if len(claims) >= max_claims:
                limitations.append(f"claim extraction stopped at the {max_claims} claim cap")
                break

        unresolved = sum(1 for c in claims if c.extraction_status != ExtractionStatus.OK)
        if unresolved:
            limitations.append(
                f"{unresolved} of {len(claims)} model claims could not be resolved to a validated "
                "source span and are shown as unresolved"
            )
        return claims, limitations

    # -- internals ---------------------------------------------------------
    def _call(self, *, system: str, user: str, mode: str, payload_source: str):
        input_hash = hashlib.sha256(payload_source.encode("utf-8")).hexdigest()
        try:
            completion, run = self.router.complete(
                system=system, user=user, mode=mode, input_hash=input_hash
            )
        except Exception as exc:
            run = self.router.runs[-1] if self.router.runs else None
            return None, run, f"{type(exc).__name__}: {exc}"

        parsed = parse_json_object(completion.text, finish_reason=completion.finish_reason)
        if parsed.ok:
            return parsed.payload, run, ""
        if completion.finish_reason == "length":
            run.validation_errors.append("response truncated at the output token cap")
            return None, run, "response truncated"

        repair_user = repair_instruction(completion.text, parsed.error)
        try:
            second, repair_run = self.router.complete(
                system=system,
                user=repair_user,
                mode=f"{mode}:repair",
                input_hash=input_hash,
            )
        except Exception as exc:
            return None, run, f"repair attempt failed: {type(exc).__name__}"
        retry = parse_json_object(second.text, finish_reason=second.finish_reason)
        if retry.ok:
            repair_run.validation_errors.append("required one repair attempt")
            return retry.payload, repair_run, ""
        return None, repair_run, retry.error or parsed.error

    def _validate_claim(
        self,
        *,
        item: dict,
        by_id: dict[str, Passage],
        canonical_by_document: dict[str, str],
        document_names: dict[str, str],
        counter: int,
    ) -> Claim:
        passage_id = coerce_str(item.get("passage_id") or item.get("source_passage_id"), "", 64)
        passage = by_id.get(passage_id)
        start = coerce_int(item.get("quote_start"))
        end = coerce_int(item.get("quote_end"))

        if passage is None:
            return with_normalized_keys(
                Claim(
                    id=f"claim-unresolved-{counter}",
                    document_id="unknown",
                    subject=coerce_str(item.get("subject")),
                    predicate=coerce_str(item.get("predicate")),
                    value=coerce_str(item.get("value"), limit=300),
                    unit=coerce_str(item.get("unit")),
                    source_passage_id=passage_id or "unknown",
                    quote_start=0,
                    quote_end=0,
                    extraction_status=ExtractionStatus.UNRESOLVED,
                    notes=f"model cited an unknown passage id '{passage_id}'",
                    origin="apertus",
                )
            )

        canonical = canonical_by_document.get(passage.document_id, "")
        resolution = resolve_span(
            passage_id=passage.id,
            start_offset=start,
            end_offset=end,
            passages_by_id=by_id,
            canonical_text=canonical,
        )
        status = ExtractionStatus.OK if resolution.resolved else ExtractionStatus.UNRESOLVED
        note = "" if resolution.resolved else resolution.reason

        # A value the model read as a quantity but which is really a clause
        # reference ('4.1' next to the word 'Policy') is reclassified so it can
        # never be paired as a conflicting amount.
        raw_value = coerce_str(item.get("value"), limit=300)
        raw_predicate = coerce_str(item.get("predicate"))
        if looks_like_clause_number(raw_value, passage.text):
            raw_predicate = "clause_reference"
            note = (note + " " if note else "") + "value is a clause reference, not a quantity"
        if resolution.citation is not None:
            quote_start, quote_end = resolution.citation.start_offset, resolution.citation.end_offset
            quote = resolution.citation.quote
        else:
            quote_start, quote_end = passage.start_offset, min(passage.end_offset, passage.start_offset + 400)
            quote = canonical[quote_start:quote_end]

        return with_normalized_keys(
            Claim(
                id=f"claim-{counter}-{passage.document_id}",
                document_id=passage.document_id,
                subject=coerce_str(item.get("subject")),
                predicate=raw_predicate,
                value=raw_value,
                unit=coerce_str(item.get("unit")),
                scope=coerce_str(item.get("scope")),
                effective_date=coerce_str(item.get("effective_date"), limit=40),
                source_passage_id=passage.id,
                quote_start=quote_start,
                quote_end=quote_end,
                quote=quote[:600],
                extraction_status=status,
                notes=note
                or f"source: {document_names.get(passage.document_id, passage.document_id)} p{passage.page}",
                origin="apertus",
            )
        )


def attach_canonical(
    extractor: ClaimExtractor, canonical_by_document: dict[str, str]
) -> ClaimExtractor:
    """Give the extractor each document's canonical text that its offsets index into."""
    setattr(extractor, "_canonical_by_document", dict(canonical_by_document))
    return extractor
