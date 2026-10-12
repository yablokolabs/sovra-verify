"""Document ingestion.

Untrusted input rules: filenames are never used as paths, documents are stored
under random internal names, MIME and size are checked, and encrypted or
unreadable files are rejected with an explicit reason. Scanned PDFs report
"OCR not implemented" instead of silently producing empty evidence.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .models import (
    EXTRACTION_VERSION,
    Document,
    ExtractionStatus,
    Passage,
    sha256_bytes,
)

TEXT_SUFFIXES = {".txt", ".md"}
PDF_SUFFIXES = {".pdf"}
SUPPORTED_MIME = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/x-markdown",
    "application/octet-stream",
}


class IngestError(Exception):
    """A rejected upload, with a message that is safe to show a user."""

    def __init__(self, message: str, *, reason: str = "rejected"):
        super().__init__(message)
        self.reason = reason


@dataclass(slots=True)
class IngestedDocument:
    document: Document
    passages: list[Passage]
    canonical_text: str
    #: canonical offset of each page's first character (page 1 starts at 0)
    page_offsets: list[int]


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ ()\-]+")


def safe_display_name(raw: str) -> str:
    """A display-only name: strips directory components and control characters."""
    name = Path(raw.replace("\\", "/")).name
    name = _SAFE_NAME.sub("_", name).strip() or "document"
    return name[:120]


def validate_upload(candidate: str, data: bytes, settings: Settings) -> None:
    if not candidate:
        raise IngestError("a filename is required", reason="missing_filename")
    if not data:
        raise IngestError(f"'{safe_display_name(candidate)}' is empty", reason="empty_file")
    if len(data) > settings.max_upload_bytes:
        raise IngestError(
            f"'{safe_display_name(candidate)}' is {len(data)} bytes which exceeds the "
            f"{settings.max_upload_bytes} byte limit",
            reason="too_large",
        )
    suffix = Path(candidate).suffix.lower()
    if suffix not in PDF_SUFFIXES | TEXT_SUFFIXES:
        raise IngestError(
            f"'{safe_display_name(candidate)}' has an unsupported type '{suffix or 'none'}'; "
            "this prototype supports text-native PDF and UTF-8 TXT only",
            reason="unsupported_type",
        )


def extract_document(
    *,
    display_name: str,
    data: bytes,
    mime: str,
    settings: Settings,
) -> IngestedDocument:
    """Extract canonical text and paragraph passages, with page provenance."""
    validate_upload(display_name, data, settings)

    name = safe_display_name(display_name)
    suffix = Path(name).suffix.lower()
    document_id = uuid.uuid4().hex[:16]
    notes: list[str] = []
    status = ExtractionStatus.OK

    if suffix in PDF_SUFFIXES:
        pages, page_notes, status = _extract_pdf(data, name)
        notes.extend(page_notes)
    else:
        pages = [_decode_text(data)]
        if pages[0] is None:
            raise IngestError(
                f"'{name}' is not valid UTF-8 text; convert it to UTF-8 TXT or supply a PDF",
                reason="not_utf8",
            )
        pages = [pages[0]]

    canonical_parts: list[str] = []
    page_offsets: list[int] = []
    cursor = 0
    for page_text in pages:
        page_offsets.append(cursor)
        canonical_parts.append(page_text)
        cursor += len(page_text) + 1  # the '\n' joining pages
    canonical_text = "\n".join(canonical_parts)

    if len(canonical_text) > settings.max_extracted_chars:
        canonical_text = canonical_text[: settings.max_extracted_chars]
        notes.append(
            f"extracted text truncated at {settings.max_extracted_chars} characters; "
            "findings beyond that point were not evaluated"
        )
        status = ExtractionStatus.TRUNCATED

    if not canonical_text.strip():
        if suffix in PDF_SUFFIXES:
            notes.append(
                "no text layer found: this looks like a scanned PDF and OCR is not implemented"
            )
            status = ExtractionStatus.OCR_NOT_IMPLEMENTED
        else:
            notes.append("the file contains no readable text")
            status = ExtractionStatus.FAILED

    passages = _paragraph_passages(document_id, canonical_text, page_offsets)

    document = Document(
        id=document_id,
        name=name,
        sha256=sha256_bytes(data),
        mime=mime or "application/octet-stream",
        size_bytes=len(data),
        extraction_version=EXTRACTION_VERSION,
        page_count=len(pages),
        extraction_status=status,
        extraction_notes=notes,
        stored_name="",
    )
    return IngestedDocument(
        document=document, passages=passages, canonical_text=canonical_text, page_offsets=page_offsets
    )


def store_original(data: bytes, settings: Settings) -> tuple[str, Path]:
    """Persist the original under a random name; never trust the given path."""
    target_dir = settings.work_dir / "originals"
    target_dir.mkdir(parents=True, exist_ok=True)
    stored = uuid.uuid4().hex
    path = target_dir / stored
    path.write_bytes(data)
    return stored, path


def page_for_offset(page_offsets: list[int], offset: int) -> int:
    """1-based page number for a canonical offset."""
    page = 1
    for index, start in enumerate(page_offsets):
        if offset >= start:
            page = index + 1
        else:
            break
    return page


def _decode_text(data: bytes) -> str | None:
    """Decode UTF-8 (optionally with a BOM).

    There is deliberately no latin-1 fallback: latin-1 decodes any byte sequence,
    which would make the 'not UTF-8' rejection unreachable and silently turn a
    binary or mis-encoded file into mojibake evidence.
    """
    for encoding in ("utf-8", "utf-8-sig"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def _extract_pdf(data: bytes, name: str) -> tuple[list[str], list[str], ExtractionStatus]:
    notes: list[str] = []
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise IngestError(
            "PDF support requires PyMuPDF (pip install pymupdf); reinstall the backend "
            "dependencies or convert the file to UTF-8 TXT",
            reason="missing_pdf_parser",
        ) from None

    try:
        pdf = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        message = str(exc).lower()
        if "encrypt" in message or "password" in message:
            raise IngestError(
                f"'{name}' is password-protected; encrypted PDFs are rejected",
                reason="encrypted_pdf",
            ) from None
        raise IngestError(f"'{name}' could not be opened as a PDF", reason="unreadable_pdf") from None

    try:
        if pdf.needs_pass:
            raise IngestError(
                f"'{name}' is password-protected; encrypted PDFs are rejected",
                reason="encrypted_pdf",
            )
        pages: list[str] = []
        empty_pages = 0
        for page in pdf:
            text = page.get_text("text") or ""
            if not text.strip():
                empty_pages += 1
            pages.append(text)
    finally:
        pdf.close()

    if empty_pages:
        notes.append(
            f"{empty_pages} of {len(pages)} pages had no text layer "
            "(scanned images are not OCR'd in this prototype)"
        )
    status = ExtractionStatus.OK if any(p.strip() for p in pages) else ExtractionStatus.OCR_NOT_IMPLEMENTED
    if any(p.strip() for p in pages) and empty_pages:
        status = ExtractionStatus.OK
    return pages, notes, status


def _paragraph_passages(
    document_id: str, canonical_text: str, page_offsets: list[int]
) -> list[Passage]:
    """Split canonical text into paragraph passages that retain page provenance."""
    passages: list[Passage] = []
    index = 0
    for match in re.finditer(r"[^\n]+(?:\n(?!\s*\n)[^\n]+)*", canonical_text):
        start, end = match.span()
        text = canonical_text[start:end]
        if not text.strip():
            continue
        passages.append(
            Passage(
                id=f"{document_id}-p{index}",
                document_id=document_id,
                page=page_for_offset(page_offsets, start),
                text=text,
                start_offset=start,
                end_offset=end,
                paragraph_index=index,
            )
        )
        index += 1
    if not passages and canonical_text.strip():
        passages.append(
            Passage(
                id=f"{document_id}-p0",
                document_id=document_id,
                page=1,
                text=canonical_text,
                start_offset=0,
                end_offset=len(canonical_text),
                paragraph_index=0,
            )
        )
    return passages
