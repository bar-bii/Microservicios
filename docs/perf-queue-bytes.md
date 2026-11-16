# Límite de la cola por bytes

Fecha de medición: 2026-11-16 (UTC). Issue: #47.

## 1. Resumen

La cola se limitaba solo por cantidad de requests (`MAX_QUEUE_SIZE`). Lo que
tarda en vaciarse depende de cuánto pesan los PDFs que tiene adentro: 40
requests pueden ser 2 MB o 370 MB de trabajo.

Este cambio agrega `MAX_QUEUE_BYTES`: un tope a los bytes admitidos a la vez
por proceso del servicio, contando los que esperan y los que se están
extrayendo. Cuando queda poco lugar, un PDF chico entra y uno de 9 MB recibe
`503`.

Medido con 5 réplicas y la cola en orden de llegada (FIFO):

- **No mejora por sí solo.** El success de Vegeta queda en 11,1–17,5 % frente
  a 8,7–10,8 %, pero los timeouts suben de ~195 a 350–450: entran muchos más
  PDFs chicos, que después esperan detrás de los grandes.
- **La memoria baja** de ~370 MiB a ~305 MiB por réplica en Vegeta.

Por eso el límite queda **disponible pero apagado** en `docker-compose.yml`.
Su efecto aparece al combinarlo con un orden de atención que deje pasar a los
PDFs chicos (`docs/perf-queue-order.md`, #48).

## 2. Qué cambió

- **`MAX_QUEUE_BYTES`** (opcional). Sin valor, el comportamiento es el
  anterior.
- **La admisión usa el `Content-Length`** de la request, así el rechazo sigue
  ocurriendo antes de leer el body (#29). Una request sin `Content-Length`
  cuenta como `MAX_UPLOAD_BYTES`.
- **Una request que no entra recibe `503`** con `Retry-After`, igual que con
  la cola llena.
- **Un servicio sin requests en curso admite cualquier tamaño**, aunque supere
  el límite: una mala configuración no deja un tamaño sin atender.
- **`MAX_QUEUE_SIZE` se mantiene** como tope de cantidad. Los dos límites se
  aplican a la vez.

## 3. Método

Mismo harness y entorno que `docs/perf-balancing.md` (Docker Desktop sobre
macOS, `linux/arm64`, 5 réplicas con `1.0` CPU y `1 GB`, balanceo `p2c`):

```bash
make stress-queue-bytes MAX_QUEUE_SIZE=100
```

El comando corre `run_benchmark.sh scaled` una vez por cada valor de
`QUEUE_MEGABYTES`, cambiando solo `MAX_QUEUE_BYTES`. Con el límite en bytes se
subió `MAX_QUEUE_SIZE` a 100 para que el tope de cantidad no actúe antes. La
referencia es la configuración vigente: cola de 40 requests, sin límite en
bytes.

Las corridas se hicieron intercaladas con las de `docs/perf-queue-order.md`,
sobre el código de #48 con `QUEUE_ORDER=fifo`, que atiende en orden de llegada
igual que el semáforo anterior. Se descartó una corrida de 130 MiB porque el
equipo se suspendió durante la medición.

Los números absolutos no son comparables con la referencia del enunciado ni
con `docs/perf-queue.md` (ver `docs/perf-balancing.md`, sección 2).

## 4. Resultados con 5 réplicas (orden FIFO)

### Vegeta (fixed-rate)

| Límite | Success | 200 | 503 | Timeouts | Requests simultáneas por réplica (máx.) | RAM máx. |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 40 requests | 10,73 % | 161 | 1.145 | 194 | 46 | 375 MiB |
| 40 requests (2.ª pasada) | 8,73 % | 131 | 1.163 | 206 | 50 | 374 MiB |
| 40 requests (3.ª pasada) | 10,80 % | 162 | 1.145 | 193 | 46 | 353 MiB |
| 130 MiB | 17,53 % | 263 | 888 | 349 | 105 | 309 MiB |
| 130 MiB (2.ª pasada) | 11,33 % | 170 | 945 | 385 | 94 | 304 MiB |
| 130 MiB (3.ª pasada) | 11,13 % | 167 | 882 | 451 | 106 | 304 MiB |
| 160 MiB | 8,93 % | 134 | 922 | 444 | 105 | 336 MiB |
| 200 MiB | 9,33 % | 140 | 852 | 508 | 107 | 384 MiB |

### k6 (spike)

| Límite | Requests | Errores | p50 / p95 | MB en curso en la réplica más cargada |
| --- | ---: | ---: | ---: | ---: |
| 40 requests | 487 | 0 % | 1,9 / 20,6 s | 96 |
| 40 requests (2.ª pasada) | 445 | 0 % | 3,6 / 21,4 s | 102 |
| 40 requests (3.ª pasada) | 540 | 0 % | 1,6 / 19,2 s | 108 |
| 130 MiB | 546 | 0 % | 2,9 / 18,5 s | 103 |
| 130 MiB (2.ª pasada) | 527 | 0 % | 1,4 / 19,9 s | 105 |
| 130 MiB (3.ª pasada) | 483 | 0 % | 4,2 / 19,0 s | 118 |
| 160 MiB | 526 | 0 % | 1,3 / 20,8 s | 98 |
| 200 MiB | 402 | 0 % | 7,5 / 20,2 s | 101 |

No hubo `503` de Traefik, trazas ni procesos caídos en ninguna corrida.

## 5. Hallazgos

1. **Con FIFO, el límite en bytes cambia timeouts por más timeouts.** Deja
   entrar muchas más requests chicas (hasta ~105 simultáneas por réplica en
   lugar de ~46), pero cada una espera detrás de todos los PDFs grandes que
   llegaron antes. Los timeouts pasan de ~195 a 350–450 con 130 MiB y a 508
   con 200 MiB.
2. **El success no mejora de forma clara.** Con 130 MiB fue 17,53 %, 11,33 % y
   11,13 %; con 40 requests, 10,73 %, 8,73 % y 10,80 %. Con 160 y 200 MiB quedó
   igual o peor que la referencia.
3. **La memoria sí baja**: ~305 MiB con 130 MiB frente a ~370 MiB con la cola
   de 40 requests, que llegó a admitir 150–230 MB por réplica.
4. **k6 no se ve afectado.** La réplica más cargada llegó a tener 96–118 MB en
   curso, por debajo de los 136 MB (130 MiB) del límite más bajo, y no hubo
   rechazos.
5. **El límite mínimo lo fija k6.** Un límite por debajo de ese pico rechaza
   requests en el spike. Con 100 MiB apareció un `503` en k6
   (`docs/perf-queue-order.md`).

## 6. Decisión

El mecanismo queda en el código y `MAX_QUEUE_BYTES` queda **sin valor** en
`docker-compose.yml`: con la cola en orden de llegada no mejora el resultado.

El valor del despliegue se decidió en `docs/perf-queue-order.md` (#48), donde
el límite en bytes se combina con un orden de atención que deja pasar a los
PDFs chicos: 130 MiB con `QUEUE_ORDER=hrrn`.

## 7. Límites

- Una a tres pasadas por valor, con el equipo en uso y corpus sintético.
- El tamaño se toma del `Content-Length`, que incluye el envoltorio multipart
  (unos cientos de bytes por request). La reserva no se corrige después de
  leer el body.
- Un cliente que no declara `Content-Length` ocupa `MAX_UPLOAD_BYTES` aunque
  suba un PDF chico.

## 8. Reproducción

```bash
# barrido completo
make stress-queue-bytes MAX_QUEUE_SIZE=100

# un solo valor
make stress-queue-bytes MAX_QUEUE_SIZE=100 QUEUE_MEGABYTES=130
```

Cada corrida deja sus artefactos en
`tests/stress/results/queue-bytes/mb-<MiB>` y `metadata.txt` registra el
`max_queue_bytes` usado.
