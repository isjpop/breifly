import pytest

from app.models import Category
from app.services.categorizer import categorize


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Treasury yields fall as Fed signals rate cut", Category.FINANCE),
        ("Nvidia unveils new GPU for AI data centers", Category.TECHNOLOGY),
        ("Retailer agrees $4 billion acquisition of rival", Category.BUSINESS),
        ("Astronomers spot water on distant moon with new telescope", Category.SCIENCE),
        ("Magnitude 7.1 earthquake strikes off the coast", Category.BREAKING_NEWS),
    ],
)
def test_keyword_categories(title: str, expected: Category) -> None:
    assert categorize(title=title, description=None, tags=[], default=Category.BUSINESS) is expected


def test_breaking_news_requires_the_headline() -> None:
    result = categorize(
        title="Insurers rethink pricing models",
        description="Losses from the earthquake and hurricane season mounted.",
        tags=[],
        default=Category.FINANCE,
    )
    assert result is not Category.BREAKING_NEWS


def test_falls_back_to_source_default_without_signals() -> None:
    assert categorize(title="A quiet day", description=None, tags=[], default=Category.SCIENCE) is (
        Category.SCIENCE
    )


def test_ties_prefer_the_source_default() -> None:
    # one finance keyword, one technology keyword
    result = categorize(title="Bitcoin app", description=None, tags=[], default=Category.FINANCE)
    assert result is Category.FINANCE


def test_feed_tags_contribute() -> None:
    result = categorize(
        title="An update", description=None, tags=["Space", "NASA"], default=Category.BUSINESS
    )
    assert result is Category.SCIENCE


def test_matching_respects_word_boundaries() -> None:
    # "ai" must not match inside "said" or "paid"
    result = categorize(
        title="Officials said fees were paid", description=None, tags=[], default=Category.BUSINESS
    )
    assert result is Category.BUSINESS
