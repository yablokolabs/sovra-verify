"""Analysis orchestration: upload -> extraction -> claims -> comparison -> citations.

The pipeline never silently substitutes a weaker model or a different provider.
If inference is unavailable the run finishes as ``failed`` (or, in extract-only
mode, completes with reasoning disabled and says so in the output), and the
failure is recorded rather than hidden.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Any

from .claims import ClaimExtractor, attach_canonical, claims_from_rules
from .compare import Comparer, build_candidates
from .config import Settings
from .ingest import IngestedDocument, extract_document, store_original
from .models import (
    Analysis,
    AnalysisStatus,
    Claim,
    Document,
    Finding,
    Passage,
    Relation,
    ProviderRun,
    utcnow,
)
from .prompts import PROMPT_VERSION
from .providers import ProviderError, ProviderRouter
from .storage import Storage

PROTOTYPE_NOTICE = (
    "Prototype: results are potential inconsistencies for human review, not a factual "
    "or legal determination."
)
UNKNOWN_DOCUMENT = "unknown"


class SovraService:
    def __init__(self, settings: Settings, storage: Storage, router: ProviderRouter):
        self.settings = settings
        self.storage = storage
        self.router = router

    # -- ingestion ---------------------------------------------------------
    def ingest(self, *, filename: str, data: bytes, mime: str = "") -> IngestedDocument:
        ingested = extract_document(
            display_name=filename, data=data, mime=mime, settings=self.settings
        )
        stored_name, _ = store_original(data, self.settings)
        ingested.document.stored_name = stored_name
        self.storage.save_document(ingested.document, ingested.passages, ingested.canonical_text)
        return ingested

    # -- analysis ----------------------------------------------------------
    def analyse(
        self,
        *,
        document_ids: list[str],
        extract_only: bool = False,
        force: bool = False,
    ) -> Analysis:
        corpus_hash = self.storage.corpus_signature(document_ids)
        idempotency_key = hashlib.sha256(
            f"{corpus_hash}|{self.settings.primary.name}|{self.settings.primary.model}|"
            f"{PROMPT_VERSION}|extract_only={extract_only}".encode()
        ).hexdigest()

        if not force:
            existing_id = self.storage.find_analysis_by_key(idempotency_key)
            if existing_id:
                existing = self.storage.analysis(existing_id)
                if existing and existing.status in (AnalysisStatus.COMPLETE, AnalysisStatus.PARTIAL):
                    existing.limitations.append(
                        "reused the previous result for the identical corpus, model and settings "
                        "(idempotent analysis)"
                    )
                    return existing

        analysis = Analysis(
            id=uuid.uuid4().hex[:16],
            idempotency_key=idempotency_key,
            document_ids=list(document_ids),
            status=AnalysisStatus.RUNNING,
            provider=self.settings.primary.name,
            model=self.settings.primary.model,
            prompt_version=PROMPT_VERSION,
            started_at=utcnow(),
        )
        analysis.limitations.append(PROTOTYPE_NOTICE)
        self.storage.save_analysis(analysis)

        try:
            self._run(analysis, extract_only=extract_only)
        except Exception as exc:  # never lose the record of a failed run
            analysis.status = AnalysisStatus.FAILED
            analysis.failures.append(f"{type(exc).__name__}: {exc}")
            analysis.limitations.append(
                "the analysis did not complete; the recorded findings are absent, not empty"
            )
        analysis.finished_at = utcnow()
        analysis.provider_runs = list(self.router.runs)
        self.storage.save_analysis(analysis)
        return analysis

    def _run(self, analysis: Analysis, *, extract_only: bool) -> None:
        documents, passages, canonical_by_doc = self._load_corpus(analysis.document_ids)
        document_names = {d.id: d.name for d in documents}
        if not documents:
            analysis.status = AnalysisStatus.FAILED
            analysis.failures.append("no documents were supplied for analysis")
            return

        skipped = [
            d.name
            for d in documents
            if d.extraction_status.value in ("ocr_not_implemented", "failed")
        ]
        if skipped:
            analysis.limitations.append(
                "documents without a usable text layer were not evaluated: " + ", ".join(skipped)
            )

        usable_passages = [p for p in passages if p.text.strip()]
        # Offsets are per document. Resolving a span must use that document's own
        # canonical text, never a string joined across the corpus.
        canonical_by_document = {
            document_id: canonical_by_doc.get(document_id, "")
            for document_id in {p.document_id for p in usable_passages}
        }
        empty_documents = [
            document_id
            for document_id, text in canonical_by_document.items()
            if not text.strip()
        ]
        if empty_documents:
            analysis.limitations.append(
                f"{len(empty_documents)} document(s) produced no canonical text; spans in those "
                "documents cannot be resolved and are excluded from evidence"
            )

        if extract_only:
            claims = claims_from_rules(usable_passages, document_names)
            self.storage.save_claims(analysis.id, claims)
            analysis.claim_count = len(claims)
            analysis.extract_only = True
            analysis.status = AnalysisStatus.COMPLETE
            analysis.limitations.append(
                "extract-only mode: no Apertus reasoning was performed. Claims come from the "
                "deterministic rule extractor; no comparison findings are produced."
            )
            return

        if not self.settings.primary.api_key:
            raise ProviderError(
                f"no credential available for the primary provider "
                f"({self.settings.primary.credential_env}); set it in the environment or in "
                "~/.hermes/.env on the build host",
                error_class="auth_error",
            )

        extractor = attach_canonical(
            ClaimExtractor(self.router, self.settings), canonical_by_document
        )
        model_claims, claim_limits = extractor.extract(
            passages=usable_passages, document_names=document_names
        )
        analysis.limitations.extend(claim_limits)

        rule_claims = claims_from_rules(usable_passages, document_names)
        claims = _merge_claims(model_claims, rule_claims)
        resolved_claims = [c for c in claims if c.extraction_status.value == "ok"]
        self.storage.save_claims(analysis.id, claims)
        analysis.claim_count = len(resolved_claims)
        if not model_claims:
            analysis.limitations.append(
                "no model-derived claims were produced; the deterministic baseline is shown instead"
            )

        candidates, coverage = build_candidates(
            resolved_claims, max_pairs=self.settings.max_compare_pairs
        )
        analysis.candidate_coverage = coverage
        analysis.pair_count = len(candidates)

        passages_by_id = {p.id: p for p in usable_passages}

        # Context for every comparison: the other extracted statements of each claim's
        # own document. An exception, carve-out or superseding date is normally written
        # beside the term it modifies, and two claims from the same document are never
        # paired, so without this the model judges a difference without ever having seen
        # the sentence that explains it. Bounded by MAX_CONTEXT_PASSAGES_PER_SIDE.
        context_by_document: dict[str, list[Passage]] = {}
        seen_context: dict[str, set[str]] = {}
        for claim in resolved_claims:
            passage = passages_by_id.get(claim.source_passage_id)
            if passage is None:
                continue
            ids = seen_context.setdefault(passage.document_id, set())
            if passage.id in ids:
                continue
            ids.add(passage.id)
            context_by_document.setdefault(passage.document_id, []).append(passage)

        comparer = Comparer(self.router, self.settings, extractor)
        outcome = comparer.compare(
            analysis_id=analysis.id,
            candidates=candidates,
            passages_by_id=passages_by_id,
            canonical_by_document=canonical_by_document,
            document_names=document_names,
            context_by_document=context_by_document,
        )

        kept: list[Finding] = []
        rejected = 0
        for finding in outcome.findings:
            if finding.relation is Relation.POTENTIAL_CONFLICT and not finding.evidence:
                rejected += 1
                continue
            kept.append(finding)

        # Every judged pair is counted by the relation it was given, so a run that
        # reports no inconsistency states what it actually considered and what it
        # concluded, instead of leaving an empty finding list to be read either way.
        judged: dict[str, int] = {}
        for finding in kept:
            judged[finding.relation.value] = judged.get(finding.relation.value, 0) + 1
        coverage["outcomes"] = dict(sorted(judged.items()))
        coverage["comparisons_without_finding"] = outcome.without_finding + rejected
        coverage["inconsistencies_reported"] = judged.get(Relation.POTENTIAL_CONFLICT.value, 0)
        analysis.candidate_coverage = coverage

        if candidates and not judged.get(Relation.POTENTIAL_CONFLICT.value, 0):
            analysis.limitations.append(
                f"{len(candidates)} candidate pair(s) were compared and none was judged a potential "
                "inconsistency. The coverage block lists the relation given to every compared pair, "
                "so this result means nothing was reported, not that nothing was checked."
            )
        if rejected:
            analysis.limitations.append(
                f"{rejected} potential conflicts were discarded because their citations did not "
                "resolve against canonical extracted text"
            )
        if coverage.get("pairs_dropped_by_cap"):
            analysis.limitations.append(
                f"{coverage['pairs_dropped_by_cap']} candidate pairs were not compared because of "
                "the configured comparison cap"
            )
        date_skips = (coverage.get("skipped_reasons_top") or {}).get("different effective dates")
        if date_skips:
            analysis.limitations.append(
                f"{date_skips} cross-document pairs were not compared because the two claims "
                "state different known effective dates; a difference of that kind is treated as "
                "an explanation, not a conflict. Check those pairs manually if a date is wrong."
            )

        analysis.findings = kept
        failed_runs = [r for r in self.router.runs if r.status != "ok"]
        analysis.failures.extend(
            f"{r.provider}/{r.model} {r.mode} failed: {r.error_message or r.error_class}"
            for r in failed_runs
        )
        if failed_runs and kept:
            analysis.status = AnalysisStatus.PARTIAL
            analysis.limitations.append(
                "some provider calls failed; these results are partial and do not cover the "
                "whole corpus"
            )
        elif failed_runs and not kept:
            analysis.status = AnalysisStatus.FAILED
            analysis.limitations.append(
                "every comparison call failed, so an empty finding list here means 'not "
                "evaluated', not 'no inconsistencies'"
            )
        elif not self.router.runs:
            analysis.status = AnalysisStatus.FAILED
        else:
            analysis.status = AnalysisStatus.COMPLETE

    def _load_corpus(
        self, document_ids: list[str]
    ) -> tuple[list[Document], list[Any], dict[str, str]]:
        documents: list[Document] = []
        passages: list[Any] = []
        canonical: dict[str, str] = {}
        for document_id in document_ids:
            document = self.storage.get_document(document_id)
            if document is None:
                continue
            documents.append(document)
            passages.extend(self.storage.passages(document_id))
            canonical[document_id] = self.storage.canonical_text(document_id)
        return documents, passages, canonical


def _merge_claims(model_claims: list[Claim], rule_claims: list[Claim]) -> list[Claim]:
    """Keep model claims and add baseline claims that add information.

    A rule claim is dropped only when a validated model claim already covers the
    same passage with the same normalised predicate *and* value. Dropping on the
    passage alone would discard the numeric baseline exactly when the model
    paraphrased a term, which is how a real conflict goes missing.
    """
    covered = {
        (c.document_id, c.source_passage_id, c.predicate_normalized, c.value_normalized)
        for c in model_claims
        if c.extraction_status.value == "ok"
    }
    merged = [c for c in model_claims if c.extraction_status.value == "ok"]
    merged.extend(
        c
        for c in rule_claims
        if (c.document_id, c.source_passage_id, c.predicate_normalized, c.value_normalized)
        not in covered
    )
    unresolved = [c for c in model_claims if c.extraction_status.value != "ok"]
    return merged + unresolved


def summarise_runs(runs: list[ProviderRun]) -> dict[str, Any]:
    """Aggregate provider, model, token usage and failures for reports."""
    total_prompt = total_completion = 0
    for run in runs:
        total_prompt += int(run.usage.get("prompt_tokens") or 0)
        total_completion += int(run.usage.get("completion_tokens") or 0)
    models = sorted({f"{r.provider}:{r.model}" for r in runs})
    return {
        "calls": len(runs),
        "failed_calls": sum(1 for r in runs if r.status != "ok"),
        "backup_calls": sum(1 for r in runs if r.is_backup),
        "downgrades": [r.downgraded_from for r in runs if r.downgraded_from],
        "prompt_tokens": total_prompt,
        "completion_tokens": total_completion,
        "total_tokens": total_prompt + total_completion,
        "models": models,
        "latency_ms_total": sum(r.latency_ms or 0 for r in runs),
    }


def iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""
