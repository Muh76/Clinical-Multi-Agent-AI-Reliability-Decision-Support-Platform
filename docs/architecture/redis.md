# Redis Architecture

## Goals

Redis is integrated as a shared async platform dependency, not as route-local infrastructure. The goal is to support low-latency state and coordination patterns for API routes, future workers, agent runtimes, safety pipelines, and evaluation systems.

## Runtime Components

```text
packages/platform/src/clinical_ai_platform/cache/
  redis.py       Async Redis manager and lifecycle functions
  service.py     Example JSON cache abstraction
```

The FastAPI app initializes Redis in `core/lifespan.py`, exposes the client through typed dependencies in `api/dependencies.py`, and closes the connection pool on shutdown.

## Why Redis Is Useful In AI Systems

AI platforms often need fast, short-lived, and coordination-heavy state. Redis is a good fit for:

- caching expensive retrieval results;
- storing model response fragments for streaming workflows;
- tracking agent scratchpad or memory pointers;
- rate limiting model calls and user actions;
- deduplicating idempotent requests;
- coordinating workflow state between API and workers;
- storing queue metadata and lightweight task state;
- enforcing safety cooldowns or policy decisions;
- keeping temporary evaluation run progress.

PostgreSQL remains the durable source of truth. Redis should hold derived, temporary, high-throughput, or coordination-oriented data.

## Connection Lifecycle

`RedisManager` creates one shared async Redis client backed by a connection pool. The pool is configured from environment settings:

```text
REDIS_URL
REDIS_MAX_CONNECTIONS
REDIS_SOCKET_TIMEOUT
REDIS_SOCKET_CONNECT_TIMEOUT
REDIS_HEALTH_CHECK_INTERVAL
REDIS_KEY_PREFIX
```

The manager is initialized during application startup and closed during shutdown. This prevents per-request client creation and gives future services a consistent resource lifecycle.

## Dependency Injection

The API exposes:

- `RedisDep`: raw async Redis client dependency;
- `CacheServiceDep`: higher-level JSON cache service dependency.

Domain services should prefer a focused abstraction such as `CacheService`, `RateLimitService`, `AgentMemoryService`, or `WorkflowStateService` instead of directly depending on raw Redis commands everywhere.

## Health Checks

The health service performs a Redis `PING` and returns dependency status in `/health`. This makes cache connectivity visible to Docker, load balancers, and uptime monitors without mixing Redis checks into route handlers.

## Scaling Pattern

As the platform grows, Redis-backed concerns should be split into focused modules:

- `cache`: deterministic cache keys, TTLs, serialization policy;
- `memory`: agent memory windows, references, and short-lived state;
- `queues`: lightweight queue coordination or broker metadata;
- `rate_limits`: token buckets and provider quota controls;
- `workflow_state`: resumable orchestration checkpoints.

Keeping these abstractions separate prevents Redis from becoming a hidden global data model and makes it easier to replace individual patterns with dedicated infrastructure later.

## Production Practices

- Use explicit key prefixes and namespaces.
- Set TTLs for temporary AI workflow data.
- Do not store PHI unless encryption, retention, and access controls are designed.
- Keep durable audit data in PostgreSQL.
- Avoid sharing mutable Redis state across unrelated workflows.
- Monitor Redis latency, memory, eviction rate, and connection saturation.
- Keep serialization formats versioned for long-lived keys.
