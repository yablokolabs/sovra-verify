"""No footer anywhere: frontend source, built assets, HTTP responses and exports.

The project forbids footer components, bottom copyright notices, attribution
bars, "Powered by" badges, closing signatures and decorative trailing sections
in any screen, generated document, report, export or PDF. This test is the
automated check for that rule.

Licensing is *not* weakened by this rule: an upstream ``LICENSE`` file and a
``/*! ... */`` vendor licence header are provenance, not a footer, so they are
excluded from the scan explicitly rather than by accident.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
REPO_ROOT = Path(__file__).resolve().parents[3]

# The marker list and the licence-header classification come from the repository's
# own checker instead of being restated here. Two copies of the rule would drift,
# and a test that is stricter than `make no-footer` fails on bundled dependency
# licence headers that the project has deliberately decided to preserve.
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from check_no_footer import MARKER_FRAGMENTS, Finding  # noqa: E402

#: Lower-cased substrings that must not appear.
FOOTER_MARKERS = tuple(fragment.lower() for fragment, _label in MARKER_FRAGMENTS) + (
    "</footer",
)

#: Lower-cased marker -> the canonical spelling the checker classifies by.
_CANONICAL_MARKER = {fragment.lower(): fragment for fragment, _label in MARKER_FRAGMENTS}

#: Text files worth scanning in the frontend tree. Build metadata such as
#: package.json and tsconfig.json is deliberately excluded: it is not a screen,
#: a report or an export, and scanning it only invites false positives.
SCANNABLE_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".html", ".css", ".svg"}

#: Never scanned: lockfiles and source maps are machine-generated, huge and not UI.
SKIP_NAME_PARTS = ("node_modules", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", ".map")

#: Provenance, not footers. Kept deliberately narrow.
LICENCE_LINE = re.compile(
    r"(spdx-license-identifier|licen[cs]e|@licen[cs]e|mit license|apache license|bsd license)",
    re.IGNORECASE,
)
LICENCE_HEADER_OPEN = re.compile(r"^\s*/\*!")
UPSTREAM_LICENCE_FILE = re.compile(r"(^|/)licen[cs]e(\.|$)", re.IGNORECASE)


def iter_frontend_files() -> list[Path]:
    if not FRONTEND_DIR.is_dir():
        return []
    files: list[Path] = []
    for path in sorted(FRONTEND_DIR.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SCANNABLE_SUFFIXES:
            continue
        if any(part in str(path) for part in SKIP_NAME_PARTS):
            continue
        if UPSTREAM_LICENCE_FILE.search(str(path)):
            continue
        files.append(path)
    return files


def scan_for_footers(path: Path) -> list[str]:
    """Return human-readable findings for one file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:  # pragma: no cover - unreadable file
        return []
    findings: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        lowered = line.lower()
        hit = next((marker for marker in FOOTER_MARKERS if marker in lowered), None)
        if hit is None:
            continue
        if LICENCE_HEADER_OPEN.match(line) or LICENCE_LINE.search(line):
            continue
        if is_upstream_licence_notice(line, hit):
            continue
        findings.append(f"{path}:{number}: '{hit}' in {line.strip()[:120]!r}")
    return findings


def is_upstream_licence_notice(line: str, hit: str) -> bool:
    """True when this match is a preserved dependency licence header.

    Delegates to the checker's own rule so the test and `make no-footer` cannot
    disagree about what counts as provenance rather than a footer. Only copyright
    notices adjacent to a licence signature qualify; a ``<footer`` element or an
    attribution bar never does.
    """
    canonical = _CANONICAL_MARKER.get(hit)
    if canonical is None:
        return False
    column = line.lower().find(hit)
    return Finding(
        location="scan",
        line=0,
        marker=canonical,
        label="scan",
        text=line,
        column=max(column, 0),
    ).is_upstream_licence_notice()


def test_no_footer_markers_in_frontend_source_or_build_output() -> None:
    files = iter_frontend_files()
    if not files:
        pytest.skip(
            "no frontend source or build output found yet under "
            f"{FRONTEND_DIR}; build the frontend (npm --prefix track_2b/frontend run build) "
            "and re-run so this check is real"
        )
    findings: list[str] = []
    for path in files:
        findings.extend(scan_for_footers(path))
    assert not findings, "footer markers found:\n" + "\n".join(findings)


