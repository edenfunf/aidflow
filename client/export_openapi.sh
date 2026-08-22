#!/usr/bin/env bash
#
# Export the live OpenAPI document from the running FastAPI service.
#
# Usage:   docker compose up -d api && bash client/export_openapi.sh
# Env:     API_BASE_URL (default http://localhost:8000)

set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${SCRIPT_DIR}/../openapi/openapi.json"

mkdir -p "$(dirname "${OUT}")"
curl -sS "${API_BASE_URL}/openapi.json" -o "${OUT}"
echo "OpenAPI exported to ${OUT}"
