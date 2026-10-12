"""Candidate pairing: dates, units, entities, clause references and coverage."""

from __future__ import annotations

from sovra.claims import with_normalized_keys
from sovra.compare import build_candidates, claim_keys, claims_align, rule_baseline
from sovra.models import Claim, Relation


def make_claim(
    *,
    claim_id: str,
    document_id: str,
    predicate: str = "Payment term",
    value: str = "30 days",
    unit: str = "days",
    subject: str = "unknown",
    scope: str = "unknown",
    effective_date: str = "unknown",
) -> Claim:
    return with_normalized_keys(
        Claim(
            id=claim_id,
            document_id=document_id,
            subject=subject,
            predicate=predicate,
            value=value,
            unit=unit,
            scope=scope,
            effective_date=effective_date,
            source_passage_id=f"{document_id}-p0",
        )
    )


# -- claim_keys ------------------------------------------------------------
def test_claim_keys_are_the_normalised_tuple() -> None:
    subject, predicate, value, unit, date = claim_keys(
        make_claim(claim_id="c1", document_id="doc-a", effective_date="2026-01-01")
    )
    assert predicate == "payment_period"
    assert unit == "days"
    assert value == "30 days"
    assert subject == "unknown"
    assert date == "2026-01-01"


# -- alignment rules -------------------------------------------------------
def test_two_claims_in_the_same_document_never_pair() -> None:
    left = make_claim(claim_id="c1", document_id="doc-a")
    right = make_claim(claim_id="c2", document_id="doc-a", value="60 days")
    assert claims_align(left, right) == (False, "same document")


def test_different_predicates_do_not_pair() -> None:
    left = make_claim(claim_id="c1", document_id="doc-a", predicate="Payment term")
    right = make_claim(claim_id="c2", document_id="doc-b", predicate="Governing law")
    ok, reason = claims_align(left, right)
    assert ok is False
    assert reason.startswith("different predicates")


def test_different_units_do_not_pair() -> None:
    left = make_claim(claim_id="c1", document_id="doc-a", predicate="amount", value="CHF 10.00", unit="CHF")
    right = make_claim(claim_id="c2", document_id="doc-b", predicate="amount", value="30 days", unit="days")
    ok, reason = claims_align(left, right)
    assert ok is False
    assert reason.startswith("different units")


def test_two_bare_numbers_with_no_unit_do_not_pair() -> None:
    left = make_claim(claim_id="c1", document_id="doc-a", predicate="amount", value="4.1", unit="unknown")
    right = make_claim(claim_id="c2", document_id="doc-b", predicate="amount", value="9.3", unit="unknown")
    ok, reason = claims_align(left, right)
    assert ok is False
    assert reason == "no comparable unit for predicate amount"


def test_different_known_entities_do_not_pair() -> None:
    left = make_claim(claim_id="c1", document_id="doc-a", subject="Nordwind Logistik AG")
    right = make_claim(claim_id="c2", document_id="doc-b", subject="Rheintal Spedition AG", value="60 days")
    ok, reason = claims_align(left, right)
    assert ok is False
    assert reason.startswith("different entities")


def test_different_known_effective_dates_are_skipped_as_an_explanation() -> None:
    left = make_claim(claim_id="c1", document_id="doc-a", effective_date="2026-01-01")
    right = make_claim(claim_id="c2", document_id="doc-b", value="45 days", effective_date="2026-05-01")
    assert claims_align(left, right) == (False, "different effective dates")


def test_a_claim_with_an_unknown_date_still_pairs() -> None:
    left = make_claim(claim_id="c1", document_id="doc-a", effective_date="unknown")
    right = make_claim(claim_id="c2", document_id="doc-b", value="60 days", effective_date="2026-03-01")
    assert claims_align(left, right) == (True, "")


def test_comparable_conflict_pair_aligns() -> None:
    left = make_claim(claim_id="c1", document_id="doc-a", value="30 days")
    right = make_claim(claim_id="c2", document_id="doc-b", value="60 days")
    assert claims_align(left, right) == (True, "")


def test_resolved_amount_claims_with_the_same_unit_align() -> None:
    left = make_claim(claim_id="c1", document_id="doc-a", predicate="amount", value="CHF 10.00", unit="CHF")
    right = make_claim(claim_id="c2", document_id="doc-b", predicate="amount", value="CHF 20.00", unit="CHF")
    assert claims_align(left, right) == (True, "")


