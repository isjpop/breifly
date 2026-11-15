"""The Alembic migrations must produce exactly the schema the models describe."""

import re

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask import Flask
from flask_migrate import downgrade, upgrade
from sqlalchemy import Index, text
from sqlalchemy.dialects import postgresql

from app.database import db

# GIN expression indexes are hand-written in a migration; Alembic cannot compare them, so they
# are checked explicitly below instead of through autogenerate.
EXPRESSION_INDEXES = {"ix_articles_search", "ix_summaries_search"}


def _include(
    obj: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    return not (type_ == "index" and name in EXPRESSION_INDEXES)


def _normalize(sql: str) -> str:
    sql = sql.lower().replace("public.", "")
    sql = re.sub(r"\b(articles|summaries)\.", "", sql)  # model SQL qualifies columns
    sql = re.sub(r"::(text|character varying)\b", "", sql)  # casts postgres adds when storing
    sql = sql.replace("cast(", "").replace(" as text)", "")
    return re.sub(r"[\s()]", "", sql)


def test_migrations_match_models_and_downgrade_cleanly(app: Flask) -> None:
    db.drop_all()
    upgrade()
    with db.engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={"include_object": _include})
        diff = compare_metadata(context, db.metadata)
        assert diff == [], f"models and migrations differ: {diff}"

        live = dict(
            conn.execute(
                text("SELECT indexname, indexdef FROM pg_indexes WHERE indexname = ANY(:names)"),
                {"names": list(EXPRESSION_INDEXES)},
            ).all()
        )
    model_indexes = {
        index.name: index
        for table in db.metadata.tables.values()
        for index in table.indexes
        if index.name in EXPRESSION_INDEXES
    }
    assert set(live) == EXPRESSION_INDEXES
    for name, index in model_indexes.items():
        assert isinstance(index, Index)
        expected = str(
            index.expressions[0].compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        assert _normalize(expected) in _normalize(live[name]), f"{name} drifted from the model"

    downgrade(revision="base")
    with db.engine.connect() as conn:
        tables = conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ).scalars()
        assert set(tables) <= {"alembic_version"}
