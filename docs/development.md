# Development

## Environment variables

| Variable                | Used by  | Default                                                        | Notes |
| ----------------------- | -------- | -------------------------------------------------------------- | ----- |
| `APP_ENV`               | backend  | `development`                                                  | `development`, `test`, `production` |
| `LOG_LEVEL`             | backend  | `INFO`                                                         | |
| `DATABASE_URL`          | backend  | `postgresql+psycopg://briefly:briefly@localhost:5432/briefly`  | `postgres://` URLs accepted |
| `TEST_DATABASE_URL`     | tests    | `postgresql+psycopg://briefly:briefly@localhost:5432/briefly_test` | Tables are created and dropped per test |
| `DATABASE_POOL_SIZE`    | backend  | `5`                                                            | |
| `DATABASE_ECHO`         | backend  | `false`                                                        | Log SQL |
| `RUN_MIGRATIONS`        | container| `true`                                                         | Run `flask db upgrade` on container start (worker sets `false`) |
| `INGESTION_INTERVAL_MINUTES` | worker | `15`                                                     | Start-to-start interval |
| `INGESTION_USER_AGENT`  | worker   | `BrieflyBot/0.1 (+news aggregator; RSS reader)`                | Sent with every feed request |
| `HTTP_TIMEOUT_SECONDS`  | worker   | `15`                                                           | Read timeout (connect is 5s) |
| `HTTP_MAX_RETRIES`      | worker   | `3`                                                            | Retries for network errors, 408/425/429/5xx |
| `HTTP_BACKOFF_BASE_SECONDS` / `HTTP_BACKOFF_MAX_SECONDS` | worker | `1` / `30`          | Exponential backoff; `Retry-After` honoured up to the max |
| `FEED_MAX_BYTES`        | worker   | `5000000`                                                      | Larger responses are rejected |
| `FEED_MAX_ENTRIES`      | worker   | `100`                                                          | Entries processed per feed per run |
| `DEDUP_LOOKBACK_HOURS`  | worker   | `72`                                                           | Window for headline-similarity checks |
| `POSTGRES_USER/PASSWORD/DB` | compose | `briefly`                                                  | Required for the prod compose file |
| `GEMINI_API_KEY`        | worker   | empty                                                          | Empty disables summarization (everything else still works) |
| `GEMINI_MODEL`          | worker   | `gemini-3.5-flash-lite`                                        | Any Interactions-API model id |
| `GEMINI_API_BASE_URL` / `GEMINI_API_REVISION` | worker | `…/v1beta` / `2026-05-20`               | |
| `LLM_REQUESTS_PER_MINUTE` | worker | `10`                                                           | Client-side throttle |
| `LLM_MAX_SUMMARIES_PER_RUN` | worker | `40`                                                         | Per-tick budget |
| `LLM_TIMEOUT_SECONDS` / `LLM_MAX_RETRIES` | worker | `45` / `2`                                  | |
| `LLM_MAX_OUTPUT_TOKENS` / `LLM_MAX_INPUT_CHARS` | worker | `1024` / `12000`                      | Article text beyond this is truncated |
| `SUMMARY_MAX_ATTEMPTS`  | worker   | `3`                                                            | Then the summary stays `failed` |
| `LLM_INPUT_COST_PER_MILLION` / `LLM_OUTPUT_COST_PER_MILLION` | worker | `0.30` / `2.50`   | For estimates only |
| `ADMIN_API_TOKEN`       | backend  | empty                                                          | Bearer token for `POST …/summarize`; empty disables it |
| `REGENERATE_MAX_PER_MINUTE` / `REGENERATE_COOLDOWN_SECONDS` | backend | `5` / `60`        | Global and per-article limits |
| `API_LLM_TIMEOUT_SECONDS` | backend | `25`                                                          | Single provider attempt inside a request |
| `BRIEFING_WINDOW_HOURS` / `BRIEFING_FALLBACK_WINDOW_HOURS` | backend | `24` / `72`         | |
| `RANKING_WEIGHT_*`      | worker   | `0.35/0.30/0.20/0.15`                                          | impact/significance/credibility/recency; must sum to 1 |
| `RANKING_RECENCY_HALF_LIFE_HOURS` | worker | `12`                                                   | |
| `RANKING_REFRESH_WINDOW_HOURS` | worker | `72`                                                      | Articles re-ranked each tick |
| `VITE_API_PROXY_TARGET` | frontend | `http://localhost:8000`                                        | Dev server `/api` proxy target |
| `VITE_API_BASE_URL`     | frontend | empty (same origin)                                            | Only set if the API is on another origin |
| `WEB_PORT`              | prod compose | `80`                                                       | |

