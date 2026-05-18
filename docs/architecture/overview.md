# Architecture Overview

## System Shape

The repository uses a Python monorepo with deployable applications under `apps/` and reusable capability packages under `packages/`.

The API is intentionally thin. It owns HTTP contracts, request validation, authentication hooks, and route composition. Domain logic belongs in packages so future workers, evaluators, pipelines, and agent runtimes can reuse the same contracts without importing web code.

## Layers

- `apps/api`: FastAPI service, routers, dependency wiring, HTTP schemas.
- `packages/platform`: Runtime infrastructure such as settings, SQLAlchemy async sessions, Redis clients, logging, telemetry, and health primitives.
- `packages/shared`: Stable cross-domain primitives, enums, identifiers, and event contracts.
- `packages/agents`: Agent orchestration abstractions and future graph/workflow adapters.
- `packages/retrieval`: Evidence retrieval interfaces, indexing pipelines, rankers, citation models.
- `packages/evaluation`: Reliability metrics, benchmark runners, regression suites, evaluation storage.
- `packages/safety`: Safety critics, risk scoring, guardrails, escalation policies.
- `packages/multimodal`: File/media normalization, modality adapters, multimodal feature extraction.

## Data Flow

1. API receives a request and creates a traceable operation context.
2. Orchestration package coordinates retrieval, safety, evaluation, and model calls.
3. Retrieval returns evidence with provenance and confidence metadata.
4. Safety critics assess candidate outputs independently from the generator.
5. Evaluation modules score reliability, grounding, consistency, and risk.
6. Audit events record inputs, evidence, decisions, model metadata, and reviewer actions.

## Separation Of Concerns

Generation, retrieval, safety criticism, evaluation, and audit logging should remain separately testable. This prevents a model provider, orchestration framework, or prompt strategy from becoming the architecture.

## Observability

Every request, pipeline run, agent step, safety assessment, and evaluation result should carry correlation IDs, trace IDs, structured logs, metrics, and audit event links.

