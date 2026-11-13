# Contributing

## Metodología: TDD obligatorio

Cada cambio sigue Red → Green → Refactor:

1. **Red**: escribir un test que falle y describa el comportamiento esperado.
2. **Green**: implementar lo mínimo para que pase.
3. **Refactor**: mejorar el diseño sin romper los tests.

No se agrega código de implementación sin un test previo. Si el test no existe, la funcionalidad no existe.

## Convención de commits

Formato: `tipo(scope): descripción en presente`

Tipos permitidos:

| Tipo | Uso |
| --- | --- |
| `feat` | nueva funcionalidad |
| `fix` | corrección de bug |
| `test` | tests |
| `refactor` | refactor sin cambio de comportamiento |
| `chore` | tooling, CI, mantenimiento |
| `docs` | documentación |

Ejemplos:

```
test(api): cubrir rechazo de MIME inválido
fix(api): validar Content-Type application/pdf
chore(ci): agregar workflow de ruff y pytest
```

Reglas:

- Un commit = un cambio lógico.
- No mezclar features distintas en un mismo commit.
- En TDD, el commit de test va antes del commit de implementación.

## Convención de ramas

Formato: `NNN-tipo-scope-descripcion`, donde `NNN` es el número de issue.

Ejemplos:

```
16-chore-ci-baseline
17-fix-api-mime-limits
18-fix-infra-docker-compose
```

- Una rama por issue.
- Sin `&`, espacios ni acentos en el nombre.
- Borrar la rama después del merge.

## Flujo de trabajo

1. Crear la issue con la plantilla correspondiente y criterios de aceptación.
2. Crear la rama desde `main` actualizado.
3. Implementar con TDD en commits pequeños.
4. Abrir PR usando la plantilla y referenciar la issue con `Closes #NNN`.
5. Merge con **squash** y borrar la rama.

## Calidad local

Antes de abrir un PR:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

El CI ejecuta lo mismo más cobertura; el umbral mínimo está en `pyproject.toml`.

## Estilo de código

- Nombres descriptivos y funciones pequeñas.
- Sin comentarios que expliquen *qué* hace el código.
- Depender de abstracciones (`Protocol`) en lugar de implementaciones concretas.
- Configuración por variables de entorno (12-factor).
