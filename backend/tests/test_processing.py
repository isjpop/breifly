import uuid
from datetime import timedelta

import pytest
from flask import Flask
from sqlalchemy import select

from app.config import Settings
from app.database import db
from app.ingestion.scheduler import PROCESSING_LOCK_KEY, advisory_lock, run_processing_once
from app.models import (
    Article,
    CategorySource,
    ContentAvailability,
    GenerationStatus,
    ProcessingStatus,
    Source,
)
from app.models.base import utcnow
from app.services.llm import LLMConfigurationError, LLMRateLimitError, LLMUnavailableError
from app.services.processing import ArticleNotFound, ProcessingService
from tests.factories import definition, make_article, make_source
from tests.llm_fakes import FakeLLM, valid_output

BODY = "Regulators approved the merger after a year-long review of competition concerns. " * 4


def add_articles(
    n: int, *, source: Source | None = None, content: str | None = BODY, **kw
) -> list[Article]:
    source = source or make_source(definition(f"src{uuid.uuid4().hex[:6]}"))
    availability = (
        ContentAvailability.FEED_CONTENT if content else ContentAvailability.HEADLINE_ONLY
    )
    return [
        make_article(
            source,
            f"Story number {i} about markets and chips",
            f"https://{source.slug}.example.com/{i}",
            content=content,
            content_availability=availability,
            published_at=kw.get("published_at", utcnow()),
        )
        for i in range(n)
    ]


def processor(settings: Settings, llm: FakeLLM | None) -> ProcessingService:
    return ProcessingService(db.session, settings, llm)


def summaries_by_status() -> dict[GenerationStatus, int]:
    counts: dict[GenerationStatus, int] = {}
    for a in db.session.scalars(select(Article)):
        if a.summary:
            counts[a.summary.generation_status] = counts.get(a.summary.generation_status, 0) + 1
    return counts


def test_without_ai_articles_are_categorized_and_ranked_but_not_failed(
    app: Flask, settings: Settings
) -> None:
    add_articles(3)
    add_articles(1, content=None)

    report = processor(settings, None).run()

    assert report.categorized == 4
    assert report.ranked == 4
    assert report.insufficient == 1  # decided without the model
    assert report.deferred == 3
    assert report.failed == 0
    articles = list(db.session.scalars(select(Article)))
    assert all(
        a.category is not None and a.category_source is CategorySource.RULES for a in articles
    )
    assert all(a.importance_score is not None for a in articles)
    pending = [a for a in articles if a.processing_status is ProcessingStatus.PENDING]
    assert len(pending) == 3


def test_with_ai_summaries_are_generated_and_rank_uses_ai_scores(
    app: Flask, settings: Settings
) -> None:
    (article,) = add_articles(1)
    before = processor(settings, None).run()
    assert before.summarized == 0
    db.session.refresh(article)
    unassessed_score = article.importance_score

    report = processor(
        settings, FakeLLM(default=valid_output(impact_score=9, significance_score=9))
    ).run()

    db.session.refresh(article)
    assert report.summarized == 1
    assert article.processing_status is ProcessingStatus.PROCESSED
    assert article.category_source is CategorySource.AI
    assert article.importance_score is not None and unassessed_score is not None
    assert article.importance_score > unassessed_score


def test_summaries_are_reused_not_regenerated(app: Flask, settings: Settings) -> None:
    add_articles(2)
    llm = FakeLLM(default=valid_output())
    processor(settings, llm).run()
    assert len(llm.calls) == 2

    second = processor(settings, llm).run()
    assert second.llm_calls == 0
    assert len(llm.calls) == 2


