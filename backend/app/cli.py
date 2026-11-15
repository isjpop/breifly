"""Operational commands: ``flask --app app.wsgi <group> <command>``."""

import uuid
from datetime import timedelta

import click
from flask import Flask, current_app
from flask.cli import AppGroup
from sqlalchemy import func, select

from app.config import Settings
from app.database import db
from app.ingestion.scheduler import (
    IngestionWorker,
    llm_client,
    run_ingestion_once,
    run_pipeline_once,
    run_processing_once,
)
from app.ingestion.sync import sync_sources
from app.models import AIUsageEvent, RunTrigger, Source
from app.models.base import utcnow
from app.services.llm import LLMConfigurationError, LLMRateLimitError
from app.services.processing import ArticleNotFound, ProcessingService

sources_cli = AppGroup("sources", help="Manage configured news sources.")
ingest_cli = AppGroup("ingest", help="Fetch and store articles.")
process_cli = AppGroup("process", help="Categorize, rank and summarize stored articles.")
summaries_cli = AppGroup("summaries", help="Manage AI summaries.")
ai_cli = AppGroup("ai", help="AI provider usage.")


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
    """Ingest and process every INGESTION_INTERVAL_MINUTES until stopped (SIGTERM/SIGINT)."""
    settings = _settings()
    app = current_app._get_current_object()  # type: ignore[attr-defined]

    def tick() -> None:
        with app.app_context():
            try:
                run_pipeline_once(settings, RunTrigger.SCHEDULER)
            finally:
                db.session.remove()

    worker = IngestionWorker(tick, settings.ingestion_interval_minutes * 60)
    worker.install_signal_handlers()
    worker.run_forever()


@process_cli.command("run")
@click.option("--no-ai", is_flag=True, help="Categorize and rank only; make no LLM calls.")
@click.option("--limit", type=int, default=None, help="Max summaries this run.")
def process_run(no_ai: bool, limit: int | None) -> None:
    """Process pending articles now."""
    report = run_processing_once(_settings(), use_ai=not no_ai, max_summaries=limit)
    if report is None:
        raise click.ClickException("another processing run is in progress")
    click.echo(
        f"categorized={report.categorized} ranked={report.ranked} "
        f"summarized={report.summarized} insufficient={report.insufficient} "
        f"failed={report.failed} deferred={report.deferred} llm_calls={report.llm_calls}"
    )
    for note in report.notes:
        click.echo(f"note: {note}")
    if report.stopped_reason:
        click.echo(f"stopped early: {report.stopped_reason}", err=True)


@summaries_cli.command("regenerate")
@click.argument("article_id", type=click.UUID)
def summaries_regenerate(article_id: uuid.UUID) -> None:
    """Regenerate the summary for one article."""
    settings = _settings()
    with llm_client(settings) as client:
        if client is None:
            raise click.ClickException("GEMINI_API_KEY is not set")
        try:
            article = ProcessingService(db.session, settings, client).regenerate(article_id)
        except ArticleNotFound as exc:
            raise click.ClickException(f"article {article_id} not found") from exc
        except (LLMRateLimitError, LLMConfigurationError) as exc:
            raise click.ClickException(f"provider error: {exc}") from exc
    summary = article.summary
    assert summary is not None
    click.echo(f"{summary.generation_status.value}: {summary.headline or summary.generation_error}")
    for bullet in summary.bullet_points:
        click.echo(f"  - {bullet}")


@ai_cli.command("usage")
@click.option("--days", type=int, default=7, show_default=True)
def ai_usage(days: int) -> None:
    """Summarize LLM calls, tokens and estimated cost."""
    since = utcnow() - timedelta(days=days)
    rows = db.session.execute(
        select(
            AIUsageEvent.model_name,
            AIUsageEvent.status,
            func.count(),
            func.sum(AIUsageEvent.input_tokens),
            func.sum(AIUsageEvent.output_tokens + AIUsageEvent.thought_tokens),
            func.sum(AIUsageEvent.estimated_cost_usd),
        )
        .where(AIUsageEvent.created_at >= since)
        .group_by(AIUsageEvent.model_name, AIUsageEvent.status)
        .order_by(AIUsageEvent.model_name)
    ).all()
    if not rows:
        click.echo(f"no LLM calls in the last {days} days")
        return
    for model, status, calls, tokens_in, tokens_out, cost in rows:
        click.echo(
            f"{model:28} {status.value:15} calls={calls:<5} in={tokens_in or 0:<8} "
            f"out={tokens_out or 0:<8} est=${cost or 0:.4f}"
        )


def register_cli(app: Flask) -> None:
    for group in (sources_cli, ingest_cli, process_cli, summaries_cli, ai_cli):
        app.cli.add_command(group)
