# Stress testing

Corpus sintético y harness reproducible para comparar el rendimiento del
servicio contra los benchmarks de referencia.

## Estructura

```
tests/stress/
├── generate_corpus.py     # genera los 4 PDFs deterministas
├── run_k6.sh              # ejecuta el escenario k6 con imagen pineada
├── run_vegeta.sh          # ejecuta el escenario Vegeta con imagen pineada
├── pdfs/                  # corpus generado (ignorado por Git salvo README/.gitkeep)
├── k6/                    # escenario k6 (spike.js)
├── vegeta/                # targets.txt y payloads/ (ignorados)
└── results/               # salidas de las corridas (ignorado por Git)
```

## Corpus

`make stress-corpus` genera cuatro PDFs con contenido fijo y semilla implícita
determinista:

| Archivo | Tamaño aproximado |
| --- | ---: |
| `small.pdf` | 50 KiB |
| `medium.pdf` | 1 MiB |
| `large.pdf` | 4 MiB |
| `xlarge.pdf` | 9 MiB |

Los tamaños exactos y SHA-256 quedan en `tests/stress/pdfs/README.md`. Los
binarios no se versionan: se regeneran con el mismo comando y producen los
mismos hashes.

## Comandos

| Comando | Descripción |
| --- | --- |
| `make stress-corpus` | Genera el corpus determinista. |
| `make stress-up` | Levanta Traefik + `REPLICAS` réplicas (default 5). |
| `make stress-down` | Detiene y elimina el stack. |
| `make stress-k6` | Ejecuta el escenario k6. |
| `make stress-vegeta` | Ejecuta el escenario Vegeta. |
| `make stress-baseline` | 1 réplica; resultados en `tests/stress/results/baseline`. |
| `make stress-scaled` | 5 réplicas; resultados en `tests/stress/results/scaled`. |

`stress-baseline` y `stress-scaled` generan el corpus, levantan el stack y
ejecutan ambos escenarios. Al terminar, bajar el stack con `make stress-down`.

## Variables

| Variable | Default | Uso |
| --- | --- | --- |
| `BASE_URL` | `http://localhost:8080` | URL de entrada por Traefik. |
| `REPLICAS` | `5` | Réplicas para `make stress-up`. |
| `RESULTS_DIR` | `tests/stress/results` | Directorio de resultados. |
| `K6_IMAGE` | `grafana/k6:1.8.3` | Imagen k6 pineada. |
| `K6_SCRIPT` | `tests/stress/k6/spike.js` | Escenario k6. |
| `K6_SUMMARY` | `k6-spike-summary.json` | Resumen exportado por k6. |
| `K6_STRICT` | `0` | `1` activa los thresholds de latencia del benchmark. |
| `VEGETA_IMAGE` | `peterevans/vegeta:6.9.1` | Imagen Vegeta pineada. |
| `VEGETA_TARGETS` | `tests/stress/vegeta/targets.txt` | Archivo de targets. |
| `VEGETA_RATE` | `50` | Tasa fija (req/s). |
| `VEGETA_DURATION` | `30s` | Duración del ataque. |
| `VEGETA_TIMEOUT` | `30s` | Timeout por request. |

Ejemplo:

```bash
make stress-corpus
make stress-up REPLICAS=1
make stress-k6 RESULTS_DIR=tests/stress/results/baseline
make stress-vegeta RESULTS_DIR=tests/stress/results/baseline
make stress-down
```

## Escenario k6 (spike)

`tests/stress/k6/spike.js` reproduce el spike del enunciado con modelo cerrado:
ramp de 0 a 100 VUs en 10s, hold de 20s y bajada de 10s. Cada VU recibe uno de
los 4 PDFs en round-robin (para acotar memoria) y hace `POST /extract` multipart
(campo `file`, tipo `application/pdf`).

Checks:

- `status is 200`.
- `json contract`: `content` string y `page_count` entero.

Thresholds y justificación:

| Métrica | Por defecto | `K6_STRICT=1` | Referencia |
| --- | --- | --- | --- |
| `http_req_failed` | `< 1%` | `< 1%` | 0.00% de errores |
| `checks` | `> 99%` | `> 99%` | contrato funcional |
| `http_req_duration` p95 | no se evalúa | `< 10s` | p95 8.80s |
| `http_req_duration` p99 | no se evalúa | `< 15s` | max 13.94s |

Los thresholds de latencia se activan con `K6_STRICT=1` para poder recolectar
primero la línea base sin abortar la corrida. Con el estado actual del servicio
esa línea base todavía no alcanza la referencia (p95 en el orden de decenas de
segundos), lo que deja el margen de optimización para las tareas de rendimiento.

El resumen se guarda en `tests/stress/results/k6-spike-summary.json`.
