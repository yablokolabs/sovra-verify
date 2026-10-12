"""The browser check's own logic, tested without a browser.

`scripts/browser_check.py` needs lightpanda and a running server to do its job, so
the parts that decide pass or fail are tested here in isolation: the rendered-state
reading, the coverage contract, the footer hit list and the way a string is turned
into a JavaScript literal. A check that quietly passes is worse than no check, so
every branch that can raise is exercised, including the one that must not be
satisfied by an absent panel.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import browser_check  # noqa: E402

COVERAGE_LINES = [
    "33 validated claims in the corpus",
    "11 candidate pairs passed the scoping filter",
    "11 pairs sent to Apertus",
    "11 compared pair(s) were judged: 10 potential conflict, 1 consistent",
]


def state(
    *,
    grids: list[dict] | None = None,
    coverage: list[str] | None = None,
    muted: list[str] | None = None,
    text: str = "",
) -> dict:
    return {
        "grids": grids
        if grids is not None
        else [
            {"Provider reachability": "primary provider reachable"},
            {"Run status": "complete", "Pairs compared": "11", "Validated claims": "33"},
            {"Provider calls": "56", "Total tokens": "132,521"},
        ],
        "coverage": coverage if coverage is not None else COVERAGE_LINES,
        "muted": muted if muted is not None else ["Showing 3 of 11 findings."],
        "text": text,
        "buttons": [],
        "documents": [],
        "failures": [],
        "limitations": [],
    }


# -- status grids ----------------------------------------------------------
def test_grid_with_finds_the_grid_that_owns_the_label() -> None:
    reading = state()
    assert browser_check.grid_with(reading, "Run status")["Pairs compared"] == "11"
    assert browser_check.grid_with(reading, "Provider calls")["Total tokens"] == "132,521"


def test_grid_with_returns_empty_when_no_grid_owns_the_label() -> None:
    assert browser_check.grid_with(state(grids=[]), "Run status") == {}


# -- footer markers --------------------------------------------------------
def test_footer_hits_finds_a_marker_and_is_case_insensitive() -> None:
    assert browser_check.footer_hits("text with \u00a9 2026") == ["\u00a9"]


def test_footer_hits_finds_a_closing_footer_tag() -> None:
    assert "</footer" in browser_check.footer_hits("<div></footer></div>")


def test_footer_hits_is_empty_for_clean_text() -> None:
    assert browser_check.footer_hits("Candidate coverage\n11 pairs sent to Apertus") == []


# -- the coverage contract -------------------------------------------------
def test_a_page_without_a_run_only_passes_when_it_says_so() -> None:
    silent = state(grids=[{"Provider reachability": "primary provider reachable"}], coverage=[])
    with pytest.raises(browser_check.CheckFailed, match="does not say so"):
        browser_check.check_rendered_text(silent)

    honest = state(
        grids=[{"Provider reachability": "primary provider reachable"}],
        coverage=[],
        text="No analysis has run in this session. Upload at least two documents.",
    )
    checks = browser_check.check_rendered_text(honest)
    assert checks["run_rendered"] is False
    assert "not applicable" in checks["coverage_notice"]


def test_a_rendered_run_without_a_coverage_notice_fails() -> None:
    with pytest.raises(browser_check.CheckFailed, match="Candidate coverage"):
        browser_check.check_rendered_text(state(coverage=[]))


def test_compared_pairs_must_have_their_judged_outcome_stated() -> None:
    without = state(coverage=["11 pairs sent to Apertus"])
    with pytest.raises(browser_check.CheckFailed, match="never states how they were judged"):
        browser_check.check_rendered_text(without)

    checks = browser_check.check_rendered_text(state())
    assert checks["judged_outcome_sentence"] is True


def test_no_comparison_does_not_require_a_judged_outcome_sentence() -> None:
    """Nothing was compared, so there is no judged outcome to state — but the run
    still has to say that nothing was reported."""
    grids = [{"Run status": "complete", "Pairs compared": "0", "Validated claims": "4"}]
    checks = browser_check.check_rendered_text(
        state(
            grids=grids,
            coverage=["4 validated claims in the corpus"],
            muted=[
                "Showing 0 of 0 findings.",
                "No potential inconsistency was reported for this run. The corpus was considered…",
            ],
        )
    )
    assert "judged_outcome_sentence" not in checks
    assert checks["empty_state_sentence"] is True


def test_an_empty_finding_list_must_be_explained() -> None:
    grids = [{"Run status": "complete", "Pairs compared": "6", "Validated claims": "9"}]
    unexplained = state(grids=grids, muted=["Showing 0 of 0 findings."])
    with pytest.raises(browser_check.CheckFailed, match="nothing was reported"):
        browser_check.check_rendered_text(unexplained)

    explained = state(
        grids=grids,
        muted=[
            "Showing 0 of 0 findings.",
            "No potential inconsistency was reported for this run. The corpus was considered…",
        ],
    )
    assert browser_check.check_rendered_text(explained)["empty_state_sentence"] is True


# -- what reaches the page -------------------------------------------------
def test_a_string_becomes_a_quoted_literal() -> None:
    assert browser_check.js_string("Select all") == '"Select all"'
    assert browser_check.js_string('a "quote" \\ and \n newline').startswith('"a \\"quote\\"')


def test_a_quote_in_a_control_label_cannot_escape_the_call() -> None:
    literal = browser_check.js_string('"); document.body.innerHTML = "x"; ("')
    assert literal.count('"') == 2 + 4  # the four escaped quotes stay inside the literal
    assert json.loads(literal).endswith('("')
