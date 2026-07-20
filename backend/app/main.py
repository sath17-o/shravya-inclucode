from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.contracts.common import ErrorResponse
from app.contracts.teacher_review import DomainError
from app.core.config import get_settings
from app.db.session import create_db_engine
from app.services.audio_workflow import recover_pending_audio_uploads


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

    @app.on_event("startup")
    def recover_audio_upload_intents_at_startup() -> None:
        """Resolve any crash-surviving upload intent before accepting uploads."""

        factory = getattr(app.state, "audio_session_factory", None)
        engine = None
        if factory is None:
            engine = create_db_engine(settings.database_url)
            factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        try:
            # Older development databases can still boot long enough to run
            # their required Alembic upgrade. Once Phase 3B's table exists,
            # recovery is mandatory before the application accepts uploads.
            with factory() as session:
                has_upload_intents = inspect(session.get_bind()).has_table("media_upload_intents")
            if has_upload_intents:
                recover_pending_audio_uploads(settings, factory, raise_on_conflict=False)
        finally:
            if engine is not None:
                engine.dispose()

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
