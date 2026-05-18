# Docker Compose Architecture

## Goals

The local Docker stack is designed to feel lightweight for developers while preserving production-style boundaries:

- one deployable FastAPI service;
- managed stateful dependencies for PostgreSQL and Redis;
- explicit health checks before dependent services start;
- stable internal DNS names for future workers and observability services;
- persistent named volumes for data and dependency cache;
- environment-driven configuration with safe local defaults.

## Services

### `clinical-ai-api`

The API service builds from `infra/docker/api.Dockerfile` and uses the `development` target by default. It bind-mounts the repository into `/workspace`, runs Uvicorn with reload in local/test environments, and exposes `/health` as the container health check.

The service uses `depends_on` with health conditions so it waits for PostgreSQL and Redis before startup. This is local orchestration only; production deployments should still implement application-level retry logic for dependency connections.

### `clinical-ai-postgres`

PostgreSQL uses `postgres:16-alpine`, named persistent storage, and an initialization script location under `infra/postgres`. Credentials and the host port are environment-controlled through `.env`.

### `clinical-ai-redis`

Redis uses `redis:7-alpine`, a checked-in Redis config, named persistent storage, and a simple `redis-cli ping` health check.

## Networking

All services join `clinical-ai-internal`, a named bridge network. Services communicate through stable Compose DNS names such as `clinical-ai-postgres` and `clinical-ai-redis`.

This keeps local service discovery close to production service-discovery patterns and leaves room for future services:

- background workers;
- scheduler/beat processes;
- OpenTelemetry collector;
- metrics stack;
- model gateway;
- retrieval indexers;
- evaluation runners.

## Image Strategy

The FastAPI Dockerfile uses multi-stage targets:

- `base`: Python 3.12, system certificates, `uv`, source copy, startup script.
- `development`: installs workspace packages plus dev tooling.
- `production`: installs workspace packages without the dev dependency group.

The Compose stack targets `development`. Production CI/CD can build the `production` target and inject the same environment contract.

## Startup Script

`infra/docker/start-api.sh` centralizes runtime behavior:

- optional Alembic migration execution through `RUN_MIGRATIONS=true`;
- reload mode for `local` and `test`;
- worker mode for staging/production-like environments;
- env-driven host, port, and worker count.

## Environment Contract

`.env.example` documents the local defaults. The Compose file also includes defaults so a first `docker compose up --build` can work without a copied `.env` file, while still allowing developers to override ports, credentials, logging, and telemetry settings.

## Operational Notes

- Named volumes preserve database and Redis state across container restarts.
- `restart: unless-stopped` gives local resilience without hiding explicit developer shutdowns.
- Health checks make dependency readiness visible through `docker compose ps`.
- The `.dockerignore` keeps build context small and avoids copying local secrets, caches, virtual environments, and Git metadata into images.
