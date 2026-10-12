#!/usr/bin/env bash
# End-to-end run through the real HTTP interface.
#
# Uploads the demo corpus, runs a real Apertus analysis, reads the findings back,
# exports all three formats, and verifies that no served route contains a footer.
#
# Everything is exercised over HTTP on purpose: a passing unit test does not
# prove that the interface a reviewer actually uses behaves correctly.
#
# Usage:
#   scripts/run_e2e.sh                 start a local host process and test it
#   scripts/run_e2e.sh --base URL      test an already-running instance
#
# `--base` is how the container run is verified: scripts/e2e_container.sh starts
# the container and then hands its URL to this same script, so the container and
# the host process are exercised by exactly the same sequence, not by two
# implementations that could drift apart.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

PYTHON="${SOVRA_PYTHON:-python3}"
if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  PYTHON="${SOVRA_PYTHON:-${REPO_ROOT}/.venv/bin/python}"
fi

PORT="${SOVRA_E2E_PORT:-8099}"
BASE="http://127.0.0.1:${PORT}"
WORK="${SOVRA_E2E_WORK:-${REPO_ROOT}/.sovra_work/e2e}"
EXPORT_DIR="${WORK}/exports"
LOG="${WORK}/server.log"
SERVER_PID=""
EXTERNAL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base)
      BASE="${2:?--base needs a URL}"
      # Keep PORT informative; the URL itself is what every request uses.
      extracted="$(printf '%s' "${BASE}" | sed -E 's#^[a-z]+://[^:/]+:([0-9]+).*#\1#')"
      if [[ "${extracted}" =~ ^[0-9]+$ ]]; then PORT="${extracted}"; fi
      EXTERNAL=1
      shift 2
      ;;
    -h|--help)
      sed -n '2,20p' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

cleanup() {
  if [[ -n "${SERVER_PID}" ]] && kill -0 "${SERVER_PID}" 2>/dev/null; then
    echo ""
    echo "-- stopping the API (pid ${SERVER_PID}) --"
    kill "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

rm -rf "${WORK}"
mkdir -p "${EXPORT_DIR}"

echo "== Sovra Verify end-to-end run =="
echo "   python: ${PYTHON}"
echo "   base:   ${BASE}"

if [[ "${EXTERNAL}" -eq 1 ]]; then
  echo ""
  echo "-- using the already-running instance at ${BASE} --"
else
  echo ""
  echo "-- starting the API --"
  PYTHONPATH="${REPO_ROOT}/track_2b/backend" \
  SOVRA_WORK_DIR="${WORK}/store" \
  SOVRA_CSCS_BASE_URL="${SOVRA_CSCS_BASE_URL:-https://api.inference.cscs.ch/v1}" \
    "${PYTHON}" -m uvicorn sovra.api:app_factory --factory \
      --host 127.0.0.1 --port "${PORT}" >"${LOG}" 2>&1 &
  SERVER_PID=$!
fi

echo "   waiting for ${BASE}/health"
ready=0
for _ in $(seq 1 90); do
  if curl -fsS "${BASE}/health" >/dev/null 2>&1; then
    ready=1
    break
  fi
  if [[ "${EXTERNAL}" -eq 0 ]] && ! kill -0 "${SERVER_PID}" 2>/dev/null; then
    echo "ERROR: the API exited during start-up. Last log lines:" >&2
    tail -n 40 "${LOG}" >&2
    exit 1
  fi
  sleep 1
done
if [[ "${ready}" -ne 1 ]]; then
  echo "ERROR: the API did not become ready in 90 s. Last log lines:" >&2
  [[ -f "${LOG}" ]] && tail -n 40 "${LOG}" >&2
  exit 1
fi
echo "   API is ready"

echo ""
echo "-- reported application configuration --"
curl -fsS "${BASE}/config" | "${PYTHON}" -c '
import json, sys
cfg = json.load(sys.stdin)
# Plain concatenation, never an escape and never a nested quote: this whole block
# is one single-quoted shell argument, so a backslash reaches Python literally and
# a single quote would end the argument. Both are avoided here on purpose.
print("   primary provider: " + cfg["primary_provider"])
print("   default model:    " + cfg["default_model"])
print("   backup provider:  " + cfg["backup_provider"] + " / " + cfg["backup_model"]
      + " (fallback enabled: " + str(cfg["backup_fallback_enabled"]) + ")")
print("   optional 8B:      " + str(cfg["optional_8b_enabled"]))
print("   limits:           " + json.dumps(cfg["limits"]))
'

echo ""
echo "-- uploading the demo corpus --"
UPLOAD_FILE="${WORK}/upload.json"
curl -fsS -o "${UPLOAD_FILE}" -X POST "${BASE}/documents" \
  -F "files=@track_2b/data/demo/01_master_supply_agreement.txt" \
  -F "files=@track_2b/data/demo/02_accounts_payable_policy.txt" \
  -F "files=@track_2b/data/demo/03_invoice_INV-2026-0417.txt"
"${PYTHON}" - "${UPLOAD_FILE}" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1]))
for document in payload["saved"]:
    print(f"   saved {document['name']}: {document['passages']} passage(s), "
          f"extraction {document['extraction_status']}")
