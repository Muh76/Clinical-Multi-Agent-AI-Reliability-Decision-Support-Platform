# Structured Logging And Request Tracing

## Goals

The platform uses structured logs and trace context so API requests, future worker jobs, agent executions, retrieval calls, safety events, and evaluation workflows can be debugged as one coherent system.

## Components

```text
packages/platform/src/clinical_ai_platform/observability/
  logging.py      structlog configuration and logger helper
  tracing.py      request/correlation ID helpers and agent trace context
apps/api/src/clinical_ai_api/middleware/
  tracing.py      ASGI request tracing middleware
```

## Request Flow

For every HTTP request, the middleware:

1. reads `x-request-id` or generates a UUID;
2. reads `x-correlation-id` or defaults it to the request ID;
3. binds both IDs into `structlog.contextvars`;
4. logs `request_started`;
5. adds trace headers to the response;
6. logs `request_completed` with status code and latency;
7. logs `request_failed` with exception details for unhandled failures.

## Example Logs

Successful request:

```json
{
  "event": "request_completed",
  "level": "info",
  "logger": "clinical_ai_api.middleware.tracing",
  "request_id": "7db2d6ef-4a5e-4760-a91f-54c61d7b63d8",
  "correlation_id": "7db2d6ef-4a5e-4760-a91f-54c61d7b63d8",
  "http_method": "GET",
  "http_path": "/health",
  "status_code": 200,
  "latency_ms": 4.31
}
```

Validation warning:

```json
{
  "event": "request_validation_error",
  "level": "warning",
  "request_id": "customer-supplied-request-id",
  "correlation_id": "workflow-123",
  "validation_error_count": 2
}
```

Future agent trace:

```json
{
  "event": "agent_step_completed",
  "level": "info",
  "request_id": "7db2d6ef-4a5e-4760-a91f-54c61d7b63d8",
  "correlation_id": "workflow-123",
  "agent_run_id": "agent-run-456",
  "agent_name": "safety-critic",
  "workflow_id": "workflow-123",
  "latency_ms": 923.4
}
```

## Error Logging Pattern

Application and HTTP exceptions are logged by centralized error handlers. Unhandled exceptions are logged by the request tracing middleware with `logger.exception`, preserving traceback data in JSON logs.

Avoid logging raw PHI, secrets, full clinical notes, provider API keys, or unredacted model prompts. Log stable identifiers, risk categories, evidence IDs, policy IDs, and summary-level metadata instead.

## Why Structured Logging Matters

Enterprise AI systems fail in distributed, non-obvious ways: retrieval drift, provider latency, tool failures, unsafe recommendations, hallucination events, and workflow retries. Structured logs make these events queryable by fields instead of brittle free text.

## Enterprise AI Tracing

The tracing utilities include `agent_trace_context()` so future agent orchestration code can bind:

- `agent_run_id`;
- `agent_name`;
- `workflow_id`;
- `safety_case_id`;
- future retrieval/evaluation identifiers.

This lets observability systems connect a user request to the internal agent steps, safety critics, evidence lookups, and evaluation events that influenced the final response.
