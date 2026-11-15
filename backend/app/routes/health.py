from datetime import UTC, datetime

from flask import Blueprint, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database import db
from app.utils.responses import success

bp = Blueprint("health", __name__, url_prefix="/api")


@bp.get("/health")
def health() -> tuple[Response, int]:
    """Liveness + database readiness. Returns 503 when the database is unreachable."""
    try:
        db.session.execute(text("SELECT 1"))
        database_ok = True
    except SQLAlchemyError:
        db.session.rollback()
        database_ok = False

    payload = {
        "status": "ok" if database_ok else "degraded",
        "database": "ok" if database_ok else "unavailable",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    return success(payload, status=200 if database_ok else 503)
