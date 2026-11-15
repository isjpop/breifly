from urllib.parse import urlsplit

from app.ingestion.sources.base import FeedEntry, SourceDefinition
from app.models.enums import Category


class BloombergSource(SourceDefinition):
    def include_entry(self, entry: FeedEntry) -> bool:
        # The markets feed mixes in video and audio segments; keep written articles only.
        path = urlsplit(str(entry.get("link", ""))).path
        return path.startswith("/news/articles/")


BLOOMBERG = BloombergSource(
    slug="bloomberg",
    name="Bloomberg",
    homepage_url="https://www.bloomberg.com",
    feed_url="https://feeds.bloomberg.com/markets/news.rss",
    default_category=Category.FINANCE,
    credibility_weight=0.95,
    notes=(
        "Publisher-hosted markets RSS. Very short descriptions only; articles themselves are "
        "paywalled and are never fetched."
    ),
)
