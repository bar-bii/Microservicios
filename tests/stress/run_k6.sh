#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

K6_IMAGE="${K6_IMAGE:-grafana/k6:1.8.3}"
K6_SCRIPT="${K6_SCRIPT:-tests/stress/k6/spike.js}"
BASE_URL="${BASE_URL:-http://localhost:8080}"
RESULTS_DIR="${RESULTS_DIR:-tests/stress/results}"
K6_SUMMARY="${K6_SUMMARY:-k6-spike-summary.json}"
K6_STRICT="${K6_STRICT:-0}"

if [[ ! -f "$K6_SCRIPT" ]]; then
  echo "Falta $K6_SCRIPT (se añade en el escenario k6)." >&2
  exit 1
fi

for _ in $(seq 1 60); do
  if curl -fsS "$BASE_URL/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS "$BASE_URL/health" >/dev/null || {
  echo "Timeout esperando $BASE_URL/health" >&2
  exit 1
}

mkdir -p "$RESULTS_DIR"

docker run --rm -i --network host \
  -v "$ROOT_DIR:/repo:ro" \
  -v "$ROOT_DIR/$RESULTS_DIR:/results" \
  -w /repo \
  -e "BASE_URL=$BASE_URL" \
  -e "K6_STRICT=$K6_STRICT" \
  "$K6_IMAGE" run \
  --summary-export "/results/$K6_SUMMARY" \
  "$K6_SCRIPT"
