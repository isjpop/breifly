from flask import Flask
from sqlalchemy import select

from app.database import db
from app.ingestion.sources import SOURCE_DEFINITIONS
from app.ingestion.sync import sync_sources
from app.models import Source
from tests.factories import definition, make_source


def test_sync_creates_registry_sources(app: Flask) -> None:
    result = sync_sources(db.session)
    assert sorted(result.created) == sorted(SOURCE_DEFINITIONS)
    assert db.session.query(Source).count() == len(SOURCE_DEFINITIONS)


def test_sync_updates_definitions_but_preserves_operator_is_active(app: Flask) -> None:
    old = definition("wire", name="Old Name")
    make_source(old, http_etag='"stale"')
    row = db.session.scalars(select(Source)).one()
    row.is_active = False
    db.session.commit()

    new = definition("wire", feed_url="https://wire.example.com/new-feed", name="New Name")
    result = sync_sources(db.session, [new])

    row = db.session.scalars(select(Source)).one()
    assert result.updated == ["wire"]
    assert row.name == "New Name"
    assert row.feed_url == "https://wire.example.com/new-feed"
    assert row.http_etag is None  # validators reset when the feed URL changes
    assert row.is_active is False


def test_sync_is_idempotent_and_reports_unregistered_rows(app: Flask) -> None:
    make_source(definition("legacy"))
    d = definition("wire")
    sync_sources(db.session, [d])
    result = sync_sources(db.session, [d])
    assert result.created == [] and result.updated == []
    assert result.unregistered == ["legacy"]
