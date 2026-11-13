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
| `K6_SUMMARY` | `k6-summary.json` | Resumen exportado por k6. |
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
