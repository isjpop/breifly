"""Shared fixtures.

Tests run against a real PostgreSQL database (the schema relies on JSONB and UUID types),
configured through ``TEST_DATABASE_URL``.
"""

import os
from collections.abc import Iterator

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app import create_app
from app.config import Settings
from app.database import db

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://briefly:briefly@localhost:5432/briefly_test"
)


@pytest.fixture
def app() -> Iterator[Flask]:
    application = create_app(Settings(app_env="test", database_url=TEST_DATABASE_URL))
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()
