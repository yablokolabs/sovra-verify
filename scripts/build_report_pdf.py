#!/usr/bin/env python3
"""Build `track_2b/technical_report.pdf` from the technical report markdown.

The submission template caps the technical report at six pages excluding
references, and this repository forbids footers of any kind — including a running
page-number block. Both are checked here against the produced PDF rather than
assumed from the renderer's settings.

Pipeline: markdown -> HTML with print CSS -> Chromium PDF (Playwright). The body
and the reference list are rendered separately so the page budget can be measured
on the body alone, then joined with a forced page break.

Requirements: `markdown` and `pypdf` in the active interpreter, and Playwright
with a Chromium build. Playwright is installed by the demo-video project, so the
renderer is invoked with NODE_PATH pointing at `videos/node_modules`.

Nothing here reads a credential. The only inputs are the markdown file and the
rendered HTML.

Exit status is 0 only when the PDF was produced and every check passed.
"""

from __future__ import annotations

import argparse
import html as html_mod
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pdf_text  # noqa: E402  (sibling module, resolved after sys.path fix)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = REPO_ROOT / "track_2b" / "technical_report.md"
DEFAULT_OUTPUT = REPO_ROOT / "track_2b" / "technical_report.pdf"
RENDERER = REPO_ROOT / "scripts" / "render_pdf.cjs"
VIDEO_NODE_MODULES = REPO_ROOT / "videos" / "node_modules"

MAX_BODY_PAGES = 6
A4_HEIGHT_PT = 841.89
# The print CSS sets an 18mm bottom margin = 51.0pt, so the body column occupies
# y >= 51pt. Anything drawn below that is outside the body box, which is exactly
# where a running footer, page number, title, URL or attribution would sit.
BODY_BOTTOM_PT = 51.0
# Allow a fraction of a point for the renderer's own rounding.
FOOTER_BAND_PT = BODY_BOTTOM_PT - 1.0

REFERENCES_HEADING = re.compile(r"^##\s+References\s*$", re.MULTILINE)

PRINT_CSS = """
@page { size: A4; margin: 18mm 19mm 18mm 19mm; }
html { font-size: 10.4pt; }
body {
  margin: 0;
  font-family: Georgia, "Times New Roman", "DejaVu Serif", serif;
  line-height: 1.38;
  color: #14181d;
  hyphens: none;
}
h1 {
  font-family: "Helvetica Neue", Helvetica, Arial, "DejaVu Sans", sans-serif;
  font-size: 1.62rem;
  line-height: 1.22;
  margin: 0 0 0.45rem 0;
  letter-spacing: -0.01em;
}
h2 {
  font-family: "Helvetica Neue", Helvetica, Arial, "DejaVu Sans", sans-serif;
  font-size: 1.1rem;
  line-height: 1.3;
  margin: 1.25rem 0 0.4rem 0;
  padding-top: 0.35rem;
  border-top: 0.6pt solid #c9ced6;
  break-after: avoid;
}
h3 { font-size: 1rem; margin: 0.9rem 0 0.3rem 0; break-after: avoid; }
p { margin: 0 0 0.5rem 0; text-align: left; }
ul, ol { margin: 0 0 0.55rem 0; padding-left: 1.15rem; }
li { margin-bottom: 0.22rem; }
strong { font-weight: 700; }
em { font-style: italic; }
hr { border: 0; border-top: 0.6pt solid #c9ced6; margin: 0.7rem 0; }
a { color: #14181d; text-decoration: none; }
code, pre {
  font-family: "DejaVu Sans Mono", ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 0.86em;
}
code { background: #f0f1f3; padding: 0 0.15em; }
pre {
  background: #f6f7f8;
  border-left: 1.5pt solid #c9ced6;
  padding: 0.4rem 0.55rem;
  margin: 0 0 0.5rem 0;
  white-space: pre-wrap;
}
pre code { background: none; padding: 0; }
table {
  border-collapse: collapse;
  width: 100%;
  margin: 0.35rem 0 0.65rem 0;
  font-size: 0.94em;
  break-inside: avoid;
}
th, td { border-bottom: 0.5pt solid #d5d9de; padding: 0.22rem 0.4rem; text-align: left; }
th { border-bottom: 0.9pt solid #9aa2ad; font-weight: 700; }
td:not(:first-child), th:not(:first-child) { text-align: right; }
#references-break { break-before: page; }
"""

