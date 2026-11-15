from collections.abc import Mapping

import httpx
import pytest
from flask import Flask
from sqlalchemy import select

from app.config import Settings
from app.database import db
from app.ingestion.http import FeedFetcher
from app.ingestion.pipeline import FeedParseError, IngestionService, parse_feed
from app.ingestion.sources.base import SourceDefinition
from app.models import (
    Article,
    ContentAvailability,
    FetchStatus,
    IngestionRun,
    ProcessingStatus,
    RunStatus,
    Source,
)
from tests.factories import definition, make_source
from tests.feeds import Route, fixture_bytes, mock_transport, rss, xml_response

LONG = "Officials confirmed the agreement after months of negotiation between the parties. " * 4


def service(
    settings: Settings,
    definitions: Mapping[str, SourceDefinition],
    routes: Mapping[str, Route],
) -> IngestionService:
    client = httpx.Client(transport=mock_transport(routes))
    fetcher = FeedFetcher(client, max_retries=1, sleep=lambda _s: None)
    return IngestionService(db.session, fetcher, settings, definitions=definitions)


def articles_for(slug: str) -> list[Article]:
    return list(
        db.session.scalars(
            select(Article).join(Source).where(Source.slug == slug).order_by(Article.title)
        )
    )


def test_successful_ingestion_stores_articles_and_tracks_source(
    app: Flask, settings: Settings
) -> None:
    d = definition("wire")
    make_source(d)
    svc = service(
        settings,
        {d.slug: d},
        {d.feed_url: xml_response(fixture_bytes("rss_basic.xml"), headers={"ETag": '"abc"'})},
    )

    run = svc.run()

    assert run.status is RunStatus.SUCCEEDED
    assert (run.articles_seen, run.articles_new, run.articles_invalid) == (3, 3, 0)
    stored = articles_for("wire")
    assert [a.title for a in stored] == [
        "Chipmaker Unveils 2nm Processor for Data Centers",
        "Markets Close Higher as Bond Yields Ease",
        "Researchers & Engineers Report Fusion Milestone",
    ]
    assert all(a.processing_status is ProcessingStatus.PENDING for a in stored)
    assert stored[0].content_availability is ContentAvailability.FEED_CONTENT

    source = db.session.scalars(select(Source)).one()
    assert source.last_fetch_status is FetchStatus.SUCCESS
    assert source.last_successful_fetch_at is not None
    assert source.http_etag == '"abc"'
    assert source.consecutive_failures == 0
    assert run.source_results["wire"]["new"] == 3


def test_reingesting_the_same_feed_inserts_nothing(app: Flask, settings: Settings) -> None:
    d = definition("wire")
    make_source(d)
    routes = {d.feed_url: xml_response(fixture_bytes("rss_basic.xml"))}
    service(settings, {d.slug: d}, routes).run()

    second = service(settings, {d.slug: d}, routes).run()

    assert second.articles_new == 0
    assert second.articles_duplicate == 3
    assert len(articles_for("wire")) == 3


def test_duplicate_entries_within_one_feed_are_stored_once(app: Flask, settings: Settings) -> None:
    d = definition("wire")
    make_source(d)
    body = rss(
        [
            {"title": "Same story twice", "link": "https://wire.example.com/s?utm_source=a"},
            {"title": "Same story twice", "link": "https://wire.example.com/s/"},
        ]
    )
    run = service(settings, {d.slug: d}, {d.feed_url: xml_response(body)}).run()
    assert (run.articles_new, run.articles_duplicate) == (1, 1)


def test_invalid_entries_are_counted_and_skipped(app: Flask, settings: Settings) -> None:
    d = definition("wire")
    make_source(d)
    body = rss(
        [
            {"title": None, "link": "https://wire.example.com/no-title"},
            {"title": "No link", "link": None},
            {"title": "Script link", "link": "javascript:alert(1)"},
            {
                "title": "Bad date but fine",
                "link": "https://wire.example.com/ok",
                "pubDate": "yesterday-ish",
            },
        ]
    )
    run = service(settings, {d.slug: d}, {d.feed_url: xml_response(body)}).run()

    assert (run.articles_new, run.articles_invalid) == (1, 3)
    assert run.source_results["wire"]["rejections"] == {
        "missing_title": 1,
        "missing_url": 1,
        "invalid_url": 1,
    }
    (article,) = articles_for("wire")
    assert article.published_at is None
    assert article.extra == {"date_issue": "unparseable"}