for rejected in payload["rejected"]:
    print(f"   rejected {rejected['name']}: {rejected['message']}")
PY

FIRST_DOC_ID="$("${PYTHON}" - "${UPLOAD_FILE}" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1]))
print(payload["saved"][0]["id"] if payload["saved"] else "")
PY
)"

echo ""
echo "-- running a real analysis (this calls CSCS) --"
IDS_JSON="$("${PYTHON}" - "${UPLOAD_FILE}" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1]))
print(json.dumps({"document_ids": [d["id"] for d in payload["saved"]], "force": True}))
PY
)"
ANALYSIS_FILE="${WORK}/analysis.json"
curl -fsS -o "${ANALYSIS_FILE}" -X POST "${BASE}/analyses" \
  -H 'Content-Type: application/json' -d "${IDS_JSON}"

ANALYSIS_ID="$("${PYTHON}" - "${ANALYSIS_FILE}" <<'PY'
import json, sys
view = json.load(open(sys.argv[1]))
analysis = view["analysis"]
print(analysis["id"])
print(f"   status:   {analysis['status']}", file=sys.stderr)
print(f"   provider: {analysis['provider']} / {analysis['model']}", file=sys.stderr)
print(f"   claims:   {analysis['claim_count']}, pairs: {analysis['pair_count']}", file=sys.stderr)
print(f"   findings: {len(analysis['findings'])}", file=sys.stderr)
print(f"   usage:    {json.dumps(view['usage'])}", file=sys.stderr)
print(f"   warning:  {view['warning']}", file=sys.stderr)
for failure in analysis["failures"]:
    print(f"   failure:  {failure}", file=sys.stderr)
PY
)"
echo "   analysis id: ${ANALYSIS_ID}"

echo ""
echo "-- reading the findings back over HTTP --"
curl -fsS "${BASE}/analyses/${ANALYSIS_ID}" | "${PYTHON}" -c '
import json, sys
view = json.load(sys.stdin)
analysis = view["analysis"]
print("   relation counts: " + json.dumps(view["relation_counts"]))
for index, finding in enumerate(analysis["findings"], start=1):
    line = "   [" + str(index) + "] " + finding["relation"]
    line += " (review " + finding["review_status"] + ")"
    line += " evidence=" + str(len(finding["evidence"]))
    print(line)
    spans = ", ".join(
        "doc " + c["document_id"][:8] + " p" + str(c["page"])
        + " [" + str(c["start_offset"]) + "," + str(c["end_offset"]) + "]"
        for c in finding["evidence"]
    )
    print("        spans: " + (spans if spans else "<none>"))
print("   limitations recorded: " + str(len(analysis["limitations"])))
'

echo ""
echo "-- fetching claims and a finding with its review history --"
curl -fsS "${BASE}/analyses/${ANALYSIS_ID}/claims" | "${PYTHON}" -c '
import json, sys
claims = json.load(sys.stdin)["claims"]
resolved = [c for c in claims if c["extraction_status"] == "ok"]
print(f"   claims: {len(claims)} ({len(resolved)} resolved, {len(claims) - len(resolved)} unresolved)")
'

