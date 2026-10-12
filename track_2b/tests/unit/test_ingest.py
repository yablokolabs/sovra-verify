"""Ingestion tests: hostile paths, size/type limits, offsets and page provenance."""

from __future__ import annotations

import pytest

from sovra.ingest import (
    IngestError,
    extract_document,
    page_for_offset,
    safe_display_name,
    validate_upload,
)
from sovra.models import ExtractionStatus

SAMPLE = (
    "Clause 7.2 Payment terms\n"
    "The Buyer shall pay each undisputed invoice within 30 days of the invoice date.\n"
    "\n"
    "Clause 9.3 Currency\n"
    "All amounts are stated in Swiss francs (CHF).\n"
)


# -- hostile filenames ------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd", "passwd"),
        ("/absolute/path/../secret.txt", "secret.txt"),
        ("..\\..\\windows\\system32\\evil.txt", "evil.txt"),
        ("dir/subdir/doc.txt", "doc.txt"),
        ("", "document"),
        ("weird<>:name?.txt", "weird_name_.txt"),
    ],
)
def test_safe_display_name_strips_paths(raw: str, expected: str) -> None:
    name = safe_display_name(raw)
    assert "/" not in name and "\\" not in name
    assert ".." not in name
    assert name == expected


def test_extract_never_uses_the_supplied_path_as_a_name(settings) -> None:
    ingested = extract_document(
        display_name="../../etc/hosts.txt",
        data=b"Payment within 30 days.\n",
        mime="text/plain",
        settings=settings,
    )
    assert ingested.document.name == "hosts.txt"
    assert ingested.document.name == safe_display_name("../../etc/hosts.txt")


# -- upload validation -----------------------------------------------------
def test_validate_upload_rejects_empty_file(settings) -> None:
    with pytest.raises(IngestError) as excinfo:
        validate_upload("empty.txt", b"", settings)
    assert excinfo.value.reason == "empty_file"


def test_validate_upload_rejects_oversized_file(make_settings) -> None:
    tiny_limit = make_settings(max_upload_bytes=16)
    with pytest.raises(IngestError) as excinfo:
        validate_upload("big.txt", b"x" * 64, tiny_limit)
    assert excinfo.value.reason == "too_large"


def test_validate_upload_rejects_unsupported_extension(settings) -> None:
    with pytest.raises(IngestError) as excinfo:
        validate_upload("notes.docx", b"payload", settings)
    assert excinfo.value.reason == "unsupported_type"


def test_validate_upload_rejects_extensionless_file(settings) -> None:
    with pytest.raises(IngestError) as excinfo:
        validate_upload("noextension", b"payload", settings)
    assert excinfo.value.reason == "unsupported_type"


def test_validate_upload_accepts_text(settings) -> None:
    validate_upload("ok.txt", b"hello", settings)


# -- extraction ------------------------------------------------------------
def test_extract_text_offsets_slice_back_to_passage_text(settings) -> None:
    ingested = extract_document(
        display_name="agreement.txt", data=SAMPLE.encode("utf-8"), mime="text/plain", settings=settings
    )
    assert ingested.passages, "expected at least one passage"
    for passage in ingested.passages:
        assert ingested.canonical_text[passage.start_offset : passage.end_offset] == passage.text
    assert ingested.document.extraction_status is ExtractionStatus.OK
    assert ingested.document.page_count == 1
    assert len(ingested.document.sha256) == 64


def test_extract_is_deterministic_for_identical_bytes(settings) -> None:
    first = extract_document(display_name="a.txt", data=SAMPLE.encode(), mime="text/plain", settings=settings)
    second = extract_document(display_name="b.txt", data=SAMPLE.encode(), mime="text/plain", settings=settings)
    assert first.canonical_text == second.canonical_text
    assert first.document.sha256 == second.document.sha256
    assert first.document.id != second.document.id


def test_extract_reports_truncation_instead_of_silence(make_settings) -> None:
    capped = make_settings(max_extracted_chars=40)
    ingested = extract_document(
        display_name="long.txt", data=(SAMPLE * 5).encode(), mime="text/plain", settings=capped
    )
    assert ingested.document.extraction_status is ExtractionStatus.TRUNCATED
    assert any("truncat" in note.lower() for note in ingested.document.extraction_notes)
    assert len(ingested.canonical_text) == 40


def test_extract_reports_whitespace_only_file_as_failed(settings) -> None:
    ingested = extract_document(
        display_name="blank.txt", data=b"   \n  \n", mime="text/plain", settings=settings
    )
    assert ingested.document.extraction_status is ExtractionStatus.FAILED
    assert ingested.passages == []


def test_page_for_offset_maps_to_one_based_pages() -> None:
    page_offsets = [0, 50, 120]
    assert page_for_offset(page_offsets, 0) == 1
    assert page_for_offset(page_offsets, 49) == 1
    assert page_for_offset(page_offsets, 50) == 2
    assert page_for_offset(page_offsets, 119) == 2
    assert page_for_offset(page_offsets, 200) == 3


# -- PDF handling ----------------------------------------------------------
def test_encrypted_pdf_is_rejected_with_a_clear_reason(settings) -> None:
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Payment within 30 days of the invoice date.")
    encrypted = doc.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="secret"
    )
    doc.close()
    with pytest.raises(IngestError) as excinfo:
        extract_document(display_name="locked.pdf", data=encrypted, mime="application/pdf", settings=settings)
    assert excinfo.value.reason == "encrypted_pdf"


def test_scanned_pdf_reports_ocr_not_implemented(settings) -> None:
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    doc.new_page()  # page with no text layer
    data = doc.tobytes()
    doc.close()
    ingested = extract_document(
        display_name="scan.pdf", data=data, mime="application/pdf", settings=settings
    )
    assert ingested.document.extraction_status is ExtractionStatus.OCR_NOT_IMPLEMENTED
    assert any("ocr" in note.lower() for note in ingested.document.extraction_notes)


def test_text_native_pdf_extracts_and_keeps_page_provenance(settings) -> None:
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Buyer shall pay within 30 days.")
    doc.new_page().insert_text((72, 72), "Supplier shall pay within 60 days.")
    data = doc.tobytes()
    doc.close()

    ingested = extract_document(
        display_name="agreement.pdf", data=data, mime="application/pdf", settings=settings
    )
    assert ingested.document.page_count == 2
    assert ingested.document.extraction_status is ExtractionStatus.OK
    pages = {passage.page for passage in ingested.passages}
    assert pages == {1, 2}
    for passage in ingested.passages:
        assert ingested.canonical_text[passage.start_offset : passage.end_offset] == passage.text
