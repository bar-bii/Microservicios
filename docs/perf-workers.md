# Evaluación de estrategias de concurrencia (GIL)

Fecha de medición: 2026-11-14 (UTC). Issue: #30.

## 1. Pregunta

`DocumentService` extrae con `pypdf` en threads (`asyncio.to_thread`) limitados
por un semáforo. `pypdf` es CPU-bound y el GIL impide que dos threads extraigan
en paralelo. ¿Conviene cambiar los threads por procesos, por varios workers de
uvicorn o por un worker pool separado, dado que cada réplica tiene como máximo
`1.0` CPU y `1 GB` de RAM?

**Respuesta corta:** no. Bajo el límite de 1 CPU por réplica ninguna alternativa
aporta CPU adicional, y las que usan varios procesos completan menos requests y
consumen más memoria. Se recomienda mantener la configuración actual
(`EXTRACTION_EXECUTOR=thread`, `WORKER_POOL_SIZE=4`).

## 2. Alternativas

| Variante | Cómo se activa | Qué cambia |
| --- | --- | --- |
| `threads-4` | valores por defecto | Estado actual: 4 extracciones simultáneas en threads. |
| `threads-1` | `WORKER_POOL_SIZE=1` | Una extracción por vez, en un thread. |
| `processes-4` | `EXTRACTION_EXECUTOR=process` | `ProcessPoolExecutor` con 4 procesos (`spawn`). |
| `processes-1` | `EXTRACTION_EXECUTOR=process WORKER_POOL_SIZE=1` | Un solo proceso de extracción, separado del runtime HTTP. |
| `uvicorn-4` | `WEB_CONCURRENCY=4 WORKER_POOL_SIZE=1` | 4 procesos de uvicorn por réplica, cada uno con su cola. |
| Worker pool como servicio dedicado | no implementado | Ver sección 7. |

`EXTRACTION_EXECUTOR=process` es el prototipo de esta evaluación: el runtime
HTTP queda en un proceso y la extracción en otros. `WEB_CONCURRENCY` es la
variable estándar de uvicorn para `--workers`. Las tres variables llegan al
servicio por `docker-compose.yml` y sus valores por defecto no cambian el
comportamiento previo.

## 3. Método

Cada variante se midió con `tests/stress/run_benchmark.sh`, que levanta una pila
limpia por escenario, corre k6 (spike, 100 VUs, ventana de 50 s) y Vegeta
(50 req/s durante 30 s, timeout de 30 s) contra el corpus sintético, y guarda
`docker stats` y los logs JSON de la app y de Traefik.

- **1 réplica**: las cinco variantes, dos pasadas cada una.
- **5 réplicas**: las cinco variantes, una pasada cada una.

Entorno:

| Ítem | Valor |
| --- | --- |
| Host | Apple M1 Pro (8 núcleos), macOS |
| Docker | Docker Desktop 29.6.2, VM `linux/arm64` con 8 CPU y ~7,75 GiB |
| Docker Compose | 5.3.1 |
| Límite por réplica | `1.0` CPU, `1 GB` de RAM |
| k6 | `grafana/k6:1.8.3` |
| Vegeta | `peterevans/vegeta:6.9.1` (imagen `amd64`, emulada) |

De dónde sale cada métrica:

- **Requests, errores, success, timeouts, p50 cliente**: resumen de k6 y reporte
  de Vegeta.
- **200, MB en 200, percentiles de los 200**: access log de Traefik, filtrando
  `DownstreamStatus=200`. La latencia es `Duration` e incluye la subida.
- **503 de Traefik / 503 de la app**: en el access log de Traefik, un `503` con
  `OriginStatus=0` lo generó el proxy; con `OriginStatus=503` lo devolvió la app.
- **CPU media y RAM máxima**: `docker stats` de los contenedores `app`. La CPU
  media considera solo las muestras con carga; la RAM es el máximo de una
  réplica.

**Por qué "MB en 200".** La cantidad de respuestas `200` no alcanza para
comparar trabajo útil, porque la mezcla de tamaños completados cambia entre
variantes: un PDF de 9 MiB cuesta unas cien veces más CPU que uno de 50 KiB. La
suma de bytes de las requests respondidas con `200` aproxima el trabajo hecho.

