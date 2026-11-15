import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta

from flask import Blueprint, Response, current_app, request
from sqlalchemy import func, select

from app.config import Settings
from app.database import db
from app.ingestion.scheduler import advisory_lock
from app.models import AIUsageEvent, GenerationStatus, Summary
from app.models.base import utcnow
from app.schemas.api import (
    ArticleListParams,
    SearchParams,
    TopParams,
)
from app.services import articles as article_service
from app.services.llm import LLMClient, LLMConfigurationError, LLMRateLimitError
from app.services.llm.gemini import GeminiClient, build_llm_http_client
from app.services.processing import ArticleNotFound, ProcessingService
from app.utils.auth import require_admin_token
from app.utils.errors import ApiError
from app.utils.params import parse_params, parse_uuid
from app.utils.responses import success

bp = Blueprint("articles", __name__, url_prefix="/api/articles")

# Distinct from the job locks; combined with the article id so each article has its own lock.
REGENERATE_LOCK_NAMESPACE = 0x72656765  # "rege"


def _settings() -> Settings:
    settings: Settings = current_app.config["BRIEFLY_SETTINGS"]
    return settings


@bp.get("")
def list_articles() -> tuple[Response, int]:
    params = parse_params(ArticleListParams, request.args)
    page = article_service.list_articles(db.session, params)
    return success(
        [card.model_dump(mode="json") for card in page.items],
        meta={"pagination": page.pagination.model_dump()},
    )


@bp.get("/top")
def top_articles() -> tuple[Response, int]:
    params = parse_params(TopParams, request.args)
    cards = article_service.top_articles(db.session, params)
    return success([c.model_dump(mode="json") for c in cards], meta={"hours": params.hours})


@bp.get("/search")
def search_articles() -> tuple[Response, int]:
    params = parse_params(SearchParams, request.args)
    page = article_service.search_articles(db.session, params)
    return success(
        [card.model_dump(mode="json") for card in page.items],
        meta={"query": params.q, "pagination": page.pagination.model_dump()},
    )


@bp.get("/<article_id>")
def get_article(article_id: str) -> tuple[Response, int]:
    detail = article_service.get_article(db.session, parse_uuid(article_id))
    if detail is None:
        raise ApiError("not_found", "Article not found.", status=404)
    return success(detail.model_dump(mode="json"))


# ------------------------------------------------------------------ summary regeneration


@contextmanager
def api_llm_client(settings: Settings) -> Iterator[LLMClient]:
    """One bounded attempt per request: no provider-side retries inside an HTTP call."""
    with build_llm_http_client(settings, timeout=settings.api_llm_timeout_seconds) as http:
        yield GeminiClient.from_settings(http, settings, max_retries=0)


def _lock_key(article_id: uuid.UUID) -> int:
    # Fold the UUID into a signed 64-bit advisory-lock key, offset by our namespace.
    return ((article_id.int ^ REGENERATE_LOCK_NAMESPACE) & 0x7FFF_FFFF_FFFF_FFFF) or 1


def _enforce_rate_limits(article_id: uuid.UUID, settings: Settings) -> None:
    now = utcnow()
    last_attempt = db.session.scalar(
        select(Summary.last_attempt_at).where(Summary.article_id == article_id)
    )
    cooldown = timedelta(seconds=settings.regenerate_cooldown_seconds)
    if last_attempt and now - last_attempt < cooldown:
        wait = int((cooldown - (now - last_attempt)).total_seconds()) + 1
        raise ApiError(
            "rate_limited",
            "This article's summary was generated moments ago; try again shortly.",
            status=429,
            headers={"Retry-After": str(wait)},
        )
    # Counted from the usage ledger, so the limit holds across all API worker processes.
    recent = db.session.scalar(
        select(func.count())
        .select_from(AIUsageEvent)
        .where(AIUsageEvent.operation == "regenerate")
        .where(AIUsageEvent.created_at >= now - timedelta(minutes=1))
    )
    if (recent or 0) >= settings.regenerate_max_per_minute:
        raise ApiError(
            "rate_limited",
            "Too many regeneration requests; try again in a minute.",
            status=429,
            headers={"Retry-After": "60"},
        )


@bp.post("/<article_id>/summarize")
@require_admin_token
def regenerate_summary(article_id: str) -> tuple[Response, int]:
    """Regenerate one article's summary now (admin only, rate limited)."""
    settings = _settings()
    parsed_id = parse_uuid(article_id)
    if not settings.ai_enabled:
        raise ApiError("ai_unavailable", "AI summarization is not configured.", status=503)

    with advisory_lock(db.engine, _lock_key(parsed_id)) as acquired:
        if not acquired:
            raise ApiError(
                "conflict", "This article's summary is already being regenerated.", status=409
            )
        _enforce_rate_limits(parsed_id, settings)
        try:
            with api_llm_client(settings) as client:
                service = ProcessingService(db.session, settings, client)
                attempt = service.regenerate(parsed_id)
        except ArticleNotFound as exc:
            raise ApiError("not_found", "Article not found.", status=404) from exc
        except LLMRateLimitError as exc:
            raise ApiError(
                "ai_rate_limited",
                "The AI provider is rate limiting requests; try again later.",
                status=503,
                headers={"Retry-After": str(int(exc.retry_after or 60))},
            ) from exc
        except LLMConfigurationError as exc:
            current_app.logger.error("Regeneration provider configuration error: %s", exc)
            raise ApiError(
                "ai_unavailable", "The AI provider rejected the request.", status=503
            ) from exc

    if attempt is GenerationStatus.FAILED:
        raise ApiError(
            "summary_failed",
            "The AI provider could not produce a valid summary; any previous summary is kept.",
            status=502,
        )
    detail = article_service.get_article(db.session, parsed_id)
    assert detail is not None
    return success(detail.model_dump(mode="json"))
