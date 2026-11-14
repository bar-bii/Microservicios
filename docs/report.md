# Reporte de rendimiento: baseline vs 5 réplicas

Fecha de medición: 2026-11-14 (UTC)

## 1. Arquitectura

El servicio expone `POST /extract` (multipart, `application/pdf`) y `GET /health`.
La extracción de texto se delega a `pypdf` mediante `asyncio.to_thread` y un
semáforo de `WORKER_POOL_SIZE=4` con cola de `MAX_QUEUE_SIZE=100`.

Despliegue medido:

- Traefik `v3.7.18` como reverse proxy/load balancer en `:8080`.
- `app` con `deploy.replicas: 5`, sin puertos publicados al host.
- Límites por réplica: `1.0` CPU y `1 GB` de RAM.
- Reservas por réplica: `0.5` CPU y `512 MB`.
- Healthcheck de Traefik contra `/health` cada `10s`.

El puerto `:8000` de la app no se publica; todo el tráfico entra por Traefik.

## 2. Hardware y software

| Ítem | Valor |
| --- | --- |
| CPU | 8 vCPU (`nproc`) |
| RAM total | 15.535.360 KiB (~15,5 GiB) |
| RAM disponible al inicio | ~6,2 GiB (baseline) / ~5,0 GiB (scaled) |
| Kernel | Linux 7.0.0-43-generic, x86_64 |
| Docker | 29.7.2 |
| Docker Compose | 5.4.0 |
| Python | 3.13 |
| k6 | `grafana/k6:1.8.3` |
| Vegeta | `peterevans/vegeta:6.9.1` |

Las corridas se hicieron en un host compartido con otros contenedores
(`postgres_empresa`, `eager_shockley`). El monitoreo de `docker stats` se limitó
a los contenedores del proyecto, pero la carga de fondo puede afectar los
resultados.

## 3. Metodología

Se usó el corpus sintético determinista de `tests/stress/pdfs` (50 KiB a 9 MiB)
y los escenarios ya definidos:

- **k6 spike**: modelo cerrado, rampa de 0 a 100 VUs en 10 s, 20 s sostenidos y
  bajada de 10 s.
- **Vegeta fixed-rate**: 50 req/s durante 30 s (1.500 requests), timeout de 30 s.

Cada escenario se ejecutó con una pila limpia:

```bash
tests/stress/run_benchmark.sh baseline   # 1 réplica
tests/stress/run_benchmark.sh scaled     # 5 réplicas
```

Equivalentes con Make: `make stress-baseline` y `make stress-scaled`. Los
resultados crudos quedaron en `tests/stress/results/{baseline,scaled}` e
incluyen `docker stats`, metadatos, reportes de k6/Vegeta y exit codes.

## 4. Resultados k6 (spike)

| Métrica | Baseline (1 réplica) | Escalado (5 réplicas) | Referencia |
| --- | ---: | ---: | ---: |
| Requests totales | 11.198 | 103 | 1.037 |
| Throughput bruto | 223,95 req/s | 2,06 req/s | 25,35 req/s |
| `http_req_failed` | 99,32 % | 0,00 % | 0,00 % |
| Checks exitosos | 0,68 % | 100,00 % | — |
| p50 global | 0,65 ms | 1,54 s | 1,88 s |
| p95 global | 2,36 ms | 28,67 s | 8,80 s |
| p99 global | 6,24 ms | 30,35 s | — |
| max | 35,53 s | 31,02 s | 13,94 s |
| p50 respuestas 200 | 16,49 s | 1,54 s | — |
| p95 respuestas 200 | 32,82 s | 28,67 s | — |

**Lectura:** el baseline tiene un throughput bruto alto porque la mayoría de
las requests se rechazan rápido con `503` por backpressure (99,32 % de fallos).
No es un throughput útil. Con 5 réplicas desaparecen los `503`, pero solo se
completan 103 requests en la ventana del spike y la latencia sigue dominada por
la espera en cola: p95 ≈ 28,7 s, muy por encima de la referencia de 8,80 s.

## 5. Resultados Vegeta (fixed-rate)

| Métrica | Baseline (1 réplica) | Escalado (5 réplicas) | Referencia |
| --- | ---: | ---: | ---: |
| Requests | 1.500 | 1.500 | 1.500 |
| Tasa objetivo | 50,03 req/s | 50,03 req/s | 50 req/s |
| Throughput efectivo | 0,67 req/s | 1,15 req/s | 16,65 req/s |
| Success | 2,67 % | 4,60 % | 66,53 % |
| `200` | 40 | 69 | 998 |
| `503` | 658 | 0 | — |
| Timeouts (`0`) | 802 | 1.431 | 501 |
| p50 | 30,00 s | 30,00 s | 14,89 s |
| p95 | 30,00 s | 30,00 s | — |
| p99 | 30,00 s | 30,00 s | — |
| max | 30,01 s | 30,01 s | — |