Limitaciones:

- Los números absolutos no son comparables con `docs/report.md` ni con la
  referencia: se midió en otra máquina, y los generadores de carga comparten los
  núcleos del host con el stack.
- Con 5 réplicas hay una sola pasada por variante.
- La primera pasada de 1 réplica se corrió antes de #40. La única diferencia es
  cómo se registra un corte del cliente (`500` con traza frente a `499`).

## 4. Resultados con 1 réplica

Cada celda muestra primera pasada / segunda pasada.

### k6 (spike)

| Variante | Requests | Errores | 200 | MB en 200 | p50 de los 200 | 503 de Traefik | RAM máx. |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `threads-4` | 39.681 / 71.562 | 99,74 % / 99,85 % | 104 / 105 | 54 / 57 | 8,7 / 7,7 s | 39.577 / 71.457 | 554 / 560 MiB |
| `threads-1` | 49 / 53 | 0 % / 0 % | 49 / 53 | 55 / 68 | 8,3 / 7,3 s | 0 / 0 | 535 / 543 MiB |
| `processes-4` | 23 / 22 | 0 % / 0 % | 23 / 22 | 33 / 29 | 15,6 / 23,2 s | 0 / 0 | 739 / 737 MiB |
| `processes-1` | 32 / 35 | 0 % / 0 % | 32 / 35 | 64 / 69 | 12,6 / 12,4 s | 0 / 0 | 600 / 622 MiB |
| `uvicorn-4` | 53 / 56 | 0 % / 0 % | 53 / 56 | 43 / 33 | 4,9 / 9,7 s | 0 / 0 | 750 / 731 MiB |

La app no devolvió ningún `503` en k6: con 100 VUs nunca se supera la capacidad
de la cola (`WORKER_POOL_SIZE + MAX_QUEUE_SIZE`). La CPU media estuvo entre 95 %
y 101 % en todas las variantes.

### Vegeta (fixed-rate)

| Variante | Success | 200 | MB en 200 | 503 de la app | 503 de Traefik | Timeouts | p50 cliente | RAM máx. |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `threads-4` | 4,00 % / 4,33 % | 60 / 65 | 33 / 41 | 18 / 24 | 369 / 420 | 1.065 / 1.005 | 30,00 / 30,00 s | 336 / 466 MiB |
| `threads-1` | 3,13 % / 3,47 % | 47 / 52 | 32 / 37 | 1.072 / 1.068 | 265 / 271 | 116 / 109 | 2,41 / 5,87 s | 688 / 734 MiB |
| `processes-4` | 1,87 % / 1,73 % | 28 / 26 | 20 / 16 | 1.368 / 1.371 | 0 / 0 | 104 / 103 | 0,13 / 0,27 s | 830 / 816 MiB |
| `processes-1` | 0,67 % / 0,87 % | 10 / 13 | 30 / 35 | 1.389 / 1.386 | 0 / 0 | 101 / 101 | 0,00 / 0,00 s | 627 / 656 MiB |
| `uvicorn-4` | 3,93 % / 3,27 % | 59 / 49 | 26 / 30 | 705 / 690 | 304 / 336 | 431 / 423 | 11,63 / 9,31 s | 1 GiB / 1 GiB (límite) |

## 5. Resultados con 5 réplicas

Una pasada por variante. Es la configuración del despliegue evaluado.

### k6 (spike)

| Variante | Requests | Errores | 200 | MB en 200 | p50 / p95 / p99 de los 200 | CPU media | RAM máx. |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `threads-4` | 305 | 0 % | 305 | 230 | 1,1 / 29,1 / 34,2 s | 97 % | 300 MiB |
| `threads-1` | 141 | 0 % | 141 | 281 | 10,7 / 30,6 / 33,2 s | 100 % | 263 MiB |
| `processes-4` | 95 | 0 % | 95 | 157 | 13,0 / 33,8 / 41,9 s | 102 % | 537 MiB |
| `processes-1` | 116 | 0 % | 116 | 285 | 12,1 / 32,4 / 36,7 s | 100 % | 343 MiB |
| `uvicorn-4` | 153 | 0 % | 154 | 212 | 3,9 / 34,4 / 38,0 s | 99 % | 504 MiB |

