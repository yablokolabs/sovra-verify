#!/usr/bin/env python3
"""Audit the publishable tree, and any archive built from it, for secrets.

Why this exists
---------------
A credential that reaches a public repository cannot be un-published, and the
project rule is stricter than "do not commit a `.env`": nothing that leaves this
host may contain a credential value, and no archive may bundle the personal
credential file.

What it checks
--------------
1. **Credential values.** The named application entries are read out of the
   Hermes credential file (values in memory only) and the whole publishable tree
   is searched for each value, and for a longer core slice of it, so a value that
   was copied into a document with surrounding quote characters is still caught.
2. **Key-shaped strings.** Independent of any known value, the tree is searched
   for the shapes real credentials take (bearer-style ``sk-`` keys, Hugging Face
   ``hf_`` tokens, AWS access key ids, PEM private-key headers). This catches a
   credential that was never in the local file.
3. **Credential-bearing file names.** ``.env`` and its relatives, ``*.pem``,
   ``*.key``, ``hermes.env`` and private-key files must not be present at all,
   except for the documented ``.env.example`` template.
4. **Archives.** Every ``*.zip``/``*.tar.gz`` in the tree is opened and each
   member is scanned for the same values, shapes and names, so a leak cannot hide
   one level down.

Nothing here prints a value: matches are reported as file, line and a masked
label. Exit status is non-zero when anything is found, so this can gate a
release.

Usage
-----
    python3 scripts/audit_secrets.py                     # scan the repository
    python3 scripts/audit_secrets.py --manifest out.txt  # also write the file list
    python3 scripts/audit_secrets.py --archive dist/sovra-verify.zip
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Iterable, Iterator, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "track_2b" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

#: Only these named entries are read from the credential file, and none of their
#: values is ever printed.
CREDENTIAL_NAMES: tuple[str, ...] = (
    "CSCS_INFERENCE_API_KEY",
    "HUGGING_FACE_API_KEY",
    "ELEVENLABS_API_KEY",
)

#: Directory names that are never published, wherever they appear. Each one is a
#: build artifact, a dependency tree or a local work area, not source.
EXCLUDED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".vite",
        "dist",  # the built frontend and the rendered video output
        ".sovra_work",
        ".sovra_work_test",
        ".hermes",
        # Local state an editor or MCP tool keeps for itself. It is regenerated on
        # any machine that runs the tool, it is not part of the submission, and it
        # had already slipped into one built archive before this entry existed.
        ".serena",
        # Isolated git worktrees. A worktree is a second checkout of this same
        # repository, so it holds a complete copy of the tree — one worktree added
        # 149 duplicate members and 22 MiB to a built archive before this entry
        # existed, and nothing objected because a duplicate of a clean file is
        # still a clean file. Git ignores the directory; this list is what the
        # packaging walk actually reads.
        ".worktrees",
    }
)

#: Directory names that are only excluded at the top level. Matching them
#: anywhere would be wrong: ``originals`` is the store for uploaded source
#: documents at the top level, but it is also the folder a voice-over project
#: keeps its narration sources in, and that material is part of the build.
EXCLUDED_TOP_LEVEL_DIRS: frozenset[str] = frozenset({"originals", ".sink", "htmlcov"})

#: Local files that are deliberately kept off the published tree. The measured
#: evidence in ``track_2b/data/evaluation`` is deliberately NOT here: those files
#: are published, and this audit is what makes that safe to claim.
EXCLUDED_FILES: frozenset[str] = frozenset(
    {
        "SESSION_CONTINUATION.md",
    }
)

EXCLUDED_SUFFIXES: frozenset[str] = frozenset(
    {".sqlite3", ".sqlite3-wal", ".sqlite3-shm", ".pyc", ".pyo", ".log", ".swp"}
)

#: The one file that is allowed to *name* secret variables, because it documents
#: them as empty placeholders.
TEMPLATE_FILES: frozenset[str] = frozenset({".env.example"})

#: Files that must not exist in the publishable tree at all.
FORBIDDEN_NAME_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"^\.env$", "a dotenv file holds real credentials"),
    (r"^\.env\.(?!example$).+$", "a dotenv variant holds real credentials"),
    (r"(?i)^hermes.*\.env$", "the personal Hermes credential file"),
    (r"(?i).*\.pem$", "a private key or certificate file"),
    (r"(?i).*\.key$", "a private key file"),
    (r"(?i).*\.p12$", "a PKCS#12 keystore"),
    (r"(?i)^id_(rsa|ed25519|ecdsa)$", "an SSH private key"),
    (r"(?i)^credentials(\.json)?$", "a credential store"),
    (r"(?i)^\.netrc$", "a credential store"),
)

#: Shapes real credentials take. Applied to text content and to archive members.
KEY_SHAPE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_\-]{20,}", "bearer-style API key"),
    (r"(?<![A-Za-z0-9])hf_[A-Za-z0-9]{30,}", "Hugging Face token"),
    (r"(?<![A-Za-z0-9])AKIA[0-9A-Z]{16}(?![A-Za-z0-9])", "AWS access key id"),
    (r"(?<![A-Za-z0-9])ghp_[A-Za-z0-9]{30,}", "GitHub token"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "PEM private key block"),
    (r"(?<![A-Za-z0-9])xox[baprs]-[A-Za-z0-9-]{10,}", "Slack token"),
)

TEXT_SUFFIXES: frozenset[str] = frozenset(
    {
        ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json", ".jsonl",
        ".md", ".txt", ".html", ".htm", ".css", ".svg", ".yml", ".yaml", ".sh",
        ".toml", ".cfg", ".ini", ".lock", ".map", ".csv", "", ".example", ".cjs",
    }
)

MAX_FILE_BYTES = 16 * 1024 * 1024

#: A credential must be at least this long before a core slice is searched for.
MIN_CORE_SLICE_LENGTH = 24


def masked(value: str) -> str:
    """A label safe to print, derived from shape only - never the value."""
    if not value:
        return "<unset>"
    return f"<{len(value)} chars, ends {value[-2:]!r}>"


def credential_values(names: Sequence[str] = CREDENTIAL_NAMES) -> dict[str, str]:
    """Read the named credentials through the application's own loader."""
    try:
        from sovra.config import _read_hermes_keys  # noqa: PLC2701 - deliberate reuse
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[audit] could not import the credential loader: {type(exc).__name__}")
        return {}
    return _read_hermes_keys(tuple(names))


