#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

K6_IMAGE="${K6_IMAGE:-grafana/k6:1.8.3}"
K6_SCRIPT="${K6_SCRIPT:-tests/stress/k6/spike.js}"
BASE_URL="${BASE_URL:-http://localhost:8080}"
RESULTS_DIR="${RESULTS_DIR:-tests/stress/results}"
K6_SUMMARY="${K6_SUMMARY:-k6-summary.json}"

if [[ ! -f "$K6_SCRIPT" ]]; then
  echo "Falta $K6_SCRIPT (se añade en el escenario k6)." >&2
  exit 1
fi

mkdir -p "$RESULTS_DIR"

docker run --rm -i --network host \
  -v "$ROOT_DIR:/repo:ro" \
  -v "$ROOT_DIR/$RESULTS_DIR:/results" \
  -w /repo \
  -e "BASE_URL=$BASE_URL" \
  "$K6_IMAGE" run \
  --summary-export "/results/$K6_SUMMARY" \
  "$K6_SCRIPT"
