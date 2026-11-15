"""Publisher integration contract.

Each publisher module defines a ``SourceDefinition`` (feed location, defaults, credibility) and may
override hooks for source-specific quirks. Adding a publisher means adding one module and
registering it in ``app/ingestion/sources/__init__.py``; the pipeline itself does not change.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.models.enums import Category, SourceType
from app.utils.text import first_image_src

FeedEntry = Mapping[str, Any]  # a feedparser entry


@dataclass(frozen=True)
class SourceDefinition:
    slug: str
    name: str
    homepage_url: str
    feed_url: str
    default_category: Category
    credibility_weight: float
    source_type: SourceType = SourceType.RSS
    active_by_default: bool = True
    notes: str = ""

    def include_entry(self, entry: FeedEntry) -> bool:
        """Return False to skip non-article items (sponsored posts, videos, podcasts...)."""
        return True

    def extract_image(self, entry: FeedEntry) -> str | None:
        """Best-effort thumbnail from common RSS/Atom media conventions."""
        for thumb in entry.get("media_thumbnail") or []:
            if thumb.get("url"):
                return str(thumb["url"])
        for media in entry.get("media_content") or []:
            medium = media.get("medium") or ""
            mime = media.get("type") or ""
            if media.get("url") and (medium == "image" or mime.startswith("image/") or not mime):
                return str(media["url"])
        for enclosure in entry.get("enclosures") or []:
            if (enclosure.get("type") or "").startswith("image/") and enclosure.get("href"):
                return str(enclosure["href"])
        for item in entry.get("content") or []:
            if src := first_image_src(item.get("value")):
                return src
        return first_image_src(entry.get("summary"))
