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
  platform/                    Config, async database, logging, observability
    src/clinical_ai_platform/cache/
      redis.py                  Async Redis client manager
      service.py                JSON cache service abstraction
    src/clinical_ai_platform/core/
      settings.py               Typed environment-driven configuration
    src/clinical_ai_platform/db/
      base.py                   SQLAlchemy declarative base and mixins
      session.py                Async engine, pool, session factory
      models/                   Patient, clinical case, and audit ORM models
    src/clinical_ai_platform/observability/
      logging.py                structlog JSON logging configuration
      tracing.py                Request, correlation, and agent trace context helpers
  shared/                      Shared contracts and domain primitives
  agents/                      Agent orchestration interfaces
  retrieval/                   Qdrant-backed evidence retrieval and indexing pipelines
  evaluation/                  Reliability and safety evaluation systems
  safety/                      Safety critics and validation policies
  multimodal/                  Multimodal ingestion and patient context processing
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
GET  /health/live
GET  /health/ready
GET  /api/v1/patients
POST /api/v1/safety/assess
GET  /api/v1/evaluation/runs
POST /api/v1/evaluation/runs
POST /api/v1/workflows/evidence-grounding
```

The backend uses thin endpoint modules, typed dependency providers, consistent response envelopes, centralized exception handling, and a service layer that can later coordinate retrieval, safety critics, evaluation runs, multimodal processing, and AI agent workflows.

`/health` includes dependency status for PostgreSQL and Redis so orchestration systems can distinguish application availability from dependency degradation. `/health/live` is process-level liveness, while `/health/ready` validates required dependencies before the instance receives traffic.

## Current Platform Foundations

Implemented foundations:

- modular Pydantic Settings with environment-specific loading and validation;
- async FastAPI application factory with lifespan-managed resources;
- versioned API routing under `/api/v1`;
- centralized response envelopes and error handling;
- SQLAlchemy 2.0 async PostgreSQL engine, pool, session factory, and request-scoped sessions;
- initial ORM models for `Patient`, `ClinicalCase`, and `AuditLog`;
- Alembic async migration environment with the first clinical tables migration;
- async Redis connection manager with pooled connections;
- Redis-backed JSON cache service abstraction;
- patient context processing layer for multimodal clinical normalization, validation, missingness,
  and temporal preparation;
- Qdrant-backed vector retrieval package with async indexing/search boundaries;
- sentence-transformers embedding provider with future hosted provider extension points;
- PubMed evidence retrieval architecture for abstract normalization, citation preservation,
  metadata extraction, and retrieval-ready biomedical indexing;
- clinical retrieval evaluation framework for evidence reliability, citation grounding,
  hallucination risk, retrieval robustness, confidence calibration, and evaluation logging;
- first end-to-end evidence grounding workflow for patient context processing, evidence retrieval,
  reranking, citation packaging, confidence scoring, and workflow tracing;
- Redis dependency health reporting through `/health`;
- liveness and readiness endpoints for container orchestration;
- structured JSON logging with request and correlation IDs;
- request tracing middleware with latency and error logging;
- Docker Compose stack for FastAPI, PostgreSQL, and Redis.

## Docker Stack

The local Compose stack includes:

- `clinical-ai-api`: FastAPI application built from `infra/docker/api.Dockerfile`.
- `clinical-ai-postgres`: PostgreSQL 16 with persistent storage and health checks.
- `clinical-ai-redis`: Redis 7 with persistent storage and health checks.
- `clinical-ai-qdrant`: Qdrant vector database for evidence retrieval indexes.

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

## Synthetic Development Data

Generate fictional clinical-looking data for local development:

```bash
python scripts/generate_synthetic_clinical_dataset.py --patients 25 --output-dir tmp/synthetic_clinical_dataset
```

The generator exports JSON and CSV files for demographics, vitals, labs, medications, and notes. It is deterministic with a seed and writes a schema file beside the generated data.

Checked-in sample outputs live under:

```text
docs/samples/synthetic_clinical_dataset/
  dataset.json
  patients.csv
  vitals.csv
  labs.csv
  medications.csv
  notes.csv
  schema.json