No hubo `503` de Traefik ni de la app en ninguna variante. La columna `200`
sale del access log de Traefik y puede diferir en una unidad del conteo de k6.

### Vegeta (fixed-rate)

| Variante | Success | 200 | MB en 200 | p50 / p95 de los 200 | 503 de la app | 502 | Timeouts | p50 cliente | RAM máx. |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `threads-4` | 18,47 % | 277 | 203 | 13,7 / 30,0 s | 431 | 203 | 789 | 30,00 s | 578 MiB |
| `threads-1` | 7,00 % | 105 | 185 | 12,0 / 27,6 s | 896 | 0 | 499 | 0,06 s | 698 MiB |
| `processes-4` | 4,73 % | 71 | 73 | 15,3 / 26,2 s | 911 | 0 | 518 | 0,05 s | 988 MiB |
| `processes-1` | 3,40 % | 51 | 177 | 14,3 / 28,9 s | 947 | 0 | 502 | 0,01 s | 775 MiB |
| `uvicorn-4` | 5,40 % | 81 | 85 | 12,9 / 27,1 s | 0 | 265 | 1.154 | 30,00 s | 1 GiB (límite) |

No hubo `503` de Traefik en ninguna variante. Sobre la columna `502`:

- En `threads-4` son subidas que el cliente cortó por su timeout de 30 s: la
  mediana de duración es 32 s, el body registrado está incompleto y la app las
  anotó como `499`. Vegeta ya las cuenta como timeouts.
- En `uvicorn-4` coinciden con workers caídos: el log de la app registra cuatro
  `Child process died` y la réplica llegó al límite de memoria.

## 6. Hallazgos

1. **El límite es la CPU, no el GIL.** Todas las variantes usan ~100 % de la CPU
   asignada. Con 1 CPU por réplica, repartir la extracción en procesos no agrega
   capacidad: solo reparte la misma CPU entre más procesos.
2. **La configuración actual completa más requests con 5 réplicas.** `threads-4`
   respondió 305 requests en k6 y 18,47 % en Vegeta; la mejor alternativa quedó
   en 153 y 7,00 %. Las variantes de una extracción por vez (`threads-1`,
   `processes-1`) procesan más bytes (281 y 285 MB frente a 230 MB) pero
   completan menos de la mitad de las requests y su p50 es diez veces peor,
   porque los PDFs chicos esperan detrás de los grandes. Con 4 threads las
   extracciones se turnan y los chicos salen rápido.
3. **Los procesos rinden menos y gastan más memoria.** `processes-4` fue la
   variante con menos trabajo útil en todos los escenarios y usó hasta
   988 MiB. `uvicorn-4` llegó al límite de 1 GiB en Vegeta en las tres corridas
   y perdió workers con 5 réplicas. No se aisló la causa del menor rendimiento;
   las candidatas son la copia de cada PDF y de su texto entre procesos, el
   reparto de 1 CPU entre el runtime HTTP y los workers, y la presión de
   memoria.
4. **Los `503` masivos con 1 réplica los genera Traefik, no la cola.** En
   `threads-4` con 1 réplica, k6 recibió 39.577 y 71.457 respuestas `503`, todas
   con `OriginStatus=0` y un body de 20 bytes (`no available server`); la app no
   devolvió ningún `503`. Es el comportamiento de Traefik cuando su health check
   saca del balanceo a la única réplica. No se capturó el log del health check
   (el nivel de log por defecto no lo emite), así que la causa se infiere del
   access log. Con 1 réplica también aparece bajo Vegeta en `threads-1` y
   `uvicorn-4` (265 a 336 respuestas); no aparece en `processes-4` ni
   `processes-1`, ni en ninguna variante con 5 réplicas. Esto corrige la
   lectura de `docs/report.md`, que atribuía esos `503` al backpressure.
