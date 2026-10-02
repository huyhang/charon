#!/usr/bin/env bash
# Walk through the main API calls with curl. Assumes `make dev` (or docker-dev) is running.
# Exits non-zero unless the download ends up renamed and moved.
#   CHARON_URL=http://nas:8080 CHARON_API_KEY=<admin or client key> LIBRARY_DIR=/media/tv scripts/smoke.sh
set -euo pipefail

URL="${CHARON_URL:-http://127.0.0.1:8080}/api/v1"
KEY="${CHARON_API_KEY:-dev-key}"
LIBRARY="${LIBRARY_DIR:-$(cd "$(dirname "$0")/.." && pwd)/var/library}"
PY="${PYTHON:-python3}"
# Unique per run, so a file left by an earlier run can't collide with this one.
RUN="$(date +%s%N)"
NAME="Smoke.$RUN.XYZ.mkv"
EXPECTED="$LIBRARY/smoke/Smoke.$RUN.ABC.mkv"

call() {
    local method=$1 path=$2 body=${3:-}
    echo "--> $method $path ${body}" >&2
    curl -sS -X "$method" "$URL$path" -H "X-API-Key: $KEY" \
        ${body:+-H "Content-Type: application/json" -d "$body"}
}
field() { "$PY" -c "import json,sys; print(json.load(sys.stdin)$1)"; }

call GET /health; echo

RULE_ID=$(call POST /rules "{\"name\":\"smoke-$RUN\",\"pattern\":\"Smoke.$RUN.*\",\"destination\":\"$LIBRARY/smoke\",\"steps\":[{\"op\":\"replace\",\"find\":\"XYZ\",\"replace\":\"ABC\"}]}" | field '["id"]')
echo "rule: $RULE_ID"

call POST /rules/preview "{\"name\":\"$NAME\"}"; echo

JOB_ID=$(call POST /downloads "{\"magnet\":\"magnet:?xt=urn:btih:$RUN&dn=$NAME\"}" | field '["id"]')
echo "job: $JOB_ID"

STATUS=unknown
for _ in $(seq 1 60); do
    STATUS=$(call GET "/downloads/$JOB_ID" 2>/dev/null | field '["status"]')
    echo "status: $STATUS"
    case "$STATUS" in done|failed|cancelled) break ;; esac
    sleep 1
done

JOB=$(call GET "/downloads/$JOB_ID"); echo "$JOB"
call GET "/downloads?limit=5"; echo
call DELETE "/rules/$RULE_ID" >/dev/null; echo "rule deleted"

FINAL=$(echo "$JOB" | field '["processing"]["final_path"]')
if [ "$STATUS" != done ] || [ "$FINAL" != "$EXPECTED" ]; then
    echo "SMOKE FAILED: status=$STATUS final_path=$FINAL (expected done at $EXPECTED)" >&2
    exit 1
fi
echo "SMOKE OK: $FINAL"
