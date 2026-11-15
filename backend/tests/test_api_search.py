import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import text

from app.database import db
from tests.api_seed import Seed, seed


@pytest.fixture
def data(app: Flask) -> Seed:
    return seed()


def search(client: FlaskClient, q: str, status: int = 200, **params: str) -> list[str]:
    response = client.get("/api/articles/search", query_string={"q": q, **params})
    assert response.status_code == status, response.get_json()
    return [a["title"] for a in response.get_json().get("data", [])]


def test_search_headlines_with_stemming(client: FlaskClient, data: Seed) -> None:
    assert search(client, "processors") == [data.chip.title]
    assert search(client, "interest rate") == [data.fed.title]


def test_search_matches_ai_entities_and_summary(client: FlaskClient, data: Seed) -> None:
    assert search(client, "Acme Semiconductor") == [data.chip.title]  # only in key_entities
    assert search(client, "laptops") == [data.chip.title]  # only in why_it_matters


def test_search_by_publisher_name(client: FlaskClient, data: Seed) -> None:
    assert set(search(client, "Tech Desk")) == {data.fed_tech.title, data.chip.title}


def test_web_search_syntax(client: FlaskClient, data: Seed) -> None:
    assert search(client, "rate -stocks") == [data.fed.title]
    assert set(search(client, "galaxy OR earnings")) == {data.unsafe.title, data.old.title}


@pytest.mark.parametrize("q", ["%%", "' OR 1=1 --", "a_b", "\\\\", "<script>", "&|!:*"])
def test_hostile_input_is_harmless(client: FlaskClient, data: Seed, q: str) -> None:
    assert search(client, q) == []


def test_query_validation(client: FlaskClient, data: Seed) -> None:
    search(client, "a", status=400)
    search(client, "x" * 201, status=400)
    assert client.get("/api/articles/search").status_code == 400


def test_sort_by_recent_and_pagination_meta(client: FlaskClient, data: Seed) -> None:
    response = client.get("/api/articles/search?q=rate&sort=recent&per_page=1")
    body = response.get_json()
    assert [a["title"] for a in body["data"]] == [data.fed_tech.title]
    assert body["meta"]["query"] == "rate"
    assert body["meta"]["pagination"]["total"] == 2


def test_search_uses_the_full_text_index(client: FlaskClient, data: Seed) -> None:
    """Guards against the query expression drifting from the indexed expression."""
    from sqlalchemy import func, select
    from sqlalchemy.dialects import postgresql

    from app.models import Article
    from app.models.article import SEARCH_CONFIG, article_search_vector

    query = select(Article.id).where(
        article_search_vector().op("@@")(func.websearch_to_tsquery(SEARCH_CONFIG, "processor"))
    )
    sql = str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    with db.engine.connect() as conn:
        conn.execute(text("SET enable_seqscan = off"))
        plan = "\n".join(conn.execute(text(f"EXPLAIN {sql}")).scalars())
    assert "ix_articles_search" in plan
