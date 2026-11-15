from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy.exc import OperationalError

from app.services import articles as article_service
from tests.api_seed import Seed, seed


@pytest.fixture
def data(app: Flask) -> Seed:
    return seed()


def get(client: FlaskClient, url: str, status: int = 200) -> dict[str, Any]:
    response = client.get(url)
    assert response.status_code == status, response.get_json()
    return response.get_json()


def titles(body: dict[str, Any]) -> list[str]:
    return [a["title"] for a in body["data"]]


# --------------------------------------------------------------------------- list


def test_list_is_paginated_and_sorted_by_importance(client: FlaskClient, data: Seed) -> None:
    body = get(client, "/api/articles?per_page=2")
    assert titles(body) == [data.fed.title, data.fed_tech.title]
    assert body["meta"]["pagination"] == {"page": 1, "per_page": 2, "total": 5, "total_pages": 3}

    page3 = get(client, "/api/articles?per_page=2&page=3")
    assert titles(page3) == [data.unsafe.title]
    assert get(client, "/api/articles?page=9")["data"] == []


def test_sort_by_recency(client: FlaskClient, data: Seed) -> None:
    assert titles(get(client, "/api/articles?sort=recent"))[:2] == [
        data.fed_tech.title,
        data.fed.title,
    ]


def test_category_filter(client: FlaskClient, data: Seed) -> None:
    assert titles(get(client, "/api/articles?category=technology")) == [
        data.fed_tech.title,
        data.chip.title,
    ]


def test_source_filter_accepts_lists(client: FlaskClient, data: Seed) -> None:
    assert len(get(client, "/api/articles?source=techdesk")["data"]) == 2
    assert len(get(client, "/api/articles?source=techdesk,wire")["data"]) == 5
    assert len(get(client, "/api/articles?source=techdesk&source=wire")["data"]) == 5
    assert get(client, "/api/articles?source=nope")["data"] == []


def test_date_filters(client: FlaskClient, data: Seed) -> None:
    old_day = data.old.published_at
    assert old_day is not None
    day = old_day.date().isoformat()
    assert titles(get(client, f"/api/articles?from={day}&to={day}")) == [data.old.title]
    recent = get(client, f"/api/articles?from={old_day.isoformat().replace('+00:00', 'Z')}")
    assert len(recent["data"]) == 5


@pytest.mark.parametrize(
    ("query", "field"),
    [
        ("category=sports", "category"),
        ("per_page=0", "per_page"),
        ("per_page=101", "per_page"),
        ("page=abc", "page"),
        ("sort=popular", "sort"),
        ("from=yesterday", "from"),
        ("from=2026-11-10&to=2026-11-01", "query"),
    ],
)
def test_invalid_parameters_return_400_with_details(
    client: FlaskClient, data: Seed, query: str, field: str
) -> None:
    body = get(client, f"/api/articles?{query}", status=400)
    assert body["error"]["code"] == "validation_error"
    assert any(field in key for key in body["error"]["details"]) or field == "query"


def test_unknown_parameters_are_ignored(client: FlaskClient, data: Seed) -> None:
    assert len(get(client, "/api/articles?_=12345")["data"]) == 5


def test_cards_expose_safe_links_and_compact_summaries(client: FlaskClient, data: Seed) -> None:
    cards = {a["title"]: a for a in get(client, "/api/articles")["data"]}

    chip = cards[data.chip.title]
    assert chip["url"] == "https://techdesk.example.com/chip"
    assert chip["source"] == {"slug": "techdesk", "name": "Tech Desk"}
    assert chip["category"] == {"slug": "technology", "label": "Technology"}
    assert chip["summary"]["status"] == "succeeded"
    assert len(chip["summary"]["bullet_points"]) == 3  # card preview is capped
    assert "key_entities" not in chip["summary"]

    unsafe = cards[data.unsafe.title]
    assert unsafe["url"] is None and unsafe["image_url"] is None
    assert unsafe["summary"] is None  # pending summaries are not shown

    assert cards[data.fed.title]["related_count"] == 1
    assert cards[data.chip.title]["related_count"] == 0


# ------------------------------------------------------------------------- detail


