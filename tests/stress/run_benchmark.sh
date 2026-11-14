#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

MODE="${1:-scaled}"
case "$MODE" in
  baseline) REPLICAS=1 ;;
  scaled) REPLICAS=5 ;;
  *)
    echo "Uso: $0 [baseline|scaled]" >&2
    exit 2
    ;;
esac

RESULTS_DIR="${RESULTS_DIR:-tests/stress/results/$MODE}"
K6_SUMMARY="${K6_SUMMARY:-k6-spike-summary.json}"

monitor_pid=""
cleanup() {
  if [[ -n "$monitor_pid" ]]; then
    kill "$monitor_pid" 2>/dev/null || true
  fi
  docker compose down --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

mkdir -p "$RESULTS_DIR"
uv run python tests/stress/generate_corpus.py >/dev/null

{
  echo "mode=$MODE"
  echo "replicas=$REPLICAS"
  echo "date=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "host=$(uname -a)"
  echo "cpus=$(nproc)"
  grep -E '^(MemTotal|MemAvailable):' /proc/meminfo
  echo "docker=$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo desconocida)"
  echo "compose=$(docker compose version --short 2>/dev/null || echo desconocida)"
} >"$RESULTS_DIR/metadata.txt"

run_scenario() {
  local scenario="$1"
  docker compose down --remove-orphans >/dev/null 2>&1
  docker compose up -d --build --scale "app=$REPLICAS" \
    >"$RESULTS_DIR/compose-up-$scenario.log" 2>&1

  : >"$RESULTS_DIR/docker-stats-$scenario.txt"
  (
    while true; do
      timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
      ids="$(docker compose ps -q 2>/dev/null || true)"
      if [[ -n "$ids" ]]; then
        mapfile -t stats_ids <<<"$ids"
        docker stats --no-stream --format '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}' \
          "${stats_ids[@]}" \
          | while IFS= read -r line; do
              printf '%s|%s\n' "$timestamp" "$line"
            done
      fi
      sleep 2
    done
  ) >>"$RESULTS_DIR/docker-stats-$scenario.txt" &
  monitor_pid=$!

  set +e
  if [[ "$scenario" == "k6" ]]; then
    RESULTS_DIR="$RESULTS_DIR" K6_SUMMARY="$K6_SUMMARY" \
      tests/stress/run_k6.sh >"$RESULTS_DIR/k6-run.log" 2>&1
  else
    RESULTS_DIR="$RESULTS_DIR" tests/stress/run_vegeta.sh \
      >"$RESULTS_DIR/vegeta-run.log" 2>&1
  fi
  local exit_code=$?
  set -e
  echo "$exit_code" >"$RESULTS_DIR/$scenario-exit-code"

  kill "$monitor_pid" 2>/dev/null || true
  wait "$monitor_pid" 2>/dev/null || true
  monitor_pid=""

  docker compose down --remove-orphans >/dev/null 2>&1
  echo "$MODE/$scenario: exit=$exit_code, resultados en $RESULTS_DIR"
}

run_scenario k6
run_scenario vegeta

echo "Benchmark $MODE completo. Artefactos en $RESULTS_DIR."
