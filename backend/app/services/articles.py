"""Read-side queries for the REST API. Every list is built with a fixed number of queries
(page + count + one batched related-coverage count), never one query per article."""

import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Select, UnaryExpression, func, or_, select
from sqlalchemy.orm import joinedload

from app.database import DbSession
from app.models import Article, Category, IngestionRun, RunStatus, Source, Summary
from app.models.article import SEARCH_CONFIG, article_search_vector, effective_time
from app.models.base import utcnow
from app.models.enums import CATEGORY_LABELS
from app.models.summary import summary_search_vector
from app.schemas.api import (
    ArticleCard,
    ArticleDetail,
    ArticleListParams,
    Briefing,
    BriefingSection,
    CategoryOut,
    CategoryRef,
    Pagination,
    SearchParams,
    SourceOut,
    TopParams,
)

BRIEFING_TOP_STORIES = 5
BRIEFING_PER_SECTION = 6
MIN_BRIEFING_ARTICLES = 5
CATEGORY_COUNT_DAYS = 7
# How many ranked candidates to scan when collapsing story clusters to one article each.
CLUSTER_SCAN_MULTIPLIER = 4


@dataclass(frozen=True)
class Page:
    items: list[ArticleCard]
    pagination: Pagination


def _with_relations(query: Select[Article]) -> Select[Article]:
    return query.options(joinedload(Article.source), joinedload(Article.summary))


def _by_importance() -> tuple[UnaryExpression[Any], ...]:
    return (
        Article.importance_score.desc().nulls_last(),
        effective_time().desc(),
        Article.id.asc(),
    )


def _by_recency() -> tuple[UnaryExpression[Any], ...]:
    return (effective_time().desc(), Article.id.asc())


def _related_counts(session: DbSession, articles: Sequence[Article]) -> dict[uuid.UUID, int]:
    cluster_ids = {a.story_cluster_id for a in articles if a.story_cluster_id}
    if not cluster_ids:
        return {}
    rows = session.execute(
        select(Article.story_cluster_id, func.count())
        .where(Article.story_cluster_id.in_(cluster_ids))
        .group_by(Article.story_cluster_id)
    ).all()
    return {cluster: count - 1 for cluster, count in rows if cluster is not None}


def _cards(session: DbSession, articles: Sequence[Article]) -> list[ArticleCard]:
    counts = _related_counts(session, articles)
    return [
        ArticleCard.of(a, counts.get(a.story_cluster_id, 0) if a.story_cluster_id else 0)
        for a in articles
    ]


def _paginate(session: DbSession, query: Select[Article], page: int, per_page: int) -> Page:
    total = session.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    articles = list(
        session.scalars(
            _with_relations(query).limit(per_page).offset((page - 1) * per_page)
        ).unique()
    )
    return Page(
        items=_cards(session, articles),
        pagination=Pagination(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=math.ceil(total / per_page) if total else 0,
        ),
    )


# ---------------------------------------------------------------------------- articles


def list_articles(session: DbSession, params: ArticleListParams) -> Page:
    query = select(Article)
    if params.category:
        query = query.where(Article.category == params.category)
    if params.source:
        query = query.join(Source).where(Source.slug.in_(params.source))
    if params.from_:
        query = query.where(effective_time() >= params.from_)
    if params.to:
        query = query.where(effective_time() < params.to)
    order = _by_importance() if params.sort == "importance" else _by_recency()
    return _paginate(session, query.order_by(*order), params.page, params.per_page)


def _one_per_story(articles: Sequence[Article], limit: int) -> list[Article]:
    """Keep the highest-ranked article of each story cluster (input is already ranked)."""
    seen: set[uuid.UUID] = set()
    picked: list[Article] = []
    for article in articles:
        if article.story_cluster_id:
            if article.story_cluster_id in seen:
                continue
            seen.add(article.story_cluster_id)
        picked.append(article)
        if len(picked) == limit:
            break
    return picked


def _ranked_since(
    session: DbSession, since: datetime, limit: int, category: Category | None = None
) -> list[Article]:
    query = select(Article).where(effective_time() >= since)
    if category:
        query = query.where(Article.category == category)
    query = _with_relations(query.order_by(*_by_importance())).limit(limit)
    return list(session.scalars(query).unique())


def top_articles(session: DbSession, params: TopParams) -> list[ArticleCard]:
    since = utcnow() - timedelta(hours=params.hours)
    candidates = _ranked_since(session, since, params.limit * CLUSTER_SCAN_MULTIPLIER)
    return _cards(session, _one_per_story(candidates, params.limit))