HTML_SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Sovra Verify technical report</title>
<style>{css}</style>
</head>
<body>
{body}
</body>
</html>
"""


def require(module: str, hint: str):
    try:
        return __import__(module)
    except ImportError:
        print(f"missing python package `{module}` in {sys.executable}", file=sys.stderr)
        print(f"  fix: {sys.executable} -m pip install {hint}", file=sys.stderr)
        return None


def to_html(markdown_text: str, md_module) -> str:
    return md_module.markdown(
        markdown_text,
        extensions=["tables", "fenced_code", "sane_lists", "attr_list"],
        output_format="html5",
    )


def render(html_text: str, out_pdf: Path) -> None:
    """Render HTML to PDF through Chromium. Raises RuntimeError on failure."""
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("node is not on PATH; the PDF renderer needs Chromium via Playwright")
    if not VIDEO_NODE_MODULES.is_dir():
        raise RuntimeError(f"playwright not installed at {VIDEO_NODE_MODULES}")

    env = dict(os.environ)
    # `require('playwright')` in the renderer resolves through NODE_PATH, so the
    # renderer can live in scripts/ while the browser libraries live in videos/.
    env["NODE_PATH"] = str(VIDEO_NODE_MODULES)

    with tempfile.TemporaryDirectory() as tmp:
        html_path = Path(tmp) / "report.html"
        html_path.write_text(html_text, encoding="utf-8")
        proc = subprocess.run(
            [node, str(RENDERER), str(html_path), str(out_pdf)],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
        )
    if proc.returncode != 0 or not out_pdf.exists():
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        raise RuntimeError("pdf render failed: " + (" | ".join(detail[-3:]) or "no output"))


def page_count(pdf: Path, pypdf_module) -> int:
    return pdf_text.page_count(pdf)


def footer_band_text(pdf: Path, pypdf_module) -> tuple[list[tuple[int, str]], list[tuple[int, float]]]:
    """Find text outside the body box.

    Returns the offending fragments and, for evidence, the lowest text position
    on each page. A running footer or page-number block is exactly this: text
    placed below the body column, in the bottom margin.
    """
    by_page: dict[int, list[tuple[float, float, str]]] = {}
    for number, x, y, text in pdf_text.iter_pdf_fragments(pdf):
        by_page.setdefault(number, []).append((x, y, text))

    hits: list[tuple[int, str]] = []
    lowest: list[tuple[int, float]] = []
    for number in sorted(by_page):
        fragments = by_page[number]
        lowest.append((number, min(y for _x, y, _t in fragments)))
        for _x, y, stripped in fragments:
            if y < FOOTER_BAND_PT:
                hits.append((number, stripped))
    return hits, lowest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the technical report PDF.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-body-pages", type=int, default=MAX_BODY_PAGES)
    args = parser.parse_args(argv)

    md_module = require("markdown", "markdown")
    pypdf_module = require("pypdf", "pypdf")
    if md_module is None or pypdf_module is None:
        return 2

    source: Path = args.source
    output: Path = args.output
    if not source.is_file():
        print(f"source markdown not found: {source}", file=sys.stderr)
        return 2

    text = source.read_text(encoding="utf-8")
    split = REFERENCES_HEADING.search(text)
    if split is None:
        print("no `## References` heading found; cannot measure the body alone", file=sys.stderr)
        return 2

    body_md = text[: split.start()].rstrip()
    refs_md = text[split.start():].strip()

    body_html = to_html(body_md, md_module)
    refs_html = to_html(refs_md, md_module)

    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        body_pdf = Path(tmp) / "body.pdf"
        render(HTML_SHELL.format(css=PRINT_CSS, body=body_html), body_pdf)
        body_pages = page_count(body_pdf, pypdf_module)

    print(f"body-only page count: {body_pages} (limit {args.max_body_pages}, references excluded)")
    if body_pages > args.max_body_pages:
        print(
            f"FAIL: the body needs {body_pages} pages, over the {args.max_body_pages}-page limit",
            file=sys.stderr,
        )
        return 1

    full_html = HTML_SHELL.format(
        css=PRINT_CSS,
        body=body_html + '\n<div id="references-break"></div>\n' + refs_html,
    )
    render(full_html, output)

    total = page_count(output, pypdf_module)
    reader = pypdf_module.PdfReader(str(output))
    refs_page = None
    for number, page in enumerate(reader.pages, start=1):
        first = (page.extract_text() or "").strip().splitlines()
        if any(line.strip() == "References" for line in first[:3]):
            refs_page = number
            break

    hits, lowest = footer_band_text(output, pypdf_module)

    print(f"wrote {output.relative_to(REPO_ROOT)}")
    print(f"total pages: {total}")
    print(f"references start on page: {refs_page if refs_page else 'not found'}")
    print(
        f"body column occupies y >= {BODY_BOTTOM_PT:.0f}pt; "
        f"footer band is y < {FOOTER_BAND_PT:.0f}pt"
    )
    print("lowest text position per page:")
    for number, y in lowest:
        print(f"  page {number}: y = {y:.1f}pt")
    print(f"text fragments in the footer band: {len(hits)}")
    for number, fragment in hits[:10]:
        print(f"  page {number}: {html_mod.escape(fragment[:60])!r}")

    ok = True
    for name, passed, detail in (
        ("body within page limit", body_pages <= args.max_body_pages, f"{body_pages} pages"),
        ("references on their own page", refs_page is not None, str(refs_page)),
        ("no footer text on any page", not hits, f"{len(hits)} fragments"),
    ):
        print(f"{'PASS' if passed else 'FAIL'}  {name}: {detail}")
        ok = ok and passed

    if not ok:
        return 1

    print("no page carries a running footer, page number, title, URL or attribution")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
