FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_SYSTEM_PYTHON=1
ENV UV_COMPILE_BYTECODE=1
ENV PATH="/workspace/.venv/bin:${PATH}"

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

COPY pyproject.toml README.md ./
COPY alembic.ini ./
COPY apps ./apps
COPY packages ./packages
COPY migrations ./migrations
COPY infra/docker/start-api.sh ./infra/docker/start-api.sh

RUN chmod +x ./infra/docker/start-api.sh

FROM base AS development

RUN uv sync --all-packages --group dev

EXPOSE 8000

CMD ["sh", "./infra/docker/start-api.sh"]

FROM base AS production

RUN uv sync --all-packages --no-dev

EXPOSE 8000

CMD ["sh", "./infra/docker/start-api.sh"]
