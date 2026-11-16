# Orden de atención de la cola: FIFO o HRRN

Fecha de medición: 2026-11-16 (UTC). Issue: #48.

## 1. Resumen

La cola atendía en orden de llegada (FIFO). Un PDF de 9 páginas, que se extrae
en milisegundos, esperaba detrás de PDFs de 500 páginas igual que cualquier
otro: en el spike de k6 el p95 de `small.pdf` era de ~15 s.

Este cambio agrega `QUEUE_ORDER=hrrn` (*highest response ratio next*): cuando
se libera un worker entra la request que más esperó **en relación con su
tamaño**. El despliegue pasa a `hrrn` con la cola limitada a 130 MiB
(`MAX_QUEUE_BYTES`, `docs/perf-queue-bytes.md`).

Con 5 réplicas, frente a la configuración anterior (FIFO, cola de 40):

- **k6**: de 445–540 a 1.640–2.029 requests, p50 de 1,6–3,6 s a ~0,5 s y p95
  de ~20 s a 5–7 s, sin errores.
- **Vegeta**: success de 8,7–10,8 % a 44,0–47,8 %, timeouts de ~195 a ~50 y
  memoria máxima de ~370 MiB a ~275 MiB.
- **Costo**: los PDFs más grandes esperan más. En k6 el p95 de `xlarge.pdf`
  sube de 25–28 s a ~36 s y la latencia máxima de 27–30 s a 36–40 s. En Vegeta
  casi no se completan (4–7 de 375).

## 2. Qué cambió

- **`WorkerGate`** (`application/worker_gate.py`) reemplaza al semáforo de
  `DocumentService`. Reparte los `WORKER_POOL_SIZE` workers y decide quién
  entra cuando se libera uno.
- **`QUEUE_ORDER`**: `fifo` (por defecto en el código) o `hrrn`.
- **`docker-compose.yml`**: `QUEUE_ORDER=hrrn`, `MAX_QUEUE_BYTES=136314880`
  (130 MiB) y `MAX_QUEUE_SIZE=100` como tope de cantidad. Un
  `MAX_QUEUE_BYTES` vacío apaga el límite en bytes.

### Cómo decide HRRN

Para cada request en espera se calcula `tiempo esperado / tamaño del PDF` y
entra la de mayor valor. Ejemplo con un worker libre:

| En espera | Tamaño | Esperó | Espera / tamaño | Entra |
| --- | ---: | ---: | ---: | --- |
| `xlarge.pdf` | 9 MB | 9 s | 1 s por MB | |
| `small.pdf` | 0,05 MB | 0,2 s | 4 s por MB | sí |

El PDF chico pasa primero aunque llegó después. El grande no queda relegado
para siempre: su valor crece mientras espera, y cuando supera al de los demás
le toca. Atender siempre al más chico (SJF) no tiene esa garantía: en k6, donde
cada cliente vuelve a pedir apenas recibe la respuesta, los PDFs grandes no se
atenderían nunca.

La política no interrumpe extracciones en curso.

## 3. Método

Mismo harness y entorno que `docs/perf-balancing.md` (Docker Desktop sobre
macOS, `linux/arm64`, 5 réplicas con `1.0` CPU y `1 GB`, balanceo `p2c`).
Se midió una matriz de orden × límite de cola, con las corridas intercaladas:

```bash
make stress-order MAX_QUEUE_SIZE=40 MAX_QUEUE_BYTES=            # cola de 40 requests
make stress-order QUEUE_ORDERS=hrrn MAX_QUEUE_BYTES=104857600   # 100 MiB
```

- "40 requests": `MAX_QUEUE_SIZE=40` sin límite en bytes (configuración
  anterior).
- "130 MiB" y demás: `MAX_QUEUE_BYTES` con `MAX_QUEUE_SIZE=100`.
- La última fila de `hrrn` con 130 MiB corrió con los valores por defecto de
  `docker-compose.yml`, sin variables.

Se descartaron dos corridas porque el equipo se suspendió durante la medición;
se repitieron. Las filas de FIFO con límite en bytes están en
`docs/perf-queue-bytes.md`.

Los números absolutos no son comparables con la referencia del enunciado (otro
hardware y otro corpus) ni con `docs/perf-queue.md` (ver
`docs/perf-balancing.md`, sección 2).

## 4. Resultados con 5 réplicas

### k6 (spike)

