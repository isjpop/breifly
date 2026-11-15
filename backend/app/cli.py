"""Operational commands: ``flask --app app.wsgi <group> <command>``."""

import click
from flask import Flask, current_app
from flask.cli import AppGroup
from sqlalchemy import select

from app.config import Settings
from app.database import db
from app.ingestion.scheduler import IngestionWorker, run_ingestion_once, sync_and_run
from app.ingestion.sync import sync_sources
from app.models import RunTrigger, Source

sources_cli = AppGroup("sources", help="Manage configured news sources.")
ingest_cli = AppGroup("ingest", help="Fetch and store articles.")


def _settings() -> Settings:
    settings: Settings = current_app.config["BRIEFLY_SETTINGS"]
    return settings


@sources_cli.command("sync")
def sources_sync() -> None:
    """Create/update source rows from the code registry."""
    result = sync_sources(db.session)
    click.echo(f"created: {result.created or '-'}  updated: {result.updated or '-'}")
    if result.unregistered:
        click.echo(f"warning: no integration for {result.unregistered}", err=True)


@sources_cli.command("list")
def sources_list() -> None:
    """Show sources and their latest fetch status."""
    for s in db.session.scalars(select(Source).order_by(Source.name)):
        status = s.last_fetch_status.value if s.last_fetch_status else "never fetched"
        last = (
            s.last_successful_fetch_at.isoformat(timespec="seconds")
            if s.last_successful_fetch_at
            else "-"
        )
        flag = "active" if s.is_active else "inactive"
        click.echo(f"{s.slug:24} {flag:8} {status:13} last ok: {last}")
        if s.last_fetch_error:
            click.echo(f"{'':24} error: {s.last_fetch_error}")


@ingest_cli.command("run")
@click.option("--source", "slugs", multiple=True, help="Limit to these source slugs.")
def ingest_run(slugs: tuple[str, ...]) -> None:
    """Run one ingestion pass now."""
    sync_sources(db.session)
    run = run_ingestion_once(_settings(), trigger=RunTrigger.MANUAL, only_slugs=slugs or None)
    if run is None:
        raise click.ClickException("another ingestion run is in progress")
    click.echo(
        f"run {run.id}: {run.status.value} | sources {run.sources_succeeded}/"
        f"{run.sources_attempted} ok | {run.articles_new} new, {run.articles_duplicate} duplicate, "
        f"{run.articles_invalid} invalid, {run.articles_filtered} filtered"
    )
    for slug, r in run.source_results.items():
        counts = f"new={r['new']} dup={r['duplicate']} related={r['related']}"
        line = f"  {slug:24} {r['status']:13} {counts}"
        click.echo(line + (f"  error: {r['error']}" if r["error"] else ""))


@ingest_cli.command("worker")
def ingest_worker() -> None:
    """Run ingestion every INGESTION_INTERVAL_MINUTES until stopped (SIGTERM/SIGINT)."""
    settings = _settings()
    app = current_app._get_current_object()  # type: ignore[attr-defined]

    def tick() -> None:
        with app.app_context():
            try:
                sync_and_run(settings, RunTrigger.SCHEDULER)
            finally:
                db.session.remove()

    worker = IngestionWorker(tick, settings.ingestion_interval_minutes * 60)
    worker.install_signal_handlers()
    worker.run_forever()


def register_cli(app: Flask) -> None:
    app.cli.add_command(sources_cli)
    app.cli.add_command(ingest_cli)
