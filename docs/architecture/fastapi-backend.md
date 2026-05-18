# FastAPI Backend Architecture

## Folder Responsibilities

```text
clinical_ai_api/
  main.py                 App factory and ASGI entrypoint
  api/                    HTTP route composition and dependency wiring
    dependencies.py       FastAPI dependency providers
    router.py             Top-level router registry
    v1/                   Versioned API surface
      router.py           V1 router registry
      endpoints/          Thin HTTP endpoint modules
  core/                   App-level lifecycle and exception handling
  middleware/             Future middleware registration hooks
  schemas/                Request and response DTOs
  services/               Application service layer
```

## Routing

The root router exposes operational health at `/health` and versioned product APIs under `/api/v1`.

Keeping `/health` outside versioning makes it stable for Docker, load balancers, uptime checks, and orchestration systems. Product APIs sit behind `/api/v1` so future breaking changes can move to `/api/v2` without disturbing existing clients.

## Dependency Injection

`api/dependencies.py` centralizes dependency creation for settings, request IDs, and services. Routers consume typed dependency aliases instead of constructing services directly.

This keeps endpoints small and makes it straightforward to swap implementations in tests, add database sessions, introduce authenticated principals, bind tenant context, or attach audit context later.

## Service Layer

Endpoint modules are intentionally thin. They handle HTTP concerns: request parsing, status codes, response models, and dependency injection.

Service modules own application workflows. Today they return placeholder data; later they should coordinate repositories, retrieval pipelines, agent orchestration, safety critics, and evaluation runners.

## Error Handling

`core/errors.py` registers centralized handlers for application errors, HTTP errors, and validation errors. All errors return a consistent envelope with metadata and machine-readable codes.

## Lifespan

`core/lifespan.py` owns startup and shutdown behavior. It configures structured logging, stores settings on app state, and gives one place to initialize future resources such as database pools, Redis clients, model gateways, OpenTelemetry exporters, and background supervisors.

## Scaling To Agents

The structure scales to agentic systems because orchestration does not live in routers. Future agent endpoints can call services that coordinate:

- retrieval;
- multimodal normalization;
- safety critics;
- evaluation metrics;
- audit logging;
- durable run state;
- model provider adapters.

This allows API routes, workers, scheduled jobs, and evaluation pipelines to reuse the same service contracts without importing web-layer code.