Settings are defined in one place: `backend/app/config/settings.py`.

## Ports
The backend uses **8000**, not Flask's default 5000, because macOS reserves 5000 for AirPlay
Receiver.

## Ingestion commands

```bash
cd backend
flask --app app.wsgi sources sync            # create/update source rows from the registry
flask --app app.wsgi sources list            # status, last successful fetch, last error
flask --app app.wsgi ingest run              # one pass over all active sources
flask --app app.wsgi ingest run --source cnbc --source techcrunch
flask --app app.wsgi ingest worker           # every INGESTION_INTERVAL_MINUTES until SIGTERM
```

In Docker the `worker` service runs `ingest worker`. Each tick syncs sources, ingests, then
processes.

## Processing and AI commands

```bash
flask --app app.wsgi process run                 # categorize, rank, summarize pending articles
flask --app app.wsgi process run --no-ai         # categorize + rank only
flask --app app.wsgi process run --limit 5       # cap summaries this run
flask --app app.wsgi summaries regenerate <article-uuid>
flask --app app.wsgi ai usage --days 7           # calls, tokens, estimated cost
```

`.env` is read from the repo root (and `backend/.env` overrides it), so the same file works for
Docker Compose and for running from `backend/`. Tests always run with no API key.
To disable a source without a deploy, run `UPDATE sources SET is_active = false WHERE slug = '…'`.
Syncs keep that setting.

## Adding a news source

1. Create `backend/app/ingestion/sources/<publisher>.py` with a `SourceDefinition`. Subclass it
   to override `include_entry` (filtering) or `extract_image` if the feed has quirks.
2. Register it in `SOURCE_DEFINITIONS` (`app/ingestion/sources/__init__.py`).
3. Add a test for any custom hook, then run `flask ingest run --source <slug>`.

## Database migrations

```bash
cd backend
flask --app app.wsgi db migrate -m "describe change"   # autogenerate from models
flask --app app.wsgi db upgrade
```

Review generated revisions before committing. Constraint names follow a fixed naming
convention (`app/database/__init__.py`), which keeps autogenerate diffs stable.

## Conventions
- Python: type hints everywhere, `ruff` for lint and format, `mypy` for types.
- TypeScript: strict types, no `any`, `oxlint --deny-warnings`.
- Routes contain HTTP concerns only. Logic belongs in `services/` or `ingestion/`.
- Every view handles loading, empty and error states with `StatusMessage`.
- UI colors come from semantic tokens (`bg-canvas`, `text-muted`, `border-line`, `text-accent`)
  defined in `frontend/src/styles/index.css`, never raw palette classes.

## Frontend

```bash
cd frontend
npm run dev            # http://localhost:5173, proxies /api to VITE_API_PROXY_TARGET
npm test               # Vitest + Testing Library
npm run test:coverage  # with thresholds (lines 80%, branches 75%), as CI runs it
npm run lint && npm run typecheck && npm run build
```

Tests mock `fetch` by URL path (`src/test/mockApi.ts`) and use shared fixtures
(`src/test/fixtures.ts`), so each test can assert exactly which API requests a page made.
Keep `src/types/api.ts` in sync when backend response models change.
