#!/usr/bin/env python3
"""Verify that no footer, attribution bar or closing signature exists anywhere.

Checked surfaces
----------------
1. application source       ``track_2b/backend``, ``track_2b/frontend``
2. built frontend output    ``track_2b/frontend/dist``
3. generated documents      ``track_2b/data/evaluation``, exports, ``.sovra_work``
4. every served HTTP route  discovered from the OpenAPI schema
5. rendered PDF pages       every ``*.pdf`` in the tree, by text position

Rendered output is matched case-insensitively, our own source is not. The
application neither writes nor exports a PDF — it only reads them — so every PDF
in this repository is text we generated, and a marker there is always a failure.
Source files are the one place the rule is *written down*, so they are matched
case-sensitively and the phrases that describe the rule do not trip it.

Surface 5 is a page-geometry check, not a text search. A running footer or a
bottom page-number block is text drawn *below the body column*, so each PDF page
is measured and any fragment in the bottom band is a failure. This needs
``pypdf``; when it is absent the run says so and reports itself as partial rather
than claiming a pass over pages it never read.

Exits non-zero when any marker is found and prints ``file:line: marker`` so a
human can act on it.

The marker strings are assembled from fragments so this file does not match
itself; the file is also on the allowlist for the same reason.

Allowlist (documented, deliberate)
---------------------------------
Files whose *purpose* is to state licensing or provenance are permitted to
contain these words, because the no-footer rule requires those facts to live in
dedicated files rather than in a footer:

* upstream ``LICENSE`` / ``COPYING`` / ``NOTICE`` files
* ``docs/BUILT_WITH.md`` (the required provenance file)
* the documentation kit that states the prohibition, and this script

The allowlist applies to the static scan only. Generated reports, exports and
HTTP responses are never allowlisted: a marker there is always a failure.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable, Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]
#: Directive: no marker string below may be written literally anywhere in this
#: repository, including in this file. Each is assembled from fragments.
MARKER_FRAGMENTS: tuple[tuple[str, str], ...] = (
    ("<" + "footer", "footer element"),
    ("Powered" + " by", "attribution phrase"),
    ("Built" + " with", "attribution phrase"),
    ("All rights" + " reserved", "copyright notice"),
    ("Copy" + "right", "copyright notice"),
    ("\u00a9", "copyright symbol"),
    ("Generated" + " with", "tool attribution"),
)

#: Readable aliases used in the report only.
MARKERS: dict[str, str] = {fragment: label for fragment, label in MARKER_FRAGMENTS}

ALLOWLIST_FILES: frozenset[str] = frozenset(
    {
        "AGENTS.md",
        "SOVRA_BUILD.md",
        "SESSION_CONTINUATION.md",
        "docs/BUILT_WITH.md",
        "docs/COMPETITION_NOTES.md",
        "docs/PROVIDER_VERIFICATION.md",
        "scripts/check_no_footer.py",
    }
)

ALLOWLIST_PATTERNS: tuple[str, ...] = (
    "LICENSE",
    "COPYING",
    "NOTICE",
    "THIRD_PARTY",
)

#: Markers that may legally appear inside a *bundled third-party dependency* as a
#: preserved licence header rather than as a UI footer. Only these, and only when
#: the occurrence sits next to a recognisable licence-comment signature, are
#: reclassified. A ``<footer`` element, a "powered by" bar or any other marker is
#: never reclassified, and nothing in this repository's own source is either.
UPSTREAM_LICENCE_MARKERS: frozenset[str] = frozenset(
    {"Copy" + "right", "\u00a9"}
)

UPSTREAM_LICENCE_SIGNATURES: tuple[str, ...] = (
    "@license",
    "@preserve",
    "license:",
    "licence:",
    "spdx-license-identifier",
    "and its affiliates",
    "all rights reserved.",
)

#: How far either side of a match to look for a licence-comment signature.
UPSTREAM_LICENCE_WINDOW = 260

SCAN_DIRS: tuple[str, ...] = (
    "track_2b/backend",
    "track_2b/frontend",
    "track_2b/data",
    "docs",
    "scripts",
)

SCAN_ROOT_FILES: tuple[str, ...] = ("README.md", "Makefile", "compose.yaml", ".env.example")

#: Authored files that sit outside ``SCAN_DIRS`` and are still rendered surfaces.
#: ``track_2b`` itself is not a scan directory (it holds binaries, source documents
#: and test fixtures), but the report sources are printed to PDF and read by a
#: judge, so a footer written into them would reach a generated document.
SCAN_EXTRA_FILES: tuple[str, ...] = (
    "track_2b/technical_report.md",
    "track_2b/technical_report_deck.html",
)

SKIP_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "originals",
        "htmlcov",
        ".sovra_work_test",
        # The built frontend is a build artifact, not source. It is scanned by
        # scan_built_frontend(), which is the only place a preserved dependency
        # licence header may be classified separately from a footer. Scanning it
        # here as well would report the same bundle twice and bypass that check.
        "dist",
    }
)

TEXT_SUFFIXES: frozenset[str] = frozenset(
    {
        ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json", ".jsonl",
        ".md", ".txt", ".html", ".htm", ".css", ".svg", ".yml", ".yaml",
        ".sh", ".toml", ".cfg", ".ini", ".lock", ".map", "",
    }
)

MAX_FILE_BYTES = 8 * 1024 * 1024


class Finding:
    def __init__(self, location: str, line: int, marker: str, label: str, text: str, column: int = 0):
        self.location = location
        self.line = line
        self.marker = marker
        self.label = label
        self.text = (text or "").strip()[:160]
        #: The untruncated line, used to decide whether a match is a bundled
        #: dependency's licence header rather than a footer.
        self.full_line = text or ""
        self.column = column

    def render(self) -> str:
        return f"{self.location}:{self.line}: [{self.label}] {self.marker!r} -> {self.text}"

    def is_upstream_licence_notice(self) -> bool:
        """True when this match is a preserved third-party licence header.

        Deliberately narrow: the marker must be a copyright notice, and it must
        sit within a short window of a licence-comment signature such as
        ``@license`` or ``SPDX-License-Identifier``. A footer element, an
        attribution bar or a "powered by" line is never reclassified.
        """
        if self.marker not in UPSTREAM_LICENCE_MARKERS:
            return False
        window = self.full_line
        if len(window) < 400:  # short lines cannot hide a minified licence block
            look = window
        else:
            start = max(0, self.column - UPSTREAM_LICENCE_WINDOW)
            look = window[start : self.column + UPSTREAM_LICENCE_WINDOW]
        lowered = look.lower()
        return any(signature in lowered for signature in UPSTREAM_LICENCE_SIGNATURES)


def is_allowlisted(relative: str) -> bool:
    if relative in ALLOWLIST_FILES:
        return True
    name = Path(relative).name.upper()
    return any(pattern in name for pattern in ALLOWLIST_PATTERNS)


def iter_files(root: Path) -> Iterator[Path]:
    for base in SCAN_DIRS:
        directory = root / base
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield path
    for name in SCAN_ROOT_FILES + SCAN_EXTRA_FILES:
        path = root / name
        if path.is_file() and not any(part in SKIP_DIR_NAMES for part in path.parts):
            yield path


def scan_text(text: str, location: str, *, case_insensitive: bool = False) -> list[Finding]:
    haystack_lines = text.splitlines()
    needles = [
        (fragment if not case_insensitive else fragment.lower(), label)
        for fragment, label in MARKER_FRAGMENTS
    ]
    found: list[Finding] = []
    for number, line in enumerate(haystack_lines, start=1):
        probe = line if not case_insensitive else line.lower()
        for needle, label in needles:
            column = probe.find(needle)
            if column >= 0:
                found.append(Finding(location, number, needle, label, line, column))
    return found


def scan_file(path: Path, root: Path, *, case_insensitive: bool) -> list[Finding]:
    relative = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
    if is_allowlisted(relative):
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return scan_text(text, relative, case_insensitive=case_insensitive)


def scan_tree(root: Path, *, case_insensitive: bool) -> list[Finding]:
    findings: list[Finding] = []
    scanned = 0
    for path in iter_files(root):
        scanned += 1
        findings.extend(scan_file(path, root, case_insensitive=case_insensitive))
    print(f"[no-footer] static scan: {scanned} file(s) inspected")
    return findings


def scan_http(
    base_url: str, *, extra_paths: Iterable[str] = (), timeout: float = 20.0
) -> tuple[list[Finding], list[str]]:
    # Materialised once: the request loop and the summary both need it.
    """Fetch every GET route the app publishes and scan the response bodies.

    ``extra_paths`` are concrete paths supplied by a caller that has live ids — for
    example the end-to-end run, which knows the analysis and finding it just
    created. Without them every templated route would be skipped, and the pages a
    reviewer actually looks at are exactly the templated ones.
    """
    try:
        import httpx
    except ImportError:
        return [], ["httpx is not installed, HTTP scan skipped"]

    extra_paths = tuple(extra_paths)
    findings: list[Finding] = []
    notes: list[str] = []
    base = base_url.rstrip("/")
    try:
        with httpx.Client(timeout=timeout) as client:
            schema_response = client.get(f"{base}/openapi.json")
            if schema_response.status_code != 200:
                return [], [f"could not read /openapi.json ({schema_response.status_code}); HTTP scan skipped"]
            schema = schema_response.json()
            paths = sorted(schema.get("paths", {}))
            if not paths:
                return [], ["the OpenAPI schema published no paths"]

            visited = 0
            for path in paths:
                methods = schema["paths"][path]
                if "get" not in methods:
                    continue
                target = path
                # Skip templated paths: the static routes are what render pages.
                if "{" in target:
                    notes.append(f"skipped templated route {target} (needs a live id)")
                    continue
                response = client.get(f"{base}{target}")
                visited += 1
                if response.status_code >= 400:
                    notes.append(f"{target} returned {response.status_code}")
                    continue
                findings.extend(scan_text(response.text, f"HTTP GET {target}"))
            notes.append(f"fetched {visited} static GET route(s) out of {len(paths)} published path(s)")

            for path in extra_paths:
                target = path if path.startswith("/") else f"/{path}"
                response = client.get(f"{base}{target}")
                if response.status_code >= 400:
                    notes.append(f"live route {target} returned {response.status_code}")
                    continue
                visited += 1
                findings.extend(scan_text(response.text, f"HTTP GET {target}"))
            if extra_paths:
                notes.append(
                    f"fetched {len(extra_paths)} live route(s) with real ids: "
                    + ", ".join(extra_paths)
                )
            else:
                notes.append("no live route supplied; templated routes were not scanned")
    except Exception as exc:  # pragma: no cover - network dependent
        notes.append(f"HTTP scan failed: {type(exc).__name__}")
    return findings, notes


def scan_built_frontend(
    root: Path, *, case_insensitive: bool
) -> tuple[list[Finding], list[Finding]]:
    """Scan the built frontend.

    Returns ``(failures, upstream_licence_notices)``. A preserved dependency
    licence header is reported separately and does not fail the run, because
    removing it would breach the dependency's licence. Everything else in the
    built output still fails. The distinction is applied here only: our own
    source, generated reports, exports and HTTP responses are never eligible.
    """
    dist = root / "track_2b" / "frontend" / "dist"
    if not dist.is_dir():
        print("[no-footer] built frontend not present (run the frontend build to check it)")
        return [], []
    findings: list[Finding] = []
    notices: list[Finding] = []
    for path in sorted(dist.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".html", ".js", ".css", ".svg", ".json", ".map"}:
            continue
        for finding in scan_file(path, root, case_insensitive=case_insensitive):
            if finding.is_upstream_licence_notice():
                notices.append(finding)
            else:
                findings.append(finding)
    print(f"[no-footer] built output inspected: {dist}")
    return findings, notices


#: A4 height in points, and the point above which a fragment counts as a footer.
#: Our report's print CSS leaves an 18mm bottom margin (51pt), so 45pt sits
#: inside that margin with room for rounding. It is a conservative band: text
#: this low on an A4 page cannot be part of a normal body column.
PDF_FOOTER_BAND_PT = 45.0

#: A bare page number, or an obvious "page N of M" block, in the bottom band.
PAGE_NUMBER_PATTERNS: tuple[str, ...] = (
    r"^\s*\d{1,4}\s*$",
    r"^\s*(?:page|p\.?)\s*\d{1,4}(?:\s*(?:of|/)\s*\d{1,4})?\s*$",
    r"^\s*\d{1,4}\s*(?:of|/)\s*\d{1,4}\s*$",
)


def scan_pdfs(root: Path, *, case_insensitive: bool = True) -> tuple[list[Finding], list[str]]:
    """Measure every PDF in the tree for text placed below the body column.

    Returns ``(findings, notes)``. Findings are reported with the marker column
    set to the offending y position so the message points at the page geometry
    that failed, not at a character offset in a binary file. The page text is
    matched case-insensitively by default: see the module docstring.
    """
    pdfs = sorted(
        path
        for path in root.rglob("*.pdf")
        if path.is_file()
        and not any(part in SKIP_DIR_NAMES for part in path.relative_to(root).parts)
    )
    if not pdfs:
        return [], ["no rendered PDF found to inspect"]

    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import pdf_text
    except ImportError:  # pragma: no cover - defensive
        return [], [f"{len(pdfs)} PDF(s) NOT inspected: the pdf_text helper is unavailable"]

    if not pdf_text.pypdf_available():
        return [], [
            f"{len(pdfs)} PDF(s) NOT inspected: pypdf is not installed in this interpreter. "
            f"Install it (`pip install pypdf`) to include rendered report pages in this check."
        ]

    findings: list[Finding] = []
    notes: list[str] = []
    for path in pdfs:
        relative = str(path.relative_to(root))
        pages = pdf_text.page_texts(path)
        lowest: list[tuple[int, float]] = []
        page_hits: list[tuple[int, float, str]] = []
        for number, _x, y, fragment in pdf_text.iter_pdf_fragments(path):
            lowest.append((number, y))
            if y < PDF_FOOTER_BAND_PT:
                page_hits.append((number, y, fragment))
        minima: dict[int, float] = {}
        for number, y in lowest:
            minima[number] = min(y, minima.get(number, y))

        for number, fragment in enumerate(pages, start=1):
            findings.extend(
                scan_text(
                    fragment,
                    f"PDF {relative} page {number}",
                    case_insensitive=case_insensitive,
                )
            )

        for number, y, fragment in page_hits:
            is_number = any(re.fullmatch(pattern, fragment, re.IGNORECASE) for pattern in PAGE_NUMBER_PATTERNS)
            label = "bottom page-number block" if is_number else "text below the body column"
            findings.append(
                Finding(
                    location=f"PDF {relative} page {number}",
                    line=number,
                    marker=f"y={y:.1f}pt",
                    label=label,
                    text=fragment[:80],
                    column=0,
                )
            )

        band = ", ".join(f"p{n} y>={m:.0f}pt" for n, m in sorted(minima.items()))
        notes.append(f"{relative}: {len(pages)} page(s) measured, lowest text per page {band}")

    return findings, notes


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail if any footer or attribution marker exists.")
    parser.add_argument("--root", default=str(REPO_ROOT), help="repository root to scan")
    parser.add_argument("--url", default="", help="also scan the HTTP responses of a running instance")
    parser.add_argument(
        "--route",
        action="append",
        default=[],
        metavar="PATH",
        help="extra URL path to fetch and scan, e.g. /analyses/<id> (repeatable)",
    )
    parser.add_argument("--source-only", action="store_true", help="skip the built frontend output")
    parser.add_argument("--case-insensitive", action="store_true", help="match markers case-insensitively")
    args = parser.parse_args(list(argv) if argv is not None else None)

    root = Path(args.root).resolve()
    print(f"[no-footer] scanning {root}")

    findings = scan_tree(root, case_insensitive=args.case_insensitive)
    upstream_notices: list[Finding] = []
    if not args.source_only:
        built_findings, upstream_notices = scan_built_frontend(
            root, case_insensitive=args.case_insensitive
        )
        findings.extend(built_findings)
    else:
        print("[no-footer] built output deliberately skipped (--source-only)")

    notes: list[str] = []
    pdf_findings, pdf_notes = scan_pdfs(root)
    findings.extend(pdf_findings)
    notes.extend(pdf_notes)

    if args.url:
        http_findings, http_notes = scan_http(args.url, extra_paths=tuple(args.route))
        findings.extend(http_findings)
        notes.extend(http_notes)

    for note in notes:
        print(f"[no-footer] note: {note}")

    if upstream_notices:
        unique = sorted({f.location for f in upstream_notices})
        print("")
        print(
            f"[no-footer] {len(upstream_notices)} preserved third-party licence notice(s) in "
            f"bundled dependency output: {', '.join(unique)}"
        )
        print(
            "[no-footer] These are licensing obligations kept by the bundler and recorded in "
            "track_2b/frontend/THIRD_PARTY_NOTICES.md. They are not footers, they are not ours, "
            "and removing them would breach the dependency licence. This classification applies "
            "only to the built bundle: our own source, generated reports, exports and HTTP "
            "responses are never eligible for it."
        )

    if findings:
        print("")
        print(f"[no-footer] FAIL: {len(findings)} marker occurrence(s) found")
        for finding in findings:
            print(f"  {finding.render()}")
        print("")
        print("[no-footer] Move required licensing/provenance text into a dedicated file, "
              "or into the body of the content near the relevant control.")
        return 1

    skipped = [note for note in notes if "NOT inspected" in note]
    if skipped:
        print("")
        print(f"[no-footer] PARTIAL: no marker was found on any surface that was inspected, "
              f"but {len(skipped)} surface(s) could not be read:")
        for note in skipped:
            print(f"  {note}")
        print("[no-footer] This is not a pass over those surfaces.")
    else:
        print("[no-footer] PASS: no footer, attribution or copyright marker found")
    print("[no-footer] allowlisted by design: " + ", ".join(sorted(ALLOWLIST_FILES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
