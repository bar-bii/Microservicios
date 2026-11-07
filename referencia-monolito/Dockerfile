# Stage de build: resuelve dependencias con uv. Todo lo que se instala acá
# (el binario de uv, cache de resolución, etc.) no llega a la imagen final.
FROM python:3.13-slim AS builder
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
# Se copian solo los manifiestos primero para aprovechar la cache de layers
# de Docker: si el código cambia pero no las dependencias, este paso no se rehace.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

# Stage final: imagen limpia, sin uv ni herramientas de build, solo runtime.
FROM python:3.13-slim
WORKDIR /app
# Se copia el .venv ya resuelto del stage anterior en vez de reinstalar acá.
COPY --from=builder /app/.venv /app/.venv
COPY . .
# uvicorn queda accesible sin necesidad de "uv run" (uv no existe en esta imagen).
ENV PATH="/app/.venv/bin:$PATH"
CMD ["uvicorn", "presentation.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
