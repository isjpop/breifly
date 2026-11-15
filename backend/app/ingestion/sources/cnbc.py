from app.ingestion.sources.base import FeedEntry, SourceDefinition
from app.models.enums import Category


class CnbcSource(SourceDefinition):
    def include_entry(self, entry: FeedEntry) -> bool:
        # CNBC marks paid placements in its own metadata namespace.
        return str(entry.get("metadata_sponsored", "false")).strip().lower() != "true"


CNBC = CnbcSource(
    slug="cnbc",
    name="CNBC",
    homepage_url="https://www.cnbc.com",
    feed_url="https://www.cnbc.com/id/100003114/device/rss/rss.html",
    default_category=Category.BUSINESS,
    credibility_weight=0.85,
    notes="Official 'Top News' RSS. Headline and ~150-character description; no body text.",
)
