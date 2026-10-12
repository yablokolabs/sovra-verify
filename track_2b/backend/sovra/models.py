"""Evidence-first data contracts.

Canonical extracted text is the authority for offsets. Quotes are derived
deterministically from ``(start_offset, end_offset)`` and never from a string a
model produced, so a fabricated citation cannot become validated evidence.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

EXTRACTION_VERSION = "extract-1"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Relation(str, Enum):
    CONSISTENT = "consistent"
    POTENTIAL_CONFLICT = "potential_conflict"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNRELATED = "unrelated"


REVIEW_STATES = ("pending", "confirmed_for_review", "dismissed")


class ExtractionStatus(str, Enum):
    OK = "ok"
    UNRESOLVED = "unresolved"
    FAILED = "failed"
    TRUNCATED = "truncated"
    OCR_NOT_IMPLEMENTED = "ocr_not_implemented"


class Document(BaseModel):
    id: str
    name: str
    sha256: str
    mime: str
    size_bytes: int
    created_at: datetime = Field(default_factory=utcnow)
    extraction_version: str = EXTRACTION_VERSION
    page_count: int = 0
    extraction_status: ExtractionStatus = ExtractionStatus.OK
    extraction_notes: list[str] = Field(default_factory=list)
    stored_name: str = ""


class Passage(BaseModel):
    id: str
    document_id: str
    page: int = Field(ge=1)
    text: str
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)
    paragraph_index: int = 0

    @field_validator("end_offset")
    @classmethod
    def _end_after_start(cls, v: int, info: Any) -> int:
        start = info.data.get("start_offset", 0)
        if v < start:
            raise ValueError("end_offset must be >= start_offset")
        return v


class Claim(BaseModel):
    """One atomic statement, always tied to a validated source span.

    The ``*_normalized`` fields are comparable keys derived from the raw wording;
    the raw fields are what the reviewer sees, so normalisation never hides the
    original text.
    """

    id: str
    document_id: str
    subject: str = "unknown"
    predicate: str = "unknown"
    value: str = "unknown"
    unit: str = "unknown"
    scope: str = "unknown"
    effective_date: str = "unknown"
    source_passage_id: str
    #: Defaults of 0 mean "no validated span"; such a claim is also marked
    #: UNRESOLVED so it can never be presented as cited evidence.
    quote_start: int = Field(default=0, ge=0)
    quote_end: int = Field(default=0, ge=0)
    quote: str = ""
    extraction_status: ExtractionStatus = ExtractionStatus.OK
    notes: str = ""
    subject_normalized: str = ""
    predicate_normalized: str = ""
    value_normalized: str = ""
    unit_normalized: str = ""
    origin: str = "apertus"


class Citation(BaseModel):
    """A span that was resolved against canonical extracted text."""

    passage_id: str
    document_id: str
    page: int
    start_offset: int
    end_offset: int
    quote: str
    resolved: bool = True
    reason: str = ""


class ProviderRun(BaseModel):
    id: str
    provider: str
    model: str
    mode: str
    input_hash: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    latency_ms: int | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    status: str = "ok"
    error_class: str = ""
    error_message: str = ""
    http_status: int | None = None
    validation_errors: list[str] = Field(default_factory=list)
    downgraded_from: str = ""
    is_backup: bool = False


class Finding(BaseModel):
    id: str
    analysis_id: str
    claim_ids: list[str]
    relation: Relation
    explanation: str
    evidence: list[Citation] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    review_status: Literal["pending", "confirmed_for_review", "dismissed"] = "pending"
    review_note: str = ""
    provider_run_id: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class ReviewEvent(BaseModel):
    id: str
    finding_id: str
    status: Literal["pending", "confirmed_for_review", "dismissed"]
    note: str = ""
    reviewer: str = "local reviewer"
    created_at: datetime = Field(default_factory=utcnow)


class AnalysisStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class Analysis(BaseModel):
    id: str
    idempotency_key: str
    document_ids: list[str]
    status: AnalysisStatus = AnalysisStatus.QUEUED
    provider: str = ""
    model: str = ""
    prompt_version: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    findings: list[Finding] = Field(default_factory=list)
    claim_count: int = 0
    pair_count: int = 0
    candidate_coverage: dict[str, Any] = Field(default_factory=dict)
    provider_runs: list[ProviderRun] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    extract_only: bool = False


class ReviewRequest(BaseModel):
    status: Literal["pending", "confirmed_for_review", "dismissed"]
    note: str = ""
    reviewer: str = "local reviewer"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def short_hash(data: bytes) -> str:
    return sha256_bytes(data)[:16]
