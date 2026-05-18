from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from clinical_ai_api.schemas.base import ErrorDetail, ErrorResponse, ResponseMeta
from clinical_ai_platform.observability import get_logger


logger = get_logger(__name__)


class AppError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code


def _request_id(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None) or request.headers.get("x-request-id")
    return value if value else None


def _error_response(
    *,
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: list[ErrorDetail] | None = None,
) -> JSONResponse:
    payload = ErrorResponse(
        meta=ResponseMeta(request_id=_request_id(request)),
        error=ErrorDetail(code=code, message=message),
        details=details or [],
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        log_method = logger.error if exc.status_code >= 500 else logger.warning
        log_method(
            "application_error",
            error_code=exc.code,
            status_code=exc.status_code,
            error_message=exc.message,
        )
        return _error_response(
            request=request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        log_method = logger.error if exc.status_code >= 500 else logger.warning
        log_method(
            "http_error",
            status_code=exc.status_code,
            error_message=str(exc.detail),
        )
        return _error_response(
            request=request,
            status_code=exc.status_code,
            code="http_error",
            message=str(exc.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        logger.warning(
            "request_validation_error",
            validation_error_count=len(exc.errors()),
        )
        details = [
            ErrorDetail(code="validation_error", message=str(error["msg"]))
            for error in exc.errors()
        ]
        return _error_response(
            request=request,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="request_validation_error",
            message="Request validation failed.",
            details=details,
        )

    @app.exception_handler(ValidationError)
    async def pydantic_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
        logger.error(
            "response_validation_error",
            validation_error_count=len(exc.errors()),
        )
        details = [
            ErrorDetail(code="validation_error", message=str(error["msg"]))
            for error in exc.errors()
        ]
        return _error_response(
            request=request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="response_validation_error",
            message="Response validation failed.",
            details=details,
        )
