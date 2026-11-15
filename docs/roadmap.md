# Roadmap

## Milestone 1: Foundation ✅
- [x] Repository layout, `.gitignore`, `.env.example`
- [x] Flask app factory, environment-based settings, SQLAlchemy and Flask-Migrate wiring
- [x] Consistent JSON response and error envelopes, `GET /api/health` with DB readiness
- [x] React, TypeScript, Vite, Tailwind shell: layout, light/dark theme, API client with
      timeouts and typed errors, shared loading/empty/error component
- [x] Dockerfiles (backend, frontend dev, frontend prod/nginx), dev and prod compose files
- [x] GitHub Actions: lint, type check, tests (≥80% backend coverage gate), builds, Docker smoke test
- [x] Backend tests (pytest with real PostgreSQL) and frontend tests (Vitest and Testing Library)

## Milestone 2: Data model and ingestion
- [ ] `sources`, `articles`, `summaries`, `ingestion_runs` models (UUID, JSONB, indexes), initial migration
- [ ] Source registry and seed data; verify each publisher's feed and licensing
- [ ] RSS adapter with timeouts, retries and exponential backoff; per-source failure isolation
- [ ] Normalizer and validator; URL normalization
- [ ] Deduplicator: exact URL, normalized URL, content hash, headline similarity
- [ ] Scheduler worker (15-minute interval, overlap prevention, run metrics), compose `worker` service

## Milestone 3: Processing and AI
- [ ] Categorization, configurable importance ranking
- [ ] OpenAI summarizer: structured output, Pydantic validation, prompt-injection isolation,
      limited-content handling, retries/rate limits, usage and cost tracking

## Milestone 4: REST API
- [ ] Articles (filters, sort, pagination), top, detail, search, categories, sources, briefing
- [ ] Protected and rate-limited `POST /api/articles/{id}/summarize`

## Milestone 5: Frontend
- [ ] Daily briefing, category feeds, article detail, search, responsive navigation

## Milestone 6: End-to-end and hardening
- [ ] Full pipeline verification, coverage review, Docker/CI verification, docs pass
