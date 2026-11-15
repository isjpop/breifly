# Briefly

**Get informed, not overwhelmed.** Briefly collects news from reputable publishers across
finance, technology, business and science, then deduplicates, categorizes, ranks and summarizes it
into a daily briefing you can read in minutes, with a link back to every original article.

> **Status:** Milestones 1–4 (foundation, ingestion from six publishers, categorization,
> ranking, Gemini summarization, REST API) are complete. See [docs/roadmap.md](docs/roadmap.md) for
> what works today and what comes next.

## Stack

| Layer     | Technology                                                       |
| --------- | ---------------------------------------------------------------- |
| Frontend  | React 19, TypeScript, Vite, Tailwind CSS v4, Lucide, React Router |
| Backend   | Python, Flask, SQLAlchemy 2, Flask-Migrate (Alembic), Pydantic    |
| Database  | PostgreSQL (JSONB, UUID primary keys)                             |
| AI        | Google Gemini (Interactions API), validated structured JSON output |
| Infra     | Docker, Docker Compose, GitHub Actions                            |

## Quick start (Docker)

```bash
cp .env.example .env     # add GEMINI_API_KEY to enable AI summaries
docker compose up --build
```

- App: http://localhost:5173
- API: http://localhost:8000/api/briefing/today (docs: [docs/api.md](docs/api.md),
  OpenAPI: http://localhost:8000/api/openapi.json)

Migrations run automatically when the backend container starts. The `worker` service begins
ingesting news immediately and then every 15 minutes.

## Quick start (without Docker)

Requires Python 3.12+, Node 24+ and a running PostgreSQL server.

```bash
# Database
createdb briefly && createdb briefly_test

# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
export DATABASE_URL=postgresql+psycopg://briefly:briefly@localhost:5432/briefly
flask --app app.wsgi db upgrade
flask --app app.wsgi ingest run          # fetch news once
flask --app app.wsgi process run         # categorize, rank, summarize (or: ingest worker)
flask --app app.wsgi run --port 8000

# Frontend (second terminal)
cd frontend
npm install
npm run dev
```

## Tests and checks

```bash
cd backend  && pytest --cov && ruff check . && mypy
cd frontend && npm test && npm run lint && npm run typecheck && npm run build
```

Backend tests run against a real PostgreSQL database set by `TEST_DATABASE_URL`.

## Documentation

- [Architecture](docs/architecture.md): pipeline, components, design decisions, source licensing
- [API](docs/api.md): endpoints and response format
- [Development](docs/development.md): environment variables, workflow, conventions
- [Roadmap](docs/roadmap.md): milestones, completed work, remaining tasks
