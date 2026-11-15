"""Generate, validate and store one article's AI summary.

Policy on thin content (never summarize from a headline alone):
- headline only, or under ``MIN_SUMMARIZABLE_CHARS`` of text: no API call, status
  ``insufficient_content``
- publisher excerpt only: 1-3 takeaways, marked ``source_coverage = excerpt``
- article body text: 3-5 takeaways, ``source_coverage = article_text``
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from app.config import Settings
from app.database import DbSession
from app.models import (
    AIUsageEvent,
    Article,
    CategorySource,
    ContentAvailability,
    GenerationStatus,
    SourceCoverage,
    Summary,
    UsageStatus,
)
from app.models.base import utcnow
from app.schemas.summary import (
    SUMMARY_JSON_SCHEMA,
    InvalidSummaryOutput,
    SummaryOutput,
    parse_summary_output,
)
from app.services.llm import (
    LLMClient,
    LLMConfigurationError,
    LLMError,
    LLMRateLimitError,
    LLMResponseError,
    LLMResult,
    LLMTimeoutError,
    TokenUsage,
)
from app.services.prompts import PROMPT_VERSION, SYSTEM_INSTRUCTION, build_summary_prompt

logger = logging.getLogger(__name__)

MIN_SUMMARIZABLE_CHARS = 100
# One extra call when the model's reply fails validation; then give up for this attempt.
MAX_CALLS_PER_ATTEMPT = 2
MAX_ERROR_LENGTH = 300


def source_coverage(article: Article) -> SourceCoverage | None:
    """What a summary would be based on, or None if there is too little to summarize."""
    content = article.content or ""
    has_body = article.content_availability is ContentAvailability.FEED_CONTENT
    if has_body and len(content) >= MIN_SUMMARIZABLE_CHARS:
        return SourceCoverage.ARTICLE_TEXT
    description = article.description or ""
    if len(description) >= MIN_SUMMARIZABLE_CHARS:
        return SourceCoverage.EXCERPT
    return None


@dataclass(frozen=True)
class SummaryAttempt:
    status: GenerationStatus
    calls: int = 0


class Summarizer:
    def __init__(
        self,
        session: DbSession,
        llm: LLMClient | None,
        settings: Settings,
        *,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._session = session
        self._llm = llm
        self._settings = settings
        self._clock = clock

    @property
    def ai_available(self) -> bool:
        return self._llm is not None

    def _summary_for(self, article: Article) -> Summary:
        if article.summary is None:
            article.summary = Summary(article_id=article.id)
        return article.summary

    def mark_insufficient(self, article: Article) -> None:
        summary = self._summary_for(article)
        summary.generation_status = GenerationStatus.INSUFFICIENT_CONTENT
        summary.generation_error = None
        summary.limitations = (
            "The publisher's feed provides only a headline"
            if article.content_availability is ContentAvailability.HEADLINE_ONLY
            else "The publisher's feed provides too little text to summarize"
        )
        summary.bullet_points = []
        summary.source_coverage = None

    def summarize(self, article: Article) -> SummaryAttempt:
        """Summarize one article. Raises ``LLMRateLimitError`` / ``LLMConfigurationError`` so
        the caller can stop the run; other provider failures are recorded on the summary."""
        coverage = source_coverage(article)
        if coverage is None:
            self.mark_insufficient(article)
            return SummaryAttempt(GenerationStatus.INSUFFICIENT_CONTENT)
        if self._llm is None:
            raise LLMConfigurationError("AI summarization is not configured")

        prompt = build_summary_prompt(
            publisher=article.source.name,
            title=article.title,
            author=article.author,
            published_at=article.published_at,
            description=article.description,
            text=article.content if coverage is SourceCoverage.ARTICLE_TEXT else None,
            coverage=coverage,
            max_chars=self._settings.llm_max_input_chars,
        )

        summary = self._summary_for(article)
        error: str | None = None
        calls = 0
        while calls < MAX_CALLS_PER_ATTEMPT:
            calls += 1
            try:
                result = self._llm.generate_json(
                    system_instruction=SYSTEM_INSTRUCTION,
                    prompt=prompt,
                    schema=SUMMARY_JSON_SCHEMA,
                    max_output_tokens=self._settings.llm_max_output_tokens,
                )
            except (LLMRateLimitError, LLMConfigurationError) as exc:
                # Not the article's fault: record usage, leave the attempt count alone.
                self._record_usage(article, None, exc)
                raise
            except LLMResponseError as exc:
                self._record_usage(article, None, exc)
                error = f"{exc.code}: {exc}"
                continue
            except LLMError as exc:  # timeout / unavailable: count the attempt, move on
                self._record_usage(article, None, exc)
                error = f"{exc.code}: {exc}"
                break

            try:
                output = parse_summary_output(result.text, coverage)
            except InvalidSummaryOutput as exc:
                self._record_usage(article, result, status=UsageStatus.INVALID_OUTPUT)
                error = f"invalid_output: {exc}"
                logger.warning("Invalid summary output for article %s: %s", article.id, exc)
                continue

            self._record_usage(article, result, status=UsageStatus.SUCCESS)
            self._apply(article, summary, output, coverage, result.model)
            self._finish_attempt(summary)
            return SummaryAttempt(summary.generation_status, calls)

        summary.generation_status = GenerationStatus.FAILED
        summary.generation_error = (error or "unknown error")[:MAX_ERROR_LENGTH]
        self._finish_attempt(summary)
        return SummaryAttempt(GenerationStatus.FAILED, calls)

    def _finish_attempt(self, summary: Summary) -> None:
        summary.attempts = (summary.attempts or 0) + 1
        summary.last_attempt_at = self._clock()

    def _apply(
        self,
        article: Article,
        summary: Summary,
        output: SummaryOutput,
        coverage: SourceCoverage,
        model: str,
    ) -> None:
        summary.model_name = model
        summary.prompt_version = PROMPT_VERSION
        summary.generated_at = self._clock()
        summary.generation_error = None
        summary.limitations = output.limitations or None
        if output.insufficient_information:
            summary.generation_status = GenerationStatus.INSUFFICIENT_CONTENT
            summary.bullet_points = []
            summary.headline = None
            summary.why_it_matters = None
            summary.key_entities = []
            summary.source_coverage = coverage
            return
        summary.generation_status = GenerationStatus.SUCCEEDED
        summary.headline = output.headline
        summary.bullet_points = list(output.summary)
        summary.why_it_matters = output.why_it_matters
        summary.key_entities = list(output.key_entities)
        summary.source_coverage = coverage
        article.category = output.category
        article.category_source = CategorySource.AI
        article.impact_score = float(output.impact_score)
        article.significance_score = float(output.significance_score)

    def _record_usage(
        self,
        article: Article,
        result: LLMResult | None,
        error: LLMError | None = None,
        *,
        status: UsageStatus | None = None,
    ) -> None:
        usage = result.usage if result else (error.usage if error else TokenUsage())
        if status is None:
            status = (
                UsageStatus.RATE_LIMITED
                if isinstance(error, LLMRateLimitError)
                else UsageStatus.TIMEOUT
                if isinstance(error, LLMTimeoutError)
                else UsageStatus.ERROR
            )
        llm = self._llm
        self._session.add(
            AIUsageEvent(
                article_id=article.id,
                operation="summarize",
                provider=llm.provider if llm else "none",
                model_name=result.model if result else (llm.model if llm else "none"),
                status=status,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                thought_tokens=usage.thought_tokens,
                estimated_cost_usd=self.estimate_cost(usage),
                latency_ms=result.latency_ms if result else (error.latency_ms if error else 0),
                error_code=error.code if error else None,
            )
        )

    def estimate_cost(self, usage: TokenUsage) -> float:
        s = self._settings
        billed_output = usage.output_tokens + usage.thought_tokens
        return round(
            (
                usage.input_tokens * s.llm_input_cost_per_million
                + billed_output * s.llm_output_cost_per_million
            )
            / 1_000_000,
            6,
        )
