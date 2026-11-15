"""Shared fixtures.

Tests run against a real PostgreSQL database (the schema relies on JSONB and UUID types),
configured through ``TEST_DATABASE_URL``. Tables are created and dropped around each test.
"""

import os
from collections.abc import Iterator

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import text

from app import create_app
from app.config import Settings
from app.database import db

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://briefly:briefly@localhost:5432/briefly_test"
)


@pytest.fixture
def settings() -> Settings:
    return Settings(app_env="test", database_url=TEST_DATABASE_URL, http_max_retries=1)


@pytest.fixture
def app(settings: Settings) -> Iterator[Flask]:
    application = create_app(settings)
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()
        with db.engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS alembic_version"))


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()
