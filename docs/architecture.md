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

## REST API

See [api.md](api.md) for endpoints. Design notes:

- **Layers:** routes do HTTP concerns only. `app/schemas/api.py` holds the request and response
  models, and `app/services/articles.py` holds the queries. Every list endpoint uses a fixed
  number of queries (the page, a count, and one batched related-coverage count) regardless of
  page size.
- **Validation:** query parameters are parsed by Pydantic models, and errors become a 400 with
  per-field details. Path UUIDs are validated explicitly (400, not 404). Links are re-checked on
  output, so a stored unsafe URL is never emitted.
- **Search:** PostgreSQL full-text search (`websearch_to_tsquery`, English stemming) over two
  GIN expression indexes: article text, and AI summary text plus entities. The query
  expressions are built by the same functions that define the indexes
  (`article_search_vector()` / `summary_search_vector()`), and a test checks the query plan
  actually uses the index.
- **Story-level de-duplication:** top stories and the briefing show one article per story
  cluster. The others are counted in `related_count` and listed on the detail page.
- **Security headers:** every API response carries `nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer` and `Content-Security-Policy: default-src 'none'`. Request
  bodies over 16 KB are rejected before routing. In production, startup refuses a default
  database URL or an admin token under 24 characters.
- **Top stories:** AI-assessed articles rank first in top-story slots, so a teaser that can
  never be assessed (it stays on the neutral default score) can't take a top slot on freshness alone.
- **Admin endpoint:** fail-closed bearer auth, rate limits stored in the database (so they work
  with several gunicorn workers), a per-article advisory lock, and one bounded provider call.
- **Time:** database sessions are pinned to UTC, so date filters and timestamps never depend on
  the server's time zone.
- **Envelope:** success is `{"data": ..., "meta": {...}}` and an error is
  `{"error": {"code", "message", "details?"}}`. Internal exception details are logged
  server-side and never returned to clients.

## Data model

