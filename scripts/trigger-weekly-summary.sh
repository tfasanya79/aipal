#!/usr/bin/env bash
set -euo pipefail

API_ENV_FILE="${AIPAL_ENV_FILE:-/opt/aipal-v2/apps/api/.env}"

if [[ ! -f "$API_ENV_FILE" ]]; then
  echo "Missing env file: $API_ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck source=/dev/null
source "$API_ENV_FILE"
set +a

if [[ -z "${AIPAL_INTERNAL_SECRET:-}" ]]; then
  echo "AIPAL_INTERNAL_SECRET is not set in $API_ENV_FILE" >&2
  exit 1
fi

curl -sf -X POST \
  "http://127.0.0.1:8102/api/v2/jobs/enqueue-weekly-summaries" \
  -H "X-Internal-Secret: ${AIPAL_INTERNAL_SECRET}"

echo "Triggered weekly summary enqueue successfully."
