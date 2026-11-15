from datetime import UTC, datetime, timedelta

from flask import Flask

from app.database import db
from app.ingestion.deduplicator import (
    Deduplicator,
    MatchReason,
    Verdict,
    jaccard,
    overlap,
    title_tokens,
)
from app.ingestion.normalizer import NormalizedArticle
from app.models import ContentAvailability
from app.utils.text import content_fingerprint
from app.utils.urls import normalize_url
from tests.factories import definition, make_article, make_source

LONG_TEXT = "The central bank held rates steady while signalling cuts next year. " * 5


def candidate(title: str, url: str, **kwargs: object) -> NormalizedArticle:
    return NormalizedArticle(
        title=title,
        url=url,
        normalized_url=normalize_url(url),
        content_availability=ContentAvailability.DESCRIPTION_ONLY,
        **kwargs,  # type: ignore[arg-type]
    )


def dedup_for_run() -> Deduplicator:
    return Deduplicator.for_run(db.session, datetime.now(UTC) - timedelta(hours=72))


def test_title_tokens_drop_stopwords_and_fold_plurals() -> None:
    assert title_tokens("SpaceX catches the Starships") == {"spacex", "catch", "starship"}
    assert title_tokens("Nvidia\u2019s chips") == {"nvidia", "chip"}


def test_similarity_measures() -> None:
    a, b = frozenset({"a", "b", "c", "d"}), frozenset({"a", "b"})
    assert jaccard(a, b) == 0.5
    assert overlap(a, b) == 1.0
    assert jaccard(frozenset(), b) == 0.0


def test_exact_and_normalized_url_duplicates(app: Flask) -> None:
    source = make_source(definition("wire"))
    make_article(source, "Original headline here", "https://wire.example.com/story")
    dedup = dedup_for_run()
    exact = candidate("Different words entirely", "https://wire.example.com/story")
    tracked = candidate("Other words again", "https://www.wire.example.com/story/?utm_source=x")
    dedup.prefetch(source.id, [exact, tracked])

    assert dedup.check(source.id, exact).reason is MatchReason.EXACT_URL
    assert dedup.check(source.id, tracked).reason is MatchReason.NORMALIZED_URL


def test_guid_duplicate_within_same_source_only(app: Flask) -> None:
    a = make_source(definition("a"))
    b = make_source(definition("b"))
    make_article(a, "Some headline words", "https://a.example.com/1", guid="post-1")
    dedup = dedup_for_run()
    moved = candidate("Totally new title words", "https://a.example.com/moved", guid="post-1")
    dedup.prefetch(a.id, [moved])
    assert dedup.check(a.id, moved).reason is MatchReason.GUID

    other = candidate("Unrelated other topic", "https://b.example.com/x", guid="post-1")
    dedup.prefetch(b.id, [other])
    assert dedup.check(b.id, other).verdict is Verdict.NEW


def test_content_hash_detects_syndicated_copy(app: Flask) -> None:
    a = make_source(definition("a"))
    b = make_source(definition("b"))
    make_article(
        a,
        "Fed holds rates",
        "https://a.example.com/fed",
        content_hash=content_fingerprint(LONG_TEXT),
    )
    dedup = dedup_for_run()
    copy = candidate(
        "Central bank pauses",
        "https://b.example.com/fed-copy",
        content_hash=content_fingerprint(LONG_TEXT),
    )
    dedup.prefetch(b.id, [copy])
    assert dedup.check(b.id, copy).reason is MatchReason.CONTENT_HASH


def test_near_identical_headline_from_same_source_is_duplicate(app: Flask) -> None:
    source = make_source(definition("wire"))
    make_article(source, "Apple unveils new MacBook Pro with M6 chip", "https://wire.example.com/1")
    dedup = dedup_for_run()
    decision = dedup.check(
        source.id,
        candidate("Apple unveils new MacBook Pro with M6 chips", "https://wire.example.com/2"),
    )
    assert decision.verdict is Verdict.DUPLICATE
    assert decision.reason is MatchReason.SIMILAR_TITLE


def test_similar_headline_from_other_source_is_related_not_duplicate(app: Flask) -> None:
    cnbc = make_source(definition("cnbc"))
    verge = make_source(definition("verge"))
    original = make_article(
        cnbc,
        "SpaceX catches upper stage of Starship rocket in historic first",
        "https://cnbc.example.com/1",
    )
    dedup = dedup_for_run()
    decision = dedup.check(
        verge.id,
        candidate(
            "Watch SpaceX successfully execute the first chopstick catch of Starship",
            "https://verge.example.com/1",
        ),
    )
    assert decision.verdict is Verdict.RELATED
    assert decision.matched_article_id == original.id


def test_unrelated_headlines_sharing_one_entity_are_new(app: Flask) -> None:
    a = make_source(definition("a"))
    b = make_source(definition("b"))
    make_article(a, "Nvidia stock suffers longest weekly losing streak", "https://a.example.com/1")
    dedup = dedup_for_run()
    decision = dedup.check(
        b.id, candidate("Where was Nvidia's security team during breach", "https://b.example.com/1")
    )
    assert decision.verdict is Verdict.NEW


def test_rollback_forgets_staged_articles(app: Flask) -> None:
    source = make_source(definition("wire"))
    dedup = dedup_for_run()
    staged = make_article(source, "Staged article headline words", "https://wire.example.com/s")
    dedup.register(staged)
    dedup.rollback()

    again = candidate("Staged article headline words", "https://wire.example.com/s")
    assert dedup.check(source.id, again).verdict is Verdict.NEW
