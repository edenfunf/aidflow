#!/usr/bin/env bash
#
# Local pre-submission check — runs the same steps as CI.
#
# Usage:   bash scripts/preflight.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if command -v python3 >/dev/null 2>&1; then PY=python3;
elif command -v python >/dev/null 2>&1; then PY=python;
else echo "ERROR: python not found" >&2; exit 1; fi

echo "==> 1/7 docker compose config"
docker compose config >/dev/null
echo "    compose config OK"

echo "==> 2/7 docker compose up -d --build db api"
docker compose up -d --build db api

echo "==> 3/7 wait for API health"
bash scripts/wait_for_api.sh

echo "==> 4/7 backend tests (pytest)"
docker compose exec -T api pytest -q

echo "==> 5/7 export OpenAPI"
bash client/export_openapi.sh

echo "==> 6/7 validate JSON schemas + samples"
"${PY}" scripts/validate_schemas.py

echo "==> 7/7 build web image (no start)"
# Build only — starting web would fail if host port 3000 is busy.
docker compose build web

echo
echo "Preflight passed. AidFlow is ready for submission."
