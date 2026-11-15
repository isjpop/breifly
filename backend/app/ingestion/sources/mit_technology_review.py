from app.ingestion.sources.base import SourceDefinition
from app.models.enums import Category

MIT_TECHNOLOGY_REVIEW = SourceDefinition(
    slug="mit-technology-review",
    name="MIT Technology Review",
    homepage_url="https://www.technologyreview.com",
    feed_url="https://www.technologyreview.com/feed/",
    default_category=Category.TECHNOLOGY,
    credibility_weight=0.9,
    notes="Official RSS. Includes article body text.",
)
