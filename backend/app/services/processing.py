"""Article processing stage: categorize → rank → summarize → re-rank.

Runs after ingestion in the worker, or on its own (``flask process run``). It never calls the
LLM for content that is too thin, spends at most ``llm_max_summaries_per_run`` calls per run on
the most important articles first, and stops calling the provider for the rest of the run on a
rate limit, a configuration error, or repeated outages. Everything except summarization keeps
working when the AI provider is unavailable.
"""

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload

from app.config import Settings
from app.database import DbSession
from app.models import (
    Article,
    CategorySource,
    GenerationStatus,
    ProcessingStatus,
    Source,
    Summary,
)
from app.models.base import utcnow
from app.services.categorizer import categorize
from app.services.llm import LLMClient, LLMConfigurationError, LLMRateLimitError
from app.services.ranking import RankingWeights, importance_score
from app.services.summarizer import Summarizer, source_coverage

logger = logging.getLogger(__name__)

# Consecutive transient provider failures (timeouts, 5xx) before pausing summarization.
MAX_CONSECUTIVE_PROVIDER_FAILURES = 3
TERMINAL_SUMMARY_STATUSES = (GenerationStatus.SUCCEEDED, GenerationStatus.INSUFFICIENT_CONTENT)


@dataclass
class ProcessingReport:
    categorized: int = 0
    ranked: int = 0
    summarized: int = 0
    insufficient: int = 0
    failed: int = 0
    llm_calls: int = 0
    deferred: int = 0  # eligible but not attempted this run (budget, AI off, stopped)
    errors: int = 0
    stopped_reason: str | None = None
    notes: list[str] = field(default_factory=list)


class ArticleNotFound(Exception):
    pass


