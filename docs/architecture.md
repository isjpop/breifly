# Architecture

## Pipeline

```
News sources (RSS / authorized APIs)
  → Ingestion (per-source adapters)      backend/app/ingestion/sources/
  → Normalization + validation           backend/app/ingestion/
  → Duplicate detection                  backend/app/ingestion/
  → Categorization + importance ranking  backend/app/services/
  → AI summarization                     backend/app/services/
  → PostgreSQL                           backend/app/models/
  → Flask REST API                       backend/app/routes/
  → React frontend                       frontend/src/
```

Ingestion and summarization run as **background jobs**, separate from request handling.
Summaries are generated once, stored, and reused. The API never calls the LLM while serving reads.

## Repository layout

```
backend/
  app/
    config/      Settings loaded from environment variables (pydantic-settings)
    database/    SQLAlchemy + Flask-Migrate extension objects
    models/      ORM models
    schemas/     Pydantic schemas (API I/O, LLM output validation)
    services/    Business logic: categorization, ranking, summarization
    ingestion/   Source adapters, normalizer, deduplicator, scheduler
    routes/      Flask blueprints (HTTP layer only)
    utils/       Response envelopes, error handling
  migrations/    Alembic revisions
  tests/
frontend/src/
  components/ pages/ services/ hooks/ types/ styles/
infrastructure/docker/   Dockerfiles, DB init script
docs/
```

## Decisions

### Ingestion lives inside the backend package
The proposed layout put `ingestion/` at the repository root. It needs the ORM models, config
and database session, so a sibling top-level package would require `sys.path` manipulation or
a second installable package. It lives at `backend/app/ingestion/` and runs from the same image
as a separate process. It stays a separate module with no dependency on `routes/`.

### Migrations live in `backend/migrations/`
This is the Flask-Migrate default, and it ships inside the backend image so containers can run
`flask db upgrade` on start. Dockerfiles live in `infrastructure/docker/`.

### No CORS
In development Vite proxies `/api` to Flask. In production nginx serves the SPA and proxies
`/api`. The browser only ever talks to one origin, so the backend has no CORS surface.

### PostgreSQL in tests
The schema relies on JSONB and native UUIDs, so tests run against real PostgreSQL instead of
SQLite. That keeps tests faithful to production behaviour.

### psycopg 3
psycopg v3 has wheels for current Python versions and is the maintained driver. Plain
`postgres://` URLs (as most hosting providers issue them) are rewritten to use it.

## API response format

Success: `{"data": ..., "meta": {...}}`. Error: `{"error": {"code", "message", "details?"}}`.
Internal exception details are logged server-side and never returned to clients.

## Data model

