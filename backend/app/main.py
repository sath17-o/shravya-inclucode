from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.contracts.common import ErrorResponse
from app.contracts.teacher_review import DomainError
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Shravya API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        _: Request, exc: HTTPException | StarletteHTTPException
    ) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        details = detail.get("details", {})
        response = ErrorResponse(
            code=detail.get("code", f"HTTP_{exc.status_code}"),
            message=detail.get("message", "The request could not be completed."),
            message_key=detail.get("message_key", detail.get("code", f"HTTP_{exc.status_code}")),
            details=details if isinstance(details, dict) else {},
            recoverable=detail.get("recoverable", exc.status_code < 500),
            next_actions=detail.get("next_actions", []),
            job_id=detail.get("job_id"),
        )
        return JSONResponse(status_code=exc.status_code, content=response.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, __: RequestValidationError) -> JSONResponse:
        response = ErrorResponse(
            code="REQUEST_VALIDATION_ERROR",
            message="The request could not be understood.",
            message_key="request.validation_error",
            details={},
            recoverable=True,
            next_actions=["Check the submitted information and try again."],
        )
        return JSONResponse(status_code=422, content=response.model_dump())

    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        status = {"not_found": 404, "validation": 422, "conflict": 409, "forbidden": 403}[
            exc.category
        ]
        return JSONResponse(
            status_code=status,
            content=ErrorResponse(
                code=exc.code,
                message=exc.message_key,
                message_key=exc.message_key,
                details=exc.details,
                recoverable=status < 500,
                next_actions=[],
                job_id=None,
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unexpected_exception_handler(_: Request, __: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                code="INTERNAL_ERROR",
                message="An unexpected error occurred.",
                message_key="error.internal",
                details={},
                recoverable=False,
            ).model_dump(),
        )

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
