# Clinical AI Reliability & Decision Intelligence Platform

Production-grade monorepo scaffold for AI reliability analysis, safety validation, evidence-grounded clinical decision support, multimodal orchestration, explainability, auditability, and observability.

This is not a diagnosis chatbot. The platform is organized around reliability, evidence, governance, and decision intelligence.

## Architecture

```text
apps/
  api/                         FastAPI service boundary
    src/clinical_ai_api/
      main.py                   App factory and ASGI entrypoint
      api/                      Route composition and dependency wiring
        v1/                     Versioned API surface
      core/                     Lifespan and centralized error handling
      middleware/               Future middleware registration hooks
      schemas/                  Request and response models
      services/                 Application service layer
packages/
  platform/                    Config, database, logging, observability
  shared/                      Shared contracts and domain primitives
  agents/                      Agent orchestration interfaces
  retrieval/                   Evidence retrieval and indexing pipelines
  evaluation/                  Reliability and safety evaluation systems
  safety/                      Safety critics and validation policies
  multimodal/                  Multimodal ingestion and normalization
infra/
  docker/                      Service container definitions
  postgres/                    Local PostgreSQL bootstrap
  redis/                       Local Redis configuration
migrations/                    Alembic migration environment
docs/
  architecture/                Architecture decision records and diagrams
  standards/                   Engineering, clinical safety, and coding rules
scripts/                       Developer and automation scripts
```

## API Surface

The service exposes infrastructure health outside the versioned API and product routes under `/api/v1`.

```text
GET  /health
GET  /api/v1/patients
POST /api/v1/safety/assess
GET  /api/v1/evaluation/runs
POST /api/v1/evaluation/runs
```

The backend uses thin endpoint modules, typed dependency providers, consistent response envelopes, centralized exception handling, and a service layer that can later coordinate retrieval, safety critics, evaluation runs, multimodal processing, and AI agent workflows.

## Docker Stack

The local Compose stack includes:

- `clinical-ai-api`: FastAPI application built from `infra/docker/api.Dockerfile`.
- `clinical-ai-postgres`: PostgreSQL 16 with persistent storage and health checks.
- `clinical-ai-redis`: Redis 7 with persistent storage and health checks.

All services run on the `clinical-ai-internal` bridge network. PostgreSQL, Redis, and the API expose developer-friendly host ports through environment variables, while containers communicate by stable internal DNS names.

Key Docker files:

```text
docker-compose.yml
.dockerignore
infra/docker/api.Dockerfile
infra/docker/start-api.sh
infra/postgres/init.sql
infra/redis/redis.conf
```

## Local Development

1. Install `uv`.
2. Copy `.env.example` to `.env` when you want to override local defaults.
3. Install local Python dependencies:

```bash
make install
```

4. Start the local stack:

```bash
make up
```

5. Visit:

```text
http://localhost:8000/health
http://localhost:8000/docs
```

The Compose stack can run without a `.env` file because the compose file includes safe local defaults. Use `.env` for explicit port, credential, logging, and telemetry overrides.

## Common Commands

```bash
make run
make test
make lint
make format
make typecheck
make migrate
make revision message="add clinical evidence tables"
```

## Environment

Important local environment variables are documented in `.env.example`:

```text
APP_NAME
APP_VERSION
ENVIRONMENT
ENABLE_DOCS
API_HOST
API_PORT
API_WORKERS
RUN_MIGRATIONS
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_DB
POSTGRES_PORT
DATABASE_URL
REDIS_PORT
REDIS_URL
LOG_LEVEL
LOG_JSON
OTEL_SERVICE_NAME
OTEL_EXPORTER_OTLP_ENDPOINT
```

## Design Principles

- Async-first service and data access.
- Strong module boundaries between API, platform infrastructure, and AI domains.
- Evidence-grounded outputs with explicit provenance and audit trails.
- Observability as a default capability, not a late-stage add-on.
- Safety validation separated from generation and orchestration.
- Agent-ready contracts without coupling the core platform to a specific agent framework.
- Versioned APIs with stable infrastructure health endpoints.
- Service-layer workflows that can be reused by API routes, workers, schedulers, and evaluation pipelines.

## Initial Roadmap

- Add clinical evidence, case, audit event, and evaluation run models.
- Add OpenTelemetry tracing middleware and metrics export.
- Add retrieval adapters for guidelines, local policies, and literature indexes.
- Add safety critic pipeline with explainable risk classifications.
- Add agent orchestration service with durable run state.
- Add multimodal ingest contracts for text, image, PDF, audio, and structured EHR payloads.

## Clinical Safety Notice

This system is intended to support reliability analysis and evidence-grounded clinical decision support workflows. It must not be represented as a standalone diagnostic authority. Human clinical oversight, validation, auditability, and deployment governance are required.
