# Configuration Architecture

## Goals

Configuration is centralized in `clinical_ai_platform.core.settings` so runtime behavior is typed, validated, and consistent across API routes, workers, migrations, agents, retrieval pipelines, and evaluation systems.

The legacy import path `clinical_ai_platform.core.config` remains as a compatibility shim.

## Modules

```text
packages/platform/src/clinical_ai_platform/core/
  settings.py     Typed Pydantic Settings implementation
  config.py       Backward-compatible re-export module
```

## Environment Loading

`get_settings()` loads environment values through Pydantic Settings. It supports:

- `.env`;
- `.env.<ENVIRONMENT>` when present;
- process environment variables.

Later files and process environment values override earlier defaults. This lets local development use `.env`, while staging and production inject values through deployment platforms, secret managers, or orchestrators.

## Configuration Groups

The top-level `Settings` class exposes flat env-compatible fields and grouped typed views:

- `settings.app`
- `settings.api`
- `settings.database`
- `settings.redis`
- `settings.observability`
- `settings.llm`
- `settings.vector_database`
- `settings.agents`

Flat attributes such as `settings.database_url` remain available for compatibility, but new code should prefer grouped settings.

## Validation

Validation covers:

- allowed environments;
- log level names;
- positive pool, timeout, and concurrency values;
- non-empty key prefixes;
- production restrictions such as disabling debug mode and API docs;
- required application secret in production;
- required LLM API key for hosted LLM providers;
- required vector database URL for external vector stores.

## Secrets

Secret-bearing fields use `SecretStr`:

- `APP_SECRET_KEY`
- `SENTRY_DSN`
- `LLM_API_KEY`
- `VECTOR_DATABASE_API_KEY`

These values should come from a secret manager in staging and production, not from committed files.

## Deployment Practices

- Keep `.env.example` committed as documentation only.
- Never commit `.env`, provider API keys, database passwords, or DSNs.
- Prefer platform-injected environment variables in production.
- Use distinct credentials per environment.
- Disable `ENABLE_DOCS` and `APP_DEBUG` in production.
- Keep `LOG_LEVEL` at `INFO` or above in production.
- Treat LLM provider and vector database settings as deploy-time choices, not hard-coded dependencies.

## Why This Matters

Centralized configuration prevents drift between services and makes operational behavior auditable. It also gives future workers, agent runtimes, and evaluation pipelines the same source of truth as the API without importing web-specific code.
