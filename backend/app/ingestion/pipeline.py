"""Ingestion orchestration: fetch → parse → normalize → deduplicate → store.

Each source is processed in its own transaction. A failure in one publisher is recorded on that
source and in the run metrics, and never prevents the remaining publishers from being processed.
"""

import logging
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import feedparser
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.config import Settings
from app.database import DbSession
from app.ingestion.deduplicator import Deduplicator, Verdict
from app.ingestion.http import FeedFetcher, FeedFetchError
from app.ingestion.normalizer import EntryRejected, NormalizedArticle, normalize_entry
from app.ingestion.sources import SOURCE_DEFINITIONS, FeedEntry, SourceDefinition
from app.models import (
    Article,
    FetchStatus,
    IngestionRun,
    ProcessingStatus,
    RunStatus,
    RunTrigger,
    Source,
    StoryCluster,
)
from app.models.base import utcnow

logger = logging.getLogger(__name__)

MAX_ERROR_LENGTH = 500


class FeedParseError(Exception):
    pass


class MissingIntegrationError(Exception):
    """A source row exists in the database but no integration is registered for its slug."""


@dataclass
class SourceResult:
    slug: str
    status: FetchStatus = FetchStatus.SUCCESS
    seen: int = 0
    new: int = 0
    duplicate: int = 0
    related: int = 0
    invalid: int = 0
    filtered: int = 0
    rejections: Counter[str] = field(default_factory=Counter)
    error: str | None = None
    duration_ms: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "seen": self.seen,
            "new": self.new,
            "duplicate": self.duplicate,
            "related": self.related,
            "invalid": self.invalid,
            "filtered": self.filtered,
            "rejections": dict(self.rejections),
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


def parse_feed(body: bytes) -> list[FeedEntry]:
    """Parse RSS/Atom bytes. Raise ``FeedParseError`` when the body is not a usable feed."""
    parsed = feedparser.parse(body)
    if not parsed.get("version") and not parsed.entries:
        detail = parsed.get("bozo_exception")
        kind = type(detail).__name__ if detail else "unknown format"
        raise FeedParseError(f"response is not a valid RSS/Atom feed ({kind})")
    return list(parsed.entries)


