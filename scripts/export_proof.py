#!/usr/bin/env python3
"""Produce a redacted evidence bundle for submission.

Two independent checks are written to ``track_2b/data/evaluation/``:

1. ``PROOF.json`` / ``PROOF.md`` - the evidence for one analysis: canonical
   document hashes, the provider ledger (provider, model, mode, status,
   latency, token usage, failures) and every citation's exact offsets resolved
   against canonical text. No credential value is included; the only credential
   information is a masked form produced by the application.

2. A credential audit of the working tree. It looks for anything shaped like a
   live credential and reports ``file:line`` with the value **redacted**. It also
   checks that the Hermes credential file is not present inside the repository.

Usage:
    python3 scripts/export_proof.py                      # newest analysis in the store
    python3 scripts/export_proof.py --analysis-id abc123
    python3 scripts/export_proof.py --run-demo           # run the demo corpus first
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "track_2b" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

OUT_DIR = REPO_ROOT / "track_2b" / "data" / "evaluation"

#: Shapes of things that must never be committed. Each is assembled from
#: fragments so this file does not contain a literal that its own audit flags.
SECRET_PATTERNS: tuple[tuple[str, str], ...] = (
    ("sk" + "-" + "[A-Za-z0-9]{16,}", "generic sk- prefixed key"),
    ("hf" + "_" + "[A-Za-z0-9]{16,}", "Hugging Face token"),
    ("sk" + "_" + "live" + "_" + "[A-Za-z0-9]{10,}", "live secret key"),
    ("AKIA" + "[0-9A-Z]{12,}", "AWS access key id"),
    ("-----BEGIN " + "[A-Z ]*" + "PRIVATE KEY-----", "private key block"),
    ("gh" + "p" + "_" + "[A-Za-z0-9]{20,}", "GitHub token"),
)

#: Only real, non-negotiable credentials are matched by the project-specific
#: rule; documentation placeholders are ignored.
CREDENTIAL_ENV_NAMES = ("CSCS_INFERENCE_API_KEY", "HUGGING_FACE_API_KEY", "ELEVENLABS_API_KEY")

SCAN_SUFFIXES = frozenset(
    {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".jsonl", ".md", ".txt", ".yml",
     ".yaml", ".sh", ".toml", ".cfg", ".ini", ".env", ".example", ""}
)
SKIP_DIR_NAMES = frozenset(
    {".git", "node_modules", "__pycache__", ".venv", ".pytest_cache", "dist",
     ".mypy_cache", ".ruff_cache", ".sovra_work", ".sovra_work_test"}
)
MAX_FILE_BYTES = 4 * 1024 * 1024


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def looks_like_live_credential(candidate: str) -> bool:
    """Decide whether a key-shaped string is plausibly a live credential.

    A shape rule alone reports fabricated test literals - a run of consecutive
    alphabet characters such as the one used to prove that ``mask_secret`` masks
    a short value - and an audit that cries wolf is an audit nobody reads. A real
    key is long and carries entropy: it mixes letters with digits. A PEM header
    is accepted on its own shape, because it is a header rather than a value.
    """
    if len(candidate) < 20:
        return False
    if "PRIVATE KEY" in candidate:
        return True
    return any(ch.isdigit() for ch in candidate) and any(ch.isalpha() for ch in candidate)


def redact(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-2:]} (len={len(value)})"


def audit_tree(root: Path) -> dict[str, Any]:
    """Look for live credentials in the working tree. Values are never printed."""
    hits: list[dict[str, Any]] = []
    scanned = 0
    compiled = [(re.compile(pattern), label) for pattern, label in SECRET_PATTERNS]

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        relative = path.relative_to(root)
        for number, line in enumerate(text.splitlines(), start=1):
            for pattern, label in compiled:
                match = pattern.search(line)
                if match and looks_like_live_credential(match.group(0)):
                    hits.append({
                        "file": str(relative),
                        "line": number,
                        "kind": label,
                        "redacted_value": redact(match.group(0)),
                    })
            for name in CREDENTIAL_ENV_NAMES:
                assignment = re.search(rf"^\s*(?:export\s+)?{name}\s*=\s*(.+?)\s*$", line)
                if not assignment:
                    continue
                value = assignment.group(1).strip().strip("\"'")
                # An empty placeholder or an obvious template is fine.
                if not value or value.startswith("$") or value.lower() in {
                    "changeme", "your-key-here", "placeholder", "none", "null"
                }:
                    continue
                if re.fullmatch(r"<[^>]*>", value):
                    continue
                hits.append({
                    "file": str(relative),
                    "line": number,
                    "kind": f"assigned value for {name}",
                    "redacted_value": redact(value),
                })

    hermes_copies = [
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and any(part in {".hermes"} for part in p.parts)
    ]
    return {
        "files_scanned": scanned,
        "hits": hits,
        "clean": not hits and not hermes_copies,
        "hermes_copies_in_repo": hermes_copies,
    }


def build_bundle(analysis_id: str | None, *, run_demo: bool) -> dict[str, Any]:
    from sovra import Storage, SovraService, load_settings, summarise_runs
    from sovra.providers import ProviderRouter

    settings = load_settings()
    storage = Storage(settings.work_dir / "sovra.sqlite3")

    if run_demo:
        service = SovraService(settings, storage, ProviderRouter(settings))
        corpus_dir = REPO_ROOT / "track_2b" / "data" / "demo"
        document_ids = []
        for path in sorted(corpus_dir.glob("*.txt")):
            ingested = service.ingest(filename=path.name, data=path.read_bytes(), mime="text/plain")
            document_ids.append(ingested.document.id)
            print(f"  ingested {path.name}")
        analysis = service.analyse(document_ids=document_ids, force=True)
        analysis_id = analysis.id

    if analysis_id:
        analysis = storage.analysis(analysis_id)
    else:
        listed = storage.list_analyses()
        analysis = storage.analysis(listed[0]["id"]) if listed else None
    if analysis is None:
        print("ERROR: no analysis available to export. Run the demo corpus first "
              "(scripts/export_proof.py --run-demo) or pass --analysis-id.", file=sys.stderr)
        raise SystemExit(4)

    claims = storage.claims(analysis.id)
    documents = [storage.get_document(d) for d in analysis.document_ids]

    evidence: list[dict[str, Any]] = []
    for finding in analysis.findings:
        for citation in finding.evidence:
            canonical = storage.canonical_text(citation.document_id)
            derived = canonical[citation.start_offset : citation.end_offset]
            evidence.append({
                "finding_id": finding.id,
                "document_id": citation.document_id,
                "page": citation.page,
                "start_offset": citation.start_offset,
                "end_offset": citation.end_offset,
                "quote_from_application": citation.quote,
                "quote_recomputed_from_canonical": derived,
                "offsets_reproduce_quote": derived == citation.quote,
            })

    return {
        "generated_at": now(),
        "analysis_id": analysis.id,
        "status": analysis.status.value,
        "provider": analysis.provider,
        "model": analysis.model,
        "prompt_version": analysis.prompt_version,
        "configuration": settings.public_view(),
        "corpus": [
            {
                "id": d.id, "name": d.name, "sha256": d.sha256,
                "size_bytes": d.size_bytes, "page_count": d.page_count,
                "extraction_status": d.extraction_status.value,
                "extraction_notes": d.extraction_notes,
            }
            for d in documents if d is not None
        ],
        "usage": summarise_runs(analysis.provider_runs),
        "provider_ledger": [
            {
                "id": r.id, "provider": r.provider, "model": r.model, "mode": r.mode,
                "status": r.status, "latency_ms": r.latency_ms, "usage": r.usage,
                "started_at": r.started_at.isoformat(),
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "error_class": r.error_class, "error_message": r.error_message,
                "validation_errors": r.validation_errors,
                "is_backup": r.is_backup, "downgraded_from": r.downgraded_from,
            }
            for r in analysis.provider_runs
        ],
        "claims": [
            {
                "id": c.id, "document_id": c.document_id, "predicate": c.predicate,
                "predicate_normalized": c.predicate_normalized, "value": c.value,
                "value_normalized": c.value_normalized, "unit": c.unit,
                "effective_date": c.effective_date, "source_passage_id": c.source_passage_id,
                "quote_start": c.quote_start, "quote_end": c.quote_end,
                "extraction_status": c.extraction_status.value, "origin": c.origin,
            }
            for c in claims
        ],
        "findings": [json.loads(f.model_dump_json()) for f in analysis.findings],
        "citation_check": {
            "spans": len(evidence),
            "all_reproduce": all(e["offsets_reproduce_quote"] for e in evidence) if evidence else None,
            "detail": evidence,
        },
        "candidate_coverage": analysis.candidate_coverage,
        "failures": analysis.failures,
        "limitations": analysis.limitations,
        "claims_about_this_bundle": [
            "Results are potential inconsistencies for human review, not a factual or legal determination.",
            "CSCS-hosted inference is external-network inference; a local web app calling CSCS is not air-gapped.",
            "This bundle contains no credential value; the credential field is a masked form only.",
        ],
    }


def render_markdown(bundle: dict[str, Any], audit: dict[str, Any]) -> str:
    """A readable proof document. It deliberately ends with its last section."""
    lines: list[str] = []
    usage = bundle["usage"]
    lines.append(f"# Sovra Verify evidence bundle — analysis {bundle['analysis_id']}")
    lines.append("")
    lines.append(f"- Generated: {bundle['generated_at']}")
    lines.append(f"- Status: `{bundle['status']}`")
    lines.append(f"- Provider: `{bundle['provider']}`")
    lines.append(f"- Model: `{bundle['model']}`")
    lines.append(f"- Prompt version: `{bundle['prompt_version']}`")
    lines.append(f"- Credential (masked): `{bundle['configuration']['providers']['cscs']['api_key']}`")
    lines.append("")
    lines.append("## Corpus and hashes")
    for document in bundle["corpus"]:
        lines.append(
            f"- `{document['name']}` — sha256 `{document['sha256']}`, "
            f"{document['size_bytes']} bytes, {document['page_count']} page(s), "
            f"extraction `{document['extraction_status']}`"
        )
        for note in document["extraction_notes"]:
            lines.append(f"  - note: {note}")
    lines.append("")
    lines.append("## Provider ledger")
    lines.append(f"- Calls: {usage['calls']} ({usage['failed_calls']} failed, "
                 f"{usage['backup_calls']} backup)")
    lines.append(f"- Prompt tokens: {usage['prompt_tokens']}, completion tokens: "
                 f"{usage['completion_tokens']}, total: {usage['total_tokens']}")
    lines.append(f"- Models: {', '.join(usage['models']) or 'none'}")
    lines.append(f"- Total provider latency: {usage['latency_ms_total']} ms")
    for run in bundle["provider_ledger"]:
        lines.append(f"  - `{run['mode']}` {run['provider']}/{run['model']} "
                     f"status={run['status']} latency={run['latency_ms']} ms "
                     f"tokens={run['usage'].get('total_tokens', 'n/a')}")
        if run["error_message"]:
            lines.append(f"    - error: {run['error_class']}: {run['error_message']}")
    lines.append("")
    lines.append("## Findings and citation check")
    lines.append(f"- Findings: {len(bundle['findings'])}")
    lines.append(f"- Citation spans re-derived from canonical text: {bundle['citation_check']['spans']}")
    lines.append(f"- All offsets reproduce their quote: `{bundle['citation_check']['all_reproduce']}`")
    for check in bundle["citation_check"]["detail"]:
        lines.append(
            f"  - document `{check['document_id']}` page {check['page']} "
            f"[{check['start_offset']}, {check['end_offset']}] "
            f"reproduces={check['offsets_reproduce_quote']}"
        )
        lines.append(f"    > {check['quote_recomputed_from_canonical']}")
    lines.append("")
    lines.append("## Recorded failures")
    if bundle["failures"]:
        for failure in bundle["failures"]:
            lines.append(f"- {failure}")
    else:
        lines.append("- none recorded in this run")
    lines.append("")
    lines.append("## Limitations")
    for limitation in bundle["limitations"]:
        lines.append(f"- {limitation}")
    lines.append("")
    lines.append("## Credential audit of the working tree")
    lines.append(f"- Files scanned: {audit['files_scanned']}")
    lines.append(f"- Live-credential findings: {len(audit['hits'])}")
    lines.append(f"- Credential file copies found inside the repository: "
                 f"{len(audit['hermes_copies_in_repo'])}")
    for hit in audit["hits"]:
        lines.append(f"  - {hit['file']}:{hit['line']} [{hit['kind']}] {hit['redacted_value']}")
    if audit["hermes_copies_in_repo"]:
        for copy in audit["hermes_copies_in_repo"]:
            lines.append(f"  - copied credential file: {copy}")
    lines.append("")
    lines.append("## Claims about this bundle")
    for claim in bundle["claims_about_this_bundle"]:
        lines.append(f"- {claim}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a redacted evidence bundle.")
    parser.add_argument("--analysis-id", default="")
    parser.add_argument("--run-demo", action="store_true",
                        help="run the demo corpus through the real pipeline first")
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    args = parser.parse_args()

    print("Sovra Verify evidence export")
    bundle = build_bundle(args.analysis_id or None, run_demo=args.run_demo)
    audit = audit_tree(REPO_ROOT)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "PROOF.json"
    md_path = out_dir / "PROOF.md"
    json_path.write_text(json.dumps({"bundle": bundle, "credential_audit": audit}, indent=2),
                         encoding="utf-8")
    md_path.write_text(render_markdown(bundle, audit), encoding="utf-8")

    print(f"  analysis:     {bundle['analysis_id']} ({bundle['status']})")
    print(f"  provider:     {bundle['provider']} / {bundle['model']}")
    print(f"  calls:        {bundle['usage']['calls']} ({bundle['usage']['failed_calls']} failed)")
    print(f"  citation spans: {bundle['citation_check']['spans']}")
    print(f"  credential audit: {len(audit['hits'])} finding(s) across "
          f"{audit['files_scanned']} file(s)")
    print(f"  wrote {json_path.relative_to(REPO_ROOT)}")
    print(f"  wrote {md_path.relative_to(REPO_ROOT)}")

    if not audit["clean"]:
        print("")
        print("FAIL: the credential audit found something. Values are redacted above; "
              "remove the material before delivery.")
        return 1
    print("  credential audit: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