def test_a_reclassified_clause_reference_never_pairs_as_an_amount() -> None:
    """A clause number such as '4.10' must not be compared as a monetary amount."""
    clause = with_normalized_keys(
        Claim(
            id="c1",
            document_id="doc-a",
            predicate="clause_reference",
            value="4.10",
            unit="unknown",
            source_passage_id="doc-a-p0",
        )
    )
    amount = make_claim(
        claim_id="c2", document_id="doc-b", predicate="amount", value="CHF 10.00", unit="CHF"
    )
    ok, reason = claims_align(clause, amount)
    assert ok is False
    assert reason.startswith("different predicates")


def test_an_unresolved_claim_never_pairs() -> None:
    from sovra.models import ExtractionStatus

    left = make_claim(claim_id="c1", document_id="doc-a")
    left.extraction_status = ExtractionStatus.UNRESOLVED
    right = make_claim(claim_id="c2", document_id="doc-b", value="60 days")
    assert claims_align(left, right) == (False, "claim is unresolved")


# -- build_candidates ------------------------------------------------------
def test_build_candidates_reports_coverage_numbers() -> None:
    claims = [
        make_claim(claim_id="c1", document_id="doc-a", value="30 days"),
        make_claim(claim_id="c2", document_id="doc-b", value="60 days"),
        make_claim(claim_id="c3", document_id="doc-a", value="30 days"),
    ]
    candidates, coverage = build_candidates(claims, max_pairs=10)
    assert coverage["claims"] == 3
    assert coverage["documents"] == 2
    # c1-c2 and c2-c3 describe the same document pair with the same normalised
    # predicate and values, so they collapse to one comparison.
    assert coverage["pairs_considered"] == 2
    assert coverage["pairs_after_dedup"] == 1
    assert coverage["pairs_compared"] == len(candidates) == 1
    assert coverage["pairs_skipped"] == 1
    assert coverage["skipped_reasons_top"]["same document"] == 1
    assert coverage["unknown_scope_candidates_kept"] == len(candidates)


def test_build_candidates_records_why_a_date_change_pair_was_skipped() -> None:
    claims = [
        make_claim(claim_id="c1", document_id="doc-a", effective_date="2026-01-01"),
        make_claim(claim_id="c2", document_id="doc-b", value="45 days", effective_date="2026-05-01"),
    ]
    candidates, coverage = build_candidates(claims, max_pairs=10)
    assert candidates == []
    assert coverage["pairs_considered"] == 0
    assert coverage["skipped_reasons_top"]["different effective dates"] == 1


def test_build_candidates_caps_the_number_of_pairs_but_reports_the_drop() -> None:
    claims = [make_claim(claim_id=f"c{i}", document_id=f"doc-{i}", value="30 days") for i in range(6)]
    candidates, coverage = build_candidates(claims, max_pairs=0)
    assert candidates == []
    assert coverage["pairs_dropped_by_cap"] == coverage["pairs_after_dedup"] > 0


def test_build_candidates_ranks_differing_values_first() -> None:
    same_value = make_claim(claim_id="c1", document_id="doc-a", value="30 days")
    other_same = make_claim(claim_id="c2", document_id="doc-b", value="30 days")
    differing = make_claim(claim_id="c3", document_id="doc-c", value="60 days")
    candidates, _ = build_candidates([same_value, other_same, differing], max_pairs=10)
    assert candidates, "expected candidates"
    top = candidates[0]
    assert {top.left.value, top.right.value} == {"30 days", "60 days"}


# -- rule baseline ---------------------------------------------------------
def test_rule_baseline_flags_equal_values_as_consistent() -> None:
    left = make_claim(claim_id="c1", document_id="doc-a", value="30 days")
    right = make_claim(claim_id="c2", document_id="doc-b", value="30 days")
    assert rule_baseline(left, right) is Relation.CONSISTENT


def test_rule_baseline_flags_differing_values_as_a_potential_conflict() -> None:
    left = make_claim(claim_id="c1", document_id="doc-a", value="30 days")
    right = make_claim(claim_id="c2", document_id="doc-b", value="60 days")
    assert rule_baseline(left, right) is Relation.POTENTIAL_CONFLICT


def test_a_date_change_pair_is_never_reported_as_a_conflict() -> None:
    """A differing effective date is an explanation for a numeric gap.

    ``claims_align`` removes the pair before the comparer runs, and
    ``rule_baseline`` returns a non-conflict relation for it as well, so the
    baseline cannot contradict the documented date policy if it is called
    directly.
    """
    left = make_claim(claim_id="c1", document_id="doc-a", value="30 days", effective_date="2026-01-01")
    right = make_claim(
        claim_id="c2", document_id="doc-b", value="45 days", effective_date="2026-05-01"
    )
    assert claims_align(left, right) == (False, "different effective dates")
    assert rule_baseline(left, right) is Relation.INSUFFICIENT_EVIDENCE
