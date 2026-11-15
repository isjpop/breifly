from flask import Blueprint, Response, current_app

from app.config import Settings
from app.database import db
from app.services import articles as article_service
from app.utils.responses import success

bp = Blueprint("catalog", __name__, url_prefix="/api")


@bp.get("/categories")
def list_categories() -> tuple[Response, int]:
    return success([c.model_dump(mode="json") for c in article_service.list_categories(db.session)])


@bp.get("/sources")
def list_sources() -> tuple[Response, int]:
    return success([s.model_dump(mode="json") for s in article_service.list_sources(db.session)])


@bp.get("/briefing/today")
def todays_briefing() -> tuple[Response, int]:
    settings: Settings = current_app.config["BRIEFLY_SETTINGS"]
    briefing = article_service.todays_briefing(
        db.session,
        window_hours=settings.briefing_window_hours,
        fallback_window_hours=settings.briefing_fallback_window_hours,
    )
    return success(briefing.model_dump(mode="json"))
