#!/usr/bin/env python3
"""Build `track_2b/technical_report_deck.pdf` from the report deck HTML.

This is the print edition of the technical report: six A4 pages authored in the
Frontend Slides skill's "Swiss Modern" design system, kept beside the prose
edition (`track_2b/technical_report.md` -> `technical_report.pdf`) rather than
replacing it.

The submission template caps the technical report at six pages, and this
repository forbids footers of any kind, including a running page-number block.
Both are measured on the produced PDF here instead of being assumed from the
renderer's settings, and both are measured where the artifact's own geometry
matters:

* page count            the deck is authored as six pages. A page whose content
                        overruns is not clipped — the page box has no hidden
                        overflow — it becomes a seventh page, which fails.
* text layer            every page must carry selectable text. A page rendered
                        as an image would pass a visual review and defeat both
                        this check and the footer scan, so it is refused.
* content on the page   each authored section's closing words must be found on
                        the page that section produced. This is the check that
                        catches a paragraph pushed off the bottom or clipped: a
                        lost tail is invisible in a page count and in a text
                        layer, and it is the failure this deck's flow layout
                        exists to make impossible.
* bottom band           no text fragment may sit below the authored 18mm bottom
                        margin, which is where a footer, page number, title, URL
                        or attribution would have to be drawn.
* footer markers        the same marker list `make no-footer` uses is applied to
                        every fragment.
* fonts                 the deck asks for Archivo and Nunito by name. A font
                        that fails to load does not fail a Chromium render — it
                        substitutes a system face and the page still looks
                        finished — so the loaded faces are checked in the
                        rendered document and the PDF is read back for the
                        fingerprint of a substitution: Chromium writes the
                        embedded variable faces as unnamed Type3 glyph programs
                        and only a substituted face gets a real system name, so
                        a system sans name in the PDF is the fallback signature.

Pipeline: HTML -> Chromium PDF (Playwright), reusing `scripts/render_pdf.cjs`
exactly as the prose report does. Nothing here reads a credential.

Exit status is 0 only when the PDF was produced and every check passed.
"""

from __future__ import annotations

import argparse
import html as html_mod
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import build_report_pdf  # noqa: E402  (sibling module: the shared HTML->PDF render)
import check_no_footer  # noqa: E402  (the marker list and its scan function)
import pdf_text  # noqa: E402

REPO_ROOT = SCRIPTS.parent
DEFAULT_SOURCE = REPO_ROOT / "track_2b" / "technical_report_deck.html"
DEFAULT_OUTPUT = REPO_ROOT / "track_2b" / "technical_report_deck.pdf"

#: The deck is authored as exactly six pages; the submission cap is six.
MAX_PAGES = 6
EXPECTED_PAGES = 6

#: The deck's print CSS leaves an 18mm bottom margin (51.02pt), so every text
#: fragment is drawn at or above that line. A fragment below it is outside the
#: body box, which is precisely where a footer would sit.
BODY_BOTTOM_PT = 51.0
FOOTER_BAND_PT = BODY_BOTTOM_PT - 1.0

#: Font families the deck asks for by name, as CSS spells them. These must be
#: registered and loaded in the rendered document.
REQUIRED_FONTS = ("Archivo", "Nunito")

#: Faces Chromium picks when a font is missing. The deck's own faces are embedded
#: and therefore unnamed in the PDF, so any of these names appearing is a
#: substitution. The monospace members are excluded: the deck's inline code is
#: deliberately set in the system monospace face, and that one is expected.
SUBSTITUTE_FACES = (
    "dejavusans",
    "dejavuserif",
    "liberationsans",
    "liberationserif",
    "arial",
    "helvetica",
    "nimbussans",
    "notosans",
    "notoserif",
    "freesans",
    "freeserif",
    "calibri",
    "carlito",
    "verdana",
    "tahoma",
)


def substitutions(fonts: set[str]) -> list[str]:
    """Return the embedded names that look like a fallback rather than the deck's own face."""
    found: list[str] = []
    for font in fonts:
        lowered = font.lower()
        if "mono" in lowered:
            continue
        if any(marker in lowered for marker in SUBSTITUTE_FACES):
            found.append(font)
    return sorted(found)


