from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import select

from app.config import Settings
from app.database import db
from app.ingestion.scheduler import advisory_lock
from app.models import AIUsageEvent, GenerationStatus, Summary, UsageStatus
from app.models.base import utcnow
from app.routes import articles as article_routes
from app.services.llm import LLMConfigurationError, LLMRateLimitError, LLMUnavailableError
from tests.api_seed import Seed, seed
from tests.conftest import TEST_DATABASE_URL
from tests.llm_fakes import FakeLLM, valid_output

TOKEN = "s3cret-admin-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="test",
        database_url=TEST_DATABASE_URL,
        gemini_api_key="fake-key",  # enables AI; the client itself is replaced below
        admin_api_token=TOKEN,
        regenerate_max_per_minute=3,
        regenerate_cooldown_seconds=60,
    )


@pytest.fixture
def data(app: Flask) -> Seed:
    return seed()


@pytest.fixture
def llm(monkeypatch: pytest.MonkeyPatch) -> FakeLLM:
    fake = FakeLLM(default=valid_output(headline="Regenerated headline"))

    @contextmanager
    def fake_client(_settings: Settings) -> Iterator[FakeLLM]:
        yield fake

    monkeypatch.setattr(article_routes, "api_llm_client", fake_client)
    return fake


def post(client: FlaskClient, article_id: object, headers: dict[str, str] | None = AUTH):
    return client.post(f"/api/articles/{article_id}/summarize", headers=headers or {})


def test_regenerates_and_returns_the_article(client: FlaskClient, data: Seed, llm: FakeLLM) -> None:
    response = post(client, data.fed.id)

    assert response.status_code == 200, response.get_json()
    body = response.get_json()["data"]
    assert body["summary"]["headline"] == "Regenerated headline"
    assert body["summary"]["status"] == "succeeded"
    assert len(llm.calls) == 1
    event = db.session.scalars(select(AIUsageEvent)).one()
    assert event.operation == "regenerate"


@pytest.mark.parametrize(
    "headers",
    [
        None,
        {"Authorization": "Bearer wrong"},
        {"Authorization": TOKEN},
        {"Authorization": "Basic x"},
    ],
)
def test_requires_a_valid_bearer_token(
    client: FlaskClient, data: Seed, llm: FakeLLM, headers
) -> None:
    response = post(client, data.fed.id, headers=headers)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"].startswith("Bearer")
    assert llm.calls == []


def test_disabled_without_configured_token(app: Flask, data: Seed, llm: FakeLLM) -> None:
    app.config["BRIEFLY_SETTINGS"] = app.config["BRIEFLY_SETTINGS"].model_copy(
        update={"admin_api_token": None}
    )
    response = post(app.test_client(), data.fed.id)
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "admin_api_disabled"


def test_unavailable_without_ai_key(app: Flask, data: Seed, llm: FakeLLM) -> None:
    app.config["BRIEFLY_SETTINGS"] = app.config["BRIEFLY_SETTINGS"].model_copy(
        update={"gemini_api_key": None}
    )
    response = post(app.test_client(), data.fed.id)
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "ai_unavailable"


def test_invalid_and_unknown_ids(client: FlaskClient, data: Seed, llm: FakeLLM) -> None:
    assert post(client, "nope").status_code == 400
    assert post(client, "00000000-0000-0000-0000-000000000000").status_code == 404


def test_per_article_cooldown(client: FlaskClient, data: Seed, llm: FakeLLM) -> None:
    assert post(client, data.fed.id).status_code == 200
    again = post(client, data.fed.id)
    assert again.status_code == 429
    assert 1 <= int(again.headers["Retry-After"]) <= 61
    assert len(llm.calls) == 1


def test_global_rate_limit_counts_across_articles(
    client: FlaskClient, data: Seed, llm: FakeLLM
) -> None:
    for article in (data.fed, data.fed_tech, data.chip):
        assert post(client, article.id).status_code == 200
    blocked = post(client, data.old.id)
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"] == "60"


def test_old_usage_does_not_count_toward_the_limit(
    client: FlaskClient, data: Seed, llm: FakeLLM
) -> None:
    for _ in range(5):
        db.session.add(
            AIUsageEvent(
                operation="regenerate", provider="fake", model_name="m",
                status=UsageStatus.SUCCESS, created_at=utcnow() - timedelta(minutes=5),
            )
        )  # fmt: skip
    db.session.commit()
    assert post(client, data.fed.id).status_code == 200


def test_concurrent_regeneration_is_rejected(client: FlaskClient, data: Seed, llm: FakeLLM) -> None:
    with advisory_lock(db.engine, article_routes._lock_key(data.fed.id)):
        response = post(client, data.fed.id)
    assert response.status_code == 409


def test_provider_rate_limit_maps_to_503_with_retry_after(
    client: FlaskClient, data: Seed, llm: FakeLLM
) -> None:
    llm._responses = [LLMRateLimitError("HTTP 429", retry_after=30)]
    response = post(client, data.fed.id)
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "30"
    assert response.get_json()["error"]["code"] == "ai_rate_limited"


def test_provider_configuration_error_is_not_leaked(
    client: FlaskClient, data: Seed, llm: FakeLLM
) -> None:
    llm._responses = [LLMConfigurationError("HTTP 403 PERMISSION_DENIED key=abc")]
    response = post(client, data.fed.id)
    assert response.status_code == 503
    assert "PERMISSION_DENIED" not in response.get_data(as_text=True)


def test_failed_regeneration_keeps_existing_summary(
    client: FlaskClient, data: Seed, llm: FakeLLM
) -> None:
    llm._responses = [LLMUnavailableError("HTTP 503")]
    response = post(client, data.chip.id)

    assert response.status_code == 502
    summary = db.session.scalars(select(Summary).where(Summary.article_id == data.chip.id)).one()
    db.session.refresh(summary)
    assert summary.generation_status is GenerationStatus.SUCCEEDED
    assert summary.headline == "Chipmaker's new processor doubles battery life"


def test_only_post_is_allowed(client: FlaskClient, data: Seed) -> None:
    response = client.get(f"/api/articles/{data.fed.id}/summarize")
    assert response.status_code == 405
    assert response.get_json()["error"]["code"] == "method_not_allowed"
