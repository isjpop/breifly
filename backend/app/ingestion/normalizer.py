"""Convert heterogeneous feed entries into one validated ``NormalizedArticle`` shape.

All feed text is treated as untrusted: markup is stripped to plain text, URLs must be absolute
http(s), and fields are length-capped. Nothing beyond the feed itself is fetched.
"""

import calendar
import enum
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.ingestion.sources.base import FeedEntry, SourceDefinition
from app.models.enums import ContentAvailability
from app.utils.text import content_fingerprint, html_to_text, truncate
from app.utils.urls import is_safe_http_url, normalize_url

MAX_TITLE = 500
MAX_AUTHOR = 300
MAX_DESCRIPTION = 5_000
MAX_CONTENT = 100_000
MAX_TAGS = 10
MAX_TAG_LENGTH = 64
# Content shorter than this is too generic to identify a copy reliably by hash.
MIN_HASHABLE_LENGTH = 200
# Publishers' clocks drift; anything further in the future is treated as an invalid date.
FUTURE_DATE_TOLERANCE = timedelta(hours=1)
EARLIEST_PLAUSIBLE_DATE = datetime(1995, 1, 1, tzinfo=UTC)


class RejectionReason(enum.StrEnum):
    MISSING_TITLE = "missing_title"
    MISSING_URL = "missing_url"
    INVALID_URL = "invalid_url"


class EntryRejected(Exception):
    def __init__(self, reason: RejectionReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


class NormalizedArticle(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1, max_length=MAX_TITLE)
    url: str = Field(max_length=2048)
    normalized_url: str = Field(max_length=2048)
    guid: str | None = Field(default=None, max_length=1024)
    author: str | None = Field(default=None, max_length=MAX_AUTHOR)
    description: str | None = None
    content: str | None = None
    content_availability: ContentAvailability
    image_url: str | None = None
    published_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    content_hash: str | None = None
    # Present when the feed supplied a date we could not trust ("unparseable", "future", ...).
    date_issue: str | None = None


def _clean(value: Any, limit: int, *, single_line: bool = False) -> str | None:
    text = html_to_text(value) if isinstance(value, str) else ""
    if single_line:
        text = " ".join(text.split())
    return truncate(text, limit) or None


def _entry_content(entry: FeedEntry) -> str | None:
    blocks = entry.get("content") or []
    text = "\n\n".join(html_to_text(b.get("value")) for b in blocks if b.get("value"))
    return truncate(text.strip(), MAX_CONTENT) or None


def _published_at(entry: FeedEntry, now: datetime) -> tuple[datetime | None, str | None]:
    for raw_key, parsed_key in (("published", "published_parsed"), ("updated", "updated_parsed")):
        if not entry.get(raw_key):
            continue
        parsed: time.struct_time | None = entry.get(parsed_key)
        if parsed is None:
            return None, "unparseable"
        value = datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)
        if value > now + FUTURE_DATE_TOLERANCE:
            return None, "future"
        if value < EARLIEST_PLAUSIBLE_DATE:
            return None, "implausible"
        return value, None
    return None, None


def _tags(entry: FeedEntry) -> list[str]:
    seen: dict[str, str] = {}
    for tag in entry.get("tags") or []:
        term = " ".join(html_to_text(tag.get("term") or "").split())
        if term and len(term) <= MAX_TAG_LENGTH and term.lower() not in seen:
            seen[term.lower()] = term
    return list(seen.values())[:MAX_TAGS]


def normalize_entry(
    entry: FeedEntry, definition: SourceDefinition, *, now: datetime | None = None
) -> NormalizedArticle:
    """Raise ``EntryRejected`` when the entry lacks what every article must have."""
    now = now or datetime.now(UTC)

    title = _clean(entry.get("title"), MAX_TITLE, single_line=True)
    if not title:
        raise EntryRejected(RejectionReason.MISSING_TITLE)

    link = str(entry.get("link") or "").strip()
    if not link:
        raise EntryRejected(RejectionReason.MISSING_URL)
    if not is_safe_http_url(link):
        raise EntryRejected(RejectionReason.INVALID_URL)

    content = _entry_content(entry)
    description = _clean(entry.get("summary"), MAX_DESCRIPTION)
    if content and description and content == description:
        content = None  # feed duplicated the teaser into the body field
    if not description and content:
        description = truncate(" ".join(content.split()), 400)

    if content:
        availability = ContentAvailability.FEED_CONTENT
    elif description:
        availability = ContentAvailability.DESCRIPTION_ONLY
    else:
        availability = ContentAvailability.HEADLINE_ONLY

    hash_source = content or description or ""
    content_hash = (
        content_fingerprint(hash_source) if len(hash_source) >= MIN_HASHABLE_LENGTH else None
    )

    image = definition.extract_image(entry)
    published_at, date_issue = _published_at(entry, now)
    guid = str(entry.get("id") or "").strip()[:1024] or None

    return NormalizedArticle(
        title=title,
        url=link,
        normalized_url=normalize_url(link),
        guid=guid,
        author=_clean(entry.get("author"), MAX_AUTHOR, single_line=True),
        description=description,
        content=content,
        content_availability=availability,
        image_url=image if is_safe_http_url(image) else None,
        published_at=published_at,
        tags=_tags(entry),
        content_hash=content_hash,
        date_issue=date_issue,
    )
