#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

VEGETA_IMAGE="${VEGETA_IMAGE:-peterevans/vegeta:6.9.1}"
VEGETA_RATE="${VEGETA_RATE:-50}"
VEGETA_DURATION="${VEGETA_DURATION:-30s}"
VEGETA_TIMEOUT="${VEGETA_TIMEOUT:-30s}"
BASE_URL="${BASE_URL:-http://localhost:8080}"
RESULTS_DIR="${RESULTS_DIR:-tests/stress/results}"
TARGETS="tests/stress/vegeta/targets.txt"

uv run python tests/stress/vegeta/build_targets.py --base-url "$BASE_URL"

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
  "$VEGETA_IMAGE" vegeta attack \
  -targets="$TARGETS" \
  -rate="$VEGETA_RATE" \
  -duration="$VEGETA_DURATION" \
  -timeout="$VEGETA_TIMEOUT" \
  -output=/results/results.bin

docker run --rm \
  -v "$ROOT_DIR/$RESULTS_DIR:/results:ro" \
  "$VEGETA_IMAGE" vegeta report /results/results.bin \
  | tee "$RESULTS_DIR/vegeta-report.txt"

docker run --rm \
  -v "$ROOT_DIR/$RESULTS_DIR:/results:ro" \
  "$VEGETA_IMAGE" vegeta report -type=json /results/results.bin \
  > "$RESULTS_DIR/vegeta-report.json"

docker run --rm \
  -v "$ROOT_DIR/$RESULTS_DIR:/results:ro" \
  "$VEGETA_IMAGE" vegeta plot /results/results.bin \
  > "$RESULTS_DIR/vegeta-plot.html"