def test_article_detail_includes_full_summary_and_related(client: FlaskClient, data: Seed) -> None:
    chip = get(client, f"/api/articles/{data.chip.id}")["data"]
    assert len(chip["summary"]["bullet_points"]) == 4
    assert chip["summary"]["key_entities"] == ["Acme Semiconductor", "Model X1"]
    assert chip["summary"]["model_name"] == "fake-model-1"
    assert chip["content_availability"] == "feed_content"

    fed = get(client, f"/api/articles/{data.fed.id}")["data"]
    assert [r["title"] for r in fed["related"]] == [data.fed_tech.title]
    assert fed["related"][0]["source"]["slug"] == "techdesk"


def test_invalid_identifier_returns_400(client: FlaskClient, data: Seed) -> None:
    assert get(client, "/api/articles/not-a-uuid", status=400)["error"]["code"] == "invalid_id"


def test_unknown_article_returns_404(client: FlaskClient, data: Seed) -> None:
    body = get(client, "/api/articles/00000000-0000-0000-0000-000000000000", status=404)
    assert body["error"]["code"] == "not_found"


# ---------------------------------------------------------------------------- top


def test_top_returns_one_article_per_story(client: FlaskClient, data: Seed) -> None:
    top = titles(get(client, "/api/articles/top"))
    assert top[0] == data.fed.title
    assert data.fed_tech.title not in top  # same cluster as fed
    assert data.old.title not in top  # outside the 24h window


def test_top_window_and_limit(client: FlaskClient, data: Seed) -> None:
    assert len(get(client, "/api/articles/top?limit=1")["data"]) == 1
    assert data.old.title in titles(get(client, "/api/articles/top?hours=168"))
    get(client, "/api/articles/top?limit=51", status=400)


# ------------------------------------------------------------------- catalog/briefing


def test_categories_list_all_with_counts(client: FlaskClient, data: Seed) -> None:
    categories = {c["slug"]: c for c in get(client, "/api/categories")["data"]}
    assert list(categories) == ["finance", "technology", "business", "science", "breaking_news"]
    assert categories["technology"]["article_count"] == 2
    assert categories["breaking_news"] == {
        "slug": "breaking_news",
        "label": "Breaking News",
        "article_count": 0,
    }


def test_sources_list(client: FlaskClient, data: Seed) -> None:
    sources = get(client, "/api/sources")["data"]
    assert [s["slug"] for s in sources] == ["wire", "techdesk"]  # ordered by name
    assert set(sources[0]) == {
        "slug", "name", "homepage_url", "default_category", "credibility_weight",
        "is_active", "last_successful_fetch_at", "last_fetch_status",
    }  # fmt: skip


def test_briefing_groups_by_category_without_repeating_top_stories(
    client: FlaskClient, data: Seed
) -> None:
    briefing = get(client, "/api/briefing/today")["data"]

    top = [a["title"] for a in briefing["top_stories"]]
    assert top[0] == data.fed.title
    assert data.fed_tech.title not in top
    in_sections = [a["title"] for s in briefing["sections"] for a in s["articles"]]
    assert not set(top) & set(in_sections)
    assert data.fed_tech.title not in in_sections  # same story as a top story
    assert all(s["articles"] for s in briefing["sections"])
    assert briefing["last_updated_at"] is not None  # latest *successful* run


def test_briefing_widens_window_when_too_few_stories(client: FlaskClient, data: Seed) -> None:
    briefing = get(client, "/api/briefing/today")["data"]
    assert briefing["window_hours"] == 72  # only 4 stories in the last 24h


def test_empty_database_gives_empty_results(client: FlaskClient) -> None:
    assert get(client, "/api/articles")["data"] == []
    briefing = get(client, "/api/briefing/today")["data"]
    assert briefing["top_stories"] == [] and briefing["sections"] == []
    assert briefing["last_updated_at"] is None


def test_database_failure_returns_503_without_internals(
    client: FlaskClient, data: Seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_args: object, **_kwargs: object) -> None:
        raise OperationalError("SELECT secret_table", {}, Exception("connection refused"))

    monkeypatch.setattr(article_service, "list_articles", broken)
    response = client.get("/api/articles")

    assert response.status_code == 503
    body = response.get_json()
    assert body["error"]["code"] == "database_unavailable"
    assert "secret_table" not in response.get_data(as_text=True)
