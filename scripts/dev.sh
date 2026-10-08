#!/usr/bin/env bash
# Run Charon against the fake Download Station locally, without Docker.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
VAR="$ROOT/var"
CHARON_PORT="${CHARON_PORT:-8080}"
FAKE_DS_PORT="${FAKE_DS_PORT:-5000}"
mkdir -p "$VAR/data" "$VAR/downloads" "$VAR/library"

FAKE_DS_DOWNLOAD_DIR="$VAR/downloads" \
FAKE_DS_DURATION_SECONDS="${FAKE_DS_DURATION_SECONDS:-5}" \
    "$PY" -m uvicorn fake_ds.app:create_app_from_env --factory \
    --host 127.0.0.1 --port "$FAKE_DS_PORT" --log-level warning &
FAKE_PID=$!
trap 'kill "$FAKE_PID" 2>/dev/null || true' EXIT

echo "fake Download Station: http://127.0.0.1:$FAKE_DS_PORT  (downloads -> $VAR/downloads)"
echo "charon:                http://127.0.0.1:$CHARON_PORT  (admin API key: ${CHARON_ADMIN_API_KEY:-dev-key})"
echo "fake TMDB:             http://127.0.0.1:$FAKE_DS_PORT/tmdb  (title lookups)"

cd "$ROOT"
CHARON_HOST=127.0.0.1 \
CHARON_PORT="$CHARON_PORT" \
CHARON_ADMIN_API_KEY="${CHARON_ADMIN_API_KEY:-dev-key}" \
CHARON_DB_PATH="$VAR/data/charon.db" \
CHARON_DOWNLOAD_DIR="$VAR/downloads" \
CHARON_RULE_ROOTS="$VAR/library" \
CHARON_POLL_INTERVAL_SECONDS=1 \
CHARON_DS_URL="http://127.0.0.1:$FAKE_DS_PORT" \
CHARON_DS_USERNAME=admin \
CHARON_DS_PASSWORD=admin \
CHARON_TMDB_URL="http://127.0.0.1:$FAKE_DS_PORT/tmdb" \
CHARON_TMDB_TOKEN=dev-tmdb-token \
    "$PY" -m charon.main