def test_one_publisher_failing_does_not_stop_others(app: Flask, settings: Settings) -> None:
    good = definition("good")
    down = definition("down")
    junk = definition("junk")
    for d in (good, down, junk):
        make_source(d)
    routes: dict[str, Route] = {
        good.feed_url: xml_response(
            rss([{"title": "Working feed story", "link": "https://good.example.com/1"}])
        ),
        down.feed_url: httpx.Response(500),
        junk.feed_url: httpx.Response(
            200, content=fixture_bytes("not_a_feed.html"), headers={"Content-Type": "text/html"}
        ),
    }
    run = service(settings, {d.slug: d for d in (good, down, junk)}, routes).run()

    assert run.status is RunStatus.PARTIAL
    assert (run.sources_attempted, run.sources_succeeded, run.sources_failed) == (3, 1, 2)
    assert len(articles_for("good")) == 1
    assert "HTTP 500" in run.source_results["down"]["error"]
    assert "not a valid RSS/Atom feed" in run.source_results["junk"]["error"]

    down_row = db.session.scalars(select(Source).where(Source.slug == "down")).one()
    assert down_row.last_fetch_status is FetchStatus.FAILED
    assert down_row.consecutive_failures == 1
    assert down_row.last_successful_fetch_at is None


def test_network_failure_and_missing_integration_are_isolated(
    app: Flask, settings: Settings
) -> None:
    good = definition("good")
    offline = definition("offline")
    orphan = definition("orphan")
    for d in (good, offline, orphan):
        make_source(d)
    routes: dict[str, Route] = {
        good.feed_url: xml_response(
            rss([{"title": "Still arrives fine", "link": "https://good.example.com/2"}])
        ),
        offline.feed_url: httpx.ConnectError("refused"),
    }
    run = service(settings, {good.slug: good, offline.slug: offline}, routes).run()

    assert run.status is RunStatus.PARTIAL
    assert run.source_results["offline"]["error"].startswith("network error")
    assert "no integration registered" in run.source_results["orphan"]["error"]
    assert run.articles_new == 1


def test_all_sources_failing_marks_run_failed(app: Flask, settings: Settings) -> None:
    d = definition("down")
    make_source(d)
    run = service(settings, {d.slug: d}, {d.feed_url: httpx.Response(503)}).run()
    assert run.status is RunStatus.FAILED


def test_not_modified_feed_is_a_success_without_parsing(app: Flask, settings: Settings) -> None:
    d = definition("wire")
    make_source(d, http_etag='"v1"')
    run = service(settings, {d.slug: d}, {d.feed_url: httpx.Response(304)}).run()

    assert run.status is RunStatus.SUCCEEDED
    assert run.source_results["wire"]["status"] == "not_modified"
    assert db.session.scalars(select(Source)).one().http_etag == '"v1"'


def test_filtered_entries_are_not_stored(app: Flask, settings: Settings) -> None:
    class NoVideos(SourceDefinition):
        def include_entry(self, entry):  # type: ignore[no-untyped-def]
            return "/video/" not in entry.get("link", "")

    d = NoVideos(**{**definition("wire").__dict__})
    make_source(d)
    body = rss(
        [
            {"title": "Watch the clip now", "link": "https://wire.example.com/video/1"},
            {"title": "Written article here", "link": "https://wire.example.com/news/1"},
        ]
    )
    run = service(settings, {d.slug: d}, {d.feed_url: xml_response(body)}).run()
    assert (run.articles_filtered, run.articles_new) == (1, 1)


