# Clinical AI Reliability & Decision Intelligence Platform

Production-grade monorepo scaffold for AI reliability analysis, safety validation, evidence-grounded clinical decision support, multimodal orchestration, explainability, auditability, and observability.

This is not a diagnosis chatbot. The platform is organized around reliability, evidence, governance, and decision intelligence.

## Architecture

```text
apps/
  api/                         FastAPI service boundary
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

## Local Development

1. Install `uv`.
2. Copy `.env.example` to `.env`.
3. Install dependencies:

```bash
make install
```

4. Start the local stack:

```bash
make up
```

5. Visit `http://localhost:8000/health`.

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

## Design Principles

- Async-first service and data access.
- Strong module boundaries between API, platform infrastructure, and AI domains.
- Evidence-grounded outputs with explicit provenance and audit trails.
- Observability as a default capability, not a late-stage add-on.
- Safety validation separated from generation and orchestration.
- Agent-ready contracts without coupling the core platform to a specific agent framework.

## Initial Roadmap

- Add clinical evidence, case, audit event, and evaluation run models.
- Add OpenTelemetry tracing middleware and metrics export.
- Add retrieval adapters for guidelines, local policies, and literature indexes.
- Add safety critic pipeline with explainable risk classifications.
- Add agent orchestration service with durable run state.
- Add multimodal ingest contracts for text, image, PDF, audio, and structured EHR payloads.

## Clinical Safety Notice

This system is intended to support reliability analysis and evidence-grounded clinical decision support workflows. It must not be represented as a standalone diagnostic authority. Human clinical oversight, validation, auditability, and deployment governance are required.

