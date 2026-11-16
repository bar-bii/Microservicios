# Cambio de librería de extracción: pypdf → pypdfium2

Fecha de medición: 2026-11-15 (UTC). Issue: #42.

## 1. Resumen

`docs/perf-workers.md` concluyó que el límite del servicio es la CPU que cuesta
cada extracción. Este cambio reemplaza `pypdf` (Python puro) por `pypdfium2`,
que envuelve PDFium (C++).

Con 5 réplicas y el mismo harness:

- **k6 (spike)**: de ~310 a 569 requests completadas (+83 %), de ~6,2 a
  11,5 req/s, p95 de ~28 s a 17,6 s, y cuatro veces más bytes procesados.
- **Vegeta (fixed-rate)**: la tasa de éxito casi no cambia (de ~17,7 % a
  14,9 %), aunque se procesan 3,3 veces más bytes y los timeouts bajan de ~820
  a 477. El freno pasa a ser la cola, no la extracción (sección 6).

## 2. Qué cambió

- `PdfiumPDFExtractor` implementa el `Protocol` `PDFExtractor` y reemplaza a
  `PypdfPDFExtractor`. `pypdf` sale de las dependencias.
- **Mutex de PDFium.** PDFium no es thread-safe: su documentación prohíbe
  llamadas simultáneas desde distintos threads, incluso con documentos
  distintos. Como el servicio extrae en 4 threads, todas las llamadas pasan por
  un mutex de módulo (`PDFIUM_LOCK`) y los objetos de PDFium se cierran de forma
  explícita, sin depender del recolector de basura.
- **El mutex se toma por página**, no por documento, para que un PDF chico no
  espere detrás de uno grande (sección 5).
- **Saltos de línea.** PDFium separa las líneas con `\r\n`; se normalizan a `\n`
  para mantener la respuesta (sección 7).

## 3. Método

Mismo harness y mismo entorno que `docs/perf-workers.md` (Docker Desktop sobre
macOS, `linux/arm64`, 5 réplicas con `1.0` CPU y `1 GB` cada una):

```bash
tests/stress/run_benchmark.sh scaled
```

Se midieron tres versiones del código, una pasada cada una en la misma sesión:
`main` con `pypdf`, `pypdfium2` con el mutex por documento y `pypdfium2` con el
mutex por página. Para `pypdf` se muestra además la pasada del día anterior
(`threads-4` en `docs/perf-workers.md`).

Los números absolutos no son comparables con la referencia del enunciado: son
otro hardware y otro corpus. Sirven para comparar versiones entre sí.

## 4. Resultados con 5 réplicas

### k6 (spike)

No hubo errores en ninguna versión, así que todas las requests son `200`.

| Versión | Requests | req/s | MB en 200 | p50 | p90 | p95 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `pypdf` (día anterior) | 305 | 6,10 | 230 | 1,13 s | 23,69 s | 29,11 s | 37,46 s |
| `pypdf` | 314 | 6,28 | 235 | 1,02 s | 19,99 s | 26,58 s | 42,23 s |
| `pypdfium2`, mutex por documento | 458 | 9,16 | 1.072 | 6,50 s | 15,28 s | 18,85 s | 21,73 s |
| `pypdfium2`, mutex por página | 569 | 11,52 | 939 | 1,94 s | 15,24 s | 17,58 s | 22,79 s |
| Referencia del enunciado | 1.037 | 25,35 | — | 1,88 s | 7,83 s | 8,80 s | 13,94 s |

### Vegeta (fixed-rate)

| Versión | Success | 200 | Throughput | MB en 200 | 503 de la app | Timeouts | p50 cliente | RAM máx. |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `pypdf` (día anterior) | 18,47 % | 277 | 4,62 req/s | 203 | 431 | 789 | 30,00 s | 578 MiB |
| `pypdf` | 16,93 % | 254 | 4,23 req/s | 192 | 396 | 849 | 30,00 s | 515 MiB |
| `pypdfium2`, mutex por documento | 16,40 % | 246 | 4,11 req/s | 790 | 777 | 477 | 0,02 s | 666 MiB |
| `pypdfium2`, mutex por página | 14,87 % | 223 | 3,73 req/s | 652 | 800 | 477 | 0,02 s | 714 MiB |
| Referencia del enunciado | 66,53 % | 998 | 16,65 req/s | — | — | 501 | 14,89 s | — |

No hubo `503` de Traefik ni caídas de la app en ninguna versión.

### Qué tamaños se completan

Respuestas `200` por tamaño de PDF, según el access log de Traefik:

| Escenario | Versión | small | medium | large | xlarge |
| --- | --- | ---: | ---: | ---: | ---: |
| k6 | `pypdf` | 224 | 61 | 21 | 8 |
| k6 | `pypdfium2`, mutex por documento | 196 | 113 | 85 | 64 |
| k6 | `pypdfium2`, mutex por página | 313 | 125 | 82 | 49 |
| Vegeta | `pypdf` | 141 | 118 | 11 | 2 |
| Vegeta | `pypdfium2`, mutex por documento | 78 | 47 | 75 | 46 |
| Vegeta | `pypdfium2`, mutex por página | 75 | 48 | 64 | 36 |

## 5. Mutex por documento o por página

Microbenchmark fuera de Docker: un thread extrae `xlarge.pdf` (517 páginas) y
0,1 s después otro extrae `small.pdf` (9 páginas, 7 ms a solas).

| Dónde se toma el mutex | Latencia de `small.pdf` | Duración de `xlarge.pdf` |
| --- | ---: | ---: |
| Por documento | 1.173 ms | 1,28 s |
| Por página | 20 ms | 1,27 s |

Tomarlo por página intercala las extracciones sin costo para la grande. Con
5 réplicas eso se traduce en 569 requests frente a 458 en k6 y un p50 de 1,94 s
frente a 6,50 s. En Vegeta la versión por documento quedó algo arriba (246
frente a 223 respuestas `200`); con una sola pasada no se puede distinguir de la
variación entre corridas, que para `pypdf` fue de 254 a 277.

Se eligió el mutex por página por su ventaja en k6.

## 6. Hallazgos

1. **La extracción es unas 3 veces más barata.** En un microbenchmark fuera de
   Docker, `pypdfium2` extrajo el mismo texto que `pypdf` en 0,15 s frente a
   0,46 s (`medium.pdf`), 0,58 s frente a 1,87 s (`large.pdf`) y 1,44 s frente a
   4,24 s (`xlarge.pdf`). Con 5 réplicas se procesan cuatro veces más bytes en
   k6 y 3,3 veces más en Vegeta.
2. **k6 mejora en todas las métricas de cola larga.** Se completan 569 requests
   en lugar de ~310 y el p95 baja de ~28 s a 17,6 s. El p50 sube de ~1,1 s a
   1,94 s porque ahora también se completan PDFs grandes, que antes casi no
   terminaban.
3. **En Vegeta el freno es la cola.** A 50 req/s llegan unos 180 MB/s y el
   servicio completa a tiempo alrededor de 11 MB/s, así que la cola de 100
   lugares por réplica se llena en segundos. Quien entra al final espera más
   que los 30 s del cliente y se pierde: por eso la cantidad de `200` casi no
   cambia aunque cada extracción cueste un tercio. La mezcla de tamaños va en
   la misma dirección: con `pypdfium2` se completan los cuatro tamaños en
   proporciones más parejas, mientras que con `pypdf` casi todo lo completado
   era chico. Una corrida exploratoria con la cola más corta va en el mismo
   sentido (sección 8).
4. **Las fallas pasan a ser rechazos rápidos.** Con `pypdfium2` los timeouts
   bajan de ~820 a 477 y los `503` de la cola suben de ~410 a 800; el p50 del
   cliente pasa de 30 s a 0,02 s. La explicación probable es que las llamadas
   a PDFium liberan el GIL, así que el runtime HTTP sigue respondiendo aunque
   los 4 threads estén ocupados.
5. **La memoria sube en Vegeta** (de ~550 MiB a 714 MiB) y queda igual en k6
   (~295 MiB). Sigue lejos del límite de 1 GiB.

## 7. Diferencias en el texto devuelto

- Dentro de una página, PDFium separa las líneas con `\r\n`. Se normaliza a
  `\n`, que es lo que devolvía `pypdf`.
- `pypdf` agregaba un `\n` al final de algunas páginas; `pypdfium2` no. Los
  fixtures del repo (`hello.pdf`, `hello_two_pages.pdf`) devuelven exactamente
  el mismo `content` que antes.
- En `small.pdf`, `medium.pdf` y `large.pdf` del corpus sintético se comparó
  página por página: las 393 páginas difieren solo en ese `\n` final.

## 8. Próximos pasos

1. **Ajustar la cola al timeout del cliente** (hallazgo 3). Es lo que ahora
   limita la tasa de éxito en Vegeta. Una corrida exploratoria con
   `MAX_QUEUE_SIZE=20` (una sola pasada, mismo código) apoya la hipótesis:

   | Cola por réplica | Success en Vegeta | 200 | Timeouts | RAM máx. | Requests en k6 | Errores en k6 |
   | --- | ---: | ---: | ---: | ---: | ---: | ---: |
   | 100 (actual) | 14,87 % | 223 | 477 | 714 MiB | 569 | 0 % |
   | 20 | 20,47 % | 307 | 2 | 288 MiB | 613 | 2,12 % |

   Con la cola corta casi desaparecen los timeouts y la memoria baja a menos de
   la mitad, pero en el spike de k6 aparecen 13 rechazos `503`, que rompen el
   umbral de 1 % de errores. Elegir el tamaño queda fuera de este cambio; el
   barrido y la decisión están en `docs/perf-queue.md`.
2. Repetir las mediciones con el corpus oficial del enunciado y en un host
   Linux aislado, con más de una pasada por versión.
3. Priorizar los PDFs chicos antes de que entren al pool de 4 threads: el
   intercalado por página solo actúa entre las extracciones ya activas.

## 9. Reproducción

```bash
make stress-scaled
```

Para comparar contra `pypdf`, correr el mismo comando sobre el commit anterior a
este cambio. Los artefactos quedan en `tests/stress/results/scaled` e incluyen
los logs de la app y de Traefik de donde salen las tablas.
