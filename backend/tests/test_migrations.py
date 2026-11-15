"""The Alembic migrations must produce exactly the schema the models describe."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask import Flask
from flask_migrate import downgrade, upgrade
from sqlalchemy import text

from app.database import db


def test_migrations_match_models_and_downgrade_cleanly(app: Flask) -> None:
    db.drop_all()
    upgrade()
    with db.engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), db.metadata)
    assert diff == [], f"models and migrations differ: {diff}"

    downgrade(revision="base")
    with db.engine.connect() as conn:
        tables = conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ).scalars()
        assert set(tables) <= {"alembic_version"}
