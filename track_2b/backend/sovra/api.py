"""FastAPI application for Sovra Verify.

Routes: POST /documents, GET /documents, POST /analyses, GET /analyses/{id},
GET /findings/{id}, POST /findings/{id}/reviews, GET /analyses/{id}/export,
GET /health, GET /config. Every screen and every exported artifact is
footer-free by construction; `scripts/check_no_footer.py` verifies it.
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import Settings, load_settings
from .ingest import IngestError
from .models import ReviewRequest
from .pipeline import SovraService, summarise_runs
from .providers import ProviderError, ProviderRouter
from .storage import Storage

WARNING_TEXT = (
    "Prototype — potential inconsistencies only. Every result requires human review and is not "
    "a legal, factual or compliance determination."
)


def create_app(settings: Settings | None = None, *, storage: Storage | None = None) -> FastAPI:
    settings = settings or load_settings()
    settings.work_dir.mkdir(parents=True, exist_ok=True)
    storage = storage or Storage(settings.work_dir / "sovra.sqlite3")
    router = ProviderRouter(settings)
    service = SovraService(settings, storage, router)

    app = FastAPI(title="Sovra Verify", version="0.1.0", docs_url="/api/docs", redoc_url=None)
    app.state.settings = settings
    app.state.storage = storage
    app.state.router = router
    app.state.service = service

    frontend_dir = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if frontend_dir.is_dir():
        app.mount("/app", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

    # ---------------------------------------------------------------- health
    @app.get("/health")
    def health() -> dict[str, Any]:
        cscs = router.health("cscs")
        return {
            "status": "ok" if cscs.get("reachable") else "degraded",
            "primary": cscs,
            "backup": {
                "provider": settings.backup.name,
                "model": settings.backup.model,
                "enabled": settings.backup.enabled,
                "fallback_allowed": settings.allow_backup_fallback,
                "credential": settings.backup.public_view()["api_key"],
            },
            "warning": WARNING_TEXT,
        }

    @app.get("/config")
    def config() -> dict[str, Any]:
        payload = settings.public_view()
        payload["provider_status"] = settings.provider_status
        payload["warning"] = WARNING_TEXT
        return payload

    # ------------------------------------------------------------- documents
    @app.post("/documents")
    async def upload_documents(files: list[UploadFile] = File(...)) -> dict[str, Any]:
        existing = len(storage.list_documents())
        if existing + len(files) > settings.max_documents:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"a project holds at most {settings.max_documents} documents; "
                    f"{existing} are already stored and {len(files)} more were supplied"
                ),
            )
        saved, rejected = [], []
        for upload in files:
            data = await upload.read()
            try:
                ingested = service.ingest(
                    filename=upload.filename or "", data=data, mime=upload.content_type or ""
                )
            except IngestError as exc:
                rejected.append({"name": upload.filename or "<unnamed>", "reason": exc.reason, "message": str(exc)})
                continue
            saved.append(
                {
                    **ingested.document.model_dump(mode="json"),
                    "passages": len(ingested.passages),
                }
            )
        if not saved and rejected:
            raise HTTPException(status_code=400, detail={"rejected": rejected})
        return {"saved": saved, "rejected": rejected}

    @app.get("/documents")
    def list_documents() -> dict[str, Any]:
        documents = []
        for document in storage.list_documents():
            documents.append(
                {
                    **document.model_dump(mode="json"),
                    "passages": len(storage.passages(document.id)),
                    "characters": len(storage.canonical_text(document.id)),
                }
            )
        return {"documents": documents, "max_documents": settings.max_documents}

    @app.get("/documents/{document_id}")
    def get_document(document_id: str) -> dict[str, Any]:
        document = storage.get_document(document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="unknown document")
        passages = storage.passages(document_id)
        return {
            "document": document.model_dump(mode="json"),
            "canonical_text": storage.canonical_text(document_id),
            "passages": [p.model_dump(mode="json") for p in passages],
        }

    # ------------------------------------------------------------- analyses
    @app.post("/analyses")
    def create_analysis(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        document_ids = [str(x) for x in (payload.get("document_ids") or [])]
        if not document_ids:
            raise HTTPException(status_code=422, detail="document_ids must not be empty")
        unknown = [d for d in document_ids if storage.get_document(d) is None]
        if unknown:
            raise HTTPException(status_code=404, detail=f"unknown document ids: {', '.join(unknown)}")
        try:
            analysis = service.analyse(
                document_ids=document_ids,
                extract_only=bool(payload.get("extract_only", False)),
                force=bool(payload.get("force", False)),
            )
        except ProviderError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from None
        return _analysis_view(analysis, storage)

    @app.get("/analyses")
    def list_analyses() -> dict[str, Any]:
        return {"analyses": storage.list_analyses()}

    @app.get("/analyses/{analysis_id}")
    def get_analysis(analysis_id: str) -> dict[str, Any]:
        analysis = storage.analysis(analysis_id)
        if analysis is None:
            raise HTTPException(status_code=404, detail="unknown analysis")
        return _analysis_view(analysis, storage)

    @app.get("/analyses/{analysis_id}/claims")
    def get_claims(analysis_id: str) -> dict[str, Any]:
        if storage.analysis(analysis_id) is None:
            raise HTTPException(status_code=404, detail="unknown analysis")
        return {"claims": [c.model_dump(mode="json") for c in storage.claims(analysis_id)]}

    # ------------------------------------------------------------- findings
    @app.get("/findings/{finding_id}")
    def get_finding(finding_id: str) -> dict[str, Any]:
        for analysis_summary in storage.list_analyses():
            analysis = storage.analysis(analysis_summary["id"])
            if analysis is None:
                continue
            for finding in analysis.findings:
                if finding.id == finding_id:
                    return {
                        "finding": finding.model_dump(mode="json"),
                        "review_history": [e.model_dump(mode="json") for e in storage.review_history(finding_id)],
                        "analysis_id": analysis.id,
                    }
        raise HTTPException(status_code=404, detail="unknown finding")

    @app.post("/findings/{finding_id}/reviews")
    def create_review(finding_id: str, request: ReviewRequest) -> dict[str, Any]:
        finding = storage.update_finding_review(
            finding_id, request.status, request.note, request.reviewer
        )
        if finding is None:
            raise HTTPException(status_code=404, detail="unknown finding")
        return {
            "finding": finding.model_dump(mode="json"),
            "review_history": [e.model_dump(mode="json") for e in storage.review_history(finding_id)],
        }

    # --------------------------------------------------------------- export
    @app.get("/analyses/{analysis_id}/export")
    def export_analysis(analysis_id: str, format: str = "json") -> Response:
        analysis = storage.analysis(analysis_id)
        if analysis is None:
            raise HTTPException(status_code=404, detail="unknown analysis")
        claims = storage.claims(analysis_id)
        documents = [storage.get_document(d) for d in analysis.document_ids]

        bundle = {
            "analysis": json.loads(analysis.model_dump_json()),
            "claims": [json.loads(c.model_dump_json()) for c in claims],
            "documents": [
                {
                    "id": d.id,
                    "name": d.name,
                    "sha256": d.sha256,
                    "page_count": d.page_count,
                    "extraction_status": d.extraction_status.value,
                    "extraction_notes": d.extraction_notes,
                }
                for d in documents
                if d is not None
            ],
            "provider_usage": summarise_runs(analysis.provider_runs),
            "prompt_version": analysis.prompt_version,
            "warning": WARNING_TEXT,
        }

        if format == "markdown":
            body = _markdown_report(bundle)
            return Response(
                content=body,
                media_type="text/markdown; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="sovra-{analysis_id}.md"'},
            )
        if format == "zip":
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("analysis.json", json.dumps(bundle, indent=2))
                archive.writestr("report.md", _markdown_report(bundle))
                for claim in claims:
                    archive.writestr(
                        f"claims/{claim.id}.json", json.dumps(json.loads(claim.model_dump_json()), indent=2)
                    )
            return Response(
                content=buffer.getvalue(),
                media_type="application/zip",
                headers={"Content-Disposition": f'attachment; filename="sovra-{analysis_id}.zip"'},
            )
        return JSONResponse(content=bundle)

    return app


def _analysis_view(analysis: Any, storage: Storage) -> dict[str, Any]:
    return {
        "analysis": json.loads(analysis.model_dump_json()),
        "relation_counts": storage.relation_counts(analysis.id),
        "usage": summarise_runs(analysis.provider_runs),
        "warning": WARNING_TEXT,
    }


def _markdown_report(bundle: dict[str, Any]) -> str:
    """A readable report. Deliberately has no closing footer or signature block."""
    analysis = bundle["analysis"]
    lines: list[str] = []
    lines.append(f"# Sovra Verify report — analysis {analysis['id']}")
    lines.append("")
    lines.append(f"- Provider: `{analysis['provider']}`")
    lines.append(f"- Model: `{analysis['model']}`")
    lines.append(f"- Prompt version: `{analysis['prompt_version']}`")
    lines.append(f"- Status: `{analysis['status']}`")
    lines.append(f"- Claims resolved: {analysis['claim_count']}")
    lines.append(f"- Candidate pairs compared: {analysis['pair_count']}")
    lines.append("")
    lines.append(f"> {bundle['warning']}")
    lines.append("")
    lines.append("## Corpus")
    for document in bundle["documents"]:
        lines.append(
            f"- `{document['name']}` — sha256 `{document['sha256'][:16]}…`, "
            f"{document['page_count']} page(s), extraction `{document['extraction_status']}`"
        )
        for note in document["extraction_notes"]:
            lines.append(f"  - note: {note}")
    lines.append("")
    lines.append("## Findings")
    if not analysis["findings"]:
        lines.append(
            "_No findings were recorded. Read the limitations below before treating this as "
            "'no inconsistencies': a failed or partial run also produces an empty list._"
        )
    for index, finding in enumerate(analysis["findings"], start=1):
        lines.append("")
        lines.append(f"### {index}. {finding['relation']} (review: {finding['review_status']})")
        lines.append("")
        lines.append(finding["explanation"])
        lines.append("")
        lines.append(f"- Claims: {', '.join(finding['claim_ids'])}")
        lines.append(f"- Provider run: `{finding['provider_run_id']}`")
        for citation in finding["evidence"]:
            lines.append(
                f"- Evidence: document `{citation['document_id']}` page {citation['page']} "
                f"offsets [{citation['start_offset']}, {citation['end_offset']}]\n"
                f"  > {citation['quote']}"
            )
        for limitation in finding["limitations"]:
            lines.append(f"- Limitation: {limitation}")
        if finding.get("review_note"):
            lines.append(f"- Reviewer note: {finding['review_note']}")
    lines.append("")
    lines.append("## Run limitations")
    for limitation in analysis["limitations"]:
        lines.append(f"- {limitation}")
    if analysis["failures"]:
        lines.append("")
        lines.append("## Recorded failures")
        for failure in analysis["failures"]:
            lines.append(f"- {failure}")
    lines.append("")
    lines.append("## Provider usage")
    usage = bundle["provider_usage"]
    lines.append(f"- Calls: {usage['calls']} ({usage['failed_calls']} failed)")
    lines.append(f"- Prompt tokens: {usage['prompt_tokens']}")
    lines.append(f"- Completion tokens: {usage['completion_tokens']}")
    lines.append(f"- Models used: {', '.join(usage['models']) or 'none'}")
    if usage["downgrades"]:
        lines.append(f"- Model changes recorded: {', '.join(usage['downgrades'])}")
    lines.append("")
    lines.append("## Evidence model")
    lines.append(
        "Quotes are sliced from canonical extracted text at the recorded offsets. A model may "
        "nominate a passage id and an offset pair; it cannot author quote text. Findings whose "
        "spans do not resolve are rejected before they reach this report."
    )
    return "\n".join(lines)


def app_factory() -> FastAPI:
    return create_app()


__all__ = ["WARNING_TEXT", "app_factory", "create_app"]
