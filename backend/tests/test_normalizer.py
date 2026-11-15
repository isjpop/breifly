from datetime import UTC, datetime

import pytest

from app.ingestion.normalizer import EntryRejected, RejectionReason, normalize_entry
from app.ingestion.sources.base import SourceDefinition
from app.models.enums import Category, ContentAvailability
from tests.feeds import fixture_bytes, parse_entries, rss

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
DEFINITION = SourceDefinition(
    slug="test",
    name="Test",
    homepage_url="https://example.com",
    feed_url="https://example.com/feed",
    default_category=Category.TECHNOLOGY,
    credibility_weight=0.8,
)


def normalize_one(**item: object):
    entries = parse_entries(rss([{"link": "https://example.com/a", **item}]))
    return normalize_entry(entries[0], DEFINITION, now=NOW)


def test_full_rss_entry_is_normalized() -> None:
    entry = parse_entries(fixture_bytes("rss_basic.xml"))[0]
    article = normalize_entry(entry, DEFINITION, now=NOW)

    assert article.title == "Chipmaker Unveils 2nm Processor for Data Centers"
    assert article.url.startswith("https://www.example.com/2026/11/14/chipmaker-2nm-processor/")
    assert article.normalized_url == "https://example.com/2026/11/14/chipmaker-2nm-processor"
    assert article.guid == "example-1001"
    assert article.author == "Jane Analyst"
    assert article.published_at == datetime(2026, 11, 14, 15, 30, tzinfo=UTC)
    assert article.description == "A new processor promises 40% better efficiency."
    assert article.content_availability is ContentAvailability.FEED_CONTENT
    assert article.content is not None and "2-nanometer" in article.content
    assert "alert" not in article.content  # script contents dropped
    assert article.image_url == "https://cdn.example.com/chip.jpg"
    assert article.tags == ["Semiconductors", "AI"]
    assert article.content_hash is not None


def test_description_only_and_headline_only_entries() -> None:
    entries = parse_entries(fixture_bytes("rss_basic.xml"))
    markets = normalize_entry(entries[1], DEFINITION, now=NOW)
    fusion = normalize_entry(entries[2], DEFINITION, now=NOW)

    assert markets.content_availability is ContentAvailability.DESCRIPTION_ONLY
    assert markets.content is None
    assert markets.image_url == "https://cdn.example.com/markets.jpg"
    assert markets.content_hash is None  # too short to fingerprint reliably

    assert fusion.content_availability is ContentAvailability.HEADLINE_ONLY
    assert fusion.title == "Researchers & Engineers Report Fusion Milestone"
    assert fusion.description is None


def test_atom_entry_is_normalized() -> None:
    entry = parse_entries(fixture_bytes("atom_basic.xml"))[0]
    article = normalize_entry(entry, DEFINITION, now=NOW)

    assert article.url == "https://atom.example.org/space/lunar-lander-window"
    assert article.author == "Sam Reporter"
    assert article.published_at == datetime(2026, 11, 14, 21, 44, 44, tzinfo=UTC)
    assert article.content_availability is ContentAvailability.FEED_CONTENT


def test_missing_title_is_rejected() -> None:
    with pytest.raises(EntryRejected) as exc:
        normalize_one(title=None)
    assert exc.value.reason is RejectionReason.MISSING_TITLE


def test_whitespace_or_markup_only_title_is_rejected() -> None:
    with pytest.raises(EntryRejected):
        normalize_one(title="   <b> </b> ")


def test_missing_url_is_rejected() -> None:
    entries = parse_entries(rss([{"title": "No link here", "link": None}]))
    with pytest.raises(EntryRejected) as exc:
        normalize_entry(entries[0], DEFINITION, now=NOW)
    assert exc.value.reason is RejectionReason.MISSING_URL


def test_non_http_url_is_rejected() -> None:
    entries = parse_entries(rss([{"title": "Bad link", "link": "javascript:alert(1)"}]))
    with pytest.raises(EntryRejected) as exc:
        normalize_entry(entries[0], DEFINITION, now=NOW)
    assert exc.value.reason is RejectionReason.INVALID_URL


def test_invalid_publication_date_is_stored_as_unknown() -> None:
    article = normalize_one(title="Has a bad date", pubDate="not a real date")
    assert article.published_at is None
    assert article.date_issue == "unparseable"


def test_future_publication_date_is_not_trusted() -> None:
    article = normalize_one(title="From the future", pubDate="Mon, 01 Jan 2035 00:00:00 GMT")
    assert article.published_at is None
    assert article.date_issue == "future"


def test_missing_date_is_allowed_without_issue() -> None:
    article = normalize_one(title="No date at all")
    assert article.published_at is None
    assert article.date_issue is None


def test_unsafe_image_url_is_dropped() -> None:
    article = normalize_one(
        title="Img",
        description='<img src="javascript:alert(1)"> text',
    )
    assert article.image_url is None


def test_overlong_fields_are_capped() -> None:
    article = normalize_one(title="T" * 800, description="D" * 9000)
    assert len(article.title) == 500
    assert article.description is not None and len(article.description) == 5000
