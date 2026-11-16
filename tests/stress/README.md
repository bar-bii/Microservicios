# Stress testing

Corpus sintético y harness reproducible para comparar el rendimiento del
servicio contra los benchmarks de referencia.

## Estructura

```
tests/stress/
├── generate_corpus.py     # genera los 4 PDFs deterministas
├── run_benchmark.sh       # baseline/scaled: stack + k6 + Vegeta + docker stats
├── run_k6.sh              # ejecuta el escenario k6 con imagen pineada
├── run_vegeta.sh          # ejecuta el escenario Vegeta con imagen pineada
├── pdfs/                  # corpus generado (ignorado por Git salvo README/.gitkeep)
├── k6/                    # escenario k6 (spike.js)
├── vegeta/                # build_targets.py, targets.txt y payloads/ (generados)
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
| `make stress-workers` | Compara hilos, procesos y workers de uvicorn con 1 réplica; resultados en `tests/stress/results/workers/<variante>`. |
| `make stress-queue` | Compara tamaños de cola con 5 réplicas; resultados en `tests/stress/results/queue/queue-<tamaño>`. |

`stress-baseline` y `stress-scaled` usan `run_benchmark.sh`: generan el corpus,
levantan el stack con `--scale app=N`, ejecutan k6 y Vegeta con una pila limpia
para cada escenario, recolectan `docker stats` y bajan el stack al terminar.

Cada directorio de resultados incluye:

- `k6-spike-summary.json`, `k6-run.log` y `k6-exit-code`.
- `vegeta-report.txt`, `vegeta-report.json`, `vegeta-plot.html`, `vegeta-run.log`
  y `vegeta-exit-code`.
- `docker-stats-{k6,vegeta}.txt` con CPU/RAM por contenedor cada 2 s.
- `metadata.txt` con fecha, CPU, memoria, kernel, versiones de Docker/Compose y
  la variante de concurrencia medida.
- `compose-up-{k6,vegeta}.log`.
- `compose-logs-{k6,vegeta}.log` con los logs JSON de la app y de Traefik.

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
| `VEGETA_RATE` | `50` | Tasa fija (req/s). |
| `VEGETA_DURATION` | `30s` | Duración del ataque. |
| `VEGETA_TIMEOUT` | `30s` | Timeout por request. |
| `EXTRACTION_EXECUTOR` | `thread` | Dónde corre la extracción: `thread` o `process`. |
| `WORKER_POOL_SIZE` | `4` | Extracciones simultáneas por proceso del servicio. |
| `MAX_QUEUE_SIZE` | ver `docker-compose.yml` | Requests en espera por proceso del servicio antes de responder `503`. |
| `MAX_QUEUE_BYTES` | ver `docker-compose.yml` | Bytes admitidos a la vez por proceso del servicio, según el `Content-Length` de cada request. Vacío = sin límite. |
| `QUEUE_ORDER` | ver `docker-compose.yml` | Orden de atención de la cola: `fifo` o `hrrn`. |
| `WEB_CONCURRENCY` | `1` | Procesos de uvicorn por réplica. |
| `WORKERS_RESULTS_DIR` | `tests/stress/results/workers` | Resultados de `make stress-workers`. |
| `QUEUE_SIZES` | `20 30 40 60 100` | Tamaños que recorre `make stress-queue`. |
| `QUEUE_RESULTS_DIR` | `tests/stress/results/queue` | Resultados de `make stress-queue`. |
| `QUEUE_MEGABYTES` | `100 130 160 200` | Límites en MiB que recorre `make stress-queue-bytes`. |
| `QUEUE_BYTES_RESULTS_DIR` | `tests/stress/results/queue-bytes` | Resultados de `make stress-queue-bytes`. |
| `QUEUE_ORDERS` | `fifo hrrn` | Órdenes que recorre `make stress-order`. |
| `ORDER_RESULTS_DIR` | `tests/stress/results/order` | Resultados de `make stress-order`. |
| `LB_STRATEGY` | ver `docker-compose.yml` | Estrategia del balanceador de Traefik: `wrr`, `p2c`, `hrw` o `leasttime`. |
| `LB_STRATEGIES` | `wrr p2c leasttime` | Estrategias que recorre `make stress-lb`. |
| `LB_RESULTS_DIR` | `tests/stress/results/lb` | Resultados de `make stress-lb`. |

Ejemplo:

```bash
make stress-corpus
make stress-up REPLICAS=1
make stress-k6 RESULTS_DIR=tests/stress/results/baseline
make stress-vegeta RESULTS_DIR=tests/stress/results/baseline
make stress-down
```

## Comparación de estrategias de concurrencia

`make stress-workers` corre `run_benchmark.sh baseline` (1 réplica) una vez por
variante, cambiando solo variables de entorno que `docker-compose.yml` pasa al
servicio:

| Variante | Variables |
| --- | --- |
| `threads-4` | valores por defecto |
| `threads-1` | `WORKER_POOL_SIZE=1` |
| `processes-4` | `EXTRACTION_EXECUTOR=process` |
| `processes-1` | `EXTRACTION_EXECUTOR=process WORKER_POOL_SIZE=1` |
| `uvicorn-4` | `WEB_CONCURRENCY=4 WORKER_POOL_SIZE=1` |

Los resultados y la recomendación están en `docs/perf-workers.md`.

## Barrido del tamaño de cola

`make stress-queue` corre `run_benchmark.sh scaled` (5 réplicas) una vez por
cada valor de `QUEUE_SIZES`, cambiando solo `MAX_QUEUE_SIZE`. Los resultados y
el valor elegido están en `docs/perf-queue.md`.

## Barrido del límite de cola en bytes

`make stress-queue-bytes` corre `run_benchmark.sh scaled` (5 réplicas) una vez
por cada valor de `QUEUE_MEGABYTES`, cambiando solo `MAX_QUEUE_BYTES`. Los
resultados y el valor elegido están en `docs/perf-queue-bytes.md`.

## Comparación de órdenes de la cola

`make stress-order` corre `run_benchmark.sh scaled` (5 réplicas) una vez por
cada valor de `QUEUE_ORDERS`, cambiando solo `QUEUE_ORDER`. Los resultados y el
orden elegido están en `docs/perf-queue-order.md`.

## Comparación de estrategias de balanceo

`make stress-lb` corre `run_benchmark.sh scaled` (5 réplicas) una vez por cada
valor de `LB_STRATEGIES`, cambiando solo `LB_STRATEGY`. Los resultados y la
estrategia elegida están en `docs/perf-balancing.md`.

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

## Escenario Vegeta (fixed-rate)

`tests/stress/vegeta/build_targets.py` genera 4 bodies multipart deterministas
(boundary fijo, campo `file`) y `tests/stress/vegeta/targets.txt`. El runner
`make stress-vegeta` ataca a **50 req/s durante 30s** con timeout de **30s**,
rotando los 4 PDFs, y escribe en `tests/stress/results/`:

- `results.bin`: resultados crudos de Vegeta.
- `vegeta-report.txt` y `vegeta-report.json`: throughput, success rate,
  percentiles (p50/p95/p99) y timeouts.
- `vegeta-plot.html`: gráfico de latencias.

Los payloads y `targets.txt` son generados y están ignorados por Git.

### Overhead de multipart

Cada body agrega headers `Content-Disposition`/`Content-Type` y el boundary
(≈176–177 bytes por request). El contrato del servicio solo acepta
`multipart/form-data`, así que ese costo fijo es despreciable frente a PDFs de
50 KiB–9 MiB y evita mantener un segundo camino de ingestión binaria.
