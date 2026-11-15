from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import db
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, string_enum
from app.models.enums import Category, FetchStatus, SourceType

if TYPE_CHECKING:
    from app.models.article import Article


class Source(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):  # type: ignore[name-defined]
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint(
            "credibility_weight >= 0 AND credibility_weight <= 1", name="credibility_range"
        ),
    )

    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    homepage_url: Mapped[str | None] = mapped_column(String(512))
    feed_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(
        string_enum(SourceType, "source_type"), nullable=False, default=SourceType.RSS
    )
    default_category: Mapped[Category] = mapped_column(
        string_enum(Category, "default_category"), nullable=False
    )
    credibility_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Fetch tracking
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_fetch_status: Mapped[FetchStatus | None] = mapped_column(
        string_enum(FetchStatus, "last_fetch_status")
    )
    last_fetch_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # HTTP conditional-request validators, so unchanged feeds are not re-downloaded.
    http_etag: Mapped[str | None] = mapped_column(String(512))
    http_last_modified: Mapped[str | None] = mapped_column(String(128))

    articles: Mapped[list["Article"]] = relationship(back_populates="source")

    def __repr__(self) -> str:
        return f"<Source {self.slug}>"
