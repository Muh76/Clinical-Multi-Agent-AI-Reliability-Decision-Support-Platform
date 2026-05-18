# Coding Standards

## Python

- Use Python 3.12 features where they improve clarity.
- Keep all I/O async in service paths.
- Prefer typed protocols for domain interfaces.
- Use Pydantic models for external contracts and SQLAlchemy models for persistence.
- Keep API schemas separate from database models.
- Avoid hidden global state except cached immutable settings.

## Architecture

- Do not put business logic in FastAPI routers.
- Domain packages must not import from `apps`.
- Shared packages should remain small and stable.
- Safety validation must be independently callable from generation logic.
- Retrieval results must include provenance in future implementations.
- Evaluation code should be deterministic where possible and version its datasets.

## Observability

- Use `structlog` for structured logs.
- Include request IDs, case IDs, agent run IDs, evaluation run IDs, and safety assessment IDs in log context.
- Emit traces around external model calls, retrieval, database queries, and safety critics.
- Never log PHI, secrets, raw clinical notes, or unredacted model prompts in normal logs.

## Testing

- Unit-test domain packages with mocked external dependencies.
- Integration-test database repositories against PostgreSQL.
- Contract-test API schemas and response codes.
- Add regression tests for reliability metrics and safety policy changes.
- Treat evaluation datasets and expected outputs as versioned artifacts.

## Security And Clinical Governance

- Explicitly classify sensitive data before persistence.
- Keep audit events append-only.
- Require human-review workflows for high-risk recommendations.
- Version prompts, policies, models, retrieval corpora, and evaluation benchmarks.
- Preserve evidence provenance and decision rationale.

