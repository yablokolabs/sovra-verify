"""Claim identification: the deterministic baseline and model-claim validation."""

from __future__ import annotations

import json

import pytest

from sovra.claims import (
    attach_canonical,
    claims_from_rules,
    find_amount,
    looks_like_clause_number,
    with_normalized_keys,
)
from sovra.claims import ClaimExtractor
from sovra.models import Claim, ExtractionStatus, Passage


def make_passage(text: str, *, document_id: str = "doc-a", index: int = 0) -> Passage:
    return Passage(
        id=f"{document_id}-p{index}",
        document_id=document_id,
        page=1,
        text=text,
        start_offset=0,
        end_offset=len(text),
        paragraph_index=index,
    )


# -- find_amount -----------------------------------------------------------
@pytest.mark.parametrize(
    "text",
    [
        "Clause 4.10 applies to all supplier invoices.",
        "Policy 6.20 Currency.",
        "Section 11.20 governs notice.",
        "The Buyer may withhold payment of a disputed amount.",
        "within 30 days of the invoice date.",
        "the period of 60 days",
    ],
)
def test_clause_numbers_and_bare_integers_are_not_amounts(text: str) -> None:
    assert find_amount(text) is None


@pytest.mark.parametrize(
    ("text", "currency", "value"),
    [
        ("Total amount due CHF 4616.50", "CHF", "4616.50"),
        ("Invoice total 250.00", "", "250.00"),
        ("Paid EUR 99.99 to the supplier", "EUR", "99.99"),
    ],
)
def test_real_amounts_are_found(text: str, currency: str, value: str) -> None:
    amount = find_amount(text)
    assert amount is not None
    assert amount.currency == currency
    assert amount.value == value


@pytest.mark.parametrize(
    ("value", "text", "expected"),
    [
        ("4.10", "Policy 4.10 Standard settlement period", True),
        ("7.2", "Clause 7.2 Payment terms", True),
        ("30", "payable within 30 days", False),
        ("4.1", "the value is 4.1 units", False),
    ],
)
def test_clause_reference_detection(value: str, text: str, expected: bool) -> None:
    assert looks_like_clause_number(value, text) is expected


# -- rule baseline ---------------------------------------------------------
def test_rule_extractor_reads_a_payment_period() -> None:
    passage = make_passage("The Buyer shall pay each undisputed invoice within 30 days of the invoice date.")
    claims = claims_from_rules([passage], {passage.document_id: "agreement.txt"})
    assert len(claims) == 1
    claim = claims[0]
    assert claim.predicate == "payment_period"
    assert claim.predicate_normalized == "payment_period"
    assert claim.unit == "days"
    assert claim.unit_normalized == "days"
    assert claim.value == "30 days"
    assert claim.value_normalized == "30 days"
    assert claim.origin == "rules"
    assert claim.extraction_status is ExtractionStatus.OK


def test_rule_extractor_reads_a_currency_amount_with_its_unit() -> None:
    passage = make_passage("Total amount due CHF 4616.50 for the March period.")
    claims = claims_from_rules([passage], {passage.document_id: "invoice.txt"})
    amounts = [c for c in claims if c.predicate == "amount"]
    assert len(amounts) == 1
    assert amounts[0].unit == "CHF"
    assert amounts[0].unit_normalized == "CHF"


def test_rule_extractor_skips_a_clause_number_passage_entirely() -> None:
    passage = make_passage("Policy 4.10 Standard settlement period. Finance approves payments.")
    assert claims_from_rules([passage], {passage.document_id: "policy.txt"}) == []


def test_rule_claims_always_carry_a_source_passage_and_offsets() -> None:
    passage = make_passage("Settled within 60 days of the invoice date.")
    for claim in claims_from_rules([passage], {passage.document_id: "policy.txt"}):
        assert claim.source_passage_id == passage.id
        assert claim.quote_start == passage.start_offset
        assert claim.quote_end == passage.end_offset


# -- normalised keys -------------------------------------------------------
def test_with_normalized_keys_populates_comparable_keys_and_keeps_raw_wording() -> None:
    claim = with_normalized_keys(
        Claim(
            id="c1",
            document_id="doc-a",
            subject="Nordwind Logistik AG",
            predicate="Payment term",
            value="30 days",
            unit="days",
            source_passage_id="doc-a-p0",
            effective_date="Effective 2026-01-01",
        )
    )
    assert claim.predicate == "Payment term"  # raw wording is preserved for review
    assert claim.predicate_normalized == "payment_period"
    assert claim.unit_normalized == "days"
    assert claim.value_normalized == "30 days"
    assert claim.subject_normalized == "nordwind logistik"
    assert claim.effective_date == "2026-01-01"