| Orden | Límite | Requests | req/s | Errores | p50 | p90 | p95 | max |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `fifo` | 40 requests | 487 | 9,82 | 0 % | 1,86 s | 17,61 s | 20,64 s | 26,62 s |
| `fifo` | 40 requests | 445 | 9,03 | 0 % | 3,59 s | 19,40 s | 21,37 s | 29,53 s |
| `fifo` | 40 requests | 540 | 10,93 | 0 % | 1,62 s | 17,12 s | 19,19 s | 26,83 s |
| `hrrn` | 40 requests | 1.679 | 34,26 | 0 % | 0,46 s | 4,67 s | 8,06 s | 37,01 s |
| `hrrn` | 40 requests | 1.560 | 31,90 | 0 % | 0,57 s | 4,74 s | 7,97 s | 39,70 s |
| `hrrn` | 100 MiB | 1.560 | 31,71 | 0,06 % | 0,56 s | 4,54 s | 6,73 s | 38,61 s |
| `hrrn` | **130 MiB** | 2.029 | 41,24 | 0 % | 0,44 s | 3,64 s | 5,20 s | 40,32 s |
| `hrrn` | **130 MiB** | 1.640 | 33,33 | 0 % | 0,50 s | 4,56 s | 6,83 s | 36,48 s |
| `hrrn` | **130 MiB** | 1.853 | 38,21 | 0 % | 0,47 s | 4,19 s | 6,05 s | 36,88 s |
| `hrrn` | **130 MiB** (valores por defecto) | 1.917 | 38,96 | 0 % | 0,44 s | 4,00 s | 6,01 s | 38,46 s |
| `hrrn` | 160 MiB | 1.488 | 30,24 | 0 % | 0,54 s | 4,34 s | 8,25 s | 40,88 s |
| `hrrn` | 160 MiB | 1.343 | 27,30 | 0 % | 0,57 s | 5,46 s | 10,09 s | 35,10 s |
| `hrrn` | 200 MiB | 1.813 | 37,69 | 0 % | 0,48 s | 4,34 s | 5,86 s | 39,78 s |
| `hrrn` | 200 MiB | 1.847 | 37,85 | 0 % | 0,49 s | 4,04 s | 5,70 s | 37,14 s |
| Referencia del enunciado | — | 1.037 | 25,35 | 0 % | 1,88 s | 7,83 s | 8,80 s | 13,94 s |

### Vegeta (fixed-rate)

| Orden | Límite | Success | 200 | Throughput | 503 | Timeouts | p50 / p95 de los 200 | RAM máx. |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `fifo` | 40 requests | 10,73 % | 161 | 2,68 req/s | 1.145 | 194 | 15,3 / 27,8 s | 375 MiB |
| `fifo` | 40 requests | 8,73 % | 131 | 2,20 req/s | 1.163 | 206 | 15,8 / 28,8 s | 374 MiB |
| `fifo` | 40 requests | 10,80 % | 162 | 2,73 req/s | 1.145 | 193 | 16,0 / 28,4 s | 353 MiB |
| `hrrn` | 40 requests | 26,80 % | 402 | 6,70 req/s | 955 | 143 | 4,8 / 26,4 s | 497 MiB |
| `hrrn` | 40 requests | 21,60 % | 324 | 5,42 req/s | 1.002 | 174 | 6,3 / 28,8 s | 442 MiB |
| `hrrn` | 100 MiB | 43,07 % | 646 | 11,27 req/s | 817 | 37 | 1,8 / 21,4 s | 266 MiB |
| `hrrn` | **130 MiB** | 47,60 % | 714 | 13,04 req/s | 735 | 51 | 1,6 / 19,9 s | 260 MiB |
| `hrrn` | **130 MiB** | 45,80 % | 687 | 11,75 req/s | 764 | 49 | 1,7 / 23,5 s | 272 MiB |
| `hrrn` | **130 MiB** | 44,00 % | 660 | 11,33 req/s | 787 | 53 | 2,1 / 19,7 s | 285 MiB |
| `hrrn` | **130 MiB** (valores por defecto) | 47,80 % | 717 | 12,20 req/s | 733 | 50 | 2,4 / 22,9 s | 274 MiB |
| `hrrn` | 160 MiB | 44,20 % | 663 | 11,06 req/s | 754 | 83 | 2,6 / 24,5 s | 309 MiB |
| `hrrn` | 160 MiB | 44,27 % | 664 | 11,44 req/s | 755 | 81 | 2,9 / 23,9 s | 315 MiB |
| `hrrn` | 200 MiB | 44,47 % | 667 | 11,33 req/s | 735 | 98 | 2,1 / 24,8 s | 351 MiB |
| `hrrn` | 200 MiB | 46,00 % | 690 | 12,14 req/s | 712 | 98 | 2,1 / 25,5 s | 365 MiB |
| Referencia del enunciado | — | 66,53 % | 998 | 16,65 req/s | — | 501 | — | — |

No hubo `503` de Traefik, trazas ni procesos caídos en ninguna corrida.

### Quién gana y quién pierde

Rangos entre pasadas, `fifo` con cola de 40 frente a `hrrn` con 130 MiB.

| Escenario | Métrica | Orden | small | medium | large | xlarge |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| k6 | p95 | `fifo` | 14,9–16,8 s | 17,5–19,9 s | 20,3–24,7 s | 24,7–28,3 s |
| k6 | p95 | `hrrn` | 1,1–1,6 s | 6,3–7,8 s | 17,7–18,9 s | 35,1–36,9 s |
| k6 | Respuestas `200` | `fifo` | 271–338 | 89–103 | 50–60 | 35–39 |
| k6 | Respuestas `200` | `hrrn` | 1.388–1.715 | 181–233 | 55–64 | 16–17 |
| Vegeta | Respuestas `200` (de 375) | `fifo` | 37–54 | 37–41 | 32–40 | 25–30 |
| Vegeta | Respuestas `200` (de 375) | `hrrn` | 359–375 | 214–248 | 80–95 | 4–7 |