def test_budget_limits_calls_and_prioritizes_most_important(app: Flask, settings: Settings) -> None:
    old = add_articles(3, published_at=utcnow() - timedelta(hours=48))
    fresh = add_articles(2)
    llm = FakeLLM(default=valid_output())

    report = processor(settings, llm).run(max_summaries=2)

    assert report.summarized == 2
    assert report.deferred == 3
    summarized = {
        a.id
        for a in db.session.scalars(select(Article))
        if a.summary and a.summary.generation_status is GenerationStatus.SUCCEEDED
    }
    assert summarized == {a.id for a in fresh}
    assert all(a.id not in summarized for a in old)


def test_rate_limit_stops_further_calls_this_run(app: Flask, settings: Settings) -> None:
    add_articles(4)
    llm = FakeLLM([valid_output(), LLMRateLimitError("HTTP 429")], default=valid_output())

    report = processor(settings, llm).run()

    assert len(llm.calls) == 2
    assert report.summarized == 1
    assert report.deferred == 3
    assert report.stopped_reason == "provider rate limit reached"


def test_configuration_error_stops_the_run(app: Flask, settings: Settings) -> None:
    add_articles(3)
    llm = FakeLLM([LLMConfigurationError("HTTP 401")], default=valid_output())
    report = processor(settings, llm).run()
    assert len(llm.calls) == 1
    assert report.stopped_reason is not None and "configuration" in report.stopped_reason


def test_repeated_outages_trip_the_circuit_breaker(app: Flask, settings: Settings) -> None:
    add_articles(5)
    llm = FakeLLM(default=None, responses=[LLMUnavailableError("HTTP 503")] * 5)

    report = processor(settings, llm).run()

    assert report.failed == 3
    assert report.deferred == 2
    assert report.stopped_reason == "repeated provider failures"


def test_failed_summaries_are_retried_until_max_attempts(app: Flask, settings: Settings) -> None:
    (article,) = add_articles(1)
    failing = FakeLLM(default=None, responses=[LLMUnavailableError("down")] * 10)
    for _ in range(settings.summary_max_attempts):
        processor(settings, failing).run()

    db.session.refresh(article)
    assert article.summary is not None
    assert article.summary.attempts == settings.summary_max_attempts
    assert article.processing_status is ProcessingStatus.PROCESSED  # gave up; stays readable

    calls_before = len(failing.calls)
    processor(settings, failing).run()
    assert len(failing.calls) == calls_before


def test_unexpected_error_marks_only_that_article_failed(
    app: Flask, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    articles = add_articles(2)
    service = processor(settings, FakeLLM(default=valid_output()))
    original = service.summarizer.summarize
    bad_id = articles[0].id

    def flaky(article: Article):  # type: ignore[no-untyped-def]
        if article.id == bad_id:
            raise RuntimeError("bug")
        return original(article)

    monkeypatch.setattr(service.summarizer, "summarize", flaky)
    report = service.run()

    assert report.errors == 1 and report.summarized == 1
    bad = db.session.get(Article, bad_id)
    assert bad is not None and bad.processing_status is ProcessingStatus.FAILED


def test_regenerate_replaces_the_existing_summary(app: Flask, settings: Settings) -> None:
    (article,) = add_articles(1)
    processor(settings, FakeLLM(default=valid_output(headline="First version"))).run()
    db.session.refresh(article)
    assert article.summary is not None
    first_id = article.summary.id

    regenerated = processor(
        settings, FakeLLM([valid_output(headline="Second version")])
    ).regenerate(article.id)

    assert regenerated.summary is not None
    assert regenerated.summary.id == first_id  # updated in place, one summary per article
    assert regenerated.summary.headline == "Second version"
    assert regenerated.summary.attempts == 2


def test_regenerate_unknown_article(app: Flask, settings: Settings) -> None:
    with pytest.raises(ArticleNotFound):
        processor(settings, FakeLLM()).regenerate(uuid.uuid4())


def test_processing_runs_do_not_overlap(app: Flask, settings: Settings) -> None:
    with advisory_lock(db.engine, PROCESSING_LOCK_KEY):
        assert run_processing_once(settings, use_ai=False) is None
    assert run_processing_once(settings, use_ai=False) is not None
