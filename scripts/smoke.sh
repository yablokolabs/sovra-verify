#!/usr/bin/env bash
# Real provider smoke test.
#
# Proves inference actually works before any claim about it is made:
#   1. GET /models on CSCS and list what the credential can reach;
#   2. one tiny real chat request against the default model (Apertus 1.5 70B),
#      recording the returned model, latency and token usage;
#   3. the smoke pair - a short synthetic agreement/policy pair with
#      incompatible payment terms under the same scope - through the real
#      comparison prompt, with deterministic citation resolution;
#   4. the full two-document pipeline, end to end.
#
# A successful /models call is never treated as proof of inference.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

PYTHON="${SOVRA_PYTHON:-python3}"
if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  PYTHON="${SOVRA_PYTHON:-${REPO_ROOT}/.venv/bin/python}"
fi

echo "== Sovra Verify smoke test =="
echo "   python: ${PYTHON}"
echo "   repo:   ${REPO_ROOT}"

echo ""
echo "-- step 1-3: provider verification (real requests) --"
"${PYTHON}" scripts/verify_providers.py "$@"

echo ""
echo "-- step 4: full pipeline over the two-document smoke corpus --"
PYTHONPATH="${REPO_ROOT}/track_2b/backend" \
SOVRA_WORK_DIR="${SOVRA_WORK_DIR:-${REPO_ROOT}/.sovra_work}" \
  "${PYTHON}" - <<'PY'
import json
import shutil
import sys
from pathlib import Path

repo = Path.cwd()
sys.path.insert(0, str(repo / "track_2b" / "backend"))

from sovra import Storage, SovraService, load_settings, summarise_runs
from sovra.providers import ProviderRouter

settings = load_settings()
work = repo / ".sovra_work" / "smoke"
if work.exists():
    shutil.rmtree(work)
settings.work_dir = work

storage = Storage(work / "smoke.sqlite3")
service = SovraService(settings, storage, ProviderRouter(settings))

corpus = [
    repo / "track_2b" / "data" / "demo" / "01_master_supply_agreement.txt",
    repo / "track_2b" / "data" / "demo" / "02_accounts_payable_policy.txt",
]
missing = [str(p) for p in corpus if not p.is_file()]
if missing:
    print("FAIL: demo fixtures missing: " + ", ".join(missing))
    raise SystemExit(1)

document_ids = []
for path in corpus:
    ingested = service.ingest(filename=path.name, data=path.read_bytes(), mime="text/plain")
    document_ids.append(ingested.document.id)
    print(f"  ingested {path.name}: {len(ingested.passages)} passage(s), "
          f"status {ingested.document.extraction_status.value}")

analysis = service.analyse(document_ids=document_ids, force=True)
usage = summarise_runs(analysis.provider_runs)
conflicts = [f for f in analysis.findings if f.relation.value == "potential_conflict"]
cited = [f for f in conflicts if f.evidence]

print(f"  status:   {analysis.status.value}")
print(f"  claims:   {analysis.claim_count}")
print(f"  pairs:    {analysis.pair_count}")
print(f"  findings: {len(analysis.findings)} ({len(conflicts)} potential conflict, {len(cited)} with a resolved citation)")
print(f"  usage:    {usage['calls']} call(s), {usage['total_tokens']} token(s), "
      f"{usage['latency_ms_total']} ms, {usage['failed_calls']} failed")
print(f"  models:   {', '.join(usage['models']) or 'none'}")
for failure in analysis.failures:
    print(f"  failure:  {failure}")

ok = analysis.status.value in ("complete", "partial") and bool(analysis.provider_runs) and len(cited) >= 1
if not ok:
    print("")
    print("FAIL: expected at least one potential conflict with a resolved citation from a real call.")
    print("      An empty result here means 'not evaluated', not 'no inconsistencies'.")
    raise SystemExit(1)

print("")
print("PASS: real inference returned a usable judgement with resolved citations.")
print(json.dumps({"analysis_id": analysis.id, "status": analysis.status.value,
                  "conflicts_with_citation": len(cited), "usage": usage}, indent=2))
PY

echo ""
echo "== smoke test complete =="