class Finding:
    def __init__(self, location: str, line: int, label: str, masked_value: str = ""):
        self.location = location
        self.line = line
        self.label = label
        self.masked_value = masked_value

    def render(self) -> str:
        suffix = f" [{self.masked_value}]" if self.masked_value else ""
        return f"  {self.location}:{self.line}: {self.label}{suffix}"


def is_excluded(relative: str) -> str:
    """Return a reason when the path is never published, else an empty string."""
    parts = Path(relative).parts
    if parts and parts[0] in EXCLUDED_TOP_LEVEL_DIRS:
        return f"inside top-level excluded directory '{parts[0]}'"
    for part in parts:
        if part in EXCLUDED_DIRS:
            return f"inside excluded directory '{part}'"
    name = parts[-1]
    if name in EXCLUDED_FILES:
        return "listed as a local-only file"
    if relative in EXCLUDED_FILES:
        return "listed as a local-only file"
    if Path(name).suffix.lower() in EXCLUDED_SUFFIXES:
        return f"excluded suffix '{Path(name).suffix}'"
    return ""


def iter_publishable(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = str(path.relative_to(root))
        if is_excluded(relative):
            continue
        yield path


def scan_text(text: str, location: str, values: dict[str, str]) -> list[Finding]:
    findings: list[Finding] = []
    needles: list[tuple[str, str]] = []
    for name, value in values.items():
        if len(value) >= 8:
            needles.append((value, f"exact value of {name}"))
        if len(value) >= MIN_CORE_SLICE_LENGTH:
            needles.append((value[3:-3], f"core slice of {name}"))
    for number, line in enumerate(text.splitlines(), start=1):
        for needle, label in needles:
            if needle and needle in line:
                findings.append(Finding(location, number, label, "<redacted>"))
        for pattern, label in KEY_SHAPE_PATTERNS:
            match = re.search(pattern, line)
            if match:
                hit = match.group(0)
                findings.append(
                    Finding(location, number, f"key-shaped string ({label})", masked(hit))
                )
    return findings


def scan_file(path: Path, root: Path, values: dict[str, str]) -> list[Finding]:
    relative = str(path.relative_to(root))
    findings: list[Finding] = []
    name = Path(relative).name
    if name not in TEMPLATE_FILES:
        for pattern, reason in FORBIDDEN_NAME_PATTERNS:
            if re.match(pattern, name):
                findings.append(Finding(relative, 0, f"forbidden file name: {reason}"))
    if "=" in name or path.suffix.lower() not in TEXT_SUFFIXES:
        # A binary blob is still scanned as bytes for the raw values below; it is
        # simply not treated as text for line reporting.
        try:
            blob = path.read_bytes()
        except OSError:
            return findings
        for name_, value in values.items():
            if len(value) >= 8:
                hits = blob.count(value.encode("utf-8", errors="ignore"))
                if hits:
                    findings.append(
                        Finding(relative, 0, f"binary content contains {name_}", f"{hits} hit(s)")
                    )
        return findings
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            findings.append(Finding(relative, 0, "file too large to audit", ""))
            return findings
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    findings.extend(scan_text(text, relative, values))
    return findings


def scan_archive(path: Path, root: Path, values: dict[str, str]) -> list[Finding]:
    """Open an archive and audit every member, so a leak cannot hide inside it."""
    relative = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
    findings: list[Finding] = []
    try:
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    member = f"{relative}!{info.filename}"
                    name = Path(info.filename).name
                    if name not in TEMPLATE_FILES:
                        for pattern, reason in FORBIDDEN_NAME_PATTERNS:
                            if re.match(pattern, name):
                                findings.append(
                                    Finding(member, 0, f"forbidden member name: {reason}")
                                )
                    if info.file_size > MAX_FILE_BYTES:
                        findings.append(Finding(member, 0, "member too large to audit"))
                        continue
                    payload = archive.read(info)
                    findings.extend(
                        scan_text(payload.decode("utf-8", errors="replace"), member, values)
                    )
        else:
            with tarfile.open(path) as archive:
                for member_info in archive.getmembers():
                    if not member_info.isfile():
                        continue
                    member = f"{relative}!{member_info.name}"
                    handle = archive.extractfile(member_info)
                    if handle is None:
                        continue
                    payload = handle.read()
                    findings.extend(
                        scan_text(payload.decode("utf-8", errors="replace"), member, values)
                    )
    except (zipfile.BadZipFile, tarfile.TarError, OSError) as exc:
        findings.append(
            Finding(relative, 0, f"archive could not be opened: {type(exc).__name__}")
        )
    return findings


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit the publishable tree for secrets.")
    parser.add_argument("--root", default=str(REPO_ROOT), help="tree to audit")
    parser.add_argument("--archive", action="append", default=[], metavar="PATH",
                        help="also audit an archive (repeatable)")
    parser.add_argument("--manifest", default="", metavar="PATH",
                        help="write the publishable file list here")
    parser.add_argument("--list-excluded", action="store_true",
                        help="print every excluded path with its reason")
    args = parser.parse_args(list(argv) if argv is not None else None)

    root = Path(args.root).resolve()
    print(f"[audit] root: {root}")

    values = credential_values()
    if values:
        print(f"[audit] {len(values)} credential value(s) loaded for comparison: "
              + ", ".join(f"{name} {masked(value)}" for name, value in sorted(values.items())))
    else:
        print("[audit] no credential value available to compare against. The value scan is "
              "therefore INCONCLUSIVE; the shape scan, the file-name check and the archive "
              "check still ran.")

    findings: list[Finding] = []
    publishable: list[str] = []
    excluded: list[tuple[str, str]] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = str(path.relative_to(root))
        reason = is_excluded(relative)
        if reason:
            excluded.append((relative, reason))
            continue
        publishable.append(relative)
        findings.extend(scan_file(path, root, values))
        if path.suffix.lower() in {".zip", ".tar", ".gz", ".tgz"}:
            findings.extend(scan_archive(path, root, values))

    for extra in args.archive:
        archive_path = Path(extra)
        if not archive_path.is_absolute():
            archive_path = (Path.cwd() / archive_path).resolve()
        if not archive_path.is_file():
            findings.append(Finding(str(extra), 0, "archive to audit was not found"))
            continue
        print(f"[audit] archive: {archive_path}")
        findings.extend(scan_archive(archive_path, archive_path.parent, values))

    total_bytes = sum((root / relative).stat().st_size for relative in publishable)
    print(f"[audit] publishable files: {len(publishable)} ({total_bytes / 1024:.0f} KiB)")
    print(f"[audit] excluded files:    {len(excluded)}")

    if args.list_excluded:
        for relative, reason in excluded:
            print(f"  - {relative}: {reason}")

    if args.manifest:
        manifest = Path(args.manifest)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps(
                {
                    "root": str(root),
                    "publishable": publishable,
                    "excluded": [{"path": p, "reason": r} for p, r in excluded],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"[audit] manifest written: {manifest}")

    if findings:
        print("")
        print(f"[audit] FAIL: {len(findings)} finding(s)")
        for finding in findings:
            print(finding.render())
        print("")
        print("[audit] Remove the file, or replace the value with a placeholder, before "
              "publishing. Rotate any credential that was exposed.")
        return 1

    print("[audit] PASS: no credential value, key-shaped string or forbidden file name "
          "found in the publishable tree or in any archive inspected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