class ProcessingService:
    def __init__(
        self,
        session: DbSession,
        settings: Settings,
        llm: LLMClient | None,
        *,
        clock: Callable[[], datetime] = utcnow,
        ai_off_reason: str = "GEMINI_API_KEY is not set",
    ) -> None:
        self._session = session
        self._settings = settings
        self._ai_off_reason = ai_off_reason
        self._clock = clock
        self._weights = RankingWeights.from_settings(settings)
        self.summarizer = Summarizer(session, llm, settings, clock=clock)

    # ----------------------------------------------------------------- run

    def run(self, *, max_summaries: int | None = None) -> ProcessingReport:
        report = ProcessingReport()
        budget = (
            self._settings.llm_max_summaries_per_run if max_summaries is None else max_summaries
        )
        self._categorize_uncategorized(report)
        self._rank_recent(report)
        self._summarize_pending(report, budget)
        self._rank_recent(report)  # fold in fresh AI impact/significance scores
        logger.info(
            "Processing: %d categorized, %d summarized, %d insufficient, %d failed, "
            "%d deferred, %d LLM calls%s",
            report.categorized,
            report.summarized,
            report.insufficient,
            report.failed,
            report.deferred,
            report.llm_calls,
            f" (stopped: {report.stopped_reason})" if report.stopped_reason else "",
        )
        return report

    def _window_start(self) -> datetime:
        return self._clock() - timedelta(hours=self._settings.ranking_refresh_window_hours)

    def _categorize_uncategorized(self, report: ProcessingReport) -> None:
        rows = self._session.execute(
            select(Article, Source.default_category)
            .join(Source)
            .where(Article.category.is_(None))
            .limit(self._settings.processing_batch_size)
        ).all()
        for article, default in rows:
            article.category = categorize(
                title=article.title, description=article.description, tags=article.tags,
                default=default,
            )  # fmt: skip
            article.category_source = CategorySource.RULES
            report.categorized += 1
        self._session.commit()

    def _rank_recent(self, report: ProcessingReport) -> None:
        now = self._clock()
        rows = self._session.execute(
            select(Article, Source.credibility_weight)
            .join(Source)
            .where(Article.created_at >= self._window_start())
        ).all()
        for article, credibility in rows:
            self._rank(article, credibility, now)
        report.ranked = len(rows)
        self._session.commit()

    def _rank(self, article: Article, credibility: float, now: datetime) -> None:
        article.importance_score = importance_score(
            impact=article.impact_score,
            significance=article.significance_score,
            credibility_weight=credibility,
            published_at=article.published_at or article.created_at,
            now=now,
            weights=self._weights,
        )

    def _candidates(self) -> list[Article]:
        """Articles still needing a summary, most important first."""
        query = (
            select(Article)
            .outerjoin(Summary)
            .options(joinedload(Article.source), joinedload(Article.summary))
            .where(Article.created_at >= self._window_start())
            .where(
                or_(
                    Summary.id.is_(None),
                    Summary.generation_status == GenerationStatus.PENDING,
                    (Summary.generation_status == GenerationStatus.FAILED)
                    & (Summary.attempts < self._settings.summary_max_attempts),
                )
            )
            .where(Article.processing_status != ProcessingStatus.FAILED)
            .order_by(Article.importance_score.desc().nulls_last(), Article.created_at.desc())
            .limit(self._settings.processing_batch_size)
        )
        return list(self._session.scalars(query).unique())

    def _summarize_pending(self, report: ProcessingReport, budget: int) -> None:
        if not self.summarizer.ai_available:
            report.notes.append(f"AI summarization off: {self._ai_off_reason}")
        consecutive_failures = 0
        stopped = False

        for article in self._candidates():
            article_id = article.id
            needs_llm = source_coverage(article) is not None
            if needs_llm and (stopped or not self.summarizer.ai_available or budget <= 0):
                report.deferred += 1
                continue
            try:
                attempt = self.summarizer.summarize(article)
            except LLMRateLimitError:
                self._session.commit()  # keep the usage record
                report.stopped_reason = "provider rate limit reached"
                report.deferred += 1
                stopped = True
                continue
            except LLMConfigurationError as exc:
                self._session.commit()
                report.stopped_reason = f"provider configuration error: {exc}"
                report.deferred += 1
                stopped = True
                continue
            except Exception:
                self._session.rollback()
                logger.exception("Unexpected error processing article %s", article_id)
                self._mark_failed(article_id, "internal error during summarization")
                report.errors += 1
                continue

            report.llm_calls += attempt.calls
            if attempt.calls:
                budget -= 1
            if attempt.status is GenerationStatus.SUCCEEDED:
                report.summarized += 1
                consecutive_failures = 0
            elif attempt.status is GenerationStatus.INSUFFICIENT_CONTENT:
                report.insufficient += 1
            else:
                report.failed += 1
                consecutive_failures += 1
            self._update_processing_status(article)
            self._session.commit()

            if consecutive_failures >= MAX_CONSECUTIVE_PROVIDER_FAILURES and not stopped:
                report.stopped_reason = "repeated provider failures"
                stopped = True

    def _update_processing_status(self, article: Article) -> None:
        summary = article.summary
        done = summary is not None and (
            summary.generation_status in TERMINAL_SUMMARY_STATUSES
            or summary.attempts >= self._settings.summary_max_attempts
        )
        article.processing_status = ProcessingStatus.PROCESSED if done else ProcessingStatus.PENDING
        article.processing_error = None

    def _mark_failed(self, article_id: uuid.UUID, message: str) -> None:
        article = self._session.get(Article, article_id)
        if article is not None:
            article.processing_status = ProcessingStatus.FAILED
            article.processing_error = message
            self._session.commit()

    # ------------------------------------------------------------ regenerate

    def regenerate(self, article_id: uuid.UUID) -> GenerationStatus:
        """Force a fresh summary regardless of previous attempts and return the attempt's
        outcome. A failed attempt keeps any previously valid summary. Raises
        ``ArticleNotFound``, ``LLMRateLimitError`` or ``LLMConfigurationError``."""
        article = self._session.scalars(
            select(Article)
            .options(joinedload(Article.source), joinedload(Article.summary))
            .where(Article.id == article_id)
        ).first()
        if article is None:
            raise ArticleNotFound(str(article_id))
        if article.category is None:
            article.category = categorize(
                title=article.title, description=article.description, tags=article.tags,
                default=article.source.default_category,
            )  # fmt: skip
            article.category_source = CategorySource.RULES
        try:
            attempt = self.summarizer.summarize(article, operation="regenerate")
        except (LLMRateLimitError, LLMConfigurationError):
            self._session.commit()
            raise
        self._rank(article, article.source.credibility_weight, self._clock())
        self._update_processing_status(article)
        self._session.commit()
        return attempt.status
