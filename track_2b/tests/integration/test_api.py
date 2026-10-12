"""HTTP API behaviour: limits, error codes, the review workflow and exports.

Every provider call is served by the injected mock transport, so the suite never
contacts CSCS or Hugging Face.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest

AGREEMENT = (
    b"Clause 7.2 Payment terms\n"
    b"The Buyer shall pay each undisputed invoice within 30 days of the invoice date.\n"
)
POLICY = (
    b"Policy 4.1 Standard settlement period\n"
    b"All supplier invoices are settled within 60 days of the invoice date.\n"
)


def upload(client, files):
    return client.post(
        "/documents",
        files=[("files", (name, data, "text/plain")) for name, data in files],
    )


@pytest.fixture
def analysed(api_client):
    """Upload two documents and run one analysis; yields (client, analysis)."""
    client, _settings = api_client()
    assert upload(client, [("agreement.txt", AGREEMENT), ("policy.txt", POLICY)]).status_code == 200
    document_ids = [d["id"] for d in client.get("/documents").json()["documents"]]
    response = client.post("/analyses", json={"document_ids": document_ids})
    assert response.status_code == 200, response.text
    return client, response.json()["analysis"]


# -- configuration and health ---------------------------------------------
def test_config_reports_the_default_model_and_provider(api_client):
    client, _settings = api_client()
    payload = client.get("/config").json()
    assert payload["primary_provider"] == "cscs"
    assert payload["default_model"] == "swiss-ai/Apertus-v1.5-70B"
    assert payload["backup_provider"] == "huggingface"
    assert payload["backup_fallback_enabled"] is False
    assert "warning" in payload


def test_config_never_exposes_a_raw_credential(api_client):
    client, _settings = api_client()
    text = client.get("/config").text
    assert "test-key-not-real" not in text
    assert "CSCS_INFERENCE_API_KEY" in text


def test_health_reports_the_primary_provider_reachability(api_client):
    client, _settings = api_client()
    payload = client.get("/health").json()
    assert payload["status"] in {"ok", "degraded"}
    assert payload["primary"]["provider"] == "cscs"
    assert payload["backup"]["enabled"] is False


# -- uploads ---------------------------------------------------------------
def test_upload_accepts_a_text_document(api_client):
    client, _settings = api_client()
    response = upload(client, [("agreement.txt", AGREEMENT)])
    assert response.status_code == 200
    saved = response.json()["saved"]
    assert len(saved) == 1
    assert saved[0]["name"] == "agreement.txt"
    assert len(saved[0]["sha256"]) == 64
    assert saved[0]["extraction_status"] == "ok"
    assert saved[0]["passages"] >= 1


def test_upload_with_a_malicious_path_stores_a_safe_display_name(api_client):
    client, _settings = api_client()
    response = upload(client, [("../../etc/passwd.txt", AGREEMENT)])
    assert response.status_code == 200
    name = response.json()["saved"][0]["name"]
    assert "/" not in name and "\\" not in name
    assert ".." not in name
    assert name == "passwd.txt"


def test_upload_rejects_an_oversized_file(api_client):
    client, _settings = api_client(max_upload_bytes=64)
    response = upload(client, [("big.txt", b"x" * 512)])
    assert response.status_code == 400
    rejected = response.json()["detail"]["rejected"]
    assert rejected[0]["reason"] == "too_large"
    assert client.get("/documents").json()["documents"] == []


def test_upload_rejects_an_unsupported_extension(api_client):
    client, _settings = api_client()
    response = client.post("/documents", files=[("files", ("notes.docx", b"hello", "application/msword"))])
    assert response.status_code == 400
    assert response.json()["detail"]["rejected"][0]["reason"] == "unsupported_type"


def test_upload_accepts_good_files_while_reporting_bad_ones(api_client):
    client, _settings = api_client()
    response = client.post(
        "/documents",
        files=[
            ("files", ("good.txt", AGREEMENT, "text/plain")),
            ("files", ("bad.docx", b"hello", "application/msword")),
        ],
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["saved"]) == 1
    assert len(payload["rejected"]) == 1
    assert payload["rejected"][0]["reason"] == "unsupported_type"


def test_the_document_cap_is_enforced(api_client):
    client, _settings = api_client(max_documents=2)
    assert upload(client, [("a.txt", AGREEMENT), ("b.txt", POLICY)]).status_code == 200
    response = upload(client, [("c.txt", AGREEMENT)])
    assert response.status_code == 413
    assert "at most 2 documents" in response.json()["detail"]


def test_listing_documents_reports_extraction_status(api_client):
    client, _settings = api_client()
    upload(client, [("agreement.txt", AGREEMENT)])
    payload = client.get("/documents").json()
    assert payload["max_documents"] == 10
    document = payload["documents"][0]
    assert document["extraction_status"] == "ok"
    assert document["characters"] > 0
    assert document["extraction_notes"] == []


def test_getting_an_unknown_document_returns_404(api_client):
    client, _settings = api_client()
    assert client.get("/documents/does-not-exist").status_code == 404


def test_a_document_can_be_fetched_with_its_passages(api_client):
    client, _settings = api_client()
    upload(client, [("agreement.txt", AGREEMENT)])
    document_id = client.get("/documents").json()["documents"][0]["id"]
    payload = client.get(f"/documents/{document_id}").json()
    assert payload["document"]["id"] == document_id
    assert payload["passages"]
    canonical = payload["canonical_text"]
    for passage in payload["passages"]:
        assert canonical[passage["start_offset"] : passage["end_offset"]] == passage["text"]


# -- analyses --------------------------------------------------------------
def test_analysis_requires_at_least_one_document(api_client):
    client, _settings = api_client()
    assert client.post("/analyses", json={"document_ids": []}).status_code == 422


def test_analysis_with_an_unknown_document_id_returns_404(api_client):
    client, _settings = api_client()
    upload(client, [("agreement.txt", AGREEMENT)])
    response = client.post("/analyses", json={"document_ids": ["not-a-document"]})
    assert response.status_code == 404
    assert "unknown document" in response.json()["detail"]


def test_getting_an_unknown_analysis_returns_404(api_client):
    client, _settings = api_client()
    assert client.get("/analyses/does-not-exist").status_code == 404


def test_claims_of_an_unknown_analysis_return_404(api_client):
    client, _settings = api_client()
    assert client.get("/analyses/does-not-exist/claims").status_code == 404


def test_analysis_response_carries_usage_and_the_warning(api_client, analysed):
    _client, analysis = analysed
    body = _client.get(f"/analyses/{analysis['id']}").json()
    assert body["analysis"]["provider"] == "cscs"
    assert body["analysis"]["model"] == "swiss-ai/Apertus-v1.5-70B"
    assert body["usage"]["calls"] > 0
    assert "requires human review" in body["warning"]
    assert set(body["relation_counts"]) >= {"consistent", "potential_conflict", "unrelated"}


def test_analysis_response_states_what_was_compared(api_client, analysed):
    """The coverage block the reviewer reads must agree with the findings they see.

    A run that reports nothing has to say what it compared, and the per-relation
    counts are the part a reviewer can check against the finding list.
    """
    _client, analysis = analysed
    body = _client.get(f"/analyses/{analysis['id']}").json()
    coverage = body["analysis"]["candidate_coverage"]

    assert coverage["pairs_compared"] >= 1
    assert "comparisons_without_finding" in coverage

    counted: dict[str, int] = {}
    for finding in body["analysis"]["findings"]:
        counted[finding["relation"]] = counted.get(finding["relation"], 0) + 1
    assert coverage["outcomes"] == counted
    assert coverage["inconsistencies_reported"] == counted.get("potential_conflict", 0)


def test_claims_endpoint_returns_claims_for_a_real_analysis(api_client, analysed):
    _client, analysis = analysed
    claims = _client.get(f"/analyses/{analysis['id']}/claims").json()["claims"]
    assert claims
    assert all(claim["source_passage_id"] for claim in claims)
    assert all(claim["predicate_normalized"] for claim in claims)


# -- findings and review ---------------------------------------------------
def test_getting_an_unknown_finding_returns_404(api_client):
    client, _settings = api_client()
    assert client.get("/findings/does-not-exist").status_code == 404


def test_reviewing_an_unknown_finding_returns_404(api_client):
    client, _settings = api_client()
    response = client.post("/findings/does-not-exist/reviews", json={"status": "dismissed"})
    assert response.status_code == 404


def test_an_invalid_review_status_is_rejected(api_client, analysed):
    _client, analysis = analysed
    if not analysis["findings"]:
        pytest.skip("the canned run produced no findings to review")
    finding_id = analysis["findings"][0]["id"]
    response = _client.post(f"/findings/{finding_id}/reviews", json={"status": "legally_resolved"})
    assert response.status_code == 422


def test_a_valid_review_updates_the_finding_and_records_history(api_client, analysed):
    _client, analysis = analysed
    if not analysis["findings"]:
        pytest.skip("the canned run produced no findings to review")
    finding_id = analysis["findings"][0]["id"]

    response = _client.post(
        f"/findings/{finding_id}/reviews",
        json={"status": "confirmed_for_review", "note": "checked against the signed copy"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["finding"]["review_status"] == "confirmed_for_review"
    assert payload["finding"]["review_note"] == "checked against the signed copy"
    assert len(payload["review_history"]) == 1
    assert payload["review_history"][0]["status"] == "confirmed_for_review"

    fetched = _client.get(f"/findings/{finding_id}").json()
    assert fetched["finding"]["review_status"] == "confirmed_for_review"
    assert len(fetched["review_history"]) == 1


def test_reviews_accumulate_as_history(api_client, analysed):
    _client, analysis = analysed
    if not analysis["findings"]:
        pytest.skip("the canned run produced no findings to review")
    finding_id = analysis["findings"][0]["id"]
    _client.post(f"/findings/{finding_id}/reviews", json={"status": "confirmed_for_review"})
    _client.post(f"/findings/{finding_id}/reviews", json={"status": "dismissed", "note": "duplicate"})
    history = _client.get(f"/findings/{finding_id}").json()["review_history"]
    assert [event["status"] for event in history] == ["confirmed_for_review", "dismissed"]


# -- exports ---------------------------------------------------------------
def test_json_export_carries_provenance_and_usage(api_client, analysed):
    _client, analysis = analysed
    response = _client.get(f"/analyses/{analysis['id']}/export")
    assert response.status_code == 200
    bundle = response.json()
    assert bundle["analysis"]["id"] == analysis["id"]
    assert bundle["prompt_version"]
    assert bundle["provider_usage"]["calls"] > 0
    assert bundle["documents"]
    assert all(len(document["sha256"]) == 64 for document in bundle["documents"])
    assert "warning" in bundle


def test_markdown_export_is_readable_and_carries_the_warning(api_client, analysed):
    _client, analysis = analysed
    response = _client.get(f"/analyses/{analysis['id']}/export", params={"format": "markdown"})
    assert response.status_code == 200
    text = response.text
    assert text.startswith("# Sovra Verify report")
    assert "## Evidence model" in text
    assert analysis["id"] in text
    assert "not a legal" in text


def test_zip_export_contains_the_bundle_and_the_report(api_client, analysed):
    _client, analysis = analysed
    response = _client.get(f"/analyses/{analysis['id']}/export", params={"format": "zip"})
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        assert {"analysis.json", "report.md"} <= names
        bundle = json.loads(archive.read("analysis.json"))
        assert bundle["analysis"]["id"] == analysis["id"]


def test_export_of_an_unknown_analysis_returns_404(api_client):
    client, _settings = api_client()
    assert client.get("/analyses/does-not-exist/export").status_code == 404


def test_an_empty_finding_list_does_not_claim_there_are_no_inconsistencies(api_client):
    """Extract-only is honest: it says no reasoning happened, not 'all clear'."""
    client, _settings = api_client()
    upload(client, [("agreement.txt", AGREEMENT), ("policy.txt", POLICY)])
    document_ids = [d["id"] for d in client.get("/documents").json()["documents"]]
    response = client.post("/analyses", json={"document_ids": document_ids, "extract_only": True})
    assert response.status_code == 200
    body = response.json()
    assert body["analysis"]["findings"] == []
    assert body["analysis"]["extract_only"] is True
    assert any("extract-only" in limitation for limitation in body["analysis"]["limitations"])

    report = client.get(
        f"/analyses/{body['analysis']['id']}/export", params={"format": "markdown"}
    ).text
    # The report must not let an empty list read as 'no inconsistencies'.
    assert "No findings were recorded" in report
    assert "before treating this as" in report