def section_texts(source_html: str) -> list[str]:
    """Return the visible text of each authored page section, in order."""
    body = source_html.split("</style>", 1)[-1]
    sections = re.findall(r'<section class="page">(.*?)</section>', body, re.S)
    texts: list[str] = []
    for fragment in sections:
        without_tags = re.sub(r"<[^>]+>", " ", fragment)
        texts.append(re.sub(r"\s+", " ", html_mod.unescape(without_tags)).strip())
    return texts


def comparable(text: str) -> str:
    """Reduce text to lowercase words for comparison.

    The deck runs its small labels through letter-spacing, which makes the glyph
    stream Chromium writes disagree with the source's own word shapes, so the
    comparison is made on letters and digits only.
    """
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def pages_missing_their_tail(authored: list[str], pages: list[str], words: int = 12) -> list[int]:
    """Return the page numbers whose section does not close on that page."""
    missing: list[int] = []
    for number, (fragment, page_text) in enumerate(zip(authored, pages), start=1):
        tokens = comparable(fragment).split()
        if not tokens:
            continue
        if " ".join(tokens[-words:]) not in comparable(page_text):
            missing.append(number)
    return missing


def require_pypdf():
    if not pdf_text.pypdf_available():
        raise SystemExit(
            "[report-deck] pypdf is not installed in this interpreter. "
            "Install it (`pip install pypdf`) to build and check the deck."
        )
    import pypdf

    return pypdf


def font_inventory(pdf: Path) -> list[tuple[str, str]]:
    """Return ``(subtype, base name)`` for every font the document uses.

    Chromium writes each font dictionary inline inside a page's ``/Resources``
    rather than as its own indirect object, so pypdf's resolved-object table finds
    none of them and the page tree is the only place the fonts exist. Every page
    is visited, including the inherited resources, so a font used on a single page
    is still accounted for.
    """
    pypdf = require_pypdf()
    reader = pypdf.PdfReader(str(pdf))
    inventory: list[tuple[str, str]] = []

    def collect(resources) -> None:
        resources = resources.get_object() if hasattr(resources, "get_object") else resources
        if not hasattr(resources, "get"):
            return
        fonts = resources.get("/Font")
        fonts = fonts.get_object() if hasattr(fonts, "get_object") else fonts
        if not hasattr(fonts, "items"):
            return
        for _key, reference in dict(fonts).items():
            font = reference.get_object() if hasattr(reference, "get_object") else reference
            if not hasattr(font, "get"):
                continue
            subtype = str(font.get("/Subtype") or "")
            base = font.get("/BaseFont")
            inventory.append((subtype, str(base).lstrip("/") if base else ""))

    for page in reader.pages:
        collect(page.get("/Resources"))
    return inventory


def embedded_fonts(pdf: Path) -> set[str]:
    """Return every base font name the PDF records."""
    return {base for _subtype, base in font_inventory(pdf) if base}


