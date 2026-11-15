from typing import TYPE_CHECKING

from sqlalchemy.orm import Mapped, relationship

from app.database import db
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.article import Article


class StoryCluster(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):  # type: ignore[name-defined]
    """Groups separate articles from different publishers that cover the same event.

    Membership is assigned conservatively at ingestion (headline overlap across sources).
    Future work attaches a consolidated, multi-source summary to the cluster.
    """

    __tablename__ = "story_clusters"

    articles: Mapped[list["Article"]] = relationship(back_populates="story_cluster")
