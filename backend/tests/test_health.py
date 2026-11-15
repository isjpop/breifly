from flask.testing import FlaskClient

from app import create_app
from app.config import Settings


def test_health_reports_ok_when_database_reachable(client: FlaskClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.get_json()
    assert body["data"]["status"] == "ok"
    assert body["data"]["database"] == "ok"
    assert "timestamp" in body["data"]


def test_health_reports_degraded_when_database_unreachable() -> None:
    # Port 1 is never a Postgres server; connect_timeout keeps the test fast.
    settings = Settings(
        app_env="test",
        database_url="postgresql+psycopg://nobody@127.0.0.1:1/none?connect_timeout=1",
    )
    app = create_app(settings)

    response = app.test_client().get("/api/health")

    assert response.status_code == 503
    assert response.get_json()["data"]["database"] == "unavailable"


def test_unknown_route_returns_json_error_envelope(client: FlaskClient) -> None:
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


def test_plain_postgres_urls_are_routed_to_psycopg_driver() -> None:
    settings = Settings(database_url="postgres://u:p@host:5432/db")
    assert settings.database_url == "postgresql+psycopg://u:p@host:5432/db"
