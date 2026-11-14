#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

BASE_URL="${BASE_URL:-http://localhost:8080}"
PDF="${PDF:-tests/application/fixtures/hello.pdf}"
EXPECTED_REPLICAS="${EXPECTED_REPLICAS:-5}"
EXPECTED_NANOCPUS="${EXPECTED_NANOCPUS:-1000000000}"
EXPECTED_MEMORY="${EXPECTED_MEMORY:-1073741824}"

source "$ROOT_DIR/tests/infra/common.sh"

trap cleanup EXIT
start_stack

wait_for_health "$BASE_URL" || fail "Traefik no responde en $BASE_URL"

health="$(curl -fsS "$BASE_URL/health")" || fail "Traefik no responde en $BASE_URL"
[[ "$health" == '{"status":"ok"}' ]] || fail "health inesperado: $health"

healthy=0
for _ in $(seq 1 60); do
  healthy=0
  for id in $(docker compose ps -q app); do
    status="$(docker inspect "$id" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')"
    if [[ "$status" == "healthy" ]]; then
      healthy=$((healthy + 1))
    fi
  done
  if [[ "$healthy" -eq "$EXPECTED_REPLICAS" ]]; then
    break
  fi
  sleep 1
done
[[ "$healthy" -eq "$EXPECTED_REPLICAS" ]] || fail "réplicas sanas: $healthy/$EXPECTED_REPLICAS"

replicas="$(docker compose ps -q app | wc -l | tr -d ' ')"
[[ "$replicas" -eq "$EXPECTED_REPLICAS" ]] || fail "réplicas: $replicas/$EXPECTED_REPLICAS"

extract="$(curl -fsS -X POST "$BASE_URL/extract" -F "file=@${PDF};type=application/pdf")"
if [[ "$extract" != *'"content"'* || "$extract" != *'"page_count"'* ]]; then
  fail "respuesta de /extract inesperada: $extract"
fi

status="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/extract" -F "file=@${PDF};type=text/plain")"
[[ "$status" == "415" ]] || fail "MIME inválido devolvió $status (esperado 415)"

for id in $(docker compose ps -q app); do
  bindings="$(docker inspect "$id" --format '{{json .HostConfig.PortBindings}}')"
  if [[ "$bindings" != "null" && "$bindings" != "{}" ]]; then
    fail "una réplica expone puertos al host: $bindings"
  fi

  nanocpus="$(docker inspect "$id" --format '{{.HostConfig.NanoCpus}}')"
  [[ "$nanocpus" == "$EXPECTED_NANOCPUS" ]] || fail "límite de CPU inesperado: $nanocpus"

  memory="$(docker inspect "$id" --format '{{.HostConfig.Memory}}')"
  [[ "$memory" == "$EXPECTED_MEMORY" ]] || fail "límite de memoria inesperado: $memory"
done

traefik_id="$(docker compose ps -q traefik)"
[[ -n "$traefik_id" ]] || fail "no se encontró el contenedor traefik"

binds="$(docker inspect "$traefik_id" --format '{{json .HostConfig.Binds}}')"
if [[ "$binds" != *'/var/run/docker.sock:/var/run/docker.sock:ro'* ]]; then
  fail "socket docker no está montado en solo lectura: $binds"
fi

for _ in $(seq 1 30); do
  curl -fsS "$BASE_URL/health" >/dev/null
done

replicas_hit="$(docker compose logs app --no-color 2>/dev/null | grep -oE 'app-[0-9]+' | sort -u | wc -l | tr -d ' ')"
[[ "$replicas_hit" -ge 2 ]] || fail "no se observó distribución entre réplicas"

victim="$(docker compose ps -q app | head -1)"
docker stop "$victim" >/dev/null
sleep 2
curl -fsS "$BASE_URL/health" >/dev/null || fail "sin respuesta tras detener una réplica"

echo "smoke routing OK (réplicas=$EXPECTED_REPLICAS, distribución=$replicas_hit, failover OK)"