def type3_font_count(pdf: Path) -> int:
    """Count the unnamed Type3 glyph programs Chromium writes for embedded faces."""
    return sum(1 for subtype, _base in font_inventory(pdf) if subtype == "/Type3")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and check the technical report deck PDF.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    if not args.source.is_file():
        print(f"[report-deck] FAIL: source not found at {args.source}", file=sys.stderr)
        return 1

    require_pypdf()
    html_text = args.source.read_text(encoding="utf-8")

    try:
        build_report_pdf.render(html_text, args.output, expect_fonts=REQUIRED_FONTS)
    except RuntimeError as exc:
        print(f"[report-deck] FAIL: {exc}", file=sys.stderr)
        return 1

    size_kib = args.output.stat().st_size / 1024
    # --output may point outside the repository (a check copy, a staging path), in
    # which case there is no meaningful repository-relative name to print.
    try:
        shown = args.output.resolve().relative_to(REPO_ROOT)
    except ValueError:
        shown = args.output
    print(f"[report-deck] rendered {shown} ({size_kib:.0f} KiB)")

    failures: list[str] = []

    pages = pdf_text.page_count(args.output)
    if pages > MAX_PAGES:
        failures.append(
            f"{pages} pages: over the {MAX_PAGES}-page cap. A page whose content "
            f"overran was pushed onto a new page rather than clipped — split or shorten it."
        )
    elif pages != EXPECTED_PAGES:
        failures.append(f"{pages} pages: the deck is authored as {EXPECTED_PAGES}.")
    else:
        print(f"[report-deck] PASS  page count: {pages} of {MAX_PAGES}")

    texts = pdf_text.page_texts(args.output)
    empty = [number for number, text in enumerate(texts, start=1) if len(text.strip()) < 200]
    if empty:
        failures.append(f"page(s) {empty} carry almost no text layer; every page must be selectable text")
    else:
        counts = ", ".join(str(len(text.split())) for text in texts)
        print(f"[report-deck] PASS  text layer on every page (words per page: {counts})")
        # Which section each page opens with: this is what shows that a page is a
        # real section rather than the tail of the one before it.
        for number, text in enumerate(texts, start=1):
            opening = " ".join(text.split())[:68]
            print(f"[report-deck]       page {number} opens: {opening}")

    authored = section_texts(html_text)
    if len(authored) != pages:
        failures.append(
            f"the source authors {len(authored)} page section(s) but the PDF has {pages} page(s)"
        )
    else:
        missing_tail = pages_missing_their_tail(authored, texts)
        if missing_tail:
            failures.append(
                f"page(s) {missing_tail}: the section's closing words are not on that page, so text "
                f"was pushed off the bottom or clipped instead of flowing onto a seventh page"
            )
        else:
            print(
                f"[report-deck] PASS  every section closes on its own page "
                f"({len(authored)} sections, closing words found on each)"
            )

    by_page: dict[int, list[tuple[float, float, str]]] = {}
    for number, x, y, fragment in pdf_text.iter_pdf_fragments(args.output):
        by_page.setdefault(number, []).append((x, y, fragment))

    lowest: list[tuple[int, float]] = []
    band_hits: list[tuple[int, float, str]] = []
    marker_hits: list[str] = []
    for number in sorted(by_page):
        fragments = by_page[number]
        lowest.append((number, min(y for _x, y, _t in fragments)))
        for _x, y, fragment in fragments:
            if y < FOOTER_BAND_PT:
                band_hits.append((number, y, fragment))
            # Case-insensitive: a rendered page is output, and output never gets
            # to spell an attribution in lower case to slip past the check.
            for finding in check_no_footer.scan_text(
                fragment, f"deck page {number}", case_insensitive=True
            ):
                marker_hits.append(finding.render().strip())

    if band_hits:
        for number, y, fragment in band_hits:
            failures.append(f"page {number}: text at y={y:.1f}pt, below the body column: {fragment[:60]!r}")
    else:
        floors = ", ".join(f"p{n} {y:.0f}pt" for n, y in lowest)
        print(f"[report-deck] PASS  no text below the body column (lowest fragment per page: {floors})")

    if marker_hits:
        failures.extend(marker_hits)
    else:
        print("[report-deck] PASS  no footer, attribution or copyright marker on any page")

    fonts = embedded_fonts(args.output)
    substituted = substitutions(fonts)
    if substituted:
        failures.append(
            f"the PDF names a substitute face {substituted}, so the deck's own fonts did not "
            f"reach the page. Named fonts: {sorted(fonts) or 'none'}"
        )
    else:
        traced = type3_font_count(args.output)
        if traced < 1:
            failures.append(
                "the PDF contains no unnamed glyph programs, which is how Chromium embeds the "
                "deck's fonts; the page was drawn in a named system face instead"
            )
        else:
            named = ", ".join(sorted(fonts)) or "none"
            print(
                f"[report-deck] PASS  no substitute face in the PDF; {traced} embedded "
                f"face(s) drawn as unnamed glyph programs (named fonts, expected mono only: {named})"
            )

    if failures:
        print("[report-deck] FAIL")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print(
        "[report-deck] PASS: six pages, selectable text, no footer anywhere, "
        "Archivo and Nunito loaded and no substitute face in the PDF"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
