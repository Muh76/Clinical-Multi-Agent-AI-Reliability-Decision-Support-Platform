FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_SYSTEM_PYTHON=1

WORKDIR /workspace

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md ./
COPY apps ./apps
COPY packages ./packages
COPY migrations ./migrations
COPY alembic.ini ./

RUN uv sync --all-packages --group dev

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "clinical_ai_api.main:app", "--host", "0.0.0.0", "--port", "8000"]

