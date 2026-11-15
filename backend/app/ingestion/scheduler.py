"""Run ingestion once or on a fixed interval.

Overlap protection: every run takes a PostgreSQL session-level advisory lock. If another process
(a second worker, or a manual ``flask ingest run``) already holds it, the run is skipped, not
queued, so jobs never pile up.
"""

import logging
import signal
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from types import FrameType

from sqlalchemy import Engine, text

from app.config import Settings
from app.database import db
from app.ingestion.http import FeedFetcher, build_http_client
from app.ingestion.pipeline import IngestionService
from app.ingestion.sync import sync_sources
from app.models import IngestionRun, RunTrigger
from app.services.llm import LLMClient
from app.services.llm.gemini import GeminiClient, build_llm_http_client
from app.services.processing import ProcessingReport, ProcessingService

logger = logging.getLogger(__name__)

# Arbitrary, stable 64-bit keys identifying each job ("brief" / "summ" in ASCII). Separate locks
# let ingestion and processing run independently while each stays single-instance.
INGESTION_LOCK_KEY = 0x6272696566
PROCESSING_LOCK_KEY = 0x73756D6D


@contextmanager
def advisory_lock(engine: Engine, key: int) -> Iterator[bool]:
    """Yield True if the lock was acquired. The lock is held on a dedicated connection and
    released on exit (or automatically by PostgreSQL if the process dies)."""
    with engine.connect() as conn:
        acquired = bool(conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}).scalar())
        try:
            yield acquired
        finally:
            if acquired:
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
                conn.commit()


def run_ingestion_once(
    settings: Settings,
    *,
    trigger: RunTrigger = RunTrigger.MANUAL,
    only_slugs: Iterable[str] | None = None,
    fetcher: FeedFetcher | None = None,
) -> IngestionRun | None:
    """Execute one ingestion pass. Returns None if another run holds the lock.

    Must be called inside a Flask application context.
    """
    with advisory_lock(db.engine, INGESTION_LOCK_KEY) as acquired:
        if not acquired:
            logger.info("Another ingestion run is in progress; skipping")
            return None
        if fetcher is not None:
            return IngestionService(db.session, fetcher, settings).run(trigger, only_slugs)
        with build_http_client(settings) as client:
            fetcher = FeedFetcher.from_settings(client, settings)
            return IngestionService(db.session, fetcher, settings).run(trigger, only_slugs)


class IngestionWorker:
    """Fixed-rate loop: a run starts every ``interval`` seconds (measured start to start).
    A run that overruns the interval is followed immediately by the next one, never in parallel.
    """

    def __init__(
        self,
        run_once: Callable[[], object],
        interval_seconds: float,
        stop_event: threading.Event | None = None,
    ) -> None:
        self._run_once = run_once
        self._interval = interval_seconds
        self.stop_event = stop_event or threading.Event()

    def install_signal_handlers(self) -> None:
        def _stop(signum: int, _frame: FrameType | None) -> None:
            logger.info("Received signal %s; stopping after the current run", signum)
            self.stop_event.set()

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)

    def run_forever(self) -> None:
        logger.info("Ingestion worker started (interval %.0fs)", self._interval)
        while not self.stop_event.is_set():
            started = time.monotonic()
            try:
                self._run_once()
            except Exception:
                # Keep the worker alive (e.g. database briefly unavailable); try next tick.
                logger.exception("Ingestion run failed")
            elapsed = time.monotonic() - started
            self.stop_event.wait(max(0.0, self._interval - elapsed))
        logger.info("Ingestion worker stopped")


@contextmanager
def llm_client(settings: Settings) -> Iterator[LLMClient | None]:
    """Yield a configured LLM client, or None when no API key is set."""
    if not settings.ai_enabled:
        yield None
        return
    with build_llm_http_client(settings) as http:
        yield GeminiClient.from_settings(http, settings)


def run_processing_once(
    settings: Settings,
    *,
    llm: LLMClient | None = None,
    use_ai: bool = True,
    max_summaries: int | None = None,
) -> ProcessingReport | None:
    """Categorize, rank and summarize pending articles. None if another run holds the lock.

    Must be called inside a Flask application context.
    """
    with advisory_lock(db.engine, PROCESSING_LOCK_KEY) as acquired:
        if not acquired:
            logger.info("Another processing run is in progress; skipping")
            return None
        if not use_ai:
            return ProcessingService(
                db.session, settings, None, ai_off_reason="disabled for this run (--no-ai)"
            ).run(max_summaries=max_summaries)
        if llm is not None:
            return ProcessingService(db.session, settings, llm).run(max_summaries=max_summaries)
        with llm_client(settings) as client:
            return ProcessingService(db.session, settings, client).run(max_summaries=max_summaries)


def run_pipeline_once(settings: Settings, trigger: RunTrigger) -> None:
    """One worker tick: sync sources, ingest, then process. Processing runs even if ingestion
    was skipped or failed, so a publisher outage never blocks summaries of stored articles."""
    sync_sources(db.session)
    try:
        run_ingestion_once(settings, trigger=trigger)
    except Exception:
        logger.exception("Ingestion failed; continuing to processing")
        db.session.rollback()
    run_processing_once(settings)
