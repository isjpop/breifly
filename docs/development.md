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

In Docker the `worker` service runs `ingest worker` and syncs sources on every tick.
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
