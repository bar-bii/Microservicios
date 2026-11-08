FROM python:3.13-slim AS builder
 WORKDIR /app 
 COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv 
 COPY pyproject.toml uv.lock README.md ./ 
 RUN uv sync --frozen --no-dev 
 FROM python:3.13-slim 
 WORKDIR /app 
 ENV PYTHONUNBUFFERED=1 \
 \ PYTHONDONTWRITEBYTECODE=1 \
 \ PATH="/app/.venv/bin:$PATH" 
 RUN useradd -m -u 1000 appuser 
 COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv 
 COPY --chown=appuser:appuser . . 
 USER appuser 
 EXPOSE 8000 
 CMD ["uvicorn", "presentation.main:app", "--host", "0.0.0.0", "--port", "8000"]