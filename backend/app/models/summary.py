import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import db
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, string_enum
from app.models.enums import GenerationStatus, SourceCoverage

if TYPE_CHECKING:
    from app.models.article import Article


class Summary(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):  # type: ignore[name-defined]
    """The current AI summary of an article. Regeneration replaces it in place."""

    __tablename__ = "summaries"

    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    headline: Mapped[str | None] = mapped_column(String(500))
    bullet_points: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    why_it_matters: Mapped[str | None] = mapped_column(Text)
    key_entities: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    model_name: Mapped[str | None] = mapped_column(String(100))
    generation_status: Mapped[GenerationStatus] = mapped_column(
        string_enum(GenerationStatus, "generation_status"),
        nullable=False,
        default=GenerationStatus.PENDING,
    )
    generation_error: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source_coverage: Mapped[SourceCoverage | None] = mapped_column(
        string_enum(SourceCoverage, "source_coverage")
    )
    # Model-reported caveat about the source material (e.g. "based on a short excerpt").
    limitations: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    article: Mapped["Article"] = relationship(back_populates="summary")
