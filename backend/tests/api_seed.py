"""A small, fully-specified dataset for API tests."""

from dataclasses import dataclass
from datetime import timedelta

from app.database import db
from app.models import (
    Article,
    Category,
    ContentAvailability,
    GenerationStatus,
    IngestionRun,
    RunStatus,
    RunTrigger,
    Source,
    SourceCoverage,
    StoryCluster,
    Summary,
)
from app.models.base import utcnow
from tests.factories import definition, make_article, make_source

# Neutral filler so every seeded article has enough text to be summarizable.
BODY = "Officials described the details in a statement on Monday. " * 3


@dataclass
class Seed:
    wire: Source
    tech: Source
    fed: Article  # finance, top importance, clustered with fed_tech
    fed_tech: Article  # technology source, same story as fed
    chip: Article  # technology, summarized with entities
    old: Article  # 5 days old
    unsafe: Article  # javascript: url, pending summary


def seed() -> Seed:
    now = utcnow()
    wire = make_source(definition("wire", name="Global Wire", default_category=Category.FINANCE))
    tech = make_source(definition("techdesk", name="Tech Desk", credibility_weight=0.7))
    cluster = StoryCluster()
    db.session.add(cluster)
    db.session.commit()

    def article(source: Source, title: str, slug: str, **kw: object) -> Article:
        kw.setdefault("content", f"{title}. " + BODY)
        return make_article(
            source,
            title,
            f"https://{source.slug}.example.com/{slug}",
            content_availability=ContentAvailability.FEED_CONTENT,
            **kw,
        )

    fed = article(
        wire, "Federal Reserve cuts interest rates by half a point", "fed",
        category=Category.FINANCE, importance_score=9.1, published_at=now - timedelta(hours=2),
        description="The central bank lowered rates.", story_cluster_id=cluster.id,
    )  # fmt: skip
    fed_tech = article(
        tech, "Fed rate cut lifts tech stocks", "fed-tech",
        category=Category.TECHNOLOGY, importance_score=8.0, published_at=now - timedelta(hours=1),
        story_cluster_id=cluster.id,
    )  # fmt: skip
    chip = article(
        tech, "New processor doubles battery life", "chip",
        category=Category.TECHNOLOGY, importance_score=6.5, published_at=now - timedelta(hours=3),
        image_url="https://cdn.example.com/chip.jpg",
    )  # fmt: skip
    old = article(
        wire, "Quarterly earnings beat expectations", "old",
        category=Category.BUSINESS, importance_score=7.0, published_at=now - timedelta(days=5),
    )  # fmt: skip
    unsafe = article(
        wire, "Telescope spots distant galaxy", "unsafe",
        category=Category.SCIENCE, importance_score=5.0, published_at=now - timedelta(hours=4),
        image_url="javascript:alert(1)",
    )  # fmt: skip
    unsafe.url = "javascript:alert(1)"  # bypass ingestion validation to prove output re-checks

    db.session.add_all(
        [
            Summary(
                article_id=chip.id,
                generation_status=GenerationStatus.SUCCEEDED,
                headline="Chipmaker's new processor doubles battery life",
                bullet_points=["Point one.", "Point two.", "Point three.", "Point four."],
                why_it_matters="Longer battery life for laptops.",
                key_entities=["Acme Semiconductor", "Model X1"],
                source_coverage=SourceCoverage.ARTICLE_TEXT,
                model_name="fake-model-1",
                generated_at=now,
                attempts=1,
            ),
            Summary(article_id=unsafe.id, generation_status=GenerationStatus.PENDING),
            IngestionRun(
                trigger=RunTrigger.SCHEDULER,
                status=RunStatus.SUCCEEDED,
                started_at=now - timedelta(minutes=10),
                finished_at=now - timedelta(minutes=9),
            ),
            IngestionRun(
                trigger=RunTrigger.SCHEDULER,
                status=RunStatus.FAILED,
                started_at=now - timedelta(minutes=2),
                finished_at=now - timedelta(minutes=1),
            ),
        ]
    )
    db.session.commit()
    return Seed(wire, tech, fed, fed_tech, chip, old, unsafe)
