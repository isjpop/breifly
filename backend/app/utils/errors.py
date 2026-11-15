"""Application error types and Flask error handlers.

Internal exception details are logged, never returned to clients.
"""

import logging
from typing import Any

from flask import Flask, Response
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException

from app.utils.responses import error

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """An error that is safe to show to API clients."""

    def __init__(
        self, code: str, message: str, status: int = 400, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def handle_api_error(exc: ApiError) -> tuple[Response, int]:
        return error(exc.code, exc.message, status=exc.status, details=exc.details)

    @app.errorhandler(HTTPException)
    def handle_http_error(exc: HTTPException) -> tuple[Response, int]:
        status = exc.code or 500
        code = (exc.name or "error").lower().replace(" ", "_")
        return error(code, exc.description or exc.name, status=status)

    @app.errorhandler(SQLAlchemyError)
    def handle_database_error(exc: SQLAlchemyError) -> tuple[Response, int]:
        logger.exception("Database error while handling request")
        return error("database_unavailable", "The database is temporarily unavailable.", status=503)

    @app.errorhandler(Exception)
    def handle_unexpected_error(exc: Exception) -> tuple[Response, int]:
        logger.exception("Unhandled error while handling request")
        return error("internal_error", "An unexpected error occurred.", status=500)
