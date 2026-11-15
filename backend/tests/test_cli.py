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


def test_scheduler_tick_ingests_and_processes(app: Flask, mocked_feeds: None) -> None:
    scheduler.run_pipeline_once(app.config["BRIEFLY_SETTINGS"], RunTrigger.SCHEDULER)

    stored = db.session.scalars(select(IngestionRun)).one()
    assert stored.trigger is RunTrigger.SCHEDULER
    articles = db.session.scalars(select(Article)).all()
    assert articles and all(a.category is not None for a in articles)
    assert all(a.importance_score is not None for a in articles)


def test_process_run_without_ai(app: Flask, mocked_feeds: None) -> None:
    runner = app.test_cli_runner()
    runner.invoke(args=["ingest", "run"])
    result = runner.invoke(args=["process", "run", "--no-ai"])

    assert result.exit_code == 0, result.output
    assert f"categorized={len(SOURCE_DEFINITIONS)}" in result.output
    assert "llm_calls=0" in result.output


def test_regenerate_requires_api_key(app: Flask) -> None:
    result = app.test_cli_runner().invoke(
        args=["summaries", "regenerate", "00000000-0000-0000-0000-000000000000"]
    )
    assert result.exit_code != 0
    assert "GEMINI_API_KEY is not set" in result.output


def test_ai_usage_report(app: Flask) -> None:
    from app.models import AIUsageEvent, UsageStatus

    db.session.add(
        AIUsageEvent(
            operation="summarize", provider="gemini", model_name="gemini-3.5-flash-lite",
            status=UsageStatus.SUCCESS, input_tokens=1000, output_tokens=200,
            estimated_cost_usd=0.0008,
        )
    )  # fmt: skip
    db.session.commit()
    result = app.test_cli_runner().invoke(args=["ai", "usage"])
    assert "gemini-3.5-flash-lite" in result.output
    assert "calls=1" in result.output
