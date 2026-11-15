"""Keep the ``sources`` table in step with the code registry.

The registry is the source of truth for definitional fields (name, feed URL, defaults,
credibility). ``is_active`` is set only on creation, so operators can disable a source in the
database without a deploy and the setting survives subsequent syncs.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select

from app.database import DbSession
from app.ingestion.sources import SOURCE_DEFINITIONS, SourceDefinition
from app.models import Source

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncResult:
    created: list[str]
    updated: list[str]
    unregistered: list[str]  # rows in the DB with no integration (left untouched)


def sync_sources(
    session: DbSession, definitions: Iterable[SourceDefinition] = SOURCE_DEFINITIONS.values()
) -> SyncResult:
    existing = {s.slug: s for s in session.scalars(select(Source))}
    created: list[str] = []
    updated: list[str] = []
    seen: set[str] = set()

    for d in definitions:
        seen.add(d.slug)
        fields = {
            "name": d.name,
            "homepage_url": d.homepage_url,
            "feed_url": d.feed_url,
            "source_type": d.source_type,
            "default_category": d.default_category,
            "credibility_weight": d.credibility_weight,
        }
        source = existing.get(d.slug)
        if source is None:
            session.add(Source(slug=d.slug, is_active=d.active_by_default, **fields))
            created.append(d.slug)
            continue
        if source.feed_url != d.feed_url:
            source.http_etag = source.http_last_modified = None  # validators belong to old URL
        changed = False
        for key, value in fields.items():
            if getattr(source, key) != value:
                setattr(source, key, value)
                changed = True
        if changed:
            updated.append(d.slug)

    session.commit()
    unregistered = sorted(set(existing) - seen)
    if created or updated:
        logger.info("Source sync: created %s, updated %s", created, updated)
    return SyncResult(created, updated, unregistered)
