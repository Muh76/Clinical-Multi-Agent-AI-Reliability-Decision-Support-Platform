"""Middleware registration hooks."""

from fastapi import FastAPI

from clinical_ai_api.middleware.tracing import RequestTracingMiddleware


def register_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestTracingMiddleware)
