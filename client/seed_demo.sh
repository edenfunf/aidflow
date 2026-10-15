#!/usr/bin/env bash
#
# AidFlow — load the 南投縣豪雨 demo scenario through the real pipeline.
#
# Usage:   bash client/seed_demo.sh            # idempotent: no-op if present
#          FORCE=1 bash client/seed_demo.sh    # build a fresh demo platform
# Env:     API_BASE_URL (default http://localhost:8000)
#          WEB_BASE_URL (default http://localhost:3000)
#          ADMIN_USERNAME / ADMIN_PASSWORD  — a 系統管理者 account (login), or
#          ADMIN_API_KEY                     — the service key, when configured

set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
WEB_BASE_URL="${WEB_BASE_URL:-http://localhost:3000}"
FORCE="${FORCE:-0}"
grep_field() {
  sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" | head -n1
}

KEY_HEADER=()
if [ -n "${ADMIN_API_KEY:-}" ]; then
  KEY_HEADER=(-H "X-API-Key: ${ADMIN_API_KEY}")
elif [ -n "${ADMIN_USERNAME:-}" ]; then
  TOKEN="$(curl -sS -X POST -H 'Content-Type: application/json' \
    -d "{\"username\":\"${ADMIN_USERNAME}\",\"password\":\"${ADMIN_PASSWORD:-}\"}" \
    "${API_BASE_URL}/v1/auth/login" | grep_field token)"
  if [ -z "${TOKEN}" ]; then echo "login failed for ${ADMIN_USERNAME}" >&2; exit 1; fi
  KEY_HEADER=(-H "Authorization: Bearer ${TOKEN}")
fi

echo "==> 1. Health check (${API_BASE_URL})"
curl -sS "${API_BASE_URL}/v1/health" >/dev/null && echo "    API OK"

echo "==> 2. Seed demo scenario (reports → clusters → cases → review → EMIC / community)"
QS=""
if [ "${FORCE}" = "1" ]; then QS="?force=true"; fi
RESP="$(curl -sS -X POST "${KEY_HEADER[@]}" "${API_BASE_URL}/v1/demo/nantou${QS}")"
echo "    ${RESP}"
SLUG="$(printf '%s' "${RESP}" | grep_field slug)"
PID="$(printf '%s' "${RESP}" | grep_field platform_id)"

cat <<EOF

============================================================
 Demo scenario ready: 南投縣豪雨災情（示範）

 Public Disaster Portal:
 ${WEB_BASE_URL}/p/${SLUG}

 Report form (mobile first):
 ${WEB_BASE_URL}/p/${SLUG}/report

 政府管理後台 (login required):
 ${WEB_BASE_URL}/console/platforms/${PID}

 Public API:
 ${API_BASE_URL}/v1/public/platforms/${SLUG}/situation
 ${API_BASE_URL}/v1/public/platforms/${SLUG}/map
 ${API_BASE_URL}/v1/public/platforms/${SLUG}/layers

 Swagger:
 ${API_BASE_URL}/docs
============================================================
EOF