def test_no_footer_markers_in_the_built_index_html() -> None:
    index = FRONTEND_DIR / "dist" / "index.html"
    if not index.is_file():
        pytest.skip("frontend has not been built (track_2b/frontend/dist/index.html is absent)")
    findings = scan_for_footers(index)
    assert not findings, "footer markers found in the built index.html:\n" + "\n".join(findings)


# -- HTTP responses --------------------------------------------------------
AGREEMENT = (
    b"Clause 7.2 Payment terms\n"
    b"The Buyer shall pay each undisputed invoice within 30 days of the invoice date.\n"
)
POLICY = (
    b"Policy 4.1 Standard settlement period\n"
    b"All supplier invoices are settled within 60 days of the invoice date.\n"
)


def assert_no_footer(text: str, where: str) -> None:
    lowered = text.lower()
    hits = [marker for marker in FOOTER_MARKERS if marker in lowered]
    assert not hits, f"footer markers {hits} found in {where}"


def test_api_responses_contain_no_footer_markers(api_client) -> None:
    client, _settings = api_client()

    assert_no_footer(client.get("/config").text, "/config")
    assert_no_footer(client.get("/documents").text, "/documents")

    upload = client.post(
        "/documents",
        files=[
            ("files", ("agreement.txt", AGREEMENT, "text/plain")),
            ("files", ("policy.txt", POLICY, "text/plain")),
        ],
    )
    assert upload.status_code == 200
    assert_no_footer(upload.text, "POST /documents")

    document_ids = [d["id"] for d in client.get("/documents").json()["documents"]]
    analysis_response = client.post("/analyses", json={"document_ids": document_ids})
    assert analysis_response.status_code == 200, analysis_response.text
    assert_no_footer(analysis_response.text, "POST /analyses")
    analysis_id = analysis_response.json()["analysis"]["id"]

    assert_no_footer(client.get(f"/analyses/{analysis_id}").text, f"/analyses/{analysis_id}")
    assert_no_footer(
        client.get(f"/analyses/{analysis_id}/claims").text, f"/analyses/{analysis_id}/claims"
    )
    assert_no_footer(client.get(f"/analyses/{analysis_id}/export").text, "json export")
    assert_no_footer(
        client.get(f"/analyses/{analysis_id}/export", params={"format": "markdown"}).text,
        "markdown export",
    )


def test_markdown_export_does_not_end_with_a_signature_block(api_client) -> None:
    client, _settings = api_client()
    client.post(
        "/documents",
        files=[
            ("files", ("agreement.txt", AGREEMENT, "text/plain")),
            ("files", ("policy.txt", POLICY, "text/plain")),
        ],
    )
    document_ids = [d["id"] for d in client.get("/documents").json()["documents"]]
    analysis_id = client.post("/analyses", json={"document_ids": document_ids}).json()["analysis"]["id"]
    report = client.get(
        f"/analyses/{analysis_id}/export", params={"format": "markdown"}
    ).text

    tail = [line for line in report.strip().splitlines() if line.strip()][-3:]
    trailing = "\n".join(tail).lower()
    assert "prove it" not in trailing, "the report must not close with a tagline"
    assert not any(marker in trailing for marker in FOOTER_MARKERS)
    assert "## Evidence model" in report


def test_a_completed_review_does_not_add_a_footer(api_client) -> None:
    client, _settings = api_client()
    client.post(
        "/documents",
        files=[
            ("files", ("agreement.txt", AGREEMENT, "text/plain")),
            ("files", ("policy.txt", POLICY, "text/plain")),
        ],
    )
    document_ids = [d["id"] for d in client.get("/documents").json()["documents"]]
    analysis = client.post("/analyses", json={"document_ids": document_ids}).json()["analysis"]
    if not analysis["findings"]:
        pytest.skip("the canned run produced no findings to review")

    finding_id = analysis["findings"][0]["id"]
    response = client.post(
        f"/findings/{finding_id}/reviews",
        json={"status": "confirmed_for_review", "note": "reviewed"},
    )
    assert response.status_code == 200
    assert_no_footer(response.text, "review response")
    assert_no_footer(
        client.get(f"/analyses/{analysis['id']}/export", params={"format": "markdown"}).text,
        "markdown export after review",
    )
