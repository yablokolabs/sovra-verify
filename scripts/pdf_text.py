#!/usr/bin/env python3
"""Read text fragments and their page positions out of a PDF.

Shared by `build_report_pdf.py` and `check_no_footer.py` so that both measure the
same page geometry. Positions are in PDF points measured from the page's
bottom-left corner, which is the space the print CSS margins are expressed in.

Why this is not just `page.extract_text()`: the text matrix handed to pypdf's
visitor is relative to the current graphics transform, so `tm[5]` on its own is
not a page coordinate. Chromium writes the report with a `cm` of
`(0.75, 0, 0, 0.75, 0, 790.9)`, so a page title has `tm[5] == 21` yet is drawn at
`y == 806.6` — near the top of the page. Reading `tm[5]` alone would report every
fragment as a footer. The absolute position is the product of the two matrices.

Requires `pypdf`.
"""

from __future__ import annotations

from pathlib import Path

#: A4 height in PDF points. Used to sanity-check measured positions.
A4_HEIGHT_PT = 841.89


def _require_pypdf():
    try:
        import pypdf  # noqa: F401
    except ImportError:
        return None
    return pypdf


def pypdf_available() -> bool:
    return _require_pypdf() is not None


def page_count(pdf: Path) -> int:
    pypdf = _require_pypdf()
    if pypdf is None:
        raise RuntimeError("pypdf is not installed")
    return len(pypdf.PdfReader(str(pdf)).pages)


def text_positions_on_page(page) -> list[tuple[float, float, str]]:
    """Return ``(x, y, text)`` for every non-empty fragment on one page."""
    fragments: list[tuple[float, float, str]] = []

    def visit(text, cm, tm, font_dict, font_size):  # pypdf visitor signature
        stripped = (text or "").strip()
        if not stripped:
            return
        cm = tuple(cm) if cm else (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        tm = tuple(tm) if tm else (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        x = cm[0] * tm[4] + cm[2] * tm[5] + cm[4]
        y = cm[1] * tm[4] + cm[3] * tm[5] + cm[5]
        fragments.append((float(x), float(y), stripped))

    try:
        page.extract_text(visitor_text=visit)
    except Exception as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"could not read text positions: {exc}")
    return fragments


def iter_pdf_fragments(pdf: Path):
    """Yield ``(page_number, x, y, text)`` over every page of a PDF."""
    pypdf = _require_pypdf()
    if pypdf is None:
        raise RuntimeError("pypdf is not installed")
    reader = pypdf.PdfReader(str(pdf))
    for number, page in enumerate(reader.pages, start=1):
        for x, y, text in text_positions_on_page(page):
            yield number, x, y, text


def page_texts(pdf: Path) -> list[str]:
    """Return the plain extracted text of each page, in page order."""
    pypdf = _require_pypdf()
    if pypdf is None:
        raise RuntimeError("pypdf is not installed")
    reader = pypdf.PdfReader(str(pdf))
    return [(page.extract_text() or "") for page in reader.pages]