```

This is synthetic development data only, not real patient data. Design notes live in `docs/architecture/synthetic-data.md`.

## Database And Migrations

The platform uses SQLAlchemy 2.0 async with `asyncpg`, request-scoped `AsyncSession` dependencies, and Alembic migrations.

Initial ORM models:

- `Patient`
- `ClinicalCase`
- `AuditLog`

Initial migration:

```text
migrations/versions/20260518_0001_initial_clinical_tables.py
```

Apply migrations:

```bash
make migrate
```

Create a new migration after model changes:

```bash
make revision message="add evaluation run tables"
```

Database design notes live in `docs/architecture/postgresql.md`.

## Redis

Redis is integrated through an async lifecycle-managed client in `packages/platform`. The API initializes Redis during FastAPI startup, closes it during shutdown, exposes a typed dependency provider, and includes Redis ping status in the health response.

Current Redis foundation:

- async Redis connection pool;
- env-driven connection timeouts and max connections;
- request-safe dependency injection;
- JSON cache service abstraction;
- health check support.

Planned Redis-backed capabilities include agent memory pointers, workflow state, queues, rate limiting, idempotency keys, retrieval caches, and short-lived evaluation progress.

Redis architecture notes live in `docs/architecture/redis.md`.

## Patient Context Processing

The multimodal package includes a patient context processing layer that normalizes vitals, labs,
medications, demographics, clinical notes, imaging metadata, and timestamps into unified structured
context for downstream agents. It records missingness explicitly, emits validation findings, builds
cross-modality timelines, and prepares retrieval, explainability, and safety profiles without acting
as a diagnosis engine.

Patient context architecture notes live in `docs/architecture/patient-context-processing.md`.
MIMIC-IV preprocessing architecture notes live in `docs/architecture/mimic-iv-processing.md`.

## Vector Retrieval

The retrieval package provides a production-oriented vector retrieval layer using Qdrant,
sentence-transformers, async service boundaries, metadata filtering, and a future reranking
interface. It supports PubMed evidence, NICE guidelines, synthetic clinical protocols, local
policies, and imaging report metadata.

The package also includes a clinical knowledge ingestion pipeline with source loaders, document
processors, citation tracking, attribution verification, chunking, embedding generation, and
Qdrant indexing for evidence-grounded RAG workflows.

The clinical retrieval pipeline supports dense search, BM25 lexical search, hybrid fusion,
cross-encoder reranking, metadata-aware filtering, confidence scoring, citation grounding, and
evidence packaging for explainable downstream AI workflows.

PubMed integration design covers ingestion architecture, abstract processing, biomedical metadata,
citation integrity, retrieval optimization, observability, and support for hallucination detection
and future Safety Critic validation.

The retrieval evaluation framework covers evidence reliability evaluation, citation faithfulness,
grounding consistency, hallucination risk, retrieval/reranking metrics, synthetic test cases,
contradictory evidence scenarios, confidence scoring, and structured evaluation logs.

Vector retrieval architecture notes live in `docs/architecture/vector-retrieval.md`.
Knowledge ingestion architecture notes live in `docs/architecture/knowledge-ingestion.md`.
Clinical retrieval pipeline notes live in `docs/architecture/clinical-retrieval-pipeline.md`.
PubMed evidence retrieval notes live in `docs/architecture/pubmed-evidence-retrieval.md`.
Retrieval evaluation framework notes live in `docs/architecture/retrieval-evaluation-framework.md`.
End-to-end evidence workflow notes live in `docs/architecture/end-to-end-evidence-workflow.md`.

## Environment

Important local environment variables are documented in `.env.example`:

```text
APP_NAME
APP_VERSION
ENVIRONMENT
APP_DEBUG
APP_SECRET_KEY
ENABLE_DOCS
API_HOST
API_PORT
API_WORKERS
CORS_ALLOWED_ORIGINS
RUN_MIGRATIONS
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_DB
POSTGRES_PORT
DATABASE_URL
DATABASE_POOL_SIZE
DATABASE_MAX_OVERFLOW
DATABASE_POOL_TIMEOUT
DATABASE_POOL_RECYCLE
DATABASE_ECHO
REDIS_PORT
REDIS_URL
REDIS_MAX_CONNECTIONS
REDIS_SOCKET_TIMEOUT
REDIS_SOCKET_CONNECT_TIMEOUT
REDIS_HEALTH_CHECK_INTERVAL
REDIS_KEY_PREFIX
LOG_LEVEL
LOG_JSON
OTEL_SERVICE_NAME
OTEL_EXPORTER_OTLP_ENDPOINT
SENTRY_DSN
METRICS_ENABLED
TRACING_ENABLED
LLM_PROVIDER
LLM_DEFAULT_MODEL
LLM_API_KEY
LLM_BASE_URL
LLM_TIMEOUT_SECONDS
LLM_MAX_RETRIES
VECTOR_PROVIDER
VECTOR_DATABASE_URL
VECTOR_DATABASE_API_KEY
VECTOR_COLLECTION_PREFIX
VECTOR_EMBEDDING_MODEL
AGENTS_ENABLED
AGENT_MAX_CONCURRENT_RUNS
AGENT_RUN_TIMEOUT_SECONDS
AGENT_MEMORY_TTL_SECONDS
WORKFLOW_STATE_TTL_SECONDS
```

Configuration design notes live in `docs/architecture/configuration.md`.

The configuration layer supports `.env` plus `.env.<ENVIRONMENT>` files when present, but production deployments should inject secrets through the runtime platform or a dedicated secret manager. Secret-bearing settings use Pydantic `SecretStr` and should not be logged or committed.

## Observability

The API emits structured `structlog` events for request start, completion, latency, validation errors, HTTP errors, application errors, service startup, and shutdown.

Trace headers:

```text
x-request-id
x-correlation-id
```

If callers omit these headers, the request middleware generates them and propagates them back in the response. Observability design notes live in `docs/architecture/observability.md`.

## Health Monitoring

Health monitoring includes async PostgreSQL and Redis checks, latency measurements, structured response bodies, degraded-state handling, and separate liveness/readiness semantics.

Health responses include an aggregate status, per-service status, detailed checks, timestamp, version, and request metadata. Readiness returns `503 Service Unavailable` when required dependencies are unavailable.

Health monitoring design notes live in `docs/architecture/health-monitoring.md`.

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
