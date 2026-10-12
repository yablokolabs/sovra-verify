#!/usr/bin/env python3
"""Run the frozen evaluation corpus through the real pipeline and measure.

The corpus is ``track_2b/data/evaluation/pairs.jsonl`` with one JSON object per
line:

    {"id": "ev-001",
     "category": "genuine_conflict",
     "left":  {"document": "agreement.txt", "text": "..."},
     "right": {"document": "policy.txt",    "text": "..."},
     "expected_relation": "potential_conflict",
     "rationale": "why this label is correct",
     "synthetic": true}

Measured output, written to ``track_2b/data/evaluation/RESULTS.json``:

  * confusion matrix over expected vs observed relation
  * per-class precision, recall and F1
  * abstention rate and, separately, provider failure rate
  * resolved-citation rate
  * end-to-end latency per case and tokens per case

Honesty rules enforced by this script:

  * failed provider requests are counted separately from correct abstentions;
  * the denominator is every case in the corpus, never only the successes;
  * a partial run still writes whatever was measured and is labelled ``partial``;
  * raw model output is stored, not a summary that could hide a bad answer.

Synthetic evaluation does not establish general real-world performance.

Usage:
    python3 scripts/evaluate.py
    python3 scripts/evaluate.py --limit 4 --model swiss-ai/Apertus-v1.5-70B
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "track_2b" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

DEFAULT_PAIRS = REPO_ROOT / "track_2b" / "data" / "evaluation" / "pairs.jsonl"
DEFAULT_OUT = REPO_ROOT / "track_2b" / "data" / "evaluation" / "RESULTS.json"

RELATIONS = ("consistent", "potential_conflict", "insufficient_evidence", "unrelated")
NO_PREDICTION = ("abstained", "failed")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_pairs(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        print(f"ERROR: evaluation corpus not found at {path}", file=sys.stderr)
        print("       the corpus is written by the evaluation-fixture step; no result is invented "
              "in its absence.", file=sys.stderr)
        raise SystemExit(3)
    pairs: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"ERROR: {path.name}:{number} is not valid JSON: {exc}", file=sys.stderr)
                raise SystemExit(3) from None
            for field in ("id", "expected_relation", "left", "right"):
                if field not in item:
                    print(f"ERROR: {path.name}:{number} is missing '{field}'", file=sys.stderr)
                    raise SystemExit(3)
            pairs.append(item)
    if not pairs:
        print(f"ERROR: {path} contains no cases", file=sys.stderr)
        raise SystemExit(3)
    return pairs


def observed_relation(findings: list[dict], runs: list[dict]) -> tuple[str, str]:
    """Collapse a finding set into one predicted relation plus a reason."""
    failed = [r for r in runs if r.get("status") != "ok"]
    if not runs:
        return "failed", "no provider call was made"
    if len(failed) == len(runs):
        return "failed", f"every provider call failed ({len(runs)} call(s))"

    relation_counts = Counter(f.get("relation", "") for f in findings)
    cited_conflicts = [
        f for f in findings
        if f.get("relation") == "potential_conflict" and f.get("evidence")
    ]
    if cited_conflicts:
        return "potential_conflict", f"{len(cited_conflicts)} conflict(s) with a resolved citation"
    if relation_counts.get("potential_conflict"):
        return "abstained", "conflicts were proposed but none carried a resolvable citation"
    for candidate in ("consistent", "unrelated", "insufficient_evidence"):
        if relation_counts.get(candidate):
            return candidate, f"highest-signal relation observed: {candidate}"
    return "abstained", "no finding was produced for this pair"


def run_case(pair: dict, settings, tmp_root: Path, *, extract_only: bool = False) -> dict[str, Any]:
    """Run one pair through the real pipeline in an isolated store."""
    from sovra import Storage, SovraService
    from sovra.providers import ProviderRouter

    work = tmp_root / pair["id"]
    work.mkdir(parents=True, exist_ok=True)
    storage = Storage(work / "eval.sqlite3")
    try:
        router = ProviderRouter(settings)
        service = SovraService(settings, storage, router)

        document_ids = []
        for side in ("left", "right"):
            body = pair[side]
            name = f"{pair['id']}-{side}-{body.get('document', 'document.txt')}"
            ingested = service.ingest(
                filename=name, data=str(body["text"]).encode("utf-8"), mime="text/plain"
            )
            document_ids.append(ingested.document.id)

        started = time.perf_counter()
        analysis = service.analyse(
            document_ids=document_ids, force=True, extract_only=extract_only
        )
        wall_ms = int((time.perf_counter() - started) * 1000)

        findings = [json.loads(f.model_dump_json()) for f in analysis.findings]
        runs = [json.loads(r.model_dump_json()) for r in analysis.provider_runs]
        predicted, reason = observed_relation(findings, runs)

        usage_prompt = sum(int(r.get("usage", {}).get("prompt_tokens") or 0) for r in runs)
        usage_completion = sum(int(r.get("usage", {}).get("completion_tokens") or 0) for r in runs)
        evidence_total = sum(len(f.get("evidence") or []) for f in findings)
        conflicts = [f for f in findings if f.get("relation") == "potential_conflict"]

        return {
            "id": pair["id"],
            "category": pair.get("category", "uncategorised"),
            "expected_relation": pair["expected_relation"],
            "observed_relation": predicted,
            "decision_reason": reason,
            "correct": predicted == pair["expected_relation"],
            "synthetic": bool(pair.get("synthetic", True)),
            "rationale": pair.get("rationale", ""),
            "analysis_status": analysis.status.value,
            "wall_ms": wall_ms,
            "provider_calls": len(runs),
            "failed_calls": sum(1 for r in runs if r.get("status") != "ok"),
            "models_used": sorted({f"{r.get('provider')}:{r.get('model')}" for r in runs}),
            "prompt_tokens": usage_prompt,
            "completion_tokens": usage_completion,
            "total_tokens": usage_prompt + usage_completion,
            "claim_count": analysis.claim_count,
            "candidate_pairs": analysis.pair_count,
            "finding_count": len(findings),
            "conflict_findings": len(conflicts),
            "conflicts_with_citation": len([f for f in conflicts if f.get("evidence")]),
            "evidence_spans": evidence_total,
            "candidate_coverage": analysis.candidate_coverage,
            "limitations": analysis.limitations,
            "failures": analysis.failures,
            "findings": [
                {
                    "relation": f.get("relation"),
                    "explanation": f.get("explanation"),
                    "evidence": [
                        {
                            "document_id": c.get("document_id"),
                            "page": c.get("page"),
                            "start_offset": c.get("start_offset"),
                            "end_offset": c.get("end_offset"),
                            "quote": c.get("quote"),
                        }
                        for c in (f.get("evidence") or [])
                    ],
                    "limitations": f.get("limitations"),
                }
                for f in findings
            ],
            "provider_runs": runs,
        }
    finally:
        storage.close()
        shutil.rmtree(work, ignore_errors=True)


def compute_metrics(rows: list[dict]) -> dict[str, Any]:
    total = len(rows)
    confusion: dict[str, dict[str, int]] = {
        expected: {observed: 0 for observed in RELATIONS + NO_PREDICTION}
        for expected in RELATIONS + NO_PREDICTION
    }
    for row in rows:
        expected = row["expected_relation"]
        observed = row["observed_relation"]
        confusion.setdefault(expected, {})
        confusion[expected][observed] = confusion[expected].get(observed, 0) + 1

    per_class: dict[str, dict[str, float]] = {}
    for relation in RELATIONS:
        true_positive = sum(
            1 for r in rows
            if r["expected_relation"] == relation and r["observed_relation"] == relation
        )
        false_positive = sum(
            1 for r in rows
            if r["observed_relation"] == relation and r["expected_relation"] != relation
        )
        false_negative = sum(
            1 for r in rows
            if r["expected_relation"] == relation and r["observed_relation"] != relation
        )
        precision = true_positive / (true_positive + false_positive) if (true_positive + false_positive) else 0.0
        recall = true_positive / (true_positive + false_negative) if (true_positive + false_negative) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        per_class[relation] = {
            "support": true_positive + false_negative,
            "predicted": true_positive + false_positive,
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    abstained = sum(1 for r in rows if r["observed_relation"] == "abstained")
    failed = sum(1 for r in rows if r["observed_relation"] == "failed")
    cited = sum(r["conflicts_with_citation"] for r in rows)
    conflicts = sum(r["conflict_findings"] for r in rows)
    spans = sum(r["evidence_spans"] for r in rows)
    findings_total = sum(r["finding_count"] for r in rows)

    latencies = [r["wall_ms"] for r in rows]
    tokens = [r["total_tokens"] for r in rows]

    return {
        "cases": total,
        "correct": sum(1 for r in rows if r["correct"]),
        "accuracy": round(sum(1 for r in rows if r["correct"]) / total, 4) if total else 0.0,
        "confusion_matrix": confusion,
        "per_class": per_class,
        "abstained_cases": abstained,
        "abstention_rate": round(abstained / total, 4) if total else 0.0,
        "failed_cases": failed,
        "failure_rate": round(failed / total, 4) if total else 0.0,
        "provider_calls": sum(r["provider_calls"] for r in rows),
        "failed_provider_calls": sum(r["failed_calls"] for r in rows),
        "resolved_citation_rate": round(cited / conflicts, 4) if conflicts else None,
        "conflict_findings": conflicts,
        "conflicts_with_citation": cited,
        "findings_total": findings_total,
        "evidence_spans_total": spans,
        "latency_ms_per_case": {
            "mean": round(statistics.fmean(latencies), 1) if latencies else None,
            "median": round(statistics.median(latencies), 1) if latencies else None,
            "max": max(latencies) if latencies else None,
        },
        "tokens_per_case": {
            "mean": round(statistics.fmean(tokens), 1) if tokens else None,
            "max": max(tokens) if tokens else None,
            "total": sum(tokens),
        },
        "categories": dict(Counter(r["category"] for r in rows)),
        "per_category_accuracy": {
            category: round(
                sum(1 for r in rows if r["category"] == category and r["correct"])
                / max(1, sum(1 for r in rows if r["category"] == category)),
                4,
            )
            for category in sorted({r["category"] for r in rows})
        },
    }


def print_summary(metrics: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    print("")
    print("== measured results ==")
    print(f"cases: {metrics['cases']}   correct: {metrics['correct']}   accuracy: {metrics['accuracy']}")
    print("")
    print("confusion matrix (rows = expected, columns = observed)")
    header = ["expected \\ observed"] + list(RELATIONS) + list(NO_PREDICTION)
    print("  " + " | ".join(f"{h[:14]:>14}" for h in header))
    for expected in list(RELATIONS) + list(NO_PREDICTION):
        row = metrics["confusion_matrix"].get(expected, {})
        cells = [f"{exp:>14}" for exp in [expected]]
        cells += [f"{row.get(o, 0):>14}" for o in list(RELATIONS) + list(NO_PREDICTION)]
        print("  " + " | ".join(cells))
    print("")
    print(f"{'class':<24}{'support':>8}{'pred':>7}{'TP':>5}{'FP':>5}{'FN':>5}{'prec':>8}{'rec':>8}{'F1':>8}")
    for relation, stats in metrics["per_class"].items():
        print(f"{relation:<24}{stats['support']:>8}{stats['predicted']:>7}{stats['true_positive']:>5}"
              f"{stats['false_positive']:>5}{stats['false_negative']:>5}{stats['precision']:>8.3f}"
              f"{stats['recall']:>8.3f}{stats['f1']:>8.3f}")
    print("")
    print(f"abstentions:          {metrics['abstained_cases']} ({metrics['abstention_rate']:.1%})")
    print(f"failed requests:      {metrics['failed_cases']} ({metrics['failure_rate']:.1%})  "
          "<- counted separately from abstentions")
    print(f"provider calls:       {metrics['provider_calls']} "
          f"({metrics['failed_provider_calls']} failed)")
    rate = metrics["resolved_citation_rate"]
    if rate is None:
        citation_line = "n/a - no conflict findings were produced"
    else:
        citation_line = f"{rate:.1%} of {metrics['conflict_findings']} conflict finding(s)"
    print(f"resolved citation rate (conflict findings): {citation_line}")
    print(f"evidence spans kept:  {metrics['evidence_spans_total']}")
    print(f"latency per case:     mean {metrics['latency_ms_per_case']['mean']} ms, "
          f"median {metrics['latency_ms_per_case']['median']} ms, "
          f"max {metrics['latency_ms_per_case']['max']} ms")
    print(f"tokens per case:      mean {metrics['tokens_per_case']['mean']}, "
          f"total {metrics['tokens_per_case']['total']}")
    print("")
    print("per category accuracy:")
    for category, value in metrics["per_category_accuracy"].items():
        print(f"  {category:<26}{value:.1%}")
    print("")
    print("per case:")
    for row in rows:
        mark = "ok " if row["correct"] else "MISS"
        print(f"  {mark} {row['id']:<10} expected={row['expected_relation']:<22} "
              f"observed={row['observed_relation']:<22} {row['decision_reason']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure the frozen evaluation corpus.")
    parser.add_argument("--pairs", default=str(DEFAULT_PAIRS))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--limit", type=int, default=0, help="evaluate only the first N cases")
    parser.add_argument("--only-category", default="", help="restrict to one category")
    parser.add_argument("--model", default="", help="override SOVRA_MODEL for this run")
    parser.add_argument("--extract-only", action="store_true",
                        help="run the deterministic baseline only (no inference)")
    args = parser.parse_args()

    if args.model:
        import os
        os.environ["SOVRA_MODEL"] = args.model

    pairs = load_pairs(Path(args.pairs))
    if args.only_category:
        pairs = [p for p in pairs if p.get("category") == args.only_category]
    if args.limit:
        pairs = pairs[: args.limit]
    if not pairs:
        print("ERROR: no cases selected", file=sys.stderr)
        return 3

    from sovra import load_settings

    settings = load_settings()
    print("Sovra Verify evaluation")
    print(f"  corpus:         {Path(args.pairs).relative_to(REPO_ROOT)} ({len(pairs)} case(s))")
    print(f"  provider:       {settings.primary.name} @ {settings.primary.base_url}")
    print(f"  model:          {settings.primary.model}")
    print(f"  mode:           {'extract-only (no inference)' if args.extract_only else 'full Apertus reasoning'}")
    print(f"  started:        {now()}")
    if not args.extract_only and not settings.primary.api_key:
        print("ERROR: no CSCS credential available; run with --extract-only to measure the "
              "deterministic baseline instead", file=sys.stderr)
        return 4

    rows: list[dict[str, Any]] = []
    started = time.time()
    tmp_root = Path(tempfile.mkdtemp(prefix="sovra-eval-"))
    try:
        for index, pair in enumerate(pairs, start=1):
            print(f"  [{index}/{len(pairs)}] {pair['id']} ({pair.get('category', '?')}) ...",
                  end="", flush=True)
            try:
                row = run_case(pair, settings, tmp_root, extract_only=args.extract_only)
            except Exception as exc:  # a broken case must not abort the measurement
                row = {
                    "id": pair["id"],
                    "category": pair.get("category", "uncategorised"),
                    "expected_relation": pair["expected_relation"],
                    "observed_relation": "failed",
                    "decision_reason": f"harness error: {type(exc).__name__}: {exc}",
                    "correct": False,
                    "synthetic": bool(pair.get("synthetic", True)),
                    "analysis_status": "failed",
                    "wall_ms": 0, "provider_calls": 0, "failed_calls": 1,
                    "models_used": [], "prompt_tokens": 0, "completion_tokens": 0,
                    "total_tokens": 0, "claim_count": 0, "candidate_pairs": 0,
                    "finding_count": 0, "conflict_findings": 0, "conflicts_with_citation": 0,
                    "evidence_spans": 0, "candidate_coverage": {}, "limitations": [],
                    "failures": [str(exc)], "findings": [], "provider_runs": [],
                }
            rows.append(row)
            print(f" {row['observed_relation']} ({row['wall_ms']} ms, {row['total_tokens']} tokens)")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    metrics = compute_metrics(rows)
    print_summary(metrics, rows)

    failures = [r for r in rows if r["observed_relation"] == "failed"]
    status = "complete" if not failures else "partial"
    payload = {
        "generated_at": now(),
        "duration_seconds": round(time.time() - started, 1),
        "run_status": status,
        "run_status_note": (
            "every case produced a judgement"
            if status == "complete"
            else f"{len(failures)} case(s) failed; the measured numbers below do not cover them"
        ),
        "corpus": {
            "path": str(Path(args.pairs).relative_to(REPO_ROOT)),
            "cases": len(pairs),
            "synthetic": all(bool(p.get("synthetic", True)) for p in pairs),
        },
        "configuration": {
            "provider": settings.primary.name,
            "base_url": settings.primary.base_url,
            "model": settings.primary.model,
            "extract_only": args.extract_only,
            "credential": settings.primary.public_view()["api_key"],
            "backup_enabled": settings.backup.enabled,
            "prompt_version": "see sovra.prompts.PROMPT_VERSION",
        },
        "metrics": metrics,
        "cases": [
            {k: v for k, v in row.items() if k != "provider_runs"}
            for row in rows
        ],
        "provider_ledger": [
            {
                "case_id": row["id"],
                "provider": run.get("provider"),
                "model": run.get("model"),
                "mode": run.get("mode"),
                "status": run.get("status"),
                "latency_ms": run.get("latency_ms"),
                "usage": run.get("usage"),
                "error_class": run.get("error_class"),
                "error_message": run.get("error_message"),
                "is_backup": run.get("is_backup"),
                "downgraded_from": run.get("downgraded_from"),
            }
            for row in rows
            for run in row.get("provider_runs", [])
        ],
        "limitations": [
            "Synthetic corpus: this does not establish general real-world performance.",
            "The model judges corpus consistency only; it makes no factual or legal determination.",
            "Cases that failed are reported as failures and are not removed from the denominator.",
        ],
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("")
    print(f"wrote {out.relative_to(REPO_ROOT)} (run_status={status})")
    return 0 if status == "complete" else 1


if __name__ == "__main__":
    sys.exit(main())
