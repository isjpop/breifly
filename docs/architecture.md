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

## News source licensing (planned; verified in Milestone 2)

Briefly uses only official RSS feeds or licensed/authorized APIs, never scraping or paywall
circumvention. Known constraints to verify during ingestion work:

| Publisher            | Expected access                                                              |
| -------------------- | ---------------------------------------------------------------------------- |
| CNBC                 | Official RSS                                                                 |
| TechCrunch           | Official RSS                                                                 |
| The Verge            | Official RSS                                                                 |
| Ars Technica         | Official RSS                                                                 |
| MIT Technology Review| Official RSS                                                                 |
| Reuters              | Public RSS discontinued (2020); requires a licensed API (e.g. Reuters Connect) |
| Associated Press     | No official public RSS; requires AP Media API licence                        |
| Bloomberg            | Limited/unclear feed terms; treated as licensed-only until confirmed         |

Sources without authorized access are configured but **inactive** until credentials exist.
RSS feeds often carry only a headline and description. The summarizer must flag limited
source content instead of presenting a full-article summary.
