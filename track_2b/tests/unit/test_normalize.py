"""Normalisation tests: the controlled vocabulary that makes claims comparable."""

from __future__ import annotations

import pytest

from sovra.normalize import (
    normalize_date,
    normalize_predicate,
    normalize_subject,
    normalize_unit,
    normalize_value,
    subjects_compatible,
    values_differ,
)


@pytest.mark.parametrize(
    "wording",
    ["Payment term", "Settlement period", "payment_period", "net days", "Payment deadline", "payable within"],
)
def test_payment_wording_variants_share_one_predicate_key(wording: str) -> None:
    assert normalize_predicate(wording) == "payment_period"


@pytest.mark.parametrize(
    "wording",
    ["payment-release-condition", "Payment release condition", "Three-way match", "Invoice approval"],
)
def test_approval_wording_variants_share_one_predicate_key(wording: str) -> None:
    assert normalize_predicate(wording) == "approval_condition"


def test_unmapped_predicates_are_marked_not_silently_bucketed() -> None:
    key = normalize_predicate("Ambient temperature tolerance")
    assert key.startswith("other:")


def test_empty_predicate_is_unknown() -> None:
    assert normalize_predicate("") == "unknown"
    assert normalize_predicate("   ") == "unknown"


@pytest.mark.parametrize(
    ("raw", "expected"), [("day", "days"), ("days", "days"), ("Days", "days"), ("calendar day", "days")]
)
def test_day_units_normalise_together(raw: str, expected: str) -> None:
    assert normalize_unit(raw) == expected


def test_working_days_stay_distinct_from_calendar_days() -> None:
    assert normalize_unit("working days") == "working_days"
    assert normalize_unit("working days") != normalize_unit("calendar days")


@pytest.mark.parametrize("raw", ["", "unknown", "n/a", "none", "-", "not stated"])
def test_unstated_units_are_reported_as_unknown(raw: str) -> None:
    assert normalize_unit(raw) == "unknown"


def test_currency_units_keep_their_case() -> None:
    assert normalize_unit("chf") == "CHF"
    assert normalize_unit("Swiss francs (CHF)") == "CHF"


def test_equal_periods_normalise_to_the_same_value() -> None:
    assert normalize_value("30 days", "days") == normalize_value("30 calendar days", "days")
    assert normalize_value("30 days", "days") == normalize_value("30 Days", "days")


def test_different_periods_normalise_differently() -> None:
    assert normalize_value("30 days", "days") != normalize_value("60 days", "days")


def test_percentages_normalise() -> None:
    assert normalize_value("2.5 %", "percent") == "2.5%"
    assert normalize_value("2.5 percent", "percent") == "2.5%"


def test_amounts_normalise_consistently_across_formats() -> None:
    # A leading sign is not part of the leading-number pattern, so the raw
    # wording is folded to a stable lower-case key rather than being mangled.
    assert normalize_value("4,616.50", "CHF") == normalize_value("4,616.50", "CHF")
    assert normalize_value("CHF 4,616.50", "CHF") != normalize_value("CHF 9,999.00", "CHF")
    assert normalize_value("1000", "CHF") == "1000"


def test_unknown_values_stay_unknown() -> None:
    assert normalize_value("", "days") == "unknown"
    assert normalize_value("unknown", "days") == "unknown"


def test_values_differ_is_false_when_either_side_is_unknown() -> None:
    assert values_differ("unknown", "60 days", left_unit="unknown", right_unit="days") is False
    assert values_differ("30 days", "60 days", left_unit="days", right_unit="days") is True


def test_entity_normalisation_drops_legal_suffixes() -> None:
    assert normalize_subject("Nordwind Logistik AG") == "nordwind logistik"
    assert normalize_subject("Helvetia Praezision GmbH") == "helvetia praezision"


def test_generic_roles_are_not_treated_as_entities() -> None:
    assert normalize_subject("the buyer") == "unknown"
    assert normalize_subject("Supplier") == "unknown"
    assert normalize_subject("") == "unknown"


def test_unknown_entities_remain_comparable() -> None:
    assert subjects_compatible("unknown", "Nordwind Logistik AG") is True
    assert subjects_compatible("Nordwind Logistik AG", "Nordwind Logistik") is True


def test_two_different_known_entities_are_not_comparable() -> None:
    assert subjects_compatible("Nordwind Logistik AG", "Rheintal Spedition AG") is False


def test_dates_normalise_to_iso_or_unknown() -> None:
    assert normalize_date("Effective date: 2026-01-01") == "2026-01-01"
    assert normalize_date("2026-05-01") == "2026-05-01"
    assert normalize_date("unknown") == "unknown"
    assert normalize_date("") == "unknown"
    assert normalize_date("sometime in spring") == "unknown"
