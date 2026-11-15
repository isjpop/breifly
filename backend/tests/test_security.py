import pytest
from flask.testing import FlaskClient
from pydantic import ValidationError

from app.config import Settings


def test_api_responses_carry_security_headers(client: FlaskClient) -> None:
    response = client.get("/api/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]


def test_error_responses_also_carry_headers(client: FlaskClient) -> None:
    response = client.get("/api/missing")
    assert response.status_code == 404
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_non_get_responses_are_not_cached(client: FlaskClient) -> None:
    response = client.post("/api/articles/not-a-uuid/summarize")
    assert response.headers["Cache-Control"] == "no-store"


def test_oversized_request_bodies_are_rejected(client: FlaskClient) -> None:
    response = client.post(
        "/api/articles/x/summarize", data=b"x" * 20_000, content_type="application/octet-stream"
    )
    assert response.status_code == 413
    assert response.get_json()["error"]["code"] == "request_entity_too_large"


PROD_DB = "postgresql+psycopg://app:s3cret@db.internal:5432/briefly"


def test_production_rejects_default_database() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(app_env="production")


def test_production_rejects_short_admin_token() -> None:
    with pytest.raises(ValidationError, match="at least 24"):
        Settings(app_env="production", database_url=PROD_DB, admin_api_token="short")


def test_valid_production_configuration() -> None:
    settings = Settings(app_env="production", database_url=PROD_DB, admin_api_token="x" * 32)
    assert settings.is_production
    # An unset admin token is allowed: the endpoint is simply disabled.
    Settings(app_env="production", database_url=PROD_DB, admin_api_token=None)
