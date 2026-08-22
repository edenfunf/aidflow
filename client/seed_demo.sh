#!/usr/bin/env bash
#
# AidFlow — load the 南投縣豪雨 demo scenario through the real pipeline.
#
# Usage:   bash client/seed_demo.sh            # idempotent: no-op if present
#          FORCE=1 bash client/seed_demo.sh    # build a fresh demo platform
# Env:     API_BASE_URL (default http://localhost:8000)
#          WEB_BASE_URL (default http://localhost:3000)
#          ADMIN_API_KEY (only if the API key gate is enabled)

set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
WEB_BASE_URL="${WEB_BASE_URL:-http://localhost:3000}"
FORCE="${FORCE:-0}"
KEY_HEADER=()
if [ -n "${ADMIN_API_KEY:-}" ]; then KEY_HEADER=(-H "X-API-Key: ${ADMIN_API_KEY}"); fi

grep_field() {
  sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" | head -n1
}

echo "==> 1. Health check (${API_BASE_URL})"
curl -sS "${API_BASE_URL}/v1/health" >/dev/null && echo "    API OK"

echo "==> 2. Seed demo scenario (plan → execute → reports → clusters → cases → dispatch)"
QS=""
if [ "${FORCE}" = "1" ]; then QS="?force=true"; fi
RESP="$(curl -sS -X POST "${KEY_HEADER[@]}" "${API_BASE_URL}/v1/demo/nantou${QS}")"
echo "    ${RESP}"
SLUG="$(printf '%s' "${RESP}" | grep_field slug)"
PID="$(printf '%s' "${RESP}" | grep_field platform_id)"

cat <<EOF

============================================================
 Demo scenario ready: 南投縣豪雨災情通報平台

 Public Disaster Portal:
 ${WEB_BASE_URL}/p/${SLUG}

 Report form (mobile first):
 ${WEB_BASE_URL}/p/${SLUG}/report

 Government Operations Console:
 ${WEB_BASE_URL}/console/platforms/${PID}

 Public API:
 ${API_BASE_URL}/v1/public/platforms/${SLUG}/situation
 ${API_BASE_URL}/v1/public/platforms/${SLUG}/map
 ${API_BASE_URL}/v1/public/platforms/${SLUG}/layers

 Swagger:
 ${API_BASE_URL}/docs
============================================================
EOF
