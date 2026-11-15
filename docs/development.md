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
| `RUN_MIGRATIONS`        | container| `true`                                                         | Run `flask db upgrade` on container start |
| `POSTGRES_USER/PASSWORD/DB` | compose | `briefly`                                                  | Required for the prod compose file |
| `VITE_API_PROXY_TARGET` | frontend | `http://localhost:8000`                                        | Dev server `/api` proxy target |
| `VITE_API_BASE_URL`     | frontend | empty (same origin)                                            | Only set if the API is on another origin |
| `WEB_PORT`              | prod compose | `80`                                                       | |

Settings are defined in one place: `backend/app/config/settings.py`.

## Ports
The backend uses **8000**, not Flask's default 5000, because macOS reserves 5000 for AirPlay
Receiver.

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
