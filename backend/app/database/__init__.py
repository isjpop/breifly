"""Database extension objects, shared by models, services and migrations."""

from typing import Any

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData
from sqlalchemy.orm import Session, scoped_session

# Deterministic constraint names keep Alembic autogenerate diffs stable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

db = SQLAlchemy(metadata=MetaData(naming_convention=NAMING_CONVENTION))
migrate = Migrate()

# Services accept either a plain Session (tests, scripts) or Flask-SQLAlchemy's scoped session.
DbSession = Session | scoped_session[Any]
