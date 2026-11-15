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

## Milestone 2: Data model and ingestion ✅
- [x] `sources`, `articles`, `summaries`, `story_clusters`, `ingestion_runs` (UUID PKs, JSONB,
      CHECK-constrained enums, indexes) and initial migration with a model/migration drift test
- [x] Six publisher integrations verified live: CNBC, Bloomberg, TechCrunch, The Verge,
      Ars Technica, MIT Technology Review. Reuters/AP documented as licence-only.
- [x] Feed fetcher: timeouts, retry with exponential backoff + `Retry-After`, conditional GET,
      size cap. Per-source failure isolation.
- [x] Normalizer/validator: HTML stripped, URL safety, date sanity, content-availability level
- [x] Deduplicator: exact URL, normalized URL, GUID, content hash, headline similarity.
      Cross-source related coverage grouped into story clusters.
- [x] Worker (fixed 15-min rate, advisory-lock overlap prevention, graceful SIGTERM), run
      metrics, CLI, compose `worker` service

## Milestone 3: Processing and AI
- [ ] Processing stage in the worker: pick up `pending` articles after ingestion
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

## Known limitations / backlog
- Headline-overlap clustering is conservative and misses differently-worded coverage. Upgrade
  to embedding- or entity-based clustering (future enhancement 1).
- Reuters and AP require commercial licences before they can be integrated.
- CNBC sends no HTTP validators, so it is fully downloaded every run (~20 KB).
