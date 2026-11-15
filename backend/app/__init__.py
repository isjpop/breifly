"""Flask application factory."""

import logging

from flask import Flask

from app.config import Settings, get_settings
from app.database import db, migrate
from app.utils.errors import register_error_handlers


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or get_settings()

    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=settings.database_url,
        SQLALCHEMY_ECHO=settings.database_echo,
        SQLALCHEMY_ENGINE_OPTIONS={
            "pool_pre_ping": True,
            "pool_size": settings.database_pool_size,
            # Sessions run in UTC so timestamps (and date filters) never depend on the
            # database server's local time zone.
            "connect_args": {"options": "-c timezone=UTC"},
        },
        JSON_SORT_KEYS=False,
        BRIEFLY_SETTINGS=settings,
    )

    db.init_app(app)
    migrate.init_app(app, db, directory="migrations")

    # Import models so they register with SQLAlchemy metadata (required by migrations).
    from app import models  # noqa: F401
    from app.routes.articles import bp as articles_bp
    from app.routes.catalog import bp as catalog_bp
    from app.routes.docs import bp as docs_bp
    from app.routes.health import bp as health_bp

    for blueprint in (health_bp, articles_bp, catalog_bp, docs_bp):
        app.register_blueprint(blueprint)
    register_error_handlers(app)

    from app.cli import register_cli

    register_cli(app)

    return app
