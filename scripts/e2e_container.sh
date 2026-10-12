#!/usr/bin/env bash
# Fresh-container end-to-end verification.
#
# Proves four things a host-process run cannot:
#   1. the container image starts and serves the API and the UI with no host
#      Python, no host virtualenv and no source checkout on PYTHONPATH;
#   2. the whole HTTP flow works through the container's published port, by
#      running the same scripts/run_e2e.sh sequence the host run uses;
#   3. the credential reaches the container only through its environment, and no
#      secret is baked into the image config or into any image layer;
#   4. every served route and every generated document is footer-free.
#
# Credential handling: scripts/launch.sh reads only the named application
# variables out of the Hermes credential file, exports them for the duration of
# its own process, and lets compose interpolate them from that environment. No
# value is printed and none is placed on a command line. Every step after start-up
# uses plain `docker` against the container id instead of compose, because
# compose.yaml requires CSCS_INFERENCE_API_KEY for *any* invocation: running
# `docker compose ps` from this shell would either fail or force the value onto a
# command line, and neither is acceptable.
#
# The layer probe runs inside the container and uses the container's own
# environment variable, so the secret never has to be exported into this shell.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

PYTHON="${SOVRA_PYTHON:-python3}"
if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  PYTHON="${SOVRA_PYTHON:-${REPO_ROOT}/.venv/bin/python}"
fi

PORT="${SOVRA_E2E_PORT:-8099}"
BASE="http://127.0.0.1:${PORT}"
IMAGE="${SOVRA_IMAGE:-sovra-verify:local}"
PROJECT="${SOVRA_COMPOSE_PROJECT:-sovra-verify}"
KEEP=0
CONTAINER_ID=""

usage() {
  sed -n '2,22p' "${BASH_SOURCE[0]}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) PORT="${2:?--port needs a number}"; BASE="http://127.0.0.1:${PORT}"; shift 2 ;;
    --keep) KEEP=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

command -v docker >/dev/null 2>&1 || { echo "ERROR: docker is not available" >&2; exit 5; }

echo "== Sovra Verify fresh-container end-to-end run =="
echo "   image: ${IMAGE}"
echo "   port:  ${PORT}"

echo ""
echo "-- confirming the image exists --"
if ! docker image inspect "${IMAGE}" >/dev/null 2>&1; then
  echo "ERROR: image ${IMAGE} not found. Build it first: make docker-build" >&2
  exit 5
fi
echo "   image present"

echo ""
echo "-- image config audit --"
# The image config records only the Dockerfile's own ENV/ARG values. A credential
# supplied at run time must not appear here, and no credential variable should be
# present at all, because the launcher supplies them at run time.
IMAGE_ENV="$(docker image inspect --format '{{json .Config.Env}}' "${IMAGE}")"
SUSPECT="$(printf '%s' "${IMAGE_ENV}" | "${PYTHON}" -c '
import json, sys
prefixes = ("CSCS_INFERENCE_API_KEY", "HUGGING_FACE_API_KEY", "ELEVENLABS", "SOVRA_SECRET")
found = [entry.split("=", 1)[0] for entry in json.load(sys.stdin)
         if entry.split("=", 1)[0].startswith(prefixes)]
print(",".join(found))
')"
if [[ -n "${SUSPECT}" ]]; then
  echo "FAIL: the image config carries credential variable(s): ${SUSPECT}" >&2
  exit 1
fi
echo "   image config carries no credential variable"

cleanup() {
  if [[ -z "${CONTAINER_ID}" ]]; then
    return
  fi
  if [[ "${KEEP}" -eq 1 ]]; then
    echo ""
    echo "-- --keep given: leaving the container running (${BASE}) --"
    echo "   container: ${CONTAINER_ID}"
    return
  fi
  echo ""
  echo "-- stopping the container --"
  docker stop "${CONTAINER_ID}" >/dev/null 2>&1 || true
  docker rm "${CONTAINER_ID}" >/dev/null 2>&1 || true
  # The named volume is kept on purpose: it holds the application's own work
  # directory, not credentials. Remove it with `docker volume rm` if you want a
  # truly clean slate.
  echo "   stopped and removed ${CONTAINER_ID}; the work volume was kept"
}
trap cleanup EXIT

echo ""
echo "-- starting a fresh container through scripts/launch.sh --"
SOVRA_PORT="${PORT}" SOVRA_HOST_PORT="${PORT}" \
  "${REPO_ROOT}/scripts/launch.sh" --docker --detach --port "${PORT}"

CONTAINER_ID="$(docker ps -q --filter "label=com.docker.compose.project=${PROJECT}" | head -n 1)"
if [[ -z "${CONTAINER_ID}" ]]; then
  echo "ERROR: no running container found for project ${PROJECT}" >&2
  docker ps --format 'table {{.ID}}\t{{.Names}}\t{{.Status}}' >&2
  exit 1
fi

echo ""
echo "-- container status --"
docker ps --filter "id=${CONTAINER_ID}" --format '   {{.Names}}  {{.Image}}  {{.Status}}  {{.Ports}}'

echo ""
echo "-- layer audit: no credential value inside the image content --"
# Runs inside the container against /app, using the container's own environment
# variable. Prints only a count, so the value is never revealed.
docker exec -i "${CONTAINER_ID}" sh -s <<'PROBE'
if [ -z "${CSCS_INFERENCE_API_KEY:-}" ]; then
  echo "   credential not present in the container environment; audit inconclusive"
  exit 1
fi
hits=$(grep -rlF -- "$CSCS_INFERENCE_API_KEY" /app 2>/dev/null | head -n 5 || true)
if [ -n "$hits" ]; then
  echo "   FAIL: the credential value appears in files under /app:"
  printf '   %s\n' "$hits"
  exit 1
fi
echo "   0 file(s) under /app contain the credential value"
PROBE

echo ""
echo "-- credential reachability inside the container --"
docker exec -i "${CONTAINER_ID}" sh -s <<'REACH'
for name in CSCS_INFERENCE_API_KEY HUGGING_FACE_API_KEY; do
  eval "value=\${${name}:-}"
  if [ -n "$value" ]; then
    printf '   %s: present (len=%s)\n' "$name" "${#value}"
  else
    printf '   %s: not set\n' "$name"
  fi
done
REACH

echo ""
echo "-- the HTTP end-to-end suite, run against the container --"
SOVRA_E2E_PORT="${PORT}" SOVRA_E2E_WORK="${REPO_ROOT}/.sovra_work/e2e_container" \
  bash "${REPO_ROOT}/scripts/run_e2e.sh" --base "${BASE}"

echo ""
echo "-- end-to-end run complete --"
echo "   the container served the full flow on ${BASE}"
