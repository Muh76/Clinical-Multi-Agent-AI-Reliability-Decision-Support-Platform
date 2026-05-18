from time import perf_counter
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from clinical_ai_platform.observability import (
    CORRELATION_ID_HEADER,
    REQUEST_ID_HEADER,
    bind_request_context,
    clear_trace_context,
    get_logger,
    resolve_correlation_id,
    resolve_request_id,
)


class RequestTracingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.logger = get_logger(__name__)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = _headers_to_dict(scope)
        request_id = resolve_request_id(headers)
        correlation_id = resolve_correlation_id(headers, request_id)
        method = str(scope.get("method", ""))
        path = str(scope.get("path", ""))
        client_ip = _client_ip(scope, headers)
        start = perf_counter()
        status_code = 500

        scope.setdefault("state", {})
        scope["state"]["request_id"] = request_id
        scope["state"]["correlation_id"] = correlation_id

        bind_request_context(
            request_id=request_id,
            correlation_id=correlation_id,
            method=method,
            path=path,
            client_ip=client_ip,
        )
        self.logger.info("request_started")

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                raw_headers = list(message.get("headers", []))
                raw_headers.append((REQUEST_ID_HEADER.encode(), request_id.encode()))
                raw_headers.append((CORRELATION_ID_HEADER.encode(), correlation_id.encode()))
                message["headers"] = raw_headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            latency_ms = round((perf_counter() - start) * 1000, 2)
            self.logger.exception(
                "request_failed",
                status_code=status_code,
                latency_ms=latency_ms,
            )
            raise
        finally:
            latency_ms = round((perf_counter() - start) * 1000, 2)
            if status_code >= 500:
                self.logger.error(
                    "request_completed",
                    status_code=status_code,
                    latency_ms=latency_ms,
                )
            elif status_code >= 400:
                self.logger.warning(
                    "request_completed",
                    status_code=status_code,
                    latency_ms=latency_ms,
                )
            else:
                self.logger.info(
                    "request_completed",
                    status_code=status_code,
                    latency_ms=latency_ms,
                )
            clear_trace_context()


def _headers_to_dict(scope: Scope) -> dict[str, str]:
    headers: dict[str, str] = {}
    for raw_key, raw_value in scope.get("headers", []):
        headers[raw_key.decode("latin-1").lower()] = raw_value.decode("latin-1")
    return headers


def _client_ip(scope: Scope, headers: dict[str, str]) -> str | None:
    forwarded_for = headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", maxsplit=1)[0].strip()
    client: Any = scope.get("client")
    if client:
        return str(client[0])
    return None