def get_article(session: DbSession, article_id: uuid.UUID) -> ArticleDetail | None:
    article = session.scalars(
        _with_relations(select(Article).where(Article.id == article_id))
    ).first()
    if article is None:
        return None
    related: list[Article] = []
    if article.story_cluster_id:
        related = list(
            session.scalars(
                select(Article)
                .options(joinedload(Article.source))
                .where(Article.story_cluster_id == article.story_cluster_id)
                .where(Article.id != article.id)
                .order_by(*_by_recency())
            )
        )
    return ArticleDetail.build(article, related)


def search_articles(session: DbSession, params: SearchParams) -> Page:
    """Full-text search over article text and the AI summary (headline, takeaways, key
    entities), plus publisher-name matching. ``websearch_to_tsquery`` accepts free-form input
    ("quoted phrases", -exclusions, OR) and never raises on user syntax."""
    tsquery = func.websearch_to_tsquery(SEARCH_CONFIG, params.q)
    escaped = params.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    article_rank = func.ts_rank(article_search_vector(), tsquery)
    summary_rank = func.coalesce(func.ts_rank(summary_search_vector(), tsquery), 0)
    query = (
        select(Article)
        .join(Source)
        .outerjoin(Summary)
        .where(
            or_(
                article_search_vector().op("@@")(tsquery),
                summary_search_vector().op("@@")(tsquery),
                Source.name.ilike(f"%{escaped}%", escape="\\"),
            )
        )
    )
    if params.sort == "relevance":
        query = query.order_by((article_rank + summary_rank).desc(), *_by_importance())
    else:
        query = query.order_by(*_by_recency())
    return _paginate(session, query, params.page, params.per_page)


# ------------------------------------------------------------------- catalog / briefing


def list_categories(session: DbSession) -> list[CategoryOut]:
    since = utcnow() - timedelta(days=CATEGORY_COUNT_DAYS)
    counts = dict(
        session.execute(
            select(Article.category, func.count())
            .where(Article.created_at >= since, Article.category.is_not(None))
            .group_by(Article.category)
        ).all()
    )
    return [
        CategoryOut(slug=category, label=label, article_count=counts.get(category, 0))
        for category, label in CATEGORY_LABELS.items()
    ]


def list_sources(session: DbSession) -> list[SourceOut]:
    return [SourceOut.of(s) for s in session.scalars(select(Source).order_by(Source.name))]


def last_updated_at(session: DbSession) -> datetime | None:
    return session.scalar(
        select(func.max(IngestionRun.finished_at)).where(
            IngestionRun.status.in_([RunStatus.SUCCEEDED, RunStatus.PARTIAL])
        )
    )


def todays_briefing(
    session: DbSession, *, window_hours: int = 24, fallback_window_hours: int = 72
) -> Briefing:
    """The most important recent stories, then the best of each category.

    "Today" is a rolling window (default 24 h) so the briefing is never empty just after
    midnight; if the window holds too few stories it widens to the fallback window.
    """
    now = utcnow()
    hours = window_hours
    since = now - timedelta(hours=hours)
    in_window = (
        session.scalar(select(func.count()).select_from(Article).where(effective_time() >= since))
        or 0
    )
    if in_window < MIN_BRIEFING_ARTICLES and fallback_window_hours > window_hours:
        hours = fallback_window_hours
        since = now - timedelta(hours=hours)

    ranked = _ranked_since(session, since, BRIEFING_TOP_STORIES * CLUSTER_SCAN_MULTIPLIER)
    top = _one_per_story(ranked, BRIEFING_TOP_STORIES)
    shown_ids = {a.id for a in top}
    shown_clusters = {a.story_cluster_id for a in top if a.story_cluster_id}

    sections: list[BriefingSection] = []
    for category in CATEGORY_LABELS:
        candidates = [
            a
            for a in _ranked_since(
                session, since, BRIEFING_PER_SECTION * CLUSTER_SCAN_MULTIPLIER, category
            )
            if a.id not in shown_ids and a.story_cluster_id not in shown_clusters
        ]
        picked = _one_per_story(candidates, BRIEFING_PER_SECTION)
        if picked:
            ref = CategoryRef.of(category)
            assert ref is not None
            sections.append(BriefingSection(category=ref, articles=_cards(session, picked)))

    return Briefing(
        generated_at=now,
        last_updated_at=last_updated_at(session),
        window_start=since,
        window_hours=hours,
        top_stories=_cards(session, top),
        sections=sections,
    )
