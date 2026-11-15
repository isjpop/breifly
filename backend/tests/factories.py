"""Small builders for database rows used across tests."""

from typing import Any

from app.database import db
from app.ingestion.sources.base import SourceDefinition
from app.models import Article, Category, ContentAvailability, Source
from app.utils.urls import normalize_url


def definition(slug: str, feed_url: str | None = None, **kwargs: Any) -> SourceDefinition:
    return SourceDefinition(
        slug=slug,
        name=kwargs.pop("name", slug.title()),
        homepage_url=f"https://{slug}.example.com",
        feed_url=feed_url or f"https://{slug}.example.com/feed",
        default_category=kwargs.pop("default_category", Category.TECHNOLOGY),
        credibility_weight=kwargs.pop("credibility_weight", 0.8),
        **kwargs,
    )


def make_source(d: SourceDefinition, **overrides: Any) -> Source:
    source = Source(
        slug=d.slug,
        name=d.name,
        homepage_url=d.homepage_url,
        feed_url=d.feed_url,
        default_category=d.default_category,
        credibility_weight=d.credibility_weight,
        is_active=True,
        **overrides,
    )
    db.session.add(source)
    db.session.commit()
    return source


def make_article(source: Source, title: str, url: str, **overrides: Any) -> Article:
    article = Article(
        source_id=source.id,
        title=title,
        url=url,
        normalized_url=normalize_url(url),
        content_availability=ContentAvailability.DESCRIPTION_ONLY,
        **overrides,
    )
    db.session.add(article)
    db.session.commit()
    return article