# -- model claim validation ------------------------------------------------
def synthetic_claim_payload(**overrides) -> dict:
    payload = {
        "passage_id": "doc-a-p0",
        "subject": "unknown",
        "predicate": "amount",
        "value": "4.10",
        "unit": "unknown",
        "scope": "unknown",
        "effective_date": "unknown",
        "quote_start": 0,
        "quote_end": 41,
    }
    payload.update(overrides)
    return payload


def test_model_claim_whose_value_is_a_clause_reference_is_reclassified(
    settings, router_factory, chat_response_factory
) -> None:
    passage = make_passage("Policy 4.10 Standard settlement period.", document_id="doc-a")
    canonical = passage.text

    def handler(request):
        return chat_response_factory(
            json.dumps({"claims": [synthetic_claim_payload(quote_end=len(canonical))]})
        )

    extractor = attach_canonical(
        ClaimExtractor(router_factory(settings, handler), settings), {passage.document_id: canonical}
    )
    claims, limitations = extractor.extract(
        passages=[passage], document_names={passage.document_id: "policy.txt"}
    )
    assert len(claims) == 1
    assert claims[0].extraction_status is ExtractionStatus.OK
    assert claims[0].predicate == "clause_reference"
    assert claims[0].predicate_normalized != "amount"
    assert "clause reference" in claims[0].notes
    assert limitations == []


def test_model_claim_citing_an_unknown_passage_is_unresolved(
    settings, router_factory, chat_response_factory
) -> None:
    passage = make_passage("Settled within 60 days of the invoice date.", document_id="doc-b")

    def handler(request):
        return chat_response_factory(
            json.dumps({"claims": [synthetic_claim_payload(passage_id="invented-id", quote_end=10)]})
        )

    extractor = attach_canonical(
        ClaimExtractor(router_factory(settings, handler), settings), {passage.document_id: passage.text}
    )
    claims, limitations = extractor.extract(
        passages=[passage], document_names={passage.document_id: "policy.txt"}
    )
    assert len(claims) == 1
    assert claims[0].extraction_status is ExtractionStatus.UNRESOLVED
    assert "unknown passage id" in claims[0].notes
    assert any("could not be resolved" in limitation for limitation in limitations)


def test_truncated_claim_response_yields_no_claims_and_a_visible_limitation(
    settings, router_factory, chat_response_factory
) -> None:
    passage = make_passage("Settled within 60 days of the invoice date.", document_id="doc-b")

    def handler(request):
        return chat_response_factory(
            '{"claims": [{"passage_id": "doc-b-p0"', finish_reason="length"
        )

    extractor = attach_canonical(
        ClaimExtractor(router_factory(settings, handler), settings), {passage.document_id: passage.text}
    )
    claims, limitations = extractor.extract(
        passages=[passage], document_names={passage.document_id: "policy.txt"}
    )
    assert claims == []
    assert any("no usable JSON" in limitation for limitation in limitations)


def test_malformed_claim_response_is_repaired_once(
    settings, router_factory, chat_response_factory
) -> None:
    passage = make_passage("Settled within 60 days of the invoice date.", document_id="doc-b")
    captured: dict[str, list[str]] = {}

    def handler(request):
        body = json.loads(request.content.decode("utf-8"))
        user = body["messages"][1]["content"]
        if user.startswith("Your previous answer could not be parsed as JSON"):
            passage_ids = captured.get("ids", [])
            return chat_response_factory(
                json.dumps(
                    {
                        "claims": [
                            {
                                "passage_id": passage_ids[0],
                                "subject": "unknown",
                                "predicate": "payment term",
                                "value": "60",
                                "unit": "days",
                                "scope": "unknown",
                                "effective_date": "unknown",
                                "quote_start": 0,
                                "quote_end": len(passage.text),
                            }
                        ]
                    }
                )
            )
        captured["ids"] = [passage.id]
        return chat_response_factory("I am afraid I cannot answer that.")

    router = router_factory(settings, handler)
    extractor = attach_canonical(
        ClaimExtractor(router, settings), {passage.document_id: passage.text}
    )
    claims, limitations = extractor.extract(
        passages=[passage], document_names={passage.document_id: "policy.txt"}
    )
    assert len(claims) == 1
    assert claims[0].predicate_normalized == "payment_period"
    assert any(run.mode.endswith(":repair") for run in router.runs), "repair attempt must be recorded"
    assert not limitations
