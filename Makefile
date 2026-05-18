.PHONY: help install sync run test lint format typecheck migrate revision up down logs clean

help:
	@echo "Clinical AI Reliability & Decision Intelligence Platform"
	@echo "make install    Install workspace dependencies"
	@echo "make run        Run API locally"
	@echo "make up         Start Docker Compose stack"
	@echo "make down       Stop Docker Compose stack"
	@echo "make test       Run tests"
	@echo "make lint       Run Ruff lint"
	@echo "make format     Format Python code"
	@echo "make typecheck  Run mypy"
	@echo "make migrate    Apply Alembic migrations"
	@echo "make revision   Create Alembic revision: make revision message='add table'"

install:
	uv sync --all-packages --group dev

sync: install

run:
	uv run uvicorn clinical_ai_api.main:app --host 0.0.0.0 --port 8000 --reload

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .
	uv run ruff check . --fix

typecheck:
	uv run mypy apps packages

migrate:
	uv run alembic upgrade head

revision:
	uv run alembic revision --autogenerate -m "$(message)"

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

clean:
	uv run ruff clean

