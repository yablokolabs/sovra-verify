"""SQLite persistence.

Stores original document hashes, canonical page text, passages, claims,
analyses, findings, provider runs and review history. Prompt contents are not
stored by default; when they are stored it is opt-in via
``SOVRA_LOG_PROMPT_CONTENTS``, and credentials are never stored at all.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any

from .models import (
    Analysis,
    AnalysisStatus,
    Claim,
    Document,
    ExtractionStatus,
    Finding,
    Passage,
    ProviderRun,
    Relation,
    ReviewEvent,
    utcnow,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    mime TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    extraction_version TEXT NOT NULL,
    page_count INTEGER NOT NULL,
    extraction_status TEXT NOT NULL,
    extraction_notes TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    canonical_text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS passages (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    page INTEGER NOT NULL,
    text TEXT NOT NULL,
    start_offset INTEGER NOT NULL,
    end_offset INTEGER NOT NULL,
    paragraph_index INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS analyses (
    id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    review_status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS provider_runs (
    id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_events (
    id TEXT PRIMARY KEY,
    finding_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_passages_document ON passages(document_id);
CREATE INDEX IF NOT EXISTS idx_findings_analysis ON findings(analysis_id);
CREATE INDEX IF NOT EXISTS idx_claims_analysis ON claims(analysis_id);
CREATE INDEX IF NOT EXISTS idx_runs_analysis ON provider_runs(analysis_id);
CREATE INDEX IF NOT EXISTS idx_reviews_finding ON review_events(finding_id);
"""


