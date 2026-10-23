import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppException

logger = logging.getLogger("ems.errors")


def _error_response(message: str, error_code: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "message": message, "error_code": error_code},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        return _error_response(exc.message, exc.error_code, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        first = errors[0] if errors else None
        message = "Validation failed"
        if first:
            loc = ".".join(str(part) for part in first.get("loc", []) if part != "body")
            message = f"{loc}: {first.get('msg')}" if loc else first.get("msg", message)
        return _error_response(message, "VALIDATION_ERROR", status.HTTP_422_UNPROCESSABLE_ENTITY)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error_response(str(exc.detail), "HTTP_ERROR", exc.status_code)

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("Database integrity error: %s", exc.orig)
        return _error_response(
            "The request conflicts with existing data.", "INTEGRITY_ERROR", status.HTTP_409_CONFLICT
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.error("Database error: %s", exc)
        return _error_response(
            "A database error occurred.", "DATABASE_ERROR", status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return _error_response(
            "An unexpected error occurred.", "INTERNAL_SERVER_ERROR", status.HTTP_500_INTERNAL_SERVER_ERROR
        )
