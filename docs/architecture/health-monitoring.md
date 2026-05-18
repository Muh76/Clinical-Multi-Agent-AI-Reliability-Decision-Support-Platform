# Health Monitoring

## Endpoints

```text
GET /health
GET /health/live
GET /health/ready
```

## Response Shape

```json
{
  "status": "healthy",
  "service": "Clinical AI Reliability & Decision Intelligence Platform",
  "version": "0.1.0",
  "environment": "local",
  "timestamp": "2026-05-18T15:20:00Z",
  "services": {
    "postgres": "connected",
    "redis": "connected"
  },
  "checks": {
    "postgres": {
      "status": "connected",
      "latency_ms": 3.24
    },
    "redis": {
      "status": "connected",
      "latency_ms": 1.18
    }
  },
  "meta": {
    "request_id": "..."
  }
}
```

## Liveness

Liveness answers: is the application process running and able to respond?

`/health/live` does not check PostgreSQL or Redis. Container orchestrators can use it to decide whether the process is wedged and should be restarted.

## Readiness

Readiness answers: should this instance receive traffic?

`/health/ready` checks required runtime dependencies, currently PostgreSQL and Redis. If either dependency is unavailable, readiness returns `503 Service Unavailable`.

## Aggregate Health

`/health` returns an aggregate platform view. It checks dependencies and can report:

- `healthy`: all required checks are connected;
- `degraded`: some checks are connected and some are unavailable;
- `unhealthy`: required checks are unavailable.

The aggregate endpoint is useful for dashboards and uptime monitors. Readiness is better for routing decisions.

## Dependency Checks

PostgreSQL is validated with `SELECT 1` through the SQLAlchemy async engine.

Redis is validated with `PING` through the async Redis client.

Checks run concurrently and include latency measurements. Each check has a timeout so health endpoints do not hang behind a failing dependency.

## Kubernetes And Containers

Recommended probe mapping:

```yaml
livenessProbe:
  httpGet:
    path: /health/live
    port: 8000

readinessProbe:
  httpGet:
    path: /health/ready
    port: 8000
```

Docker Compose can keep using `/health` or move to `/health/live` depending on whether the desired behavior is process-level or dependency-aware health.

## Production Notes

- Keep liveness cheap and dependency-free.
- Keep readiness strict for required dependencies.
- Emit structured logs for failed health checks when adding deeper monitoring.
- Do not include secrets, PHI, or raw connection strings in health responses.
- Add future checks for vector stores, model gateways, object storage, and queue brokers only when they are required for serving traffic.