| Table            | Purpose |
| ---------------- | ------- |
| `sources`        | One row per publisher integration: feed URL, default category, credibility weight (0–1), `is_active`, fetch tracking (`last_fetched_at`, `last_successful_fetch_at`, `last_fetch_status`, `last_fetch_error`, `consecutive_failures`) and HTTP validators (`http_etag`, `http_last_modified`). |
| `articles`       | Normalized articles. `normalized_url` is unique. Also holds `guid`, `content_hash`, `content_availability`, `published_at` (null when the feed's date is missing/untrustworthy), `category` + `category_source`, `impact_score`/`significance_score` (from the model), `importance_score` (computed), `processing_status`, `story_cluster_id`, and `extra` JSONB (e.g. `date_issue`). |
| `summaries`      | One current AI summary per article (`article_id` unique): bullets, why it matters, entities, `source_coverage`, `limitations`, model, prompt version, attempts. Regeneration updates it in place. |
| `ai_usage_events`| One row per LLM call: operation (`summarize`/`regenerate`), tokens, latency, status, estimated cost. Also backs the API's regeneration rate limit. |
| `story_clusters` | Groups separate articles from different publishers about the same event. |
| `ingestion_runs` | Metrics for every run: trigger, status, timings, counts, per-source breakdown JSONB. |

Indexes beyond the obvious foreign keys include `coalesce(published_at, created_at)` (the
"effective time" used for date filters and recency sorting) and GIN full-text indexes on
article and summary text. The GIN indexes are hand-written in a migration because Alembic
cannot render them.

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

## Processing and AI summarization

Runs after ingestion on every worker tick (`flask process run` runs it alone). It has its own
advisory lock, separate from ingestion, so two processing runs can never double-spend API calls.

```
categorize (rules)  →  rank  →  summarize (Gemini, budgeted, most important first)  →  re-rank
```

1. **Categorize:** every uncategorized article gets a keyword-based category, falling back to
   the source default. It is free and deterministic, so categories exist even without AI. A
   validated AI category replaces it later (`category_source`: `rules` → `ai`).
2. **Rank:** `importance = 0.35·impact + 0.30·significance + 0.20·credibility + 0.15·recency`.
   Each component is 1–10 and the weights are configurable (they must sum to 1). The model
   assesses impact and significance. Unassessed articles use a neutral-low 4. Credibility is the
   source weight. Recency halves every 12 h. All articles from the last 72 h are re-ranked every
   tick so scores track age. Coverage volume is deliberately not an input.
   - *Deviation from the brief:* the brief has the model return `importance_score` directly.
     The model can't know source credibility weights, and recency changes after generation,
     so it returns the two judgement components and Briefly computes the final score.
3. **Summarize:** see the policy below. Summaries are generated once, stored, and reused.
   Requests never trigger generation.

### Thin-content policy (never summarize from a headline alone)

| Feed provided | Model call? | Output | `source_coverage` |
| ------------- | ----------- | ------ | ----------------- |
| Headline only, or <100 chars of text | **No** | status `insufficient_content` + limitation note | — |
| Publisher excerpt only (CNBC, TechCrunch, Bloomberg) | Yes | **1–3** takeaways, limitation noted | `excerpt` |
| Article body text (MIT TR, The Verge, Ars) | Yes | **3–5** takeaways | `article_text` |

*Deviation from the brief:* "3–5 bullet points" applies to full-text articles. Forcing five
points out of a 150-character teaser would mean inventing facts, which the brief forbids.
The model can also decline (`insufficient_information`), and that is stored as
`insufficient_content`.

### Reliability and cost controls

- **Provider:** Gemini REST Interactions API over httpx (`app/services/llm/gemini.py`), behind a
  provider-neutral `LLMClient` protocol. The SDK was not used because it adds about 10
  transitive dependencies. Requests send `store: false`.
- **Structured output:** a JSON schema is sent with each request, and every reply is re-validated
  with Pydantic (`app/schemas/summary.py`): categories, 1–10 scores, bullet counts per
  coverage, length caps, deduplication. Invalid output gets one retry, then the attempt fails.
  Nothing invalid is stored.
- **Retries:** the client retries 429 (honouring `Retry-After`), 5xx, timeouts and network
  errors with exponential backoff. 4xx configuration errors (bad key or model) are not retried.
- **Budget and circuit breakers:** a client-side throttle (`LLM_REQUESTS_PER_MINUTE`) and at
  most `LLM_MAX_SUMMARIES_PER_RUN` summaries per tick. The run stops calling the provider on a
  rate limit, a configuration error, or 3 consecutive outages. Failed summaries are retried on
  later ticks up to `SUMMARY_MAX_ATTEMPTS`, then left as failed. The article stays readable
  with its publisher description.
- **Usage and cost:** every call, successful or not, is a row in `ai_usage_events` (tokens,
  thought tokens, latency, status, estimated USD at configured prices). Run `flask ai usage`.
- **Prompt injection:** article text goes into the prompt only as a JSON object inside one
  `<article>` block, with `<` escaped so the text can't close the block. The system
  instruction marks it untrusted data, the model has no tools, and output must match the
  schema.
- **Provenance:** each summary stores `model_name`, `prompt_version`, `generated_at`,
  `attempts` and `source_coverage`.
- **Free-tier data use:** on Gemini's free tier, Google may use submitted content to improve
  its products. Briefly sends only publisher feed text, never user data. Use a paid key to
  opt out.

## Frontend

React 19 + TypeScript + Vite + Tailwind v4 (`frontend/src`).

```
pages/       BriefingPage, CategoryPage, ArticlePage, SearchPage, NotFoundPage
components/  Layout (header, section nav, header search), ArticleCard (lead/standard/compact),
             SummaryBlock + BasisTag, ImportanceMeter, ExternalLink, Pagination, SortToggle,
             StatusMessage (loading/empty/error), CardSkeleton, SectionHeading, ScrollToTop
services/    api.ts: typed client; unwraps {data, meta}, timeouts, typed ApiError
hooks/       useAsync (abortable loads + reload), useSearchParam, useNow, useTheme
lib/         format (relative/absolute time), categories (URL ↔ API slugs), urls, summary
types/       api.ts: mirrors backend response models
```

- **URL is the state:** sort, publisher filter, page and query live in the query string, so
  views are shareable and the back button works. Category URLs use hyphens
  (`/category/breaking-news`), mapped to API slugs.
- **Every data view has loading (skeletons), empty and error (with retry) states.**
  Requests are aborted when the view changes, so stale responses never overwrite newer ones.
- **Honest AI labelling:** cards show takeaways only for successful summaries. Excerpt-based
  summaries carry an `Excerpt` tag. Articles without a summary show the publisher's description,
  tagged `Teaser only` or `Summary pending`. The detail page shows the model, generation time
  and a "may contain errors" note.
- **External vs internal links:** publisher links always use `ExternalLink`: an ↗ marker, a new
  tab, `rel="noopener noreferrer"`, screen-reader text, and the URL re-validated as http(s)
  (unsafe URLs are not rendered). In-app navigation uses router links with no marker. Article
  images use `referrerPolicy="no-referrer"` and hide themselves on load error.
- **Design tokens:** colors are semantic CSS variables (`canvas`, `surface`, `ink`, `muted`,
  `line`, `accent`) switched by a `.dark` class. The theme is applied before first paint from
  the saved choice or the OS preference.
- **Content Security Policy:** in production nginx sends `script-src 'self'` with no inline
  scripts. The pre-paint theme script is a static file (`public/theme-init.js`). `vite preview`
  reads its headers from `nginx.conf`, so local preview runs under the production policy.
- **Accessibility:** a skip link, landmark regions labelled by their headings,
  `aria-current` navigation, radio-group sort controls, labelled inputs, visible focus rings,
  and an importance meter exposed as "Importance 7.6 out of 10".

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
