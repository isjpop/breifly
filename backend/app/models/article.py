import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import db
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, string_enum
from app.models.enums import Category, CategorySource, ContentAvailability, ProcessingStatus

if TYPE_CHECKING:
    from app.models.source import Source
    from app.models.story_cluster import StoryCluster
    from app.models.summary import Summary


class Article(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):  # type: ignore[name-defined]
    __tablename__ = "articles"
    __table_args__ = (
        CheckConstraint(
            "importance_score IS NULL OR (importance_score >= 1 AND importance_score <= 10)",
            name="importance_range",
        ),
        CheckConstraint(
            "impact_score IS NULL OR (impact_score >= 1 AND impact_score <= 10)",
            name="impact_range",
        ),
        CheckConstraint(
            "significance_score IS NULL OR (significance_score >= 1 AND significance_score <= 10)",
            name="significance_range",
        ),
        Index("ix_articles_source_guid", "source_id", "guid"),
        Index("ix_articles_category_published", "category", "published_at"),
        Index("ix_articles_importance_published", "importance_score", "published_at"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    story_cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("story_clusters.id", ondelete="SET NULL"), index=True
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
    normalized_url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    guid: Mapped[str | None] = mapped_column(String(1024))
    author: Mapped[str | None] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    content_availability: Mapped[ContentAvailability] = mapped_column(
        string_enum(ContentAvailability, "content_availability"), nullable=False
    )
    image_url: Mapped[str | None] = mapped_column(String(2048))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    category: Mapped[Category | None] = mapped_column(string_enum(Category, "category"))
    category_source: Mapped[CategorySource | None] = mapped_column(
        string_enum(CategorySource, "category_source")
    )
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # Ranking inputs assessed by the model (1-10); null until a summary succeeds.
    impact_score: Mapped[float | None] = mapped_column(Float)
    significance_score: Mapped[float | None] = mapped_column(Float)
    # Weighted score (1-10), recomputed by the processing stage as articles age.
    importance_score: Mapped[float | None] = mapped_column(Float)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)

    processing_status: Mapped[ProcessingStatus] = mapped_column(
        string_enum(ProcessingStatus, "processing_status"),
        nullable=False,
        default=ProcessingStatus.PENDING,
        index=True,
    )
    processing_error: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    source: Mapped["Source"] = relationship(back_populates="articles")
    story_cluster: Mapped["StoryCluster | None"] = relationship(back_populates="articles")
    summary: Mapped["Summary | None"] = relationship(
        back_populates="article", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Article {self.id} {self.title[:40]!r}>"
