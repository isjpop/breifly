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

logger = logging.getLogger(__name__)

# Arbitrary, stable 64-bit key identifying the ingestion job ("brief" in ASCII).
INGESTION_LOCK_KEY = 0x6272696566


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


def sync_and_run(settings: Settings, trigger: RunTrigger) -> IngestionRun | None:
    sync_sources(db.session)
    return run_ingestion_once(settings, trigger=trigger)