class Storage:
    """Thread-safe SQLite store (FastAPI runs handlers on a worker pool)."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        if self.path.parent and str(self.path.parent) not in ("", "."):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- documents ---------------------------------------------------------
    def save_document(self, document: Document, passages: list[Passage], canonical_text: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    document.id,
                    document.name,
                    document.sha256,
                    document.mime,
                    document.size_bytes,
                    document.created_at.isoformat(),
                    document.extraction_version,
                    document.page_count,
                    document.extraction_status.value,
                    json.dumps(document.extraction_notes),
                    document.stored_name,
                    canonical_text,
                ),
            )
            self._conn.execute("DELETE FROM passages WHERE document_id = ?", (document.id,))
            self._conn.executemany(
                "INSERT OR REPLACE INTO passages VALUES (?,?,?,?,?,?,?)",
                [
                    (p.id, p.document_id, p.page, p.text, p.start_offset, p.end_offset, p.paragraph_index)
                    for p in passages
                ],
            )
            self._conn.commit()

    def get_document(self, document_id: str) -> Document | None:
        row = self._conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if row is None:
            return None
        return Document(
            id=row["id"],
            name=row["name"],
            sha256=row["sha256"],
            mime=row["mime"],
            size_bytes=row["size_bytes"],
            created_at=row["created_at"],
            extraction_version=row["extraction_version"],
            page_count=row["page_count"],
            extraction_status=ExtractionStatus(row["extraction_status"]),
            extraction_notes=json.loads(row["extraction_notes"]),
            stored_name=row["stored_name"],
        )

    def list_documents(self) -> list[Document]:
        rows = self._conn.execute("SELECT id FROM documents ORDER BY created_at DESC").fetchall()
        return [d for d in (self.get_document(r["id"]) for r in rows) if d is not None]

    def canonical_text(self, document_id: str) -> str:
        row = self._conn.execute(
            "SELECT canonical_text FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
        return row["canonical_text"] if row else ""

    def passages(self, document_id: str) -> list[Passage]:
        rows = self._conn.execute(
            "SELECT * FROM passages WHERE document_id = ? ORDER BY paragraph_index", (document_id,)
        ).fetchall()
        return [
            Passage(
                id=r["id"],
                document_id=r["document_id"],
                page=r["page"],
                text=r["text"],
                start_offset=r["start_offset"],
                end_offset=r["end_offset"],
                paragraph_index=r["paragraph_index"],
            )
            for r in rows
        ]

    def corpus_signature(self, document_ids: list[str]) -> str:
        """Hash of the analysed corpus, used for analysis idempotency."""
        import hashlib

        hasher = hashlib.sha256()
        for document_id in sorted(document_ids):
            row = self._conn.execute(
                "SELECT sha256 FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
            hasher.update((row["sha256"] if row else "missing").encode())
            hasher.update(document_id.encode())
        return hasher.hexdigest()

    # -- analyses ----------------------------------------------------------
    def save_analysis(self, analysis: Analysis) -> None:
        payload = analysis.model_dump(mode="json")
        payload.pop("findings", None)
        payload.pop("provider_runs", None)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO analyses VALUES (?,?,?,?,?)",
                (
                    analysis.id,
                    analysis.idempotency_key,
                    json.dumps(payload),
                    analysis.status.value,
                    analysis.created_at.isoformat(),
                ),
            )
            for run in analysis.provider_runs:
                self._conn.execute(
                    "INSERT OR REPLACE INTO provider_runs VALUES (?,?,?,?,?,?,?)",
                    (
                        run.id,
                        analysis.id,
                        run.provider,
                        run.model,
                        run.mode,
                        run.status,
                        json.dumps(run.model_dump(mode="json")),
                    ),
                )
            self._conn.execute("DELETE FROM findings WHERE analysis_id = ?", (analysis.id,))
            for finding in analysis.findings:
                self._conn.execute(
                    "INSERT OR REPLACE INTO findings VALUES (?,?,?,?,?)",
                    (
                        finding.id,
                        analysis.id,
                        json.dumps(finding.model_dump(mode="json")),
                        finding.review_status,
                        finding.created_at.isoformat(),
                    ),
                )
            self._conn.commit()

    def save_claims(self, analysis_id: str, claims: list[Claim]) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM claims WHERE analysis_id = ?", (analysis_id,))
            self._conn.executemany(
                "INSERT OR REPLACE INTO claims VALUES (?,?,?,?)",
                [
                    (c.id, analysis_id, c.document_id, json.dumps(c.model_dump(mode="json")))
                    for c in claims
                ],
            )
            self._conn.commit()

    def claims(self, analysis_id: str) -> list[Claim]:
        rows = self._conn.execute(
            "SELECT payload FROM claims WHERE analysis_id = ?", (analysis_id,)
        ).fetchall()
        return [Claim.model_validate(json.loads(r["payload"])) for r in rows]

    def analysis(self, analysis_id: str) -> Analysis | None:
        row = self._conn.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload"])
        payload["status"] = AnalysisStatus(row["status"])
        payload["findings"] = [
            Finding.model_validate(json.loads(r["payload"]))
            for r in self._conn.execute(
                "SELECT payload FROM findings WHERE analysis_id = ? ORDER BY created_at", (analysis_id,)
            ).fetchall()
        ]
        payload["provider_runs"] = [
            ProviderRun.model_validate(json.loads(r["payload"]))
            for r in self._conn.execute(
                "SELECT payload FROM provider_runs WHERE analysis_id = ?", (analysis_id,)
            ).fetchall()
        ]
        return Analysis.model_validate(payload)

    def list_analyses(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, status, payload, created_at FROM analyses ORDER BY created_at DESC"
        ).fetchall()
        out = []
        for row in rows:
            payload = json.loads(row["payload"])
            out.append(
                {
                    "id": row["id"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "provider": payload.get("provider", ""),
                    "model": payload.get("model", ""),
                    "document_ids": payload.get("document_ids", []),
                    "claim_count": payload.get("claim_count", 0),
                    "extract_only": payload.get("extract_only", False),
                }
            )
        return out

    def find_analysis_by_key(self, idempotency_key: str) -> str | None:
        row = self._conn.execute(
            "SELECT id FROM analyses WHERE idempotency_key = ? ORDER BY created_at DESC LIMIT 1",
            (idempotency_key,),
        ).fetchone()
        return row["id"] if row else None

    def update_finding_review(self, finding_id: str, status: str, note: str, reviewer: str) -> Finding | None:
        row = self._conn.execute("SELECT payload FROM findings WHERE id = ?", (finding_id,)).fetchone()
        if row is None:
            return None
        finding = Finding.model_validate(json.loads(row["payload"]))
        finding.review_status = status  # type: ignore[assignment]
        finding.review_note = note
        event = ReviewEvent(
            id=uuid.uuid4().hex[:16],
            finding_id=finding_id,
            status=status,  # type: ignore[arg-type]
            note=note,
            reviewer=reviewer,
            created_at=utcnow(),
        )
        with self._lock:
            self._conn.execute(
                "UPDATE findings SET payload = ?, review_status = ? WHERE id = ?",
                (json.dumps(finding.model_dump(mode="json")), status, finding_id),
            )
            self._conn.execute(
                "INSERT INTO review_events VALUES (?,?,?,?)",
                (event.id, finding_id, json.dumps(event.model_dump(mode="json")), event.created_at.isoformat()),
            )
            self._conn.commit()
        return finding

    def review_history(self, finding_id: str) -> list[ReviewEvent]:
        rows = self._conn.execute(
            "SELECT payload FROM review_events WHERE finding_id = ? ORDER BY created_at", (finding_id,)
        ).fetchall()
        return [ReviewEvent.model_validate(json.loads(r["payload"])) for r in rows]

    def relation_counts(self, analysis_id: str) -> dict[str, int]:
        counts: dict[str, int] = {r.value: 0 for r in Relation}
        for row in self._conn.execute(
            "SELECT payload FROM findings WHERE analysis_id = ?", (analysis_id,)
        ).fetchall():
            relation = json.loads(row["payload"]).get("relation", "")
            if relation in counts:
                counts[relation] += 1
        return counts
