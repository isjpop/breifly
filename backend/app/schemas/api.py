"""Request-parameter validation and response shapes for the REST API.

Response models double as the OpenAPI component schemas (see ``app/routes/docs.py``).
External URLs are re-checked on output: a link is emitted only if it is an absolute http(s) URL.
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import Article, Category, GenerationStatus, Source, SourceCoverage, Summary
from app.models.enums import CATEGORY_LABELS, ContentAvailability, FetchStatus
from app.utils.text import truncate
from app.utils.urls import is_safe_http_url

CARD_BULLETS = 3
CARD_DESCRIPTION_CHARS = 300


def _safe_url(value: str | None) -> str | None:
    return value if is_safe_http_url(value) else None


def _parse_bound(value: Any, *, end: bool) -> datetime | None:
    """Accept YYYY-MM-DD or ISO datetimes. A bare ``to`` date includes that whole day."""
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        if len(text) == 10:
            day = date.fromisoformat(text)
            moment = datetime.combine(day + timedelta(days=1) if end else day, time(), tzinfo=UTC)
        else:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("must be YYYY-MM-DD or an ISO 8601 datetime") from exc
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


# ------------------------------------------------------------------- request parameters


class _Query(BaseModel):
    # Unknown params (e.g. cache-busters) are ignored; known ones are strictly validated.
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class PageParams(_Query):
    page: int = Field(default=1, ge=1, le=1000)
    per_page: int = Field(default=20, ge=1, le=100)


class ArticleListParams(PageParams):
    category: Category | None = None
    source: list[str] = Field(default_factory=list, max_length=20)
    from_: datetime | None = Field(default=None, alias="from")
    to: datetime | None = None
    sort: Literal["importance", "recent"] = "importance"

    @field_validator("source", mode="before")
    @classmethod
    def split_sources(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [s.strip() for s in value.split(",") if s.strip()]
        return value

    @field_validator("from_", mode="before")
    @classmethod
    def parse_from(cls, value: Any) -> datetime | None:
        return _parse_bound(value, end=False)

    @field_validator("to", mode="before")
    @classmethod
    def parse_to(cls, value: Any) -> datetime | None:
        return _parse_bound(value, end=True)

    @model_validator(mode="after")
    def ordered_range(self) -> "ArticleListParams":
        if self.from_ and self.to and self.from_ >= self.to:
            raise ValueError("'from' must be earlier than 'to'")
        return self


class SearchParams(PageParams):
    q: str = Field(min_length=2, max_length=200)
    sort: Literal["relevance", "recent"] = "relevance"

    @field_validator("q", mode="before")
    @classmethod
    def strip_query(cls, value: Any) -> Any:
        return " ".join(value.split()) if isinstance(value, str) else value


class TopParams(_Query):
    limit: int = Field(default=10, ge=1, le=50)
    hours: int = Field(default=24, ge=1, le=168)


# ---------------------------------------------------------------------- response models


class SourceRef(BaseModel):
    slug: str
    name: str


class CategoryRef(BaseModel):
    slug: Category
    label: str

    @classmethod
    def of(cls, category: Category | None) -> "CategoryRef | None":
        return cls(slug=category, label=CATEGORY_LABELS[category]) if category else None


class SummaryPreview(BaseModel):
    status: GenerationStatus
    headline: str | None
    bullet_points: list[str]
    why_it_matters: str | None
    source_coverage: SourceCoverage | None
    limitations: str | None


class SummaryDetail(SummaryPreview):
    key_entities: list[str]
    model_name: str | None
    generated_at: datetime | None


class ArticleCard(BaseModel):
    id: uuid.UUID
    title: str
    url: str | None = Field(description="Original publisher URL (absolute http/https only).")
    source: SourceRef
    author: str | None
    published_at: datetime | None
    first_seen_at: datetime
    category: CategoryRef | None
    importance_score: float | None
    image_url: str | None
    description: str | None
    summary: SummaryPreview | None
    related_count: int = Field(description="Other publishers' articles on the same story.")

    @classmethod
    def of(cls, article: Article, related_count: int = 0) -> "ArticleCard":
        return cls(**_card_fields(article, related_count), summary=_preview(article.summary))


class RelatedArticle(BaseModel):
    id: uuid.UUID
    title: str
    url: str | None
    source: SourceRef
    published_at: datetime | None


class ArticleDetail(ArticleCard):
    content_availability: ContentAvailability
    tags: list[str]
    summary: SummaryDetail | None
    related: list[RelatedArticle]

    @classmethod
    def build(cls, article: Article, related: list[Article]) -> "ArticleDetail":
        return cls(
            **_card_fields(article, len(related)),
            content_availability=article.content_availability,
            tags=article.tags,
            summary=_detail(article.summary),
            related=[
                RelatedArticle(
                    id=r.id,
                    title=r.title,
                    url=_safe_url(r.url),
                    source=SourceRef(slug=r.source.slug, name=r.source.name),
                    published_at=r.published_at,
                )
                for r in related
            ],
        )


class Pagination(BaseModel):
    page: int
    per_page: int
    total: int
    total_pages: int


class CategoryOut(BaseModel):
    slug: Category
    label: str
    article_count: int = Field(description="Articles first seen in the last 7 days.")


class SourceOut(BaseModel):
    slug: str
    name: str
    homepage_url: str | None
    default_category: CategoryRef
    credibility_weight: float
    is_active: bool
    last_successful_fetch_at: datetime | None
    last_fetch_status: FetchStatus | None

    @classmethod
    def of(cls, source: Source) -> "SourceOut":
        category = CategoryRef.of(source.default_category)
        assert category is not None
        return cls(
            slug=source.slug,
            name=source.name,
            homepage_url=_safe_url(source.homepage_url),
            default_category=category,
            credibility_weight=source.credibility_weight,
            is_active=source.is_active,
            last_successful_fetch_at=source.last_successful_fetch_at,
            last_fetch_status=source.last_fetch_status,
        )


class BriefingSection(BaseModel):
    category: CategoryRef
    articles: list[ArticleCard]


class Briefing(BaseModel):
    generated_at: datetime
    last_updated_at: datetime | None = Field(
        description="When the most recent successful ingestion run finished."
    )
    window_start: datetime
    window_hours: int
    top_stories: list[ArticleCard]
    sections: list[BriefingSection]


# ----------------------------------------------------------------------------- helpers


def _card_fields(article: Article, related_count: int) -> dict[str, Any]:
    return {
        "id": article.id,
        "title": article.title,
        "url": _safe_url(article.url),
        "source": SourceRef(slug=article.source.slug, name=article.source.name),
        "author": article.author,
        "published_at": article.published_at,
        "first_seen_at": article.created_at,
        "category": CategoryRef.of(article.category),
        "importance_score": article.importance_score,
        "image_url": _safe_url(article.image_url),
        "description": truncate(article.description, CARD_DESCRIPTION_CHARS),
        "related_count": related_count,
    }


def _preview(summary: Summary | None) -> SummaryPreview | None:
    if summary is None or summary.generation_status is GenerationStatus.PENDING:
        return None
    return SummaryPreview(
        status=summary.generation_status,
        headline=summary.headline,
        bullet_points=list(summary.bullet_points)[:CARD_BULLETS],
        why_it_matters=summary.why_it_matters,
        source_coverage=summary.source_coverage,
        limitations=summary.limitations,
    )


def _detail(summary: Summary | None) -> SummaryDetail | None:
    if summary is None or summary.generation_status is GenerationStatus.PENDING:
        return None
    return SummaryDetail(
        status=summary.generation_status,
        headline=summary.headline,
        bullet_points=list(summary.bullet_points),
        why_it_matters=summary.why_it_matters,
        source_coverage=summary.source_coverage,
        limitations=summary.limitations,
        key_entities=list(summary.key_entities),
        model_name=summary.model_name,
        generated_at=summary.generated_at,
    )
