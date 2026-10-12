"""Scoped comparison.

Only claims from *different* documents are paired, and only when normalised
subject/predicate/date/scope plausibly align. Unknown scope is deliberately
allowed through as a review candidate so a retrieval miss cannot hide a real
conflict; the coverage numbers are reported so that is visible.

A model judgement becomes a finding only when at least one of its nominated
spans resolves deterministically. Otherwise the finding is rejected and the
reason is recorded.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field

from .citations import resolve_all
from .claims import ClaimExtractor
from .config import Settings
from .claims import UNIT_REQUIRED_PREDICATES
from .normalize import (
    normalize_date,
    normalize_predicate,
    normalize_subject,
    normalize_unit,
    normalize_value,
    subjects_compatible,
)
from .jsonio import coerce_str, parse_json_object, repair_instruction
from .models import (
    Claim,
    Finding,
    Passage,
    Relation,
    ReviewEvent,
    utcnow,
)
from .prompts import COMPARE_SYSTEM, COMPARE_USER_TEMPLATE, UNTRUSTED_PREAMBLE, render_passages
from .providers import ProviderRouter

_NUMERIC = re.compile(r"-?\d+(?:[.,]\d+)?")
_VALID_RELATIONS = {r.value for r in Relation}
NEGATIVE_RELATIONS = (Relation.CONSISTENT, Relation.UNRELATED, Relation.INSUFFICIENT_EVIDENCE)


@dataclass(slots=True)
class Candidate:
    left: Claim
    right: Claim
    score: float
    reason: str


@dataclass(slots=True)
class ComparisonOutcome:
    findings: list[Finding] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    baseline: dict[str, str] = field(default_factory=dict)
    coverage: dict[str, object] = field(default_factory=dict)


def claim_keys(claim: Claim) -> tuple[str, str, str, str, str]:
    """Comparable keys for a claim: (subject, predicate, value, unit, date)."""
    predicate = claim.predicate_normalized or normalize_predicate(claim.predicate)
    unit = claim.unit_normalized or normalize_unit(claim.unit)
    value = claim.value_normalized or normalize_value(claim.value, unit)
    subject = claim.subject_normalized or normalize_subject(claim.subject)
    return subject, predicate, value, unit, normalize_date(claim.effective_date)


def claims_align(left: Claim, right: Claim) -> tuple[bool, str]:
    """Do two claims describe the same kind of thing closely enough to compare?"""
    if left.document_id == right.document_id:
        return False, "same document"
    if left.extraction_status.value != "ok" or right.extraction_status.value != "ok":
        return False, "claim is unresolved"

    l_subject, l_predicate, _, l_unit, l_date = claim_keys(left)
    r_subject, r_predicate, _, r_unit, r_date = claim_keys(right)

    if l_predicate != r_predicate:
        return False, f"different predicates ({l_predicate} vs {r_predicate})"
    if l_predicate == "clause_reference" and r_predicate == "clause_reference":
        return False, "both values are clause references"
    if l_unit != r_unit and "unknown" not in (l_unit, r_unit):
        return False, f"different units ({l_unit} vs {r_unit})"
    # Two bare numbers with no stated unit are not evidence of a conflict.
    if l_predicate in UNIT_REQUIRED_PREDICATES and l_unit == "unknown" and r_unit == "unknown":
        return False, f"no comparable unit for predicate {l_predicate}"
    if not subjects_compatible(left.subject, right.subject):
        return False, f"different entities ({l_subject} vs {r_subject})"
    # A known, differing effective date is an explanation for a numeric
    # difference, so the pair is not treated as a conflict candidate. The count
    # is reported in coverage so this never hides a conflict silently.
    if l_date != r_date and "unknown" not in (l_date, r_date):
        return False, "different effective dates"
    return True, ""


#: How many distinct skip reasons are kept; the rest are summarised by count.
MAX_SKIP_REASONS = 12


def build_candidates(
    claims: list[Claim], *, max_pairs: int
) -> tuple[list[Candidate], dict[str, object]]:
    candidates: list[Candidate] = []
    skipped: dict[str, int] = {}
    documents = {c.document_id for c in claims}
    for index, left in enumerate(claims):
        for right in claims[index + 1 :]:
            ok, reason = claims_align(left, right)
            if not ok:
                skipped[reason] = skipped.get(reason, 0) + 1
                continue
            score = 1.0
            l_subject, _, l_value, l_unit, _ = claim_keys(left)
            r_subject, _, r_value, r_unit, _ = claim_keys(right)
            if l_unit != "unknown" and l_unit == r_unit:
                score += 0.5
            if l_value != r_value:
                score += 1.0
            if l_subject != "unknown" and l_subject == r_subject:
                score += 0.5
            if left.scope == "unknown" or right.scope == "unknown":
                score += 0.25
            candidates.append(Candidate(left, right, score, reason=""))

    candidates.sort(key=lambda c: c.score, reverse=True)
    # Collapse duplicates: the same document pair raising the same predicate with
    # the same normalised values is one comparison, not one per claim. Without
    # this a single conflict is reported several times, once per paraphrased claim.
    deduped: list[Candidate] = []
    seen: set[tuple] = set()
    for candidate in candidates:
        l_subject, l_predicate, l_value, l_unit, _ = claim_keys(candidate.left)
        r_subject, _, r_value, r_unit, _ = claim_keys(candidate.right)
        key = (
            tuple(sorted((candidate.left.document_id, candidate.right.document_id))),
            l_predicate,
            tuple(sorted((l_unit, r_unit))),
            tuple(sorted((l_value, r_value))),
            tuple(sorted((l_subject, r_subject))),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    kept = deduped[:max_pairs]

    top_reasons = dict(sorted(skipped.items(), key=lambda kv: -kv[1])[:MAX_SKIP_REASONS])
    other = sum(v for k, v in skipped.items() if k not in top_reasons)
    coverage: dict[str, object] = {
        "claims": len(claims),
        "documents": len(documents),
        "pairs_considered": len(candidates),
        "pairs_after_dedup": len(deduped),
        "pairs_compared": len(kept),
        "pairs_dropped_by_cap": max(0, len(deduped) - len(kept)),
        "pairs_skipped": sum(skipped.values()),
        "skipped_reasons_top": top_reasons,
        "skipped_reasons_other_count": other,
        "distinct_skip_reasons": len(skipped),
        "unknown_scope_candidates_kept": sum(
            1 for c in kept if c.left.scope == "unknown" or c.right.scope == "unknown"
        ),
    }
    return kept, coverage


def rule_baseline(left: Claim, right: Claim) -> Relation:
    """Deterministic numeric baseline used as the comparison floor."""
    l_subject, l_predicate, l_value, l_unit, l_date = claim_keys(left)
    r_subject, r_predicate, r_value, r_unit, r_date = claim_keys(right)
    # A known, differing effective date is checked first: it explains a numeric
    # difference, so such a pair is never a baseline conflict.
    if l_date != r_date and "unknown" not in (l_date, r_date):
        return Relation.INSUFFICIENT_EVIDENCE
    if l_unit != "unknown" and l_unit == r_unit:
        if l_value == r_value and l_date == r_date:
            return Relation.CONSISTENT
        if l_predicate == r_predicate and l_value != r_value:
            return Relation.POTENTIAL_CONFLICT
    if l_subject != r_subject and "unknown" not in (l_subject, r_subject):
        return Relation.UNRELATED
    return Relation.INSUFFICIENT_EVIDENCE


class Comparer:
    def __init__(self, router: ProviderRouter, settings: Settings, extractor: ClaimExtractor):
        self.router = router
        self.settings = settings
        self.extractor = extractor

    def compare(
        self,
        *,
        analysis_id: str,
        candidates: list[Candidate],
        passages_by_id: dict[str, Passage],
        canonical_by_document: dict[str, str],
        document_names: dict[str, str],
    ) -> ComparisonOutcome:
        outcome = ComparisonOutcome()
        for candidate in candidates:
            baseline = rule_baseline(candidate.left, candidate.right)
            outcome.baseline[f"{candidate.left.id}|{candidate.right.id}"] = baseline.value
            try:
                finding = self._compare_one(
                    analysis_id=analysis_id,
                    candidate=candidate,
                    passages_by_id=passages_by_id,
                    canonical_by_document=canonical_by_document,
                    document_names=document_names,
                )
            except Exception as exc:
                outcome.rejected.append(
                    f"comparison of {candidate.left.id} / {candidate.right.id} failed "
                    f"({type(exc).__name__})"
                )
                continue
            if finding is None:
                continue
            outcome.findings.append(finding)
        return outcome

    # -- internals ---------------------------------------------------------
    def _compare_one(
        self,
        *,
        analysis_id: str,
        candidate: Candidate,
        passages_by_id: dict[str, Passage],
        canonical_by_document: dict[str, str],
        document_names: dict[str, str],
    ) -> Finding | None:
        rows = []
        for claim in (candidate.left, candidate.right):
            passage = passages_by_id.get(claim.source_passage_id)
            if passage is None:
                return None
            rows.append(
                {
                    "id": passage.id,
                    "document_name": document_names.get(passage.document_id, passage.document_id),
                    "page": passage.page,
                    "start_offset": passage.start_offset,
                    "end_offset": passage.end_offset,
                    "text": passage.text[: self.settings.max_chunk_chars],
                }
            )

        user = COMPARE_USER_TEMPLATE.format(
            preamble=UNTRUSTED_PREAMBLE,
            claim_a=_render_claim(candidate.left, document_names),
            claim_b=_render_claim(candidate.right, document_names),
            passages=render_passages(rows),
        )
        context = "|".join(
            f"{doc_id}:{text[:256]}" for doc_id, text in sorted(canonical_by_document.items())
        )
        input_hash = hashlib.sha256((user + context).encode("utf-8")).hexdigest()

        try:
            completion, run = self.router.complete(
                system=COMPARE_SYSTEM, user=user, mode="compare", input_hash=input_hash
            )
        except Exception as exc:
            self._record_failure(str(exc))
            return None

        parsed = parse_json_object(completion.text, finish_reason=completion.finish_reason)
        if not parsed.ok:
            if completion.finish_reason == "length":
                run.validation_errors.append("comparison response truncated")
                return None
            repair_user = repair_instruction(completion.text, parsed.error)
            try:
                second, repair_run = self.router.complete(
                    system=COMPARE_SYSTEM,
                    user=repair_user,
                    mode="compare:repair",
                    input_hash=input_hash,
                )
            except Exception:
                return None
            repair_run.validation_errors.append("required one repair attempt")
            run = repair_run
            parsed = parse_json_object(second.text, finish_reason=second.finish_reason)
            if not parsed.ok:
                run.validation_errors.append(f"repair failed: {parsed.error}")
                return None

        payload = parsed.payload or {}
        relation_raw = coerce_str(payload.get("relation"), "").lower().strip()
        if relation_raw not in _VALID_RELATIONS:
            run.validation_errors.append(f"model returned an unknown relation '{relation_raw}'")
            return None
        relation = Relation(relation_raw)

        nominations = payload.get("cited_spans")
        if not isinstance(nominations, list):
            nominations = []
        citations, reasons = resolve_all(
            nominations=[n for n in nominations if isinstance(n, dict)],
            passages_by_id=passages_by_id,
            canonical_by_document=canonical_by_document,
        )
        run.validation_errors.extend(reasons)

        limitations = [coerce_str(x, "", 300) for x in (payload.get("limitations") or []) if coerce_str(x, "", 300)]

        if relation is Relation.POTENTIAL_CONFLICT and not citations:
            # A conflict with no validated citation is not evidence.
            return None
        if relation is not Relation.POTENTIAL_CONFLICT and citations:
            # Negative judgements keep their spans for transparent review.
            pass
        if not citations:
            limitations.append(
                "no span could be resolved for this judgement; it is shown without citation"
            )

        explanation = coerce_str(payload.get("reasoning"), "", 1200) or (
            "The model returned a relation without reasoning."
        )
        limitations.append("model judgement; not a legal or factual determination")

        return Finding(
            id=uuid.uuid4().hex[:16],
            analysis_id=analysis_id,
            claim_ids=[candidate.left.id, candidate.right.id],
            relation=relation,
            explanation=explanation,
            evidence=citations,
            limitations=limitations,
            provider_run_id=run.id,
            created_at=utcnow(),
        )

    def _record_failure(self, message: str) -> None:
        self._last_failure = message[:300]


def _render_claim(claim: Claim, document_names: dict[str, str]) -> str:
    return (
        f'- claim_id="{claim.id}" document="{document_names.get(claim.document_id, claim.document_id)}"\n'
        f'  predicate={claim.predicate} value="{claim.value}" unit={claim.unit} '
        f'scope="{claim.scope}" effective_date={claim.effective_date} '
        f'source_passage="{claim.source_passage_id}"'
    )


def make_review_event(finding_id: str, status: str, note: str, reviewer: str) -> ReviewEvent:
    return ReviewEvent(
        id=uuid.uuid4().hex[:16],
        finding_id=finding_id,
        status=status,  # type: ignore[arg-type]
        note=note,
        reviewer=reviewer,
    )