class IngestionService:
    def __init__(
        self,
        session: DbSession,
        fetcher: FeedFetcher,
        settings: Settings,
        *,
        definitions: Mapping[str, SourceDefinition] = SOURCE_DEFINITIONS,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._session = session
        self._fetcher = fetcher
        self._settings = settings
        self._definitions = definitions
        self._clock = clock

    # ----------------------------------------------------------------- run

    def run(
        self, trigger: RunTrigger = RunTrigger.MANUAL, only_slugs: Iterable[str] | None = None
    ) -> IngestionRun:
        session = self._session
        run = IngestionRun(trigger=trigger, status=RunStatus.RUNNING, started_at=self._clock())
        session.add(run)
        session.commit()

        try:
            sources = self._active_sources(only_slugs)
            dedup = Deduplicator.for_run(
                session, self._clock() - timedelta(hours=self._settings.dedup_lookback_hours)
            )
            results = [self._ingest_source_safely(source, dedup) for source in sources]
            self._finalize(run, results)
        except SQLAlchemyError as exc:
            # The database itself failed (not a single publisher): record and re-raise.
            session.rollback()
            logger.exception("Ingestion run %s aborted by a database error", run.id)
            run.status = RunStatus.FAILED
            run.error = f"database error: {type(exc).__name__}"
            run.finished_at = self._clock()
            session.commit()
            raise
        return run

    def _active_sources(self, only_slugs: Iterable[str] | None) -> list[Source]:
        query = select(Source).where(Source.is_active.is_(True)).order_by(Source.name)
        if only_slugs is not None:
            query = query.where(Source.slug.in_(list(only_slugs)))
        return list(self._session.scalars(query))

    def _finalize(self, run: IngestionRun, results: list[SourceResult]) -> None:
        failed = [r for r in results if r.status is FetchStatus.FAILED]
        run.sources_attempted = len(results)
        run.sources_failed = len(failed)
        run.sources_succeeded = len(results) - len(failed)
        run.articles_seen = sum(r.seen for r in results)
        run.articles_new = sum(r.new for r in results)
        run.articles_duplicate = sum(r.duplicate for r in results)
        run.articles_invalid = sum(r.invalid for r in results)
        run.articles_filtered = sum(r.filtered for r in results)
        run.source_results = {r.slug: r.as_dict() for r in results}
        if not failed:
            run.status = RunStatus.SUCCEEDED
        elif len(failed) == len(results):
            run.status = RunStatus.FAILED
        else:
            run.status = RunStatus.PARTIAL
        run.finished_at = self._clock()
        self._session.commit()
        logger.info(
            "Ingestion run %s %s: %d/%d sources ok, %d new, %d duplicate, %d invalid",
            run.id,
            run.status.value,
            run.sources_succeeded,
            run.sources_attempted,
            run.articles_new,
            run.articles_duplicate,
            run.articles_invalid,
        )

    # -------------------------------------------------------------- source

    def _ingest_source_safely(self, source: Source, dedup: Deduplicator) -> SourceResult:
        started = time.monotonic()
        slug = source.slug  # read before any rollback expires the instance
        source_id = source.id
        try:
            result = self.ingest_source(source, dedup)
        except (FeedFetchError, FeedParseError, MissingIntegrationError) as exc:
            result = self._record_failure(source_id, slug, str(exc), dedup)
        except SQLAlchemyError:
            raise
        except Exception as exc:  # unexpected bug in one adapter must not stop the run
            logger.exception("Unexpected error ingesting %s", slug)
            result = self._record_failure(
                source_id, slug, f"internal error: {type(exc).__name__}", dedup
            )
        result.duration_ms = int((time.monotonic() - started) * 1000)
        return result

    def _record_failure(
        self, source_id: Any, slug: str, message: str, dedup: Deduplicator
    ) -> SourceResult:
        self._session.rollback()
        dedup.rollback()
        message = message[:MAX_ERROR_LENGTH]
        logger.warning("Ingestion failed for %s: %s", slug, message)
        source = self._session.get(Source, source_id)
        if source is not None:
            now = self._clock()
            source.last_fetched_at = now
            source.last_fetch_status = FetchStatus.FAILED
            source.last_fetch_error = message
            source.consecutive_failures = (source.consecutive_failures or 0) + 1
            self._session.commit()
        return SourceResult(slug=slug, status=FetchStatus.FAILED, error=message)

    def ingest_source(self, source: Source, dedup: Deduplicator) -> SourceResult:
        definition = self._definitions.get(source.slug)
        if definition is None:
            raise MissingIntegrationError(f"no integration registered for source '{source.slug}'")

        result = SourceResult(slug=source.slug)
        fetched = self._fetcher.fetch(
            source.feed_url, etag=source.http_etag, last_modified=source.http_last_modified
        )

        if fetched.not_modified:
            result.status = FetchStatus.NOT_MODIFIED
        else:
            entries = parse_feed(fetched.body or b"")
            candidates = self._normalize(entries, definition, result)
            dedup.prefetch(source.id, candidates)
            for candidate in candidates:
                self._store(source, candidate, dedup, result)

        now = self._clock()
        source.last_fetched_at = now
        source.last_successful_fetch_at = now
        source.last_fetch_status = result.status
        source.last_fetch_error = None
        source.consecutive_failures = 0
        source.http_etag = fetched.etag
        source.http_last_modified = fetched.last_modified
        self._session.commit()
        dedup.commit()
        logger.info(
            "%s: %s, %d seen, %d new, %d duplicate, %d related, %d invalid, %d filtered",
            source.slug,
            result.status.value,
            result.seen,
            result.new,
            result.duplicate,
            result.related,
            result.invalid,
            result.filtered,
        )
        return result

    def _normalize(
        self, entries: list[FeedEntry], definition: SourceDefinition, result: SourceResult
    ) -> list[NormalizedArticle]:
        now = self._clock()
        candidates: list[NormalizedArticle] = []
        for entry in entries[: self._settings.feed_max_entries]:
            result.seen += 1
            if not definition.include_entry(entry):
                result.filtered += 1
                continue
            try:
                candidates.append(normalize_entry(entry, definition, now=now))
            except EntryRejected as exc:
                result.invalid += 1
                result.rejections[exc.reason.value] += 1
        return candidates

    def _store(
        self,
        source: Source,
        candidate: NormalizedArticle,
        dedup: Deduplicator,
        result: SourceResult,
    ) -> None:
        decision = dedup.check(source.id, candidate)
        if decision.verdict is Verdict.DUPLICATE:
            result.duplicate += 1
            return

        extra: dict[str, Any] = {}
        if candidate.date_issue:
            extra["date_issue"] = candidate.date_issue
        article = Article(
            source_id=source.id,
            title=candidate.title,
            url=candidate.url,
            normalized_url=candidate.normalized_url,
            guid=candidate.guid,
            author=candidate.author,
            description=candidate.description,
            content=candidate.content,
            content_availability=candidate.content_availability,
            image_url=candidate.image_url,
            published_at=candidate.published_at,
            tags=candidate.tags,
            content_hash=candidate.content_hash,
            processing_status=ProcessingStatus.PENDING,
            extra=extra,
        )

        try:
            with self._session.begin_nested():
                self._session.add(article)
                self._session.flush()
        except IntegrityError:
            # Unique normalized_url hit (e.g. a concurrent writer): it's a duplicate.
            result.duplicate += 1
            return

        if decision.verdict is Verdict.RELATED and decision.matched_article_id is not None:
            self._link_related(
                article, decision.matched_article_id, decision.matched_cluster_id, dedup
            )
            result.related += 1

        dedup.register(article)
        result.new += 1

    def _link_related(
        self,
        article: Article,
        matched_id: Any,
        matched_cluster_id: Any,
        dedup: Deduplicator,
    ) -> None:
        cluster_id = matched_cluster_id
        if cluster_id is None:
            cluster = StoryCluster()
            self._session.add(cluster)
            self._session.flush()
            cluster_id = cluster.id
            self._session.execute(
                update(Article).where(Article.id == matched_id).values(story_cluster_id=cluster_id)
            )
            dedup.assign_cluster(matched_id, cluster_id)
        article.story_cluster_id = cluster_id
        self._session.flush()
