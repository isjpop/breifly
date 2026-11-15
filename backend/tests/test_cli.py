import httpx
import pytest
from flask import Flask
from sqlalchemy import select

from app.database import db
from app.ingestion import scheduler
from app.ingestion.sources import SOURCE_DEFINITIONS
from app.models import Article, IngestionRun, RunTrigger, Source
from tests.feeds import mock_transport, rss, xml_response


@pytest.fixture
def mocked_feeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Serve one synthetic article per registered source instead of hitting the network."""
    routes = {
        d.feed_url: xml_response(
            rss(
                [
                    {
                        "title": f"{d.name} exclusive report today",
                        "link": f"{d.homepage_url}/news/articles/1",
                    }
                ]
            )
        )
        for d in SOURCE_DEFINITIONS.values()
    }
    monkeypatch.setattr(
        scheduler, "build_http_client", lambda _s: httpx.Client(transport=mock_transport(routes))
    )


def test_sources_sync_and_list(app: Flask) -> None:
    runner = app.test_cli_runner()
    result = runner.invoke(args=["sources", "sync"])
    assert result.exit_code == 0, result.output
    assert "created" in result.output

    listing = runner.invoke(args=["sources", "list"])
    assert "never fetched" in listing.output
    assert db.session.query(Source).count() == len(SOURCE_DEFINITIONS)


def test_ingest_run_command_ingests_all_registered_sources(app: Flask, mocked_feeds: None) -> None:
    result = app.test_cli_runner().invoke(args=["ingest", "run"])

    assert result.exit_code == 0, result.output
    assert "succeeded" in result.output
    assert db.session.query(Article).count() == len(SOURCE_DEFINITIONS)


def test_scheduler_tick_syncs_and_records_a_scheduler_run(app: Flask, mocked_feeds: None) -> None:
    run = scheduler.sync_and_run(app.config["BRIEFLY_SETTINGS"], RunTrigger.SCHEDULER)
    assert run is not None
    stored = db.session.scalars(select(IngestionRun)).one()
    assert stored.trigger is RunTrigger.SCHEDULER