FIRST_FINDING="$(curl -fsS "${BASE}/analyses/${ANALYSIS_ID}" | "${PYTHON}" -c '
import json, sys
view = json.load(sys.stdin)
findings = view["analysis"]["findings"]
print(findings[0]["id"] if findings else "")
')"
if [[ -n "${FIRST_FINDING}" ]]; then
  curl -fsS "${BASE}/findings/${FIRST_FINDING}" | "${PYTHON}" -c '
import json, sys
payload = json.load(sys.stdin)
finding = payload["finding"]
print("   finding " + finding["id"] + ": relation=" + finding["relation"]
      + ", review history entries=" + str(len(payload["review_history"])))
'
  echo "   recording a human review decision (confirmed_for_review)"
  curl -fsS -o /dev/null -X POST "${BASE}/findings/${FIRST_FINDING}/reviews" \
    -H 'Content-Type: application/json' \
    -d '{"status":"confirmed_for_review","note":"e2e run: reviewer confirmed the citation resolves","reviewer":"e2e"}'
  echo "   review recorded"
else
  echo "   no finding was produced, so review and export were not exercised"
fi

echo ""
echo "-- exporting every format --"
echo "   these are the exact bytes a reviewer downloads; they are scanned for footer markers below"
curl -fsS -o "${EXPORT_DIR}/analysis.json" "${BASE}/analyses/${ANALYSIS_ID}/export?format=json"
curl -fsS -o "${EXPORT_DIR}/report.md" "${BASE}/analyses/${ANALYSIS_ID}/export?format=markdown"
curl -fsS -o "${EXPORT_DIR}/bundle.zip" "${BASE}/analyses/${ANALYSIS_ID}/export?format=zip"
ls -l "${EXPORT_DIR}" | tail -n +2 | awk '{printf "   %s bytes  %s\n", $5, $9}'

echo ""
echo "-- no-footer inspection over every served route --"
# The schema lists templated routes, which the checker must skip because it has no
# live id. This run has the ids, so it supplies the concrete paths: the analysis
# page, its claims, the finding page and the document page are exactly the screens
# a reviewer looks at, and they would otherwise go unchecked.
# Written as explicit `if` blocks, not `[[ ... ]] && ...` one-liners: under
# `set -e` a false test in a bare `&&` list exits the whole script.
NO_FOOTER_ROUTES=(--route /app)
if [[ -n "${ANALYSIS_ID:-}" ]]; then
  NO_FOOTER_ROUTES+=(--route "/analyses/${ANALYSIS_ID}" --route "/analyses/${ANALYSIS_ID}/claims")
fi
if [[ -n "${FIRST_FINDING:-}" ]]; then
  NO_FOOTER_ROUTES+=(--route "/findings/${FIRST_FINDING}")
fi
if [[ -n "${FIRST_DOC_ID:-}" ]]; then
  NO_FOOTER_ROUTES+=(--route "/documents/${FIRST_DOC_ID}")
fi
"${PYTHON}" scripts/check_no_footer.py --root "${REPO_ROOT}" --url "${BASE}" "${NO_FOOTER_ROUTES[@]}"

echo ""
echo "-- generated document inspection --"
"${PYTHON}" - "${EXPORT_DIR}" <<'PY'
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "scripts"))
out = Path(sys.argv[1])
findings = 0

from check_no_footer import scan_text  # reuse the exact marker set

for path in sorted(out.iterdir()):
    if path.suffix in {".json", ".md"}:
        hits = scan_text(path.read_text(encoding="utf-8", errors="replace"), str(path.name))
    elif path.suffix == ".zip":
        import zipfile

        hits = []
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if name.endswith((".json", ".md")):
                    text = archive.read(name).decode("utf-8", errors="replace")
                    hits.extend(scan_text(text, f"{path.name}!{name}"))
    else:
        continue
    findings += len(hits)
    print(f"   {path.name}: {'FAIL' if hits else 'clean'}")

if findings:
    print("FAIL: a generated document contains a footer marker")
    raise SystemExit(1)
print("   all generated documents are footer-free")
PY

echo ""
echo "-- end-to-end run complete --"
echo "   analysis: ${ANALYSIS_ID}"
echo "   exports:  ${EXPORT_DIR}"
if [[ "${EXTERNAL}" -eq 1 ]]; then
  echo "   instance: ${BASE} (started outside this script; left running)"
else
  echo "   notes:    the API log is at ${LOG} (prompt contents are not logged)"
fi