## 5. Hallazgos

1. **En k6 se completan 3–4 veces más requests.** Los megabytes procesados
   casi no cambian (630–750 MB con `hrrn`, 640–730 MB con `fifo`): el servicio
   hace el mismo trabajo, pero ya no deja a los PDFs chicos esperando detrás de
   los grandes. Como cada cliente de k6 vuelve a pedir al recibir la respuesta,
   los de PDFs chicos completan muchas más vueltas.
2. **La latencia baja para tres de los cuatro tamaños.** En k6 el p95 de
   `small.pdf` pasa de ~15 s a ~1,5 s, el de `medium.pdf` de ~18 s a ~7 s y el
   de `large.pdf` de ~22 s a ~18 s.
3. **`xlarge.pdf` paga el costo.** En k6 su p95 sube de 25–28 s a ~36 s, se
   completan la mitad (16–17 frente a 35–39) y la latencia máxima del escenario
   sube de 27–30 s a 36–40 s. No hubo errores: el timeout de k6 es de 60 s.
4. **En Vegeta el success se multiplica por cuatro**, de 8,7–10,8 % a
   44,0–47,8 %. Se completan casi todos los `small.pdf`, cerca del 60 % de los
   `medium.pdf` y cerca de un cuarto de los `large.pdf`. De `xlarge.pdf` se completan
   4–7 de 375: a 50 req/s la carga supera varias veces la capacidad y el
   procesador se usa en las requests que cuestan menos.
5. **El límite en bytes es lo que deja la puerta abierta.** Con `hrrn` y la
   cola de 40 requests, la cola se llena de PDFs grandes en espera (270–370 MB
   por réplica) y los chicos se rechazan en la entrada: el success queda en
   21,6–26,8 % y la memoria sube a 440–500 MiB. Con el límite en bytes, un PDF
   chico casi siempre entra.
6. **130 MiB es el límite con menos timeouts sin rechazos en k6.** Con 160 y
   200 MiB el success es parecido (44–46 %), pero los timeouts suben de ~50 a
   ~80 y ~98 y la memoria de ~275 a ~310 y ~360 MiB. Con 100 MiB hay menos
   timeouts (37), pero apareció un `503` en k6: en el spike, la réplica más
   cargada llega a tener 95–112 MB en curso.
7. **Las fallas son rechazos rápidos.** Con `hrrn` y 130 MiB, las requests que
   no se atienden reciben `503` en milisegundos (733–787) en lugar de agotar
   los 30 s del cliente (49–53 timeouts).

## 6. Decisión

`docker-compose.yml` queda con `QUEUE_ORDER=hrrn`,
`MAX_QUEUE_BYTES=136314880` (130 MiB) y `MAX_QUEUE_SIZE=100`.

Los valores por defecto del código no cambian (`fifo`, sin límite en bytes,
cola de 100): dependen del despliegue y se ajustan por entorno.

**Es una decisión con un costo explícito.** Bajo sobrecarga el servicio
prioriza la cantidad de requests completadas, y los PDFs más pesados son los
que más esperan o se rechazan. Si para un despliegue importa más un trato
parejo entre tamaños que el total completado, `QUEUE_ORDER=fifo` vuelve al
comportamiento anterior.

## 7. Límites

- Dos a cuatro pasadas por configuración, con el equipo en uso. La diferencia
  entre `fifo` y `hrrn` es mucho mayor que la variación entre pasadas; la
  diferencia entre 130, 160 y 200 MiB en success no lo es.
- Corpus sintético con cuatro tamaños repartidos por igual. La ganancia de
  `hrrn` depende de esa mezcla: con PDFs de tamaño parecido el orden importa
  poco.
- El tamaño del archivo se usa como estimación del costo de extracción. En el
  corpus sintético es proporcional; un PDF real de 9 MB con muchas imágenes y
  poco texto se trataría como caro sin serlo.
- La referencia del enunciado usa otro hardware y otro corpus: no se puede
  afirmar que se la supera.

## 8. Próximos pasos

1. Repetir la matriz con el corpus oficial y en un host Linux aislado.
2. Liberar el lugar de las requests grandes que ya no pueden terminar a
   tiempo. Hoy ocupan el límite en bytes mientras esperan: en Vegeta, más de un
   tercio de los `medium.pdf` recibe `503` en la entrada y casi todos los
   timeouts son de `xlarge.pdf`.
3. Estimar el costo por cantidad de páginas en lugar de bytes.

## 9. Reproducción

```bash
# valores por defecto del despliegue (hrrn, 130 MiB)
make stress-scaled

# fifo y hrrn con la misma configuración de cola
make stress-order

# la configuración anterior
make stress-order QUEUE_ORDERS=fifo MAX_QUEUE_SIZE=40 MAX_QUEUE_BYTES=
```

Cada corrida deja sus artefactos en `tests/stress/results/order/<orden>` y
`metadata.txt` registra `queue_order`, `max_queue_size` y `max_queue_bytes`.
