#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

VEGETA_IMAGE="${VEGETA_IMAGE:-peterevans/vegeta:6.9.1}"
VEGETA_TARGETS="${VEGETA_TARGETS:-tests/stress/vegeta/targets.txt}"
VEGETA_RATE="${VEGETA_RATE:-50}"
VEGETA_DURATION="${VEGETA_DURATION:-30s}"
VEGETA_TIMEOUT="${VEGETA_TIMEOUT:-30s}"
BASE_URL="${BASE_URL:-http://localhost:8080}"
RESULTS_DIR="${RESULTS_DIR:-tests/stress/results}"

if [[ ! -f "$VEGETA_TARGETS" ]]; then
  echo "Falta $VEGETA_TARGETS (se añade en el escenario Vegeta)." >&2
  exit 1
fi

mkdir -p "$RESULTS_DIR"

docker run --rm -i --network host \
  -v "$ROOT_DIR:/repo:ro" \
  -v "$ROOT_DIR/$RESULTS_DIR:/results" \
  -w /repo \
  -e "BASE_URL=$BASE_URL" \
  "$VEGETA_IMAGE" attack \
  -targets="$VEGETA_TARGETS" \
  -rate="$VEGETA_RATE" \
  -duration="$VEGETA_DURATION" \
  -timeout="$VEGETA_TIMEOUT" \
  -output=/results/vegeta.bin

docker run --rm \
  -v "$ROOT_DIR/$RESULTS_DIR:/results:ro" \
  "$VEGETA_IMAGE" report /results/vegeta.bin \
  | tee "$RESULTS_DIR/vegeta-report.txt"

docker run --rm \
  -v "$ROOT_DIR/$RESULTS_DIR:/results:ro" \
  "$VEGETA_IMAGE" report -type=json /results/vegeta.bin \
  > "$RESULTS_DIR/vegeta-report.json"
