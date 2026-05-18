from collections.abc import Mapping
from contextlib import contextmanager
from typing import Any
from uuid import uuid4

import structlog

REQUEST_ID_HEADER = "x-request-id"
CORRELATION_ID_HEADER = "x-correlation-id"


def new_request_id() -> str:
    return str(uuid4())


def normalize_trace_id(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def resolve_request_id(headers: Mapping[str, str]) -> str:
    return normalize_trace_id(headers.get(REQUEST_ID_HEADER)) or new_request_id()


def resolve_correlation_id(headers: Mapping[str, str], request_id: str) -> str:
    return normalize_trace_id(headers.get(CORRELATION_ID_HEADER)) or request_id


def bind_request_context(
    *,
    request_id: str,
    correlation_id: str,
    method: str | None = None,
    path: str | None = None,
    client_ip: str | None = None,
) -> None:
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        correlation_id=correlation_id,
        http_method=method,
        http_path=path,
        client_ip=client_ip,
    )


def bind_execution_context(**values: Any) -> None:
    structlog.contextvars.bind_contextvars(**values)


def clear_trace_context() -> None:
    structlog.contextvars.clear_contextvars()


@contextmanager
def agent_trace_context(
    *,
    agent_run_id: str,
    agent_name: str,
    workflow_id: str | None = None,
    safety_case_id: str | None = None,
):
    bind_values: dict[str, Any] = {
        "agent_run_id": agent_run_id,
        "agent_name": agent_name,
    }
    if workflow_id:
        bind_values["workflow_id"] = workflow_id
    if safety_case_id:
        bind_values["safety_case_id"] = safety_case_id

    tokens = structlog.contextvars.bind_contextvars(**bind_values)
    try:
        yield
    finally:
        structlog.contextvars.reset_contextvars(**tokens)
