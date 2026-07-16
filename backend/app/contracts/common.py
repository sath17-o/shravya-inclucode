from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class SuccessResponse(BaseModel, Generic[T]):
    status: Literal["success"] = "success"
    data: T


class ErrorResponse(BaseModel):
    status: Literal["error"] = "error"
    code: str
    message: str
    message_key: str
    details: dict[str, Any] = Field(default_factory=dict)
    recoverable: bool
    next_actions: list[str] = Field(default_factory=list)
    job_id: str | None = None


class HealthPayload(BaseModel):
    service: Literal["shravya-backend"] = "shravya-backend"
    environment: str
    provider_mode: str