**Lectura:** el `503` del baseline se convierte en timeout con 5 réplicas: la
cola ya no rechaza, pero las requests esperan más de los 30 s del cliente. El
throughput efectivo apenas sube de 0,67 a 1,15 req/s y el success rate sigue
muy lejos del 66,53 % de referencia. Los percentiles están recortados por el
timeout de 30 s, por lo que la latencia real de las requests que quedan en cola
es al menos ese valor.

## 6. Uso de CPU y memoria

`docker stats --no-stream` cada 2 s, solo contenedores del proyecto:

| Escenario | CPU promedio por réplica | CPU máxima | Memoria máxima |
| --- | ---: | ---: | ---: |
| Baseline + k6 | 85,4 % | 107,6 % | 318 MiB |
| Baseline + Vegeta | 95,2 % | 112,7 % | 236 MiB |
| 5 réplicas + k6 | 88,1–91,6 % | 104,4 % | 207 MiB |
| 5 réplicas + Vegeta | 92,9–97,5 % | 106,7 % | 210 MiB |

Todas las réplicas de `app` quedan saturadas alrededor de su límite de `1.0`
CPU. Traefik se mantuvo por debajo del 4 % de CPU y alrededor de 330 MiB de
RAM, por lo que no aparece como cuello de botella. La memoria de `app` tampoco
llega al límite de 1 GiB en estas corridas.

## 7. Cuello de botella identificado

El cuello de botella es **CPU-bound en la extracción con `pypdf`**, agravado
por el modelo de concurrencia actual:

1. `pypdf` es CPU-bound y corre con `asyncio.to_thread`, por lo que el GIL
   limita el paralelismo real dentro de cada réplica.
2. Cada réplica usa un solo proceso de uvicorn; el semáforo de 4 threads no
   aumenta el uso efectivo de CPU más allá de lo que permite el GIL.
3. Las 5 réplicas suman capacidad, pero cada request pesada consume segundos de
   CPU; la cola crece más rápido de lo que se drena.
4. El router lee el body completo antes de consultar la capacidad del servicio
   (#29), así que el backpressure protege la cola pero no la memoria ni evita
   el trabajo de recepción de requests que luego esperan.
5. El timeout de 30 s de Vegeta y el de 60 s de k6 recortan las latencias
   observadas; la cola real es aún más lenta.

No se observaron `502` en la última corrida escalada ni saturación de Traefik.
El límite está en el procesamiento de PDFs, no en el proxy ni en la red.

## 8. Comparación con la referencia

| Escenario | Throughput | Success | p50 | p95 | max |
| --- | ---: | ---: | ---: | ---: | ---: |
| k6 referencia | 25,35 req/s | 0,00 % error | 1,88 s | 8,80 s | 13,94 s |
| k6 5 réplicas | 2,06 req/s | 0,00 % error | 1,54 s | 28,67 s | 31,02 s |
| Vegeta referencia | 16,65 req/s | 66,53 % | 14,89 s | — | — |
| Vegeta 5 réplicas | 1,15 req/s | 4,60 % | 30,00 s | 30,00 s | 30,01 s |

El servicio todavía no alcanza la referencia. La comparación de k6 debe mirar
el success rate y la latencia de respuestas exitosas: el throughput bruto del
baseline está inflado por rechazos rápidos y no representa capacidad útil.

## 9. Próximos pasos

1. **#29 — backpressure antes de leer el body**: exponer una admisión explícita
   en `DocumentService` y responder `503` sin consumir el upload completo.
2. **#30 — GIL/worker pool**: comparar `ProcessPoolExecutor`, múltiples workers
   de uvicorn y un worker pool separado del runtime HTTP; medir throughput y
   percentiles con este mismo harness.
3. Evaluar librerías de extracción con menor costo de CPU o lectura en streaming.
4. Ajustar el tamaño de cola y la política de rechazo (`429`/`503`) con
   `Retry-After` para evitar requests que esperan más que su timeout.
5. Repetir las corridas en un host aislado y con más de una muestra para
   reducir el ruido.

## 10. Reproducción

```bash
tests/stress/run_benchmark.sh baseline
tests/stress/run_benchmark.sh scaled
# o, con make instalado:
make stress-baseline
make stress-scaled
```

Artefactos esperados en `tests/stress/results/{baseline,scaled}`:

- `k6-spike-summary.json`, `k6-run.log`, `k6-exit-code`
- `vegeta-report.txt`, `vegeta-report.json`, `vegeta-plot.html`, `vegeta-run.log`
- `docker-stats-k6.txt`, `docker-stats-vegeta.txt`
- `metadata.txt`, `compose-up-*.log`

Los artefactos están ignorados por Git y se regeneran con los comandos
anteriores. El detalle del harness está en `tests/stress/README.md`.
