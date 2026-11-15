import threading

import httpx
from flask import Flask
from sqlalchemy import text

from app.config import Settings
from app.database import db
from app.ingestion.http import FeedFetcher
from app.ingestion.scheduler import (
    INGESTION_LOCK_KEY,
    IngestionWorker,
    advisory_lock,
    run_ingestion_once,
)
from tests.feeds import mock_transport


def test_advisory_lock_is_exclusive_and_released(app: Flask) -> None:
    with advisory_lock(db.engine, INGESTION_LOCK_KEY) as first:
        assert first
        with advisory_lock(db.engine, INGESTION_LOCK_KEY) as second:
            assert not second
    with advisory_lock(db.engine, INGESTION_LOCK_KEY) as again:
        assert again


def test_run_is_skipped_while_another_holds_the_lock(app: Flask, settings: Settings) -> None:
    fetcher = FeedFetcher(httpx.Client(transport=mock_transport({})), sleep=lambda _s: None)
    with db.engine.connect() as other:
        other.execute(text("SELECT pg_advisory_lock(:k)"), {"k": INGESTION_LOCK_KEY})
        assert run_ingestion_once(settings, fetcher=fetcher) is None
        other.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": INGESTION_LOCK_KEY})
    assert run_ingestion_once(settings, fetcher=fetcher) is not None


def test_worker_runs_repeatedly_survives_errors_and_stops() -> None:
    stop = threading.Event()
    calls: list[int] = []

    def tick() -> None:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("transient failure")
        if len(calls) == 3:
            stop.set()

    IngestionWorker(tick, interval_seconds=0, stop_event=stop).run_forever()
    assert len(calls) == 3
