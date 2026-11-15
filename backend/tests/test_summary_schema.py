import json

import pytest

from app.models import Category, SourceCoverage
from app.schemas.summary import SUMMARY_JSON_SCHEMA, InvalidSummaryOutput, parse_summary_output
from tests.llm_fakes import valid_output

FULL = SourceCoverage.ARTICLE_TEXT
EXCERPT = SourceCoverage.EXCERPT


def test_valid_structured_output_is_parsed() -> None:
    output = parse_summary_output(valid_output(), FULL)
    assert output.category is Category.TECHNOLOGY
    assert len(output.summary) == 3
    assert output.impact_score == 7
    assert output.key_entities == ["Example Chips Inc.", "2nm process"]


def test_malformed_json_is_rejected() -> None:
    with pytest.raises(InvalidSummaryOutput, match="malformed JSON"):
        parse_summary_output('{"headline": "cut off', FULL)
    with pytest.raises(InvalidSummaryOutput, match="non-object"):
        parse_summary_output('["a list"]', FULL)


def test_missing_bullet_points_are_rejected() -> None:
    data = json.loads(valid_output())
    del data["summary"]
    with pytest.raises(InvalidSummaryOutput, match="summary"):
        parse_summary_output(json.dumps(data), FULL)


@pytest.mark.parametrize("count", [0, 2, 6])
def test_full_text_requires_three_to_five_points(count: int) -> None:
    bullets = [f"Distinct factual point number {i}." for i in range(count)]
    with pytest.raises(InvalidSummaryOutput):
        parse_summary_output(valid_output(summary=bullets), FULL)


def test_excerpt_allows_one_to_three_points_only() -> None:
    one = parse_summary_output(valid_output(summary=["Only one fact is available."]), EXCERPT)
    assert len(one.summary) == 1
    with pytest.raises(InvalidSummaryOutput, match="1-3"):
        parse_summary_output(valid_output(summary=["a1", "b2", "c3", "d4"]), EXCERPT)


def test_unsupported_category_is_rejected() -> None:
    with pytest.raises(InvalidSummaryOutput, match="unsupported category"):
        parse_summary_output(valid_output(category="Sports"), FULL)


@pytest.mark.parametrize("label", ["Breaking News", "breaking news", "breaking_news"])
def test_category_labels_and_values_are_accepted(label: str) -> None:
    assert (
        parse_summary_output(valid_output(category=label), FULL).category is Category.BREAKING_NEWS
    )


def test_scores_must_be_within_range() -> None:
    with pytest.raises(InvalidSummaryOutput, match="impact_score"):
        parse_summary_output(valid_output(impact_score=11), FULL)
    with pytest.raises(InvalidSummaryOutput, match="significance_score"):
        parse_summary_output(valid_output(significance_score=0), FULL)


def test_duplicate_and_blank_bullets_are_removed_before_counting() -> None:
    bullets = ["- Same point.", "Same point.", "  ", "Second point.", "Third point."]
    output = parse_summary_output(valid_output(summary=bullets), FULL)
    assert output.summary == ["Same point.", "Second point.", "Third point."]


def test_overlong_fields_are_rejected() -> None:
    with pytest.raises(InvalidSummaryOutput):
        parse_summary_output(valid_output(headline="H" * 300), FULL)
    with pytest.raises(InvalidSummaryOutput):
        parse_summary_output(valid_output(summary=["x" * 500, "b", "c"]), FULL)


def test_insufficient_information_needs_no_bullets() -> None:
    output = parse_summary_output(
        valid_output(insufficient_information=True, summary=[], limitations="Only a headline"),
        FULL,
    )
    assert output.insufficient_information
    assert output.limitations == "Only a headline"


def test_entities_are_deduplicated_and_capped() -> None:
    entities = ["Nvidia", "nvidia", " Jensen  Huang "] + [f"E{i}" for i in range(20)]
    output = parse_summary_output(valid_output(key_entities=entities), FULL)
    assert output.key_entities[:2] == ["Nvidia", "Jensen Huang"]
    assert len(output.key_entities) == 10


def test_schema_lists_exactly_the_supported_categories() -> None:
    assert SUMMARY_JSON_SCHEMA["properties"]["category"]["enum"] == [
        "Finance", "Technology", "Business", "Science", "Breaking News",
    ]  # fmt: skip
