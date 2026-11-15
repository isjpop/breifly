from app.ingestion.sources.base import SourceDefinition
from app.models.enums import Category

ARS_TECHNICA = SourceDefinition(
    slug="ars-technica",
    name="Ars Technica",
    homepage_url="https://arstechnica.com",
    feed_url="https://feeds.arstechnica.com/arstechnica/index",
    default_category=Category.TECHNOLOGY,
    credibility_weight=0.85,
    notes="Official RSS. Partial article body and media thumbnails.",
)
