# PostgreSQL And SQLAlchemy Async Architecture

## Goals

The PostgreSQL integration is designed around async-first application paths, predictable connection lifecycle management, Alembic-compatible metadata, and service-layer dependency injection.

## Runtime Components

```text
packages/platform/src/clinical_ai_platform/db/
  base.py                 Declarative base, naming conventions, shared mixins
  session.py              Async engine, pool config, session factory, session provider
  models/                 SQLAlchemy ORM models
migrations/
  env.py                  Alembic async migration environment
  versions/               Versioned migration scripts
```

## Models

The initial schema includes:

- `patients`: patient reliability context records.
- `clinical_cases`: case-level reliability and safety workflow state.
- `audit_logs`: append-oriented audit events linked to cases when available.

The models use UUID primary keys, timezone-aware timestamps, explicit indexes, PostgreSQL `JSONB` for evidence snapshots and audit payloads, and named constraints through a metadata naming convention.

## Async Engine And Pooling

`clinical_ai_platform.db.session` creates a SQLAlchemy 2.0 async engine with `asyncpg`.

Pool behavior is controlled through environment settings:

```text
DATABASE_POOL_SIZE
DATABASE_MAX_OVERFLOW
DATABASE_POOL_TIMEOUT
DATABASE_POOL_RECYCLE
DATABASE_ECHO
```

`pool_pre_ping=True` is enabled so stale connections are detected before use. `pool_recycle` limits the lifetime of pooled connections, which helps with network infrastructure and managed database timeouts.

## Connection Lifecycle

The FastAPI lifespan handler initializes the database engine on startup and disposes it on shutdown. This avoids unmanaged global connection pools and gives the application a single clean place to initialize future Redis clients, telemetry exporters, model gateways, and worker resources.

## Session Lifecycle

`get_session()` creates one `AsyncSession` per request dependency scope. If the request path raises an exception, the provider rolls back the session before closing it.

Service methods should own transaction boundaries:

```python
async with session.begin():
    ...
```

That keeps transaction intent explicit and avoids committing read-only requests by accident.

## Alembic Workflow

Apply migrations:

```bash
make migrate
```

Create a new autogeneration revision after changing ORM models:

```bash
make revision message="add evaluation run tables"
```

Review generated migrations before committing. Autogeneration is useful, but production migrations should be treated as code: verify constraints, indexes, nullable changes, backfills, downgrade behavior, and lock impact.

## Production Practices

- Keep sessions short-lived and request-scoped.
- Do not share `AsyncSession` instances across concurrent tasks.
- Use explicit transaction blocks around writes.
- Prefer repositories or data-access services once queries become non-trivial.
- Keep Alembic migrations backward-compatible for rolling deployments.
- Add indexes based on query patterns, not guesses alone.
- Avoid logging PHI or raw clinical payloads from model instances.
- Store audit data as append-oriented records and design future retention policies deliberately.
