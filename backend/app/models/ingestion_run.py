from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import db
from app.models.base import UUIDPrimaryKeyMixin, string_enum, utcnow
from app.models.enums import RunStatus, RunTrigger


class IngestionRun(UUIDPrimaryKeyMixin, db.Model):  # type: ignore[name-defined]
    """Execution metrics for one ingestion pass over all active sources."""

    __tablename__ = "ingestion_runs"

    trigger: Mapped[RunTrigger] = mapped_column(string_enum(RunTrigger, "trigger"), nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        string_enum(RunStatus, "status"), nullable=False, default=RunStatus.RUNNING, index=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sources_attempted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sources_succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sources_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    articles_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    articles_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    articles_duplicate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    articles_invalid: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    articles_filtered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Per-source breakdown: {slug: {status, new, duplicate, invalid, reasons, error, ...}}
    source_results: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
