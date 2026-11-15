from app.ingestion.sources.base import SourceDefinition
from app.models.enums import Category

THE_VERGE = SourceDefinition(
    slug="the-verge",
    name="The Verge",
    homepage_url="https://www.theverge.com",
    feed_url="https://www.theverge.com/rss/index.xml",
    default_category=Category.TECHNOLOGY,
    credibility_weight=0.8,
    notes="Official Atom feed. Includes partial article body.",
)
