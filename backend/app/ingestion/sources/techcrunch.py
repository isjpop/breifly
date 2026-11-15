from app.ingestion.sources.base import SourceDefinition
from app.models.enums import Category

TECHCRUNCH = SourceDefinition(
    slug="techcrunch",
    name="TechCrunch",
    homepage_url="https://techcrunch.com",
    feed_url="https://techcrunch.com/feed/",
    default_category=Category.TECHNOLOGY,
    credibility_weight=0.8,
    notes="Official RSS. Headline, author and a short excerpt.",
)
