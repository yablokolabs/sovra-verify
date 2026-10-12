#!/usr/bin/env python3
"""Build the submission archive from the publishable tree, then audit it.

The archive is assembled from exactly the file set that ``scripts/audit_secrets``
considers publishable, so the archive and the audit cannot disagree about what
ships. Each member is scanned as it is added; a file that carries a credential
value, a key-shaped string or a forbidden name stops the build instead of being
packed.

The archive is then reopened and re-audited end to end, because a member added by
a bug in this script would not be caught by scanning the input list.

Reproducible on purpose: entries are sorted and carry a fixed timestamp, so two
builds of the same tree produce the same archive.

Usage:
    python3 scripts/package_submission.py                    # dist/sovra-verify-submission.zip
    python3 scripts/package_submission.py --out /tmp/x.zip
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import audit_secrets  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "dist" / "sovra-verify-submission.zip"

#: A fixed timestamp keeps the archive reproducible. It is the earliest value a
#: ZIP entry can carry, and it makes an unrelated rebuild byte-identical.
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

#: Top-level folder inside the archive, so extraction cannot scatter files over
#: whatever directory the reviewer happens to be in.
ARCHIVE_ROOT = "sovra-verify"


def publishable_files(root: Path) -> list[str]:
    files: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = str(path.relative_to(root))
        if audit_secrets.is_excluded(relative):
            continue
        files.append(relative)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Package and audit the submission archive.")
    parser.add_argument("--root", default=str(REPO_ROOT))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    out = Path(args.out)
    if not out.is_absolute():
        out = (Path.cwd() / out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.is_file():
        out.unlink()

    values = audit_secrets.credential_values()
    if not values:
        print("[package] refusing to build: no credential value could be read, so the "
              "scan that keeps a secret out of the archive cannot run.")
        return 1
    print(f"[package] comparing against {len(values)} loaded credential value(s)")

    files = publishable_files(root)
    findings: list[audit_secrets.Finding] = []
    packed: list[str] = []
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative in files:
            path = root / relative
            for finding in audit_secrets.scan_file(path, root, values):
                findings.append(finding)
            info = zipfile.ZipInfo(filename=f"{ARCHIVE_ROOT}/{relative}", date_time=FIXED_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
            packed.append(relative)

    if findings:
        print(f"[package] FAIL: {len(findings)} finding(s) in the input tree; no archive kept")
        for finding in findings:
            print(finding.render())
        out.unlink(missing_ok=True)
        return 1

    print(f"[package] wrote {out} ({out.stat().st_size / 1024:.0f} KiB, {len(packed)} member(s))")

    # Reopen and audit what is actually inside, not what was intended.
    print("[package] re-opening the archive and auditing every member")
    archive_findings = audit_secrets.scan_archive(out, out.parent, values)
    if archive_findings:
        print(f"[package] FAIL: {len(archive_findings)} finding(s) inside the archive")
        for finding in archive_findings:
            print(finding.render())
        out.unlink(missing_ok=True)
        return 1

    with zipfile.ZipFile(out) as archive:
        names = [info.filename for info in archive.infolist()]
    expected = {f"{ARCHIVE_ROOT}/{relative}" for relative in packed}
    if set(names) != expected:
        print("[package] FAIL: the archive does not contain exactly the publishable set")
        for missing in sorted(expected - set(names)):
            print(f"  missing: {missing}")
        for extra in sorted(set(names) - expected):
            print(f"  unexpected: {extra}")
        out.unlink(missing_ok=True)
        return 1

    if any(name.endswith("/.env") or name.endswith(".env") for name in names):
        print("[package] FAIL: a dotenv file is present in the archive")
        return 1

    print(f"[package] PASS: {len(names)} member(s) match the publishable set exactly, and no "
          f"credential value, key-shaped string or forbidden file name is present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
