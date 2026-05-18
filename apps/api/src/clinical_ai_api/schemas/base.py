from datetime import UTC, datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

DataT = TypeVar("DataT")


class ResponseMeta(BaseModel):
    request_id: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ApiResponse(BaseModel, Generic[DataT]):
    data: DataT
    meta: ResponseMeta

    @classmethod
    def from_data(cls, *, data: DataT, request_id: str | None = None) -> "ApiResponse[DataT]":
        return cls(data=data, meta=ResponseMeta(request_id=request_id))


class CollectionResponse(BaseModel, Generic[DataT]):
    data: list[DataT]
    meta: ResponseMeta
    total: int

    @classmethod
    def from_data(
        cls,
        *,
        data: list[DataT],
        request_id: str | None = None,
    ) -> "CollectionResponse[DataT]":
        return cls(data=data, total=len(data), meta=ResponseMeta(request_id=request_id))


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    meta: ResponseMeta
    error: ErrorDetail
    details: list[ErrorDetail] = Field(default_factory=list)

