# Estrategia de balanceo de Traefik

Fecha de medición: 2026-11-16 (UTC). Issue: #46.

## 1. Resumen

Traefik repartía las requests con `wrr` (round robin): iguala cuántas requests
*entran* a cada réplica, no cuántas tiene *en curso*. Como un PDF grande tarda
cientos de veces más que uno chico, una réplica podía acumular varias
extracciones largas mientras otra estaba casi libre (`docs/perf-queue.md`,
hallazgo 5).

Se midieron tres estrategias con 5 réplicas y el despliegue pasa de `wrr` a
**`p2c`** (*power of two choices*): para cada request Traefik toma dos réplicas
al azar y elige la que tiene menos conexiones activas.

- **Reparto**: en el spike de k6 el pico de requests simultáneas por réplica
  queda en 22–23 en todas, en lugar de variar entre 14 y 30.
- **k6**: 512–523 requests completadas frente a 455–479, sin errores.
- **Vegeta**: sin diferencia que se distinga de la variación entre corridas.
- **`leasttime` se descarta**: manda casi todo el tráfico a la réplica que
  responde más rápido, que bajo sobrecarga es la que está rechazando.

El cambio es solo de configuración (`docker-compose.yml`).

## 2. Método

Mismo harness y entorno que `docs/perf-queue.md` (Docker Desktop sobre macOS,
`linux/arm64`, 5 réplicas con `1.0` CPU y `1 GB`, cola de 40):

```bash
make stress-lb
```

El comando corre `run_benchmark.sh scaled` una vez por cada valor de
`LB_STRATEGIES` (`wrr`, `p2c` y `leasttime`), cambiando solo `LB_STRATEGY`. Se
hicieron dos pasadas intercaladas (`wrr`, `p2c`, `leasttime`, y otra vez).

El reparto sale del access log de Traefik: `ServiceAddr` identifica la réplica
y `StartUTC` + `Duration` dicen cuándo estuvo en curso cada request.

**Estos números no se comparan con los de `docs/perf-queue.md`.** La misma
configuración (`wrr`, cola de 40) dio allí 560–600 requests en k6 y 17–19 % en
Vegeta; aquí dio 455–479 y 8–14 %. Esta campaña se midió con el equipo en uso
(durante la primera pasada, además, corrían otras tareas de desarrollo). Solo
se comparan entre sí las corridas de esta campaña.

## 3. Resultados con 5 réplicas

### k6 (spike)

| Estrategia | Requests | req/s | Errores | p50 / p95 | Pico de requests simultáneas por réplica |
| --- | ---: | ---: | ---: | ---: | --- |
| `wrr` | 455 | 9,14 | 0 % | 3,7 / 20,4 s | 21, 21, 22, 24, 29 |
| `wrr` (2.ª pasada) | 479 | 9,60 | 0 % | 3,5 / 20,0 s | 14, 25, 27, 27, 30 |
| `p2c` | 523 | 10,46 | 0 % | 2,6 / 18,6 s | 22, 22, 22, 22, 22 |
| `p2c` (2.ª pasada) | 512 | 10,45 | 0 % | 1,3 / 22,1 s | 22, 22, 23, 23, 23 |
| `leasttime` | 4.000 | 80,64 | 85,60 % | 0,1 / 4,3 s | 17, 17, 19, 19, 76 |
| `leasttime` (2.ª pasada) | 605 | 12,10 | 0 % | 0,2 / 20,1 s | 21, 23, 26, 26, 28 |

En la primera pasada de `leasttime`, una réplica recibió 3.577 de las 4.000
requests y rechazó 3.424 con `503`; las respuestas `200` fueron 576.

### Vegeta (fixed-rate)

| Estrategia | Success | 200 | 503 | Timeouts | Requests recibidas por réplica |
| --- | ---: | ---: | ---: | ---: | --- |
| `wrr` | 8,47 % | 127 | 1.168 | 205 | 293, 293, 293, 294, 327 |
| `wrr` (2.ª pasada) | 13,93 % | 209 | 1.130 | 161 | 288, 289, 289, 289, 345 |
| `p2c` | 10,13 % | 152 | 1.147 | 201 | 203, 206, 227, 235, 629 |
| `p2c` (2.ª pasada) | 10,33 % | 155 | 1.163 | 182 | 208, 213, 228, 232, 619 |
| `leasttime` | 7,33 % | 110 | 1.309 | 81 | 6, 7, 45, 633, 809 |
| `leasttime` (2.ª pasada) | 3,00 % | 45 | 1.411 | 44 | 3, 4, 5, 6, 1.482 |

No hubo `503` de Traefik, trazas ni procesos caídos en ninguna corrida.

## 4. Hallazgos

1. **`p2c` empareja las requests en curso.** Con 100 VUs y 5 réplicas tocan
   20 por réplica. Con `p2c` el pico fue de 22–23 en todas; con `wrr` fue de
   14 a 30 en esta campaña y llegó a 36 en `docs/perf-queue.md`.
2. **En k6 se completan más requests con `p2c`**: 512 y 523 frente a 455 y
   479, con un p50 más bajo. El p95 no muestra una diferencia clara (18,6 y
   22,1 s frente a 20,4 y 20,0 s).
3. **En Vegeta no hay diferencia medible.** Con `wrr` el success fue 8,47 % y
   13,93 %; con `p2c`, 10,13 % y 10,33 %. Bajo esa sobrecarga las cinco
   réplicas están llenas y da igual a cuál se le pide.
4. **Con `p2c`, una réplica recibe ~41 % de las requests de Vegeta.** La
   explicación probable: cuando todas están llenas, la que tiene una conexión
   menos gana cada vez que sale sorteada. No cambió el resultado: esa réplica
   rechaza lo que no puede atender, igual que harían las otras.
5. **`leasttime` se vuelve un agujero negro.** Elige según el tiempo de
   respuesta, y una réplica llena responde `503` en milisegundos: parece la más
   rápida y atrae casi todo el tráfico mientras las demás quedan ociosas. En
   Vegeta dejó cuatro réplicas casi sin uso (3–45 requests de 1.500) y en una
   de las dos pasadas de k6 produjo 85,60 % de errores.
6. **El pico en megabytes no cambia.** `p2c` iguala la cantidad de requests,
   no su tamaño: la réplica más cargada llegó a tener ~110 MB en curso con
   `p2c` y 109–125 MB con `wrr`.

## 5. Decisión

`LB_STRATEGY` pasa a **`p2c`** en `docker-compose.yml`. Empareja la carga
entre réplicas, completó más requests en k6 en las dos pasadas y no empeoró
Vegeta. `leasttime` queda descartada por el hallazgo 5.

`MAX_QUEUE_SIZE` no cambia en este issue, aunque con `p2c` el pico de k6
(22–23) deja más margen bajo la cola de 40.

## 6. Límites

- Dos pasadas por estrategia, con el equipo en uso. La ventaja de `p2c` en k6
  (~10 % más requests) es consistente entre pasadas pero chica frente a la
  variación entre días.
- Corpus sintético: con otra mezcla de tamaños cambia cuánto se desbalancea
  `wrr`.
- El hallazgo 4 no tuvo efecto medible aquí; con réplicas de distinta
  capacidad convendría revisarlo.

## 7. Reproducción

```bash
# las tres estrategias
make stress-lb

# una sola
make stress-lb LB_STRATEGIES=p2c
```

Cada corrida deja sus artefactos en `tests/stress/results/lb/<estrategia>` y
`metadata.txt` registra el `lb_strategy` usado.