| Table            | Purpose |
| ---------------- | ------- |
| `sources`        | One row per publisher integration: feed URL, default category, credibility weight (0–1), `is_active`, fetch tracking (`last_fetched_at`, `last_successful_fetch_at`, `last_fetch_status`, `last_fetch_error`, `consecutive_failures`) and HTTP validators (`http_etag`, `http_last_modified`). |
| `articles`       | Normalized articles. `normalized_url` is unique. Also holds `guid`, `content_hash`, `content_availability`, `published_at` (null when the feed's date is missing/untrustworthy), `category`/`importance_score` (set in Milestone 3), `processing_status`, `story_cluster_id`, and `extra` JSONB (e.g. `date_issue`). |
| `summaries`      | One current AI summary per article (`article_id` unique). Regeneration replaces it. |
| `story_clusters` | Groups separate articles from different publishers about the same event. |
| `ingestion_runs` | Metrics for every run: trigger, status, timings, counts, per-source breakdown JSONB. |

All primary keys are UUIDs. Enums are stored as VARCHAR + CHECK constraints rather than native
PostgreSQL enums, so adding a value is a simple migration. A test asserts that the migrations
produce exactly the schema the models describe.

## Ingestion

```
flask ingest worker  ──(every 15 min, PostgreSQL advisory lock)──►  IngestionService.run()
                                                                        │ per active source, own transaction
   FeedFetcher ── conditional GET, timeouts, retry+backoff, size cap ───┤
   parse_feed  ── feedparser on bytes (never lets feedparser fetch) ────┤
   SourceDefinition.include_entry  ── drop sponsored/video/audio ───────┤
   normalize_entry ── strip HTML, validate URL/title, cap lengths ──────┤
   Deduplicator ── URL / normalized URL / GUID / hash / headline ───────┤
   insert (savepoint; unique normalized_url as a final guard) ──────────┘
```

- **Failure isolation:** each source runs in its own transaction. Fetch, parse and adapter errors
  roll back that source only, are recorded on the source row and in the run's
  `source_results`, and the run continues. Run status is `succeeded`, `partial` or `failed`.
  Only a database outage aborts a run.
- **Overlap prevention:** every run takes `pg_try_advisory_lock`. A concurrent run (a second
  worker, or a manual `flask ingest run`) is skipped, not queued. PostgreSQL releases the lock
  if the process dies.
- **Scheduling:** a fixed-rate loop in a dedicated `worker` process, measured start to start,
  that stops gracefully on SIGTERM. That's enough for 6 feeds every 15 minutes. If volume grows,
  swap in Celery/RQ. `IngestionService` does not depend on the scheduler.
- **Politeness:** an identifying User-Agent and ETag/Last-Modified conditional requests. Five of
  the six feeds answer unchanged polls with `304 Not Modified`. CNBC sends no validators.

### Duplicate detection

| Level | Signal | Scope | Result |
| ----- | ------ | ----- | ------ |
| 1 | Exact URL | global | duplicate |
| 2 | Normalized URL: no tracking params, `www.`, fragment, trailing slash, `/amp`; http≡https | global | duplicate |
| 3 | Feed GUID | same source | duplicate |
| 4 | SHA-256 of content/description, case- and whitespace-insensitive, ≥200 chars | global | duplicate (e.g. syndicated copy) |
| 5a | Headline Jaccard ≥ 0.85 | same source | duplicate (re-published) |
| 5b | Headline overlap: ≥3 shared words at ≥0.6, or ≥4 at ≥0.5 | different source | **related**: stored and grouped into a `story_cluster` |

Different reporting on the same event is never discarded. The URL normalizer is conservative
on purpose (generic params like `source` or `id` are kept), because wrongly merging two articles
is worse than missing a duplicate. The level-5b thresholds were tuned on real headlines from
all six feeds and found 4 correct pairs and no false positives in ~100 articles. Headline overlap
is still weak evidence, and robust event clustering (embeddings or LLM-extracted entities) is
planned as a future enhancement.

## News sources

Verified on 2026-11-14 by fetching each feed. Briefly uses only publisher-provided feeds,
never scraping or paywall circumvention, and fetches **only the feed**, never article pages.

| Publisher             | Integration | Feed provides | Status |
| --------------------- | ----------- | ------------- | ------ |
| CNBC                  | Official "Top News" RSS | headline + ~150-char description; sponsored items flagged and skipped | active |
| Bloomberg             | Publisher-hosted markets RSS | headline + very short description; video/audio items skipped | active |
| TechCrunch            | Official RSS | headline, author, ~360-char excerpt | active |
| The Verge             | Official Atom | headline, author, article body text | active |
| Ars Technica          | Official RSS | headline, author, partial body, thumbnail | active |
| MIT Technology Review | Official RSS | headline, author, full body text | active |
| Reuters               | None. Public RSS retired in 2020 | n/a | **not integrated**: needs a Reuters Connect licence |
| Associated Press      | None. `apnews.com/index.rss` returns 403 | n/a | **not integrated**: needs an AP Media API licence |

Third-party feed mirrors (e.g. RSSHub) for Reuters/AP were deliberately not used: they scrape
the publisher's site, which is not authorized access. Adding either publisher means writing a
`SourceType.API` integration once credentials exist. No pipeline changes are needed.

**Content limits:** every article records `content_availability` (`feed_content`,
`description_only`, `headline_only`). Three of the six sources provide only short descriptions.
The summarizer (Milestone 3) must flag limited source material and never present a
headline-based summary as a full-article analysis.

**Terms of use:** publisher RSS terms commonly permit headline/link display with attribution,
and some restrict commercial use. Review each publisher's feed terms before any public or
commercial deployment.