5. **Separar la extracción del runtime HTTP hace que el rechazo sea rápido.**
   Con procesos, Vegeta recibe el `503` de la cola en milisegundos (p50 de
   0,00 a 0,27 s) y hay menos timeouts: unos 100 frente a más de 1.000 con
   1 réplica, y unos 500 frente a 789 con 5 réplicas. Con `threads-4`, la
   mayoría de las fallas son timeouts de 30 s, es decir, trabajo que se paga y
   no se entrega.
6. **La memoria crece con la cola.** Cada request admitida conserva su PDF en
   memoria mientras espera turno. Con `MAX_QUEUE_SIZE=100` y PDFs de hasta
   9 MiB eso explica los picos de 700 MiB o más, y `uvicorn-4` multiplica la
   cola por cuatro.

## 7. Recomendación

- **Mantener `EXTRACTION_EXECUTOR=thread` y `WORKER_POOL_SIZE=4`** en el
  despliegue de 5 réplicas. Es la variante con más requests completadas y mejor
  p50, y su memoria queda lejos del límite.
- **No adoptar el process pool ni `WEB_CONCURRENCY > 1`** mientras cada réplica
  tenga 1 CPU y 1 GB: completan menos requests y dejan la réplica cerca del
  límite de memoria o sobre él.
- **Conservar el prototipo detrás de `EXTRACTION_EXECUTOR`**, desactivado por
  defecto, para repetir la comparación si cambia el límite de CPU por réplica o
  la librería de extracción.

Trade-off que se acepta: con `threads-4`, una réplica sola y saturada puede
perder su health check (hallazgo 4), y las fallas llegan como timeouts en lugar
de rechazos rápidos (hallazgo 5).

**Worker pool como servicio dedicado.** No se midió. Bajo las restricciones del
enunciado, un servicio de workers aparte toma CPU del mismo presupuesto de
réplicas o agrega contenedores fuera del límite, y el process pool, que es la
versión más barata de esa separación, ya muestra que separar no aumenta el
trabajo útil con 1 CPU. Queda descartado hasta que cambie esa restricción.

## 8. Próximos pasos

1. Evaluar una librería de extracción con menor costo de CPU. Como el límite es
   la CPU, es la vía con más potencial para subir la capacidad por réplica.
2. Ajustar la cola al timeout del cliente: con `MAX_QUEUE_SIZE=100` hay requests
   que esperan más de 30 s y se pierden después de consumir CPU y memoria.
3. Priorizar explícitamente los PDFs chicos. Hoy el efecto aparece de forma
   indirecta por el reparto entre 4 threads (hallazgo 2).
4. Revisar el health check de Traefik para que una réplica saturada no salga del
   balanceo (hallazgo 4).
5. Repetir las corridas de 5 réplicas en un host Linux aislado y con más de una
   pasada.

## 9. Reproducción

```bash
# 1 réplica, cinco variantes
make stress-workers

# 5 réplicas, una variante por comando
RESULTS_DIR=tests/stress/results/workers-scaled/threads-4 \
  tests/stress/run_benchmark.sh scaled
WORKER_POOL_SIZE=1 RESULTS_DIR=tests/stress/results/workers-scaled/threads-1 \
  tests/stress/run_benchmark.sh scaled
EXTRACTION_EXECUTOR=process RESULTS_DIR=tests/stress/results/workers-scaled/processes-4 \
  tests/stress/run_benchmark.sh scaled
EXTRACTION_EXECUTOR=process WORKER_POOL_SIZE=1 \
  RESULTS_DIR=tests/stress/results/workers-scaled/processes-1 \
  tests/stress/run_benchmark.sh scaled
WEB_CONCURRENCY=4 WORKER_POOL_SIZE=1 RESULTS_DIR=tests/stress/results/workers-scaled/uvicorn-4 \
  tests/stress/run_benchmark.sh scaled
```

Cada directorio de resultados incluye `metadata.txt` con la variante medida,
los reportes de k6 y Vegeta, `docker-stats-{k6,vegeta}.txt` y
`compose-logs-{k6,vegeta}.log`. Los artefactos están ignorados por Git. El
detalle del harness está en `tests/stress/README.md`.
