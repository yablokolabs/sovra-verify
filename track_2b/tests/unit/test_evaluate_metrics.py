"""The evaluation's own metrics must be honest and must stay stable.

``scripts/evaluate.py`` decides what the project is allowed to claim about its
accuracy, so its arithmetic is tested like any other contract. Three things are
pinned here:

* ``accuracy`` keeps its original definition - correct over every case in the
  corpus - so the headline number can never quietly improve by redefining it;
* the new decomposition is correct on a hand-built set of rows that contains one
  of each bucket, including the case that was never compared at all;
* the rate denominators are the cases in the bucket, never only the successes.

The rows are fabricated dictionaries. No network, no credential file, no
inference.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import evaluate  # noqa: E402


def row(
    case_id: str,
    expected: str,
    observed: str,
    *,
    pairs: int = 1,
    correct: bool | None = None,
    category: str = "conflict",
) -> dict:
    """One per-case row, with only the fields the metrics read."""
    return {
        "id": case_id,
        "category": category,
        "expected_relation": expected,
        "observed_relation": observed,
        "correct": (expected == observed) if correct is None else correct,
        "candidate_pairs": pairs,
        "conflict_findings": 1 if observed == "potential_conflict" else 0,
        "conflicts_with_citation": 1 if observed == "potential_conflict" else 0,
        "evidence_spans": 2 if observed == "potential_conflict" else 0,
        "finding_count": 0 if observed in ("abstained", "failed") else 1,
        "provider_calls": 1 if pairs == 0 else 2,
        "failed_calls": 0,
        "wall_ms": 1000,
        "total_tokens": 100,
    }


def mixed_rows() -> list[dict]:
    """One of every bucket the decomposition distinguishes."""
    return [
        # compared and correct: a real conflict, found
        row("case-conflict-ok", "potential_conflict", "potential_conflict"),
        # compared and correct: a genuine negative, correctly reported
        row("case-consistent-ok", "consistent", "consistent"),
        # compared and wrong: a false alarm on an exception case
        row("case-false-alarm", "consistent", "potential_conflict", category="valid_exception"),
        # compared and wrong: a conflict asserted with no governing context
        row("case-context", "insufficient_evidence", "potential_conflict", category="missing_context"),
        # expected a conflict, reported nothing, and the pair was looked at
        row("case-missed", "potential_conflict", "abstained"),
        # expected a conflict, reported nothing, no pair ever formed
        row("case-never-compared", "potential_conflict", "abstained", pairs=0),
        # a negative where nothing was reported and nothing was compared
        row("case-silent-negative", "unrelated", "abstained", pairs=0),
        # a negative that was compared and correctly reported
        row("case-negative-ok", "insufficient_evidence", "insufficient_evidence"),
    ]


def test_accuracy_keeps_its_original_definition() -> None:
    rows = mixed_rows()
    metrics = evaluate.compute_metrics(rows)
    # correct rows: conflict-ok, consistent-ok, negative-ok  -> 3 of 8
    assert metrics["correct"] == 3
    assert metrics["cases"] == 8
    assert metrics["accuracy"] == round(3 / 8, 4)


def test_the_denominator_is_every_case_never_only_the_successes() -> None:
    rows = mixed_rows()
    metrics = evaluate.compute_metrics(rows)
    assert metrics["cases"] == len(rows)
    assert metrics["abstained_cases"] == 3  # case-missed, case-never-compared, case-silent-negative
    assert metrics["abstention_rate"] == round(3 / 8, 4)


def test_accuracy_on_compared_cases_uses_only_compared_cases() -> None:
    metrics = evaluate.compute_metrics(mixed_rows())
    # compared: conflict-ok, consistent-ok, false-alarm, context, missed, negative-ok -> 6
    assert metrics["compared_cases"] == 6
    assert metrics["correct_on_compared_cases"] == 3
    assert metrics["accuracy_on_compared_cases"] == round(3 / 6, 4)
    # and it is never the same shortcut as the headline figure
    assert metrics["accuracy_on_compared_cases"] != metrics["accuracy"]


def test_negative_case_buckets_are_counted_separately() -> None:
    metrics = evaluate.compute_metrics(mixed_rows())
    # negatives: case-context, case-silent-negative, case-negative-ok -> 3
    assert metrics["negative_cases"] == 3
    # without an inconsistency: silent-negative, negative-ok -> 2
    assert metrics["negative_cases_without_inconsistency"] == 2
    assert metrics["negative_case_clean_rate"] == round(2 / 3, 4)
    # the one negative the system wrongly called a conflict
    assert metrics["false_alarm_cases"] == 1
    # two conflicts were expected and not reported
    assert metrics["missed_inconsistency_cases"] == 2


def test_diagnostics_name_the_case_ids_behind_every_bucket() -> None:
    diagnostics = evaluate.compute_diagnostics(mixed_rows())
    assert diagnostics["never_compared"] == ["case-never-compared", "case-silent-negative"]
    assert diagnostics["false_alarm"] == ["case-context"]
    assert diagnostics["missed_inconsistency"] == ["case-missed", "case-never-compared"]
    assert diagnostics["silent_negative"] == ["case-silent-negative"]


def test_empty_input_does_not_divide_by_zero() -> None:
    metrics = evaluate.compute_metrics([])
    assert metrics["cases"] == 0
    assert metrics["accuracy"] == 0.0
    assert metrics["accuracy_on_compared_cases"] == 0.0
    assert metrics["negative_case_clean_rate"] == 0.0
    assert metrics["compared_cases"] == 0
    assert metrics["negative_cases"] == 0


def test_a_perfect_run_reaches_every_secondary_rate() -> None:
    rows = [
        row("a", "potential_conflict", "potential_conflict"),
        row("b", "insufficient_evidence", "insufficient_evidence"),
        row("c", "unrelated", "unrelated", pairs=0),
    ]
    metrics = evaluate.compute_metrics(rows)
    assert metrics["accuracy"] == 1.0
    assert metrics["accuracy_on_compared_cases"] == 1.0
    assert metrics["negative_case_clean_rate"] == 1.0
    assert metrics["false_alarm_cases"] == 0
    assert metrics["missed_inconsistency_cases"] == 0
