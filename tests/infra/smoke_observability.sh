#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

BASE_URL="${BASE_URL:-http://localhost:8080}"
DASHBOARD_URL="${DASHBOARD_URL:-http://127.0.0.1:8081/dashboard/}"
PDF="${PDF:-tests/application/fixtures/hello.pdf}"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

cleanup() {
  docker compose down --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose config >/dev/null
docker compose up -d --build --scale app=5 >/dev/null

for _ in $(seq 1 60); do
  if curl -fsS "$BASE_URL/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

curl -fsS "$BASE_URL/health" >/dev/null || fail "Traefik no responde en $BASE_URL"
for _ in $(seq 1 10); do
  curl -fsS -X POST "$BASE_URL/extract" -F "file=@${PDF};type=application/pdf" >/dev/null
done
sleep 1

app_logs="$(docker compose logs app --no-color 2>/dev/null || true)"
grep -q '"replica":' <<<"$app_logs" || fail "la app no emite logs JSON con réplica"

replica="$(grep -o '"replica":"[^"]*"' <<<"$app_logs" | head -1 | cut -d'"' -f4)"
[[ -n "$replica" ]] || fail "no se pudo extraer la réplica del log JSON"

hostnames=""
for id in $(docker compose ps -q app); do
  hostnames+="$(docker inspect "$id" --format '{{.Config.Hostname}}')"$'\n'
done
grep -qx "$replica" <<<"$hostnames" || fail "la réplica logueada ($replica) no coincide con ningún hostname"

traefik_logs="$(docker compose logs traefik --no-color 2>/dev/null || true)"
access_logs="$(grep '"DownstreamStatus"' <<<"$traefik_logs" || true)"
[[ -n "$access_logs" ]] || fail "Traefik no emite access logs JSON"
grep -q '"ServiceName"' <<<"$access_logs" || fail "access log sin ServiceName"
grep -q '"ServiceAddr"' <<<"$access_logs" || fail "access log sin ServiceAddr"

traefik_id="$(docker compose ps -q traefik)"
bindings="$(docker inspect "$traefik_id" --format '{{range $conf := .HostConfig.PortBindings}}{{range $conf}}{{.HostIp}}:{{.HostPort}}{{end}}{{end}}')"
grep -q '127.0.0.1:8081' <<<"$bindings" || fail "dashboard no está limitado a 127.0.0.1:8081: $bindings"

status="$(curl -4 -s -o /dev/null -w '%{http_code}' "$DASHBOARD_URL")"
[[ "$status" == "200" ]] || fail "dashboard local devolvió $status"

echo "smoke observability OK (réplica=$replica, dashboard=127.0.0.1:8081, access logs JSON)"
