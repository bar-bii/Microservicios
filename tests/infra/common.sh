#!/usr/bin/env bash

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

cleanup() {
  docker compose down --remove-orphans >/dev/null 2>&1 || true
}

start_stack() {
  docker compose config >/dev/null
  docker compose up -d --build "$@"
}

wait_for_health() {
  local base_url="$1"
  for _ in $(seq 1 60); do
    if curl -fsS "$base_url/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}
