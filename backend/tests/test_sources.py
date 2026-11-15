from app.ingestion.sources import SOURCE_DEFINITIONS
from app.ingestion.sources.bloomberg import BLOOMBERG
from app.ingestion.sources.cnbc import CNBC
from app.utils.urls import is_safe_http_url


def test_registry_has_at_least_five_active_sources_with_valid_config() -> None:
    active = [d for d in SOURCE_DEFINITIONS.values() if d.active_by_default]
    assert len(active) >= 5
    for d in SOURCE_DEFINITIONS.values():
        assert is_safe_http_url(d.feed_url), d.slug
        assert 0 <= d.credibility_weight <= 1, d.slug


def test_cnbc_skips_sponsored_items() -> None:
    assert CNBC.include_entry({"metadata_sponsored": "false"})
    assert CNBC.include_entry({})
    assert not CNBC.include_entry({"metadata_sponsored": "true"})


def test_bloomberg_keeps_written_articles_only() -> None:
    assert BLOOMBERG.include_entry({"link": "https://www.bloomberg.com/news/articles/2026-11-14/x"})
    assert not BLOOMBERG.include_entry(
        {"link": "https://www.bloomberg.com/news/videos/2026-11-14/x"}
    )
    assert not BLOOMBERG.include_entry(
        {"link": "https://www.bloomberg.com/news/audio/2026-11-14/x"}
    )
