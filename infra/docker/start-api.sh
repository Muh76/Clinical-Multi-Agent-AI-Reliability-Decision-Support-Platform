#!/usr/bin/env sh
set -eu

HOST="${API_HOST:-0.0.0.0}"
PORT="${API_PORT:-8000}"
ENVIRONMENT="${ENVIRONMENT:-local}"

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
  uv run alembic upgrade head
fi

if [ "${ENVIRONMENT}" = "local" ] || [ "${ENVIRONMENT}" = "test" ]; then
  exec uv run uvicorn clinical_ai_api.main:app \
    --host "${HOST}" \
    --port "${PORT}" \
    --reload
fi

exec uv run uvicorn clinical_ai_api.main:app \
  --host "${HOST}" \
  --port "${PORT}" \
  --workers "${API_WORKERS:-2}" \
  --proxy-headers
