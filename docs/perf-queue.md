# Ajuste del tamaño de cola

Fecha de medición: 2026-11-16 (UTC). Issue: #44.

## 1. Resumen

Cada réplica admite `WORKER_POOL_SIZE + MAX_QUEUE_SIZE` requests a la vez y
responde `503` a las demás. Con `MAX_QUEUE_SIZE=100`, bajo la carga de Vegeta
las requests que entran al final esperan más que los 30 s del cliente y se
pierden después de consumir CPU y memoria (`docs/perf-extractor.md`).

Se midieron cinco tamaños con 5 réplicas y el valor por defecto del despliegue
pasa de **100 a 40**:

- **Vegeta**: success de 12,3–14,9 % a 17,0–19,1 %, timeouts de ~485 a ~140 y
  memoria máxima por réplica de ~715 MiB a ~410 MiB.
- **k6**: sin errores en las tres pasadas y la misma cantidad de requests.

El cambio es solo de configuración (`docker-compose.yml`).

## 2. Método

Mismo harness y entorno que `docs/perf-extractor.md` (Docker Desktop sobre
macOS, `linux/arm64`, 5 réplicas con `1.0` CPU y `1 GB`):

```bash
make stress-queue
```

El comando corre `run_benchmark.sh scaled` una vez por cada valor de
`QUEUE_SIZES` (20, 30, 40, 60 y 100), cambiando solo `MAX_QUEUE_SIZE`. Después
se repitieron 40 (dos veces más) y 30 (una vez más).

Los números absolutos no son comparables con la referencia del enunciado.

## 3. Resultados con 5 réplicas

### k6 (spike)

| Cola | Requests | req/s | Errores | 503 de la app | p50 / p95 de los 200 | RAM máx. |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20 | 622 | 12,84 | 2,57 % | 16 | 4,0 / 15,9 s | 279 MiB |
| 30 | 566 | 11,53 | 0 % | 0 | 4,2 / 17,1 s | 272 MiB |
| 30 (2.ª pasada) | 583 | 11,95 | 0 % | 0 | 4,2 / 15,8 s | 269 MiB |
| 40 | 600 | 12,02 | 0 % | 0 | 2,8 / 17,1 s | 274 MiB |
| 40 (2.ª pasada) | 560 | 11,34 | 0 % | 0 | 3,8 / 17,8 s | 294 MiB |
| 40 (3.ª pasada) | 590 | 11,85 | 0 % | 0 | 3,0 / 18,2 s | 293 MiB |
| 60 | 628 | 12,66 | 0 % | 0 | 3,1 / 16,3 s | 279 MiB |
| 100 | 574 | 11,64 | 0 % | 0 | 3,0 / 16,4 s | 268 MiB |

### Vegeta (fixed-rate)

| Cola | Success | 200 | Throughput | 503 | Timeouts | p50 / p95 de los 200 | RAM máx. |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20 | 20,40 % | 306 | 6,05 req/s | 1.193 | 1 | 14,1 / 24,7 s | 302 MiB |
| 30 | 18,80 % | 282 | 4,73 req/s | 1.162 | 56 | 19,5 / 29,0 s | 355 MiB |
| 30 (2.ª pasada) | 14,20 % | 213 | 3,60 req/s | 1.180 | 107 | 15,2 / 29,0 s | 348 MiB |
| 40 | 19,13 % | 287 | 4,79 req/s | 1.081 | 132 | 17,7 / 29,0 s | 407 MiB |
| 40 (2.ª pasada) | 17,00 % | 255 | 4,28 req/s | 1.098 | 147 | 17,6 / 27,7 s | 409 MiB |
| 40 (3.ª pasada) | 17,67 % | 265 | 4,42 req/s | 1.096 | 139 | 17,8 / 29,1 s | 415 MiB |
| 60 | 17,33 % | 260 | 4,34 req/s | 997 | 243 | 18,6 / 28,8 s | 532 MiB |
| 100 | 12,33 % | 185 | 3,09 req/s | 822 | 493 | 16,0 / 28,2 s | 716 MiB |

Para 20 y 100 hay además una pasada del día anterior en
`docs/perf-extractor.md`: 20,47 % con 2 timeouts y 14,87 % con 477 timeouts.

No hubo `503` de Traefik, trazas ni procesos caídos en ninguna corrida.

## 4. Hallazgos

1. **Una cola más corta mejora Vegeta.** El success tiende a subir a medida
   que baja la cola y los timeouts bajan de ~485 (cola de 100) a ~140 (40) y a
   1 (20). Lo
   que deja de atenderse se rechaza con `503` en milisegundos en lugar de
   ocupar CPU hasta que el cliente se va.
2. **La memoria baja con la cola.** Cada request admitida conserva su PDF en
   memoria mientras espera: de ~715 MiB con cola de 100 a ~410 MiB con 40.
3. **En k6 el tamaño de cola no cambia el throughput.** Entre 30 y 100 las
   requests van de 560 a 628, sin un orden claro: es variación entre corridas.
4. **La cola de 20 rompe el umbral de k6.** Rechazó 16 requests (2,57 %) y 13
   en la pasada del día anterior (2,12 %), por encima del 1 % permitido.
5. **30 no tiene margen; 40 sí.** Con 100 VUs el reparto entre réplicas no es
   parejo. Según el access log de Traefik, la réplica más cargada llegó a tener
   entre 27 y 36 requests simultáneas en las corridas sin rechazos. La cola de
   30 admite 34 por réplica, menos que ese máximo; la de 40 admite 44.
6. **La variación entre corridas es grande.** Para la misma cola de 30, el
   success de Vegeta fue 18,80 % y 14,20 %. Por eso la decisión se apoya en la
   diferencia entre 40 y 100, que no se solapa (17,0–19,1 % frente a
   12,3–14,9 %), y no en la diferencia entre 30 y 40.

## 5. Decisión

`MAX_QUEUE_SIZE` pasa a **40** en `docker-compose.yml`. Es el menor de los
valores medidos que deja margen sobre el pico de k6 (hallazgo 5) y conserva
casi toda la mejora de Vegeta.

El valor por defecto del código (`application/config.py`) sigue en 100: el
ajuste depende del despliegue (réplicas, CPU por réplica y timeout del
cliente), y se puede cambiar por entorno sin tocar el código.

## 6. Límites

- El valor se eligió con el corpus sintético. Con otros PDFs cambia el tiempo
  por extracción y, con él, el tamaño de cola que conviene.
- Una a tres pasadas por valor, en un laptop donde los generadores de carga
  comparten núcleos con el stack.
- El pico de 36 requests por réplica es el máximo observado en siete corridas,
  no una cota garantizada.

## 7. Próximos pasos

1. Repetir el barrido con el corpus oficial y en un host Linux aislado.
2. Reemplazar el tamaño fijo por un descarte según el tiempo de espera, para
   que el límite no dependa del tamaño de los PDFs.
3. Evaluar si otra estrategia de balanceo en Traefik reduce el desbalance del
   hallazgo 5, lo que permitiría una cola más corta. Hecho en
   `docs/perf-balancing.md` (#46): el despliegue usa `p2c`.

## 8. Reproducción

```bash
# barrido completo
make stress-queue

# un solo valor
make stress-queue QUEUE_SIZES=40
```

Cada corrida deja sus artefactos en `tests/stress/results/queue/queue-<tamaño>`
y `metadata.txt` registra el `max_queue_size` usado.