def test_syndicated_copy_across_sources_is_a_duplicate(app: Flask, settings: Settings) -> None:
    a, b = definition("a"), definition("b")
    make_source(a)
    make_source(b)
    routes = {
        a.feed_url: xml_response(
            rss(
                [{"title": "Treaty signed", "link": "https://a.example.com/t", "description": LONG}]
            )
        ),
        b.feed_url: xml_response(
            rss(
                [
                    {
                        "title": "Accord reached",
                        "link": "https://b.example.com/t",
                        "description": LONG,
                    }
                ]
            )
        ),
    }
    run = service(settings, {"a": a, "b": b}, routes).run()
    assert (run.articles_new, run.articles_duplicate) == (1, 1)


def test_cross_source_coverage_is_grouped_into_a_story_cluster(
    app: Flask, settings: Settings
) -> None:
    a, b, c = definition("a"), definition("b"), definition("c")
    for d in (a, b, c):
        make_source(d)
    routes = {
        a.feed_url: xml_response(
            rss(
                [
                    {
                        "title": "SpaceX catches upper stage of Starship rocket in historic first",
                        "link": "https://a.example.com/s",
                    }
                ]
            )
        ),
        b.feed_url: xml_response(
            rss(
                [
                    {
                        "title": "Watch SpaceX successfully execute the first chopstick "
                        "catch of Starship",
                        "link": "https://b.example.com/s",
                    }
                ]
            )
        ),
        c.feed_url: xml_response(
            rss(
                [
                    {
                        "title": "Central bank leaves interest rates unchanged",
                        "link": "https://c.example.com/r",
                    }
                ]
            )
        ),
    }
    run = service(settings, {d.slug: d for d in (a, b, c)}, routes).run()

    assert run.articles_new == 3  # related coverage is kept, not discarded
    spacex = articles_for("a") + articles_for("b")
    assert spacex[0].story_cluster_id is not None
    assert spacex[0].story_cluster_id == spacex[1].story_cluster_id
    assert articles_for("c")[0].story_cluster_id is None


def test_inactive_sources_are_skipped(app: Flask, settings: Settings) -> None:
    d = definition("paused")
    make_source(d)
    db.session.scalars(select(Source)).one().is_active = False
    db.session.commit()
    run = service(settings, {d.slug: d}, {}).run()
    assert run.sources_attempted == 0
    assert run.status is RunStatus.SUCCEEDED


def test_only_slugs_limits_the_run(app: Flask, settings: Settings) -> None:
    a, b = definition("a"), definition("b")
    make_source(a)
    make_source(b)
    routes = {a.feed_url: xml_response(rss([])), b.feed_url: httpx.Response(500)}
    run = service(settings, {"a": a, "b": b}, routes).run(only_slugs=["a"])
    assert list(run.source_results) == ["a"]


def test_runs_are_persisted(app: Flask, settings: Settings) -> None:
    service(settings, {}, {}).run()
    stored = db.session.scalars(select(IngestionRun)).one()
    assert stored.finished_at is not None


def test_parse_feed_rejects_non_feed_and_accepts_empty_feed() -> None:
    with pytest.raises(FeedParseError):
        parse_feed(fixture_bytes("not_a_feed.html"))
    with pytest.raises(FeedParseError):
        parse_feed(b"")
    assert parse_feed(rss([])) == []


def test_bug_in_one_integration_is_isolated(app: Flask, settings: Settings) -> None:
    class Broken(SourceDefinition):
        def include_entry(self, entry):  # type: ignore[no-untyped-def]
            raise KeyError("adapter bug")

    broken = Broken(**{**definition("broken").__dict__})
    good = definition("good")
    make_source(broken)
    make_source(good)
    routes = {
        broken.feed_url: xml_response(
            rss([{"title": "Never stored", "link": "https://x.example.com/1"}])
        ),
        good.feed_url: xml_response(
            rss([{"title": "Stored fine", "link": "https://good.example.com/1"}])
        ),
    }
    run = service(settings, {"broken": broken, "good": good}, routes).run()

    assert run.status is RunStatus.PARTIAL
    assert run.source_results["broken"]["error"] == "internal error: KeyError"
    assert run.articles_new == 1
