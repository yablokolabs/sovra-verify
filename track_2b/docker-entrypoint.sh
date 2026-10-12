#!/usr/bin/env bash
# Container entrypoint.
#
# Validates that the credential was injected as an environment variable, prints
# only a masked form of it, and then starts the API. It never reads a credential
# file: inside the container there is no credential file to read.
#
# If a command is supplied, this runs that command instead (so the image is
# usable for one-off tasks such as a smoke test).

set -euo pipefail

masked() {
  local value="${1:-}"
  if [[ -z "${value}" ]]; then
    printf '<unset>'
  elif [[ ${#value} -le 8 ]]; then
    printf '********(len=%s)' "${#value}"
  else
    printf '%s... (len=%s)' "${value:0:4}" "${#value}"
  fi
}

HOST="${SOVRA_HOST:-0.0.0.0}"
PORT="${SOVRA_PORT:-8080}"
WORK_DIR="${SOVRA_WORK_DIR:-/app/.sovra_work}"
MODEL="${SOVRA_MODEL:-swiss-ai/Apertus-v1.5-70B}"

echo "Sovra Verify container"
echo "  default model:    ${MODEL}"
echo "  primary provider: cscs (${SOVRA_CSCS_BASE_URL:-https://api.inference.cscs.ch/v1})"
echo "  listen:           ${HOST}:${PORT}"
echo "  work dir:         ${WORK_DIR}"

if [[ -n "${1:-}" ]]; then
  echo "  running supplied command: $*"
  exec "$@"
fi

echo "  CSCS_INFERENCE_API_KEY: $(masked "${CSCS_INFERENCE_API_KEY:-}")"
echo "  HUGGING_FACE_API_KEY:   $(masked "${HUGGING_FACE_API_KEY:-}")"

if [[ -z "${CSCS_INFERENCE_API_KEY:-}" ]]; then
  cat >&2 <<'EOF'

ERROR: CSCS_INFERENCE_API_KEY was not injected into this container.

The primary provider cannot start without it. The application deliberately does
not fall back to another provider or to a smaller model on its own.

Set it yourself, for example:

    export CSCS_INFERENCE_API_KEY="<your own key>"
    docker compose up

Judges must use their own credential. The developer's credential file is never
part of this image.
EOF
  exit 78
fi

if [[ "${SOVRA_ALLOW_BACKUP_FALLBACK:-0}" == "1" && -n "${HUGGING_FACE_API_KEY:-}" ]]; then
  echo "  backup fallback is ENABLED - note that the Hugging Face router does not"
  echo "  serve swiss-ai/Apertus-v1.5-70B for this model family, so a fallback can"
  echo "  only reach the 8B model. That change is recorded against every finding."
else
  echo "  backup fallback is off: a failed CSCS call will fail visibly"
fi

mkdir -p "${WORK_DIR}"

echo "  starting uvicorn; the UI is served at /app"
exec python3 -m uvicorn sovra.api:app_factory --factory --host "${HOST}" --port "${PORT}"
