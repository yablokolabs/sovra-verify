#!/usr/bin/env bash
# Sovra Verify local launcher.
#
# Purpose: read ONLY the named application credentials out of the Hermes
# credential file and inject them into the application, either as a Docker
# container environment or as a local process environment.
#
# Hard rules enforced here:
#   * the credential file is never sourced, never cat'd and never copied;
#   * only two named entries are ever read, never the whole file;
#   * no credential value is printed, echoed, logged or placed on a command
#     line - only the variable NAME is passed to Docker;
#   * the file itself is never mounted into a container or baked into an image.
#
# Judges: do not use this script. Supply your own credentials in the
# environment (CSCS_INFERENCE_API_KEY, optionally HUGGING_FACE_API_KEY), or
# point SOVRA_LOCAL_BASE_URL at your own Apertus endpoint.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${SOVRA_HERMES_ENV:-${HOME}/.hermes/.env}"
PORT="${SOVRA_PORT:-8080}"
KEYS=(CSCS_INFERENCE_API_KEY HUGGING_FACE_API_KEY)
MODE="docker"
DETACH=0
BUILD=0

usage() {
  cat <<'USAGE'
Sovra Verify launcher

  scripts/launch.sh [options]

Options:
  --local         run the app directly on this host (no Docker)
  --docker        run in Docker via docker compose (default)
  --build         rebuild the container image before starting
  --detach        start in the background and return
  --port N        host port (default 8080, or SOVRA_PORT)
  -h, --help      show this help

The CSCS credential is required. The Hugging Face credential is injected only
if present; the backup provider still stays disabled unless SOVRA_BACKUP_ENABLED=1
and SOVRA_ALLOW_BACKUP_FALLBACK=1 are also set, because the router does not
serve Apertus 1.5 70B.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --local)   MODE="local"; shift ;;
    --docker)  MODE="docker"; shift ;;
    --build)   BUILD=1; shift ;;
    --detach)  DETACH=1; shift ;;
    --port)    PORT="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

masked() {
  local value="$1"
  if [[ -z "${value}" ]]; then
    printf '<unset>'
  elif [[ ${#value} -le 8 ]]; then
    printf '********(len=%s)' "${#value}"
  else
    printf '%s... (len=%s)' "${value:0:4}" "${#value}"
  fi
}

if [[ ! -f "${ENV_FILE}" ]]; then
  cat >&2 <<EOF
ERROR: credential file not found at ${ENV_FILE}

This host has no Hermes credential file. That is expected when the application
runs somewhere else. Either:
  * set SOVRA_HERMES_ENV to the correct path, or
  * export CSCS_INFERENCE_API_KEY (and optionally HUGGING_FACE_API_KEY) yourself
    before running this script.

Never copy the credential file into this repository.
EOF
  exit 3
fi

echo "Sovra Verify launcher"
echo "  credential file: ${ENV_FILE}"
echo "  mode:            ${MODE}"
echo "  port:            ${PORT}"
echo "  reading only:    ${KEYS[*]}"

# Read the named entries with a dotenv parser. Only NAME=value lines for the
# allowlisted names reach stdout; everything else goes to stderr.
LOADED_KEYS=()
while IFS='=' read -r name value; do
  [[ -z "${name}" ]] && continue
  export "${name}=${value}"
  LOADED_KEYS+=("${name}")
  printf '  injecting %s = %s\n' "${name}" "$(masked "${value}")"
done < <(python3 - "${ENV_FILE}" "${KEYS[@]}" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
wanted = list(sys.argv[2:])

def parse(text: str) -> dict[str, str]:
    """Minimal dotenv parser used when python-dotenv is unavailable."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if key:
            values[key] = val
    return values

try:
    from dotenv import dotenv_values  # type: ignore

    parsed = {k: v for k, v in dotenv_values(str(path)).items() if isinstance(v, str)}
except Exception:
    # ImportError, or anything the parser raises: fall back without echoing it.
    try:
        parsed = parse(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        parsed = {}

found = 0
for name in wanted:
    value = (parsed.get(name) or "").strip()
    if not value:
        print(f"  not present in the credential file: {name}", file=sys.stderr)
        continue
    if not re.fullmatch(r"[A-Za-z0-9_\-.:/+=]{8,512}", value):
        print(f"  refused {name}: value is not a well-formed credential", file=sys.stderr)
        continue
    found += 1
    sys.stdout.write(f"{name}={value}\n")
if found == 0:
    print("  no allowlisted credential could be read", file=sys.stderr)
PY
)

if [[ ${#LOADED_KEYS[@]} -eq 0 ]]; then
  echo "ERROR: no allowlisted credential could be read from ${ENV_FILE}" >&2
  echo "       expected at least CSCS_INFERENCE_API_KEY" >&2
  exit 4
fi

have_key() {
  local wanted="$1" key
  for key in "${LOADED_KEYS[@]}"; do
    [[ "${key}" == "${wanted}" ]] && return 0
  done
  return 1
}

if ! have_key CSCS_INFERENCE_API_KEY && [[ "${MODE}" == "docker" ]]; then
  echo "ERROR: CSCS_INFERENCE_API_KEY is required for the primary provider." >&2
  echo "       The app will not fall back to another provider silently." >&2
  exit 4
fi

if [[ "${MODE}" == "local" ]]; then
  echo "  starting the API on http://127.0.0.1:${PORT} (UI at /app)"
  PYTHONPATH="${REPO_ROOT}/track_2b/backend" \
  SOVRA_WORK_DIR="${SOVRA_WORK_DIR:-${REPO_ROOT}/.sovra_work}" \
    exec python3 -m uvicorn sovra.api:app_factory --factory \
      --host 127.0.0.1 --port "${PORT}"
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is not available. Re-run with --local for a host process." >&2
  exit 5
fi

COMPOSE=(docker compose -f "${REPO_ROOT}/compose.yaml")
export SOVRA_HOST_PORT="${PORT}"

if [[ "${BUILD}" -eq 1 ]]; then
  echo "  building the image (secrets are injected at run time, never baked in)"
  "${COMPOSE[@]}" build
fi

# Only the variable NAMES are passed on the command line. Values travel through
# the environment, so no credential ever appears in a process argument list.
PASSTHROUGH=(-e CSCS_INFERENCE_API_KEY)
if have_key HUGGING_FACE_API_KEY; then
  PASSTHROUGH+=(-e HUGGING_FACE_API_KEY)
else
  echo "  HUGGING_FACE_API_KEY not injected; the backup provider stays unavailable"
fi

if [[ "${DETACH}" -eq 1 ]]; then
  # `docker compose up` has no per-variable flag, so the values reach the
  # container through the environment exported above: compose interpolates
  # ${CSCS_INFERENCE_API_KEY} in compose.yaml from the shell environment. No
  # value is ever placed on a command line, and the credential file is not
  # referenced by compose at all (there is no env_file).
  echo "  starting detached; UI at http://127.0.0.1:${PORT}/app"
  "${COMPOSE[@]}" up -d
else
  echo "  starting in the foreground; UI at http://127.0.0.1:${PORT}/app"
  echo "  press Ctrl-C to stop"
  # `run -e` passes the variable NAME only; the value is inherited from the
  # environment, so it never appears in a process argument list.
  exec "${COMPOSE[@]}" run --rm --service-ports "${PASSTHROUGH[@]}" sovra
fi
