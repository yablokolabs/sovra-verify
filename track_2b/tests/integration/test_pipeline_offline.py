"""Offline end-to-end pipeline: ingestion -> claims -> comparison -> citations.

The provider layer is an ``httpx.MockTransport``; nothing here contacts CSCS or
Hugging Face.
"""

from __future__ import annotations

import json

import httpx
import pytest

from sovra.config import DEFAULT_MODEL
from sovra.models import AnalysisStatus, Relation
from sovra.pipeline import SovraService, summarise_runs
from sovra.providers import ProviderRouter

AGREEMENT = (
    "Clause 7.2 Payment terms\n"
    "The Buyer shall pay each undisputed invoice within 30 days of the invoice date.\n"
)
POLICY = (
    "Policy 4.1 Standard settlement period\n"
    "All supplier invoices are settled within 60 days of the invoice date.\n"
)


@pytest.fixture
def corpus(settings, storage) -> list[str]:
    """Ingest two synthetic documents with no provider involved."""
    service = SovraService(settings, storage, ProviderRouter(settings))
    documents = [
        service.ingest(filename="agreement.txt", data=AGREEMENT.encode(), mime="text/plain"),
        service.ingest(filename="policy.txt", data=POLICY.encode(), mime="text/plain"),
    ]
    return [item.document.id for item in documents]


@pytest.fixture
def service_factory(settings, storage, router_factory):
    def factory(handler) -> tuple[SovraService, ProviderRouter]:
        router = router_factory(settings, handler)
        return SovraService(settings, storage, router), router

    return factory


# -- the happy path --------------------------------------------------------
def test_full_offline_run_produces_findings_and_records_the_run(
    service_factory, corpus, canned_handler_fn
):
    service, router = service_factory(canned_handler_fn)
    analysis = service.analyse(document_ids=corpus)

    assert analysis.status is AnalysisStatus.COMPLETE, analysis.failures
    assert analysis.failures == []
    assert analysis.claim_count > 0
    assert analysis.pair_count > 0
    assert analysis.findings, "expected at least one finding from the canned provider"
    assert analysis.provider == "cscs"
    assert analysis.model == DEFAULT_MODEL
    assert router.runs, "provider runs must be recorded"


def test_every_produced_citation_resolves_into_the_canonical_text_of_its_document(
    service_factory, storage, corpus, canned_handler_fn
):
    """A displayed citation must be a slice of the cited document's own text.

    This is the core evidence rule: the quote is derived from canonical
    extracted text at the recorded offsets, so a reader can open the page and
    find exactly that string. If this test fails while the offsets look sane,
    suspect ``pipeline.SovraService._run``: it builds a single ``canonical``
    string by joining one canonical text per *passage* across the whole corpus
    (``"\\n".join(canonical_by_doc.get(p.document_id, "") for p in usable_passages)``),
    while passage offsets are per document. With more than one document the
    offsets of the second document are then interpreted in the first
    document's coordinate space.
    """
    service, _router = service_factory(canned_handler_fn)
    analysis = service.analyse(document_ids=corpus)

    checked = 0
    for finding in analysis.findings:
        assert finding.evidence, f"{finding.relation.value} finding has no citation"
        for citation in finding.evidence:
            canonical = storage.canonical_text(citation.document_id)
            assert canonical != "", "the cited document must be stored"
            assert citation.end_offset <= len(canonical), (
                f"citation offsets {citation.start_offset}:{citation.end_offset} run past "
                f"the end of document {citation.document_id} ({len(canonical)} chars)"
            )
            assert canonical[citation.start_offset : citation.end_offset] == citation.quote, (
                f"citation quote does not match canonical text of {citation.document_id} "
                f"at offsets {citation.start_offset}:{citation.end_offset}"
            )
            checked += 1
    assert checked > 0, "no citations were produced to check"


def test_the_run_records_usage_without_failures_or_downgrades(
    service_factory, corpus, canned_handler_fn
):
    service, _router = service_factory(canned_handler_fn)
    analysis = service.analyse(document_ids=corpus)
    usage = summarise_runs(analysis.provider_runs)
    assert usage["calls"] == len(analysis.provider_runs) > 0
    assert usage["failed_calls"] == 0
    assert usage["total_tokens"] > 0
    assert usage["models"] == [f"cscs:{DEFAULT_MODEL}"]
    assert usage["backup_calls"] == 0
    assert usage["downgrades"] == []


def test_every_provider_run_records_provider_model_and_mode(
    service_factory, corpus, canned_handler_fn
):
    service, _router = service_factory(canned_handler_fn)
    analysis = service.analyse(document_ids=corpus)
    modes = {run.mode for run in analysis.provider_runs}
    assert "claims" in modes
    assert "compare" in modes
    for run in analysis.provider_runs:
        assert run.provider == "cscs"
        assert run.model == DEFAULT_MODEL
        assert run.input_hash
        assert run.status == "ok"
        assert run.latency_ms is not None


def test_analysis_is_idempotent_for_the_same_corpus(service_factory, corpus, canned_handler_fn):
    service, _router = service_factory(canned_handler_fn)
    first = service.analyse(document_ids=corpus)
    second = service.analyse(document_ids=corpus)
    assert second.id == first.id
    assert any("idempotent" in limitation for limitation in second.limitations)


def test_force_recomputes_the_analysis(service_factory, corpus, canned_handler_fn):
    service, _router = service_factory(canned_handler_fn)
    first = service.analyse(document_ids=corpus)
    second = service.analyse(document_ids=corpus, force=True)
    assert second.id != first.id


