# syntax=docker/dockerfile:1
# Both stages must use the same Python image: the venv links to its interpreter.
ARG PYTHON_IMAGE=python:3.13-slim

FROM ghcr.io/astral-sh/uv:0.13 AS uv

FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app

# Dependencies first so code changes reuse the cached layer.
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

FROM ${PYTHON_IMAGE} AS final
RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --no-create-home app
WORKDIR /app

# Code stays root-owned (read-only for the app user); only local storage is writable.
COPY --from=build /app /app
RUN mkdir -p /app/App_Data && chown app:app /app/App_Data

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

USER app
EXPOSE 8080

# Cloud Run sets PORT. Migrations run from this same image: `alembic upgrade head`.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8080}\" --proxy-headers --forwarded-allow-ips '*'"]
