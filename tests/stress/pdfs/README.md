# Corpus sintético

Generado por `make stress-corpus`. No editar a mano: los PDFs son
deterministas y se regeneran con el mismo contenido y hashes.

| Archivo | Objetivo | Páginas | Bytes | SHA-256 |
| --- | --- | ---: | ---: | --- |
| `small.pdf` | ~51200 | 9 | 50194 | `9747b462e27597429075496a29b2643dc7a977cc5b46cc8816536280c0e34807` |
| `medium.pdf` | ~1048576 | 95 | 1027329 | `12cac731d84f2ffa44b79783266f2efef55ad8d304e5409abb2a58dd8841f3d7` |
| `large.pdf` | ~4194304 | 289 | 4129276 | `0e637866ed3fab502db78fb99181f849c51caa09648cbe1316b1253d0b74bd8c` |
| `xlarge.pdf` | ~9437184 | 517 | 9302927 | `380f4bf553242e968e1fa5d5bbb6d1c8f68f7c2b21ff16cf9822e1df98bbc035` |

Los binarios están ignorados por Git. Regenerar con:

```bash
make stress-corpus
```
