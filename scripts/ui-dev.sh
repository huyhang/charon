#!/usr/bin/env bash
# Run the fake Download Station, Charon and the UI dev server together, without Docker.
# Open http://localhost:5173 and sign in with the admin key (dev-key).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHARON_PORT="${CHARON_PORT:-8080}"
FAKE_DS_PORT="${FAKE_DS_PORT:-5000}"
# Slower fake downloads than `make dev`, so progress bars have time to move.
export FAKE_DS_DURATION_SECONDS="${FAKE_DS_DURATION_SECONDS:-90}"
export CHARON_PORT FAKE_DS_PORT

port_in_use() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }
for port in "$CHARON_PORT" "$FAKE_DS_PORT" 5173; do
    if port_in_use "$port"; then
        echo "Port $port is already in use. Free it, or pick other ports, e.g." >&2
        echo "  make ui-dev CHARON_PORT=18080 FAKE_DS_PORT=15000" >&2
        echo "  make ui-seed CHARON_PORT=18080 FAKE_DS_PORT=15000" >&2
        exit 1
    fi
done

if [ ! -d "$ROOT/ui/node_modules" ]; then
    (cd "$ROOT/ui" && npm ci)
fi

# Job control puts each part in its own process group, so stopping a group also stops what it
# started (npm starts vite; dev.sh starts uvicorn and Charon). Input comes from /dev/null, or a
# background group reading the terminal would be stopped.
set -m
"$ROOT/scripts/dev.sh" </dev/null &
STACK_PID=$!
(cd "$ROOT/ui" &&
    CHARON_URL="http://127.0.0.1:$CHARON_PORT" FAKE_DS_URL="http://127.0.0.1:$FAKE_DS_PORT" \
        npm run dev) </dev/null &
UI_PID=$!
trap 'kill -- "-$STACK_PID" "-$UI_PID" 2>/dev/null || true' EXIT
trap 'exit 130' INT TERM

echo "ui:                    http://localhost:5173  (seed sample data: make ui-seed)"
# If any part stops (e.g. Charon can't start), stop everything rather than run half a stack.
# A polling loop rather than `wait -n`, which the bash 3.2 that macOS ships lacks.
while kill -0 "$STACK_PID" 2>/dev/null && kill -0 "$UI_PID" 2>/dev/null; do
    sleep 1
done
echo "A dev server stopped; shutting the rest down." >&2
exit 1
