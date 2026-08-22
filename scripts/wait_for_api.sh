#!/usr/bin/env bash
#
# Poll the API health endpoint until it responds; exit 1 on timeout.
# Env: API_HEALTH_URL (default http://localhost:8000/v1/health), MAX_WAIT (default 60).

set -euo pipefail

API_HEALTH_URL="${API_HEALTH_URL:-http://localhost:8000/v1/health}"
MAX_WAIT="${MAX_WAIT:-60}"
INTERVAL=2

echo "Waiting for API at ${API_HEALTH_URL} (up to ${MAX_WAIT}s)..."
elapsed=0
while [ "${elapsed}" -lt "${MAX_WAIT}" ]; do
  if curl -sf "${API_HEALTH_URL}" >/dev/null 2>&1; then
    echo "API is ready"
    exit 0
  fi
  sleep "${INTERVAL}"
  elapsed=$((elapsed + INTERVAL))
done

echo "ERROR: API did not become ready within ${MAX_WAIT}s" >&2
exit 1
