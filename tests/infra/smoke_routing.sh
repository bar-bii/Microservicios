#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

BASE_URL="${BASE_URL:-http://localhost:8080}"
PDF="${PDF:-tests/application/fixtures/hello.pdf}"

cleanup() {
  docker compose down --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose config >/dev/null
docker compose up -d --build

for _ in $(seq 1 30); do
  if curl -fsS "$BASE_URL/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

health="$(curl -fsS "$BASE_URL/health")"
if [[ "$health" != '{"status":"ok"}' ]]; then
  echo "health inesperado: $health" >&2
  exit 1
fi

extract="$(curl -fsS -X POST "$BASE_URL/extract" -F "file=@${PDF};type=application/pdf")"
if [[ "$extract" != *'"content"'* || "$extract" != *'"page_count"'* ]]; then
  echo "respuesta de /extract inesperada: $extract" >&2
  exit 1
fi

status="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/extract" -F "file=@${PDF};type=text/plain")"
if [[ "$status" != "415" ]]; then
  echo "MIME inválido devolvió $status (esperado 415)" >&2
  exit 1
fi

app_id="$(docker compose ps -q app)"
if [[ -z "$app_id" ]]; then
  echo "no se encontró el contenedor app" >&2
  exit 1
fi

bindings="$(docker inspect "$app_id" --format '{{json .HostConfig.PortBindings}}')"
if [[ "$bindings" != "null" && "$bindings" != "{}" ]]; then
  echo "app expone puertos al host: $bindings" >&2
  exit 1
fi

traefik_id="$(docker compose ps -q traefik)"
if [[ -z "$traefik_id" ]]; then
  echo "no se encontró el contenedor traefik" >&2
  exit 1
fi

binds="$(docker inspect "$traefik_id" --format '{{json .HostConfig.Binds}}')"
if [[ "$binds" != *'/var/run/docker.sock:/var/run/docker.sock:ro'* ]]; then
  echo "socket docker no está montado en solo lectura: $binds" >&2
  exit 1
fi

echo "smoke routing OK"