def test_analysis_records_candidate_coverage_so_misses_are_visible(
    service_factory, corpus, canned_handler_fn
):
    service, _router = service_factory(canned_handler_fn)
    analysis = service.analyse(document_ids=corpus)
    coverage = analysis.candidate_coverage
    assert coverage["claims"] >= 2
    assert coverage["documents"] == 2
    assert coverage["pairs_compared"] > 0
    assert "skipped_reasons_top" in coverage
    assert "pairs_skipped" in coverage


def test_finding_relations_and_limitations_are_within_the_documented_vocabulary(
    service_factory, corpus, canned_handler_fn
):
    service, _router = service_factory(canned_handler_fn)
    analysis = service.analyse(document_ids=corpus)
    valid = {relation.value for relation in Relation}
    for finding in analysis.findings:
        assert finding.relation.value in valid
        assert finding.claim_ids
        assert "not a legal or factual determination" in " ".join(finding.limitations)
        assert finding.review_status == "pending"


def test_unknown_document_ids_are_ignored_rather_than_crashing(
    service_factory, corpus, canned_handler_fn
):
    service, _router = service_factory(canned_handler_fn)
    analysis = service.analyse(document_ids=[*corpus, "does-not-exist"])
    assert analysis.status in {AnalysisStatus.COMPLETE, AnalysisStatus.PARTIAL}
    assert len(analysis.document_ids) == 3


# -- failure paths ---------------------------------------------------------
def test_a_completely_failed_run_does_not_look_like_clean_results(
    service_factory, corpus, failing_handler_fn
):
    """Every provider call fails: the run must be failed, not 'no conflicts'."""
    service, _router = service_factory(failing_handler_fn(401))
    analysis = service.analyse(document_ids=corpus)

    assert analysis.status is AnalysisStatus.FAILED
    assert analysis.failures, "a failed run must record why it failed"
    assert analysis.findings == []
    joined = " ".join(analysis.limitations).lower()
    assert "not evaluated" in joined or "did not complete" in joined
    assert any(run.status == "failed" for run in analysis.provider_runs)


def test_a_failed_run_keeps_the_rule_baseline_claims_visible(
    service_factory, storage, corpus, failing_handler_fn
):
    service, _router = service_factory(failing_handler_fn(500))
    analysis = service.analyse(document_ids=corpus)
    claims = storage.claims(analysis.id)
    assert claims, "the deterministic baseline must still be stored"
    assert any(claim.origin == "rules" for claim in claims)
    assert analysis.status is AnalysisStatus.FAILED


def test_a_failed_run_reports_no_backup_call_when_fallback_is_off(
    service_factory, corpus, failing_handler_fn
):
    service, router = service_factory(failing_handler_fn(503))
    analysis = service.analyse(document_ids=corpus)
    assert all(run.is_backup is False for run in analysis.provider_runs)
    assert summarise_runs(analysis.provider_runs)["backup_calls"] == 0
    assert analysis.status is AnalysisStatus.FAILED


def test_missing_credential_fails_visibly_without_switching_provider(
    service_factory, settings, corpus
):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={})

    service, router = service_factory(handler)
    settings.primary.api_key = ""
    analysis = service.analyse(document_ids=corpus)
    assert analysis.status is AnalysisStatus.FAILED
    assert analysis.failures
    assert "credential" in " ".join(analysis.failures).lower()
    assert router.runs == [], "no request may be attempted without a credential"
    assert calls == [], "no HTTP call may be attempted without a credential"


def test_extract_only_mode_never_calls_a_provider(
    settings, storage, corpus, router_factory
):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500, json={})

    service = SovraService(settings, storage, router_factory(settings, handler))
    analysis = service.analyse(document_ids=corpus, extract_only=True)

    assert calls == []
    assert analysis.status is AnalysisStatus.COMPLETE
    assert analysis.extract_only is True
    assert analysis.findings == []
    assert analysis.claim_count > 0
    assert any("extract-only" in limitation for limitation in analysis.limitations)


def test_an_empty_corpus_fails_with_an_explicit_reason(
    settings, storage, canned_handler_fn, router_factory
):
    service = SovraService(settings, storage, router_factory(settings, canned_handler_fn))
    analysis = service.analyse(document_ids=[])
    assert analysis.status is AnalysisStatus.FAILED
    assert any("no documents" in failure.lower() for failure in analysis.failures)


# -- a run that reports nothing says what it compared ----------------------
def _only_consistent_handler(canned_handler):
    """Reuse the canned handler, then rewrite compare answers to "consistent".

    Wrapping the shared handler keeps one implementation of the claim-request
    parsing in the suite instead of a second copy that could drift from it.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        response = canned_handler(request)
        if request.method == "GET" or not request.content:
            return response
        system = json.loads(request.content.decode("utf-8"))["messages"][0]["content"]
        if "procurement-document analyst" in system:
            return response
        payload = response.json()
        content = json.loads(payload["choices"][0]["message"]["content"])
        content["relation"] = "consistent"
        payload["choices"][0]["message"]["content"] = json.dumps(content)
        return httpx.Response(response.status_code, json=payload)

    return handler


def test_every_compared_pair_is_counted_and_an_empty_report_says_so(
    service_factory, corpus, canned_handler_fn
):
    service, _ = service_factory(_only_consistent_handler(canned_handler_fn))
    analysis = service.analyse(document_ids=corpus)

    assert analysis.status is AnalysisStatus.COMPLETE, analysis.failures
    assert analysis.findings, "the canned claims should still produce compared pairs"
    assert all(finding.relation is Relation.CONSISTENT for finding in analysis.findings)

    coverage = analysis.candidate_coverage
    assert coverage["outcomes"] == {"consistent": len(analysis.findings)}
    assert coverage["inconsistencies_reported"] == 0
    assert coverage["comparisons_without_finding"] == 0
    assert any(
        "nothing was reported, not that nothing was checked" in limitation
        for limitation in analysis.limitations
    ), analysis.limitations
