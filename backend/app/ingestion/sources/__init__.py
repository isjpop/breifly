"""Registry of publisher integrations.

Reuters and the Associated Press are not registered: Reuters retired its public RSS feeds and AP
does not offer one (apnews.com/index.rss returns 403). Both require a commercial licence
(Reuters Connect, AP Media API). Add a ``SourceType.API`` integration here once credentials exist.
"""

from app.ingestion.sources.ars_technica import ARS_TECHNICA
from app.ingestion.sources.base import FeedEntry, SourceDefinition
from app.ingestion.sources.bloomberg import BLOOMBERG
from app.ingestion.sources.cnbc import CNBC
from app.ingestion.sources.mit_technology_review import MIT_TECHNOLOGY_REVIEW
from app.ingestion.sources.techcrunch import TECHCRUNCH
from app.ingestion.sources.the_verge import THE_VERGE

SOURCE_DEFINITIONS: dict[str, SourceDefinition] = {
    definition.slug: definition
    for definition in (
        CNBC,
        BLOOMBERG,
        TECHCRUNCH,
        THE_VERGE,
        ARS_TECHNICA,
        MIT_TECHNOLOGY_REVIEW,
    )
}

__all__ = ["SOURCE_DEFINITIONS", "FeedEntry", "SourceDefinition"]
