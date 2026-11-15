from flask import Flask
from sqlalchemy import select

from app.config import Settings
from app.database import db
from app.models import (
    AIUsageEvent,
    Article,
    Category,
    CategorySource,
    ContentAvailability,
    GenerationStatus,
    SourceCoverage,
    UsageStatus,
)
from app.services.llm import LLMRateLimitError, LLMTimeoutError
from app.services.prompts import PROMPT_VERSION
from app.services.summarizer import Summarizer, source_coverage
from tests.factories import definition, make_article, make_source
from tests.llm_fakes import FakeLLM, valid_output

BODY = "The company said the processor delivers 40% better efficiency. " * 6
EXCERPT = (
    "Stocks rose on Friday as Treasury yields fell for a third straight session, "
    "with traders pointing to softer inflation data."
)


def article_with(content: str | None = BODY, description: str | None = None, **kw) -> Article:
    source = make_source(definition("wire"))
    availability = (
        ContentAvailability.FEED_CONTENT
        if content
        else ContentAvailability.DESCRIPTION_ONLY
        if description
        else ContentAvailability.HEADLINE_ONLY
    )
    article = make_article(
        source,
        kw.pop("title", "Chipmaker unveils processor"),
        kw.pop("url", "https://wire.example.com/a"),
        content=content,
        description=description,
        content_availability=availability,
        **kw,
    )
    db.session.refresh(article)
    return article


def usage_events() -> list[AIUsageEvent]:
    return list(db.session.scalars(select(AIUsageEvent).order_by(AIUsageEvent.created_at)))


def test_valid_output_is_validated_stored_and_tracked(app: Flask, settings: Settings) -> None:
    article = article_with()
    llm = FakeLLM([valid_output()])

    attempt = Summarizer(db.session, llm, settings).summarize(article)
    db.session.commit()

    assert attempt.status is GenerationStatus.SUCCEEDED and attempt.calls == 1
    summary = article.summary
    assert summary is not None
    assert summary.headline == "Chipmaker launches 2nm data-center processor"
    assert len(summary.bullet_points) == 3
    assert summary.key_entities == ["Example Chips Inc.", "2nm process"]
    assert summary.model_name == "fake-model-1"
    assert summary.prompt_version == PROMPT_VERSION
    assert summary.generated_at is not None
    assert summary.source_coverage is SourceCoverage.ARTICLE_TEXT
    assert summary.attempts == 1
    assert article.category is Category.TECHNOLOGY
    assert article.category_source is CategorySource.AI
    assert (article.impact_score, article.significance_score) == (7.0, 6.0)

    (event,) = usage_events()
    assert event.status is UsageStatus.SUCCESS
    assert (event.input_tokens, event.output_tokens, event.thought_tokens) == (1000, 200, 50)
    # 1000*0.30/1M + (200+50)*2.50/1M
    assert event.estimated_cost_usd == round(0.0003 + 0.000625, 6)


def test_empty_article_content_is_never_sent_to_the_model(app: Flask, settings: Settings) -> None:
    article = article_with(content=None, description=None)
    llm = FakeLLM()

    attempt = Summarizer(db.session, llm, settings).summarize(article)

    assert attempt.status is GenerationStatus.INSUFFICIENT_CONTENT
    assert llm.calls == []
    assert article.summary is not None
    assert article.summary.limitations == "The publisher's feed provides only a headline"


def test_tiny_description_counts_as_insufficient(app: Flask, settings: Settings) -> None:
    article = article_with(content=None, description="Short teaser.")
    assert source_coverage(article) is None


def test_excerpt_only_articles_are_summarized_as_excerpts(app: Flask, settings: Settings) -> None:
    article = article_with(content=None, description=EXCERPT)
    llm = FakeLLM(
        [valid_output(summary=["Stocks rose as Treasury yields fell."], limitations="Excerpt only")]
    )

    Summarizer(db.session, llm, settings).summarize(article)

    assert "ONLY a short publisher excerpt" in llm.calls[0]["prompt"]
    assert article.summary is not None
    assert article.summary.source_coverage is SourceCoverage.EXCERPT
    assert article.summary.limitations == "Excerpt only"


def test_malformed_json_is_retried_once(app: Flask, settings: Settings) -> None:
    article = article_with()
    llm = FakeLLM(['{"headline": ', valid_output()])

    attempt = Summarizer(db.session, llm, settings).summarize(article)
    db.session.commit()

    assert attempt.status is GenerationStatus.SUCCEEDED and attempt.calls == 2
    assert [e.status for e in usage_events()] == [UsageStatus.INVALID_OUTPUT, UsageStatus.SUCCESS]


def test_repeated_invalid_output_fails_the_attempt(app: Flask, settings: Settings) -> None:
    article = article_with()
    llm = FakeLLM([valid_output(summary=[]), valid_output(category="Sports")])

    attempt = Summarizer(db.session, llm, settings).summarize(article)

    assert attempt.status is GenerationStatus.FAILED
    summary = article.summary
    assert summary is not None
    assert summary.attempts == 1
    assert summary.generation_error is not None
    assert "unsupported category" in summary.generation_error
    assert article.category_source is not CategorySource.AI  # nothing invalid was applied


def test_rate_limit_propagates_without_consuming_an_attempt(app: Flask, settings: Settings) -> None:
    article = article_with()
    llm = FakeLLM([LLMRateLimitError("HTTP 429 RESOURCE_EXHAUSTED")])

    try:
        Summarizer(db.session, llm, settings).summarize(article)
        raised = False
    except LLMRateLimitError:
        raised = True
    db.session.commit()

    assert raised
    assert article.summary is None or article.summary.attempts == 0
    assert [e.status for e in usage_events()] == [UsageStatus.RATE_LIMITED]


def test_timeout_fails_the_attempt_and_is_recorded(app: Flask, settings: Settings) -> None:
    article = article_with()
    llm = FakeLLM([LLMTimeoutError("Gemini request timed out")])

    attempt = Summarizer(db.session, llm, settings).summarize(article)
    db.session.commit()

    assert attempt.status is GenerationStatus.FAILED
    assert article.summary is not None
    assert article.summary.generation_error == "timeout: Gemini request timed out"
    assert len(llm.calls) == 1  # transport-level retries happen inside the client
    assert usage_events()[0].status is UsageStatus.TIMEOUT


def test_model_reported_insufficient_information(app: Flask, settings: Settings) -> None:
    article = article_with()
    llm = FakeLLM(
        [valid_output(insufficient_information=True, summary=[], limitations="Text is a teaser")]
    )

    attempt = Summarizer(db.session, llm, settings).summarize(article)

    assert attempt.status is GenerationStatus.INSUFFICIENT_CONTENT
    assert article.summary is not None
    assert article.summary.bullet_points == []
    assert article.summary.limitations == "Text is a teaser"
    assert article.impact_score is None
