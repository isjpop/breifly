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

## Milestone 3: Processing and AI ✅
- [x] Processing stage after ingestion in the worker, plus `flask process run`, with its own
      overlap lock
- [x] Rule-based categorizer, replaced by a validated AI category
- [x] Configurable weighted importance ranking, recomputed as articles age
- [x] Gemini summarizer (switched from OpenAI to use the free tier): structured output,
      Pydantic validation, one retry on invalid output, prompt-injection isolation,
      thin-content policy, retries/backoff, throttle, per-run budget, circuit breakers,
      attempt limits, usage and cost ledger, regeneration (CLI; API endpoint in Milestone 4)
- [x] Verified live against Gemini (`gemini-3.5-flash-lite`, 2026-11-15) on full-text and
      excerpt articles; bullets checked against source text. Prompt revised twice from what
      that review found (v2: "why it matters" must not use outside knowledge; v3: excerpts
      with at least one concrete fact are summarized, not declined).

## Milestone 4: REST API ✅
- [x] `GET /api/articles` (category, source, date range, importance/recency sort, pagination),
      `/top` (one per story), `/search` (full-text incl. AI entities and publisher), `/{id}`
      (full summary + related coverage)
- [x] `GET /api/categories`, `/api/sources`, `/api/briefing/today` (rolling window with
      fallback, top stories + per-category sections, last-updated time)
- [x] `POST /api/articles/{id}/summarize`: bearer auth (fails closed), global and per-article
      limits stored in the DB, per-article lock, single bounded provider call, previous summary
      kept on failure
- [x] Pydantic request validation, consistent envelope and status codes, safe-link output,
      UTC sessions, GIN search indexes (query plan tested)
- [x] OpenAPI 3.1 at `/api/openapi.json`, generated from response models; a test requires every
      route to be documented

## Milestone 5: Frontend ✅
- [x] Daily Briefing: date, last-updated time, lead story + top stories, per-category
      sections with "View all"
- [x] Category feeds: importance/latest sort, publisher filter, pagination (URL-driven)
- [x] Article detail: original headline and attribution, prominent link to the original, AI
      takeaways, why it matters, provenance, searchable entities, related coverage
- [x] Search: header and page search, web-search syntax hints, sort, pagination
- [x] Light/dark themes, responsive layout (verified at 1280 px and 390 px in both themes
      with real data), skeleton/empty/error states, accessibility basics
- [x] 51 frontend tests (95% coverage, thresholds enforced in CI)

## Milestone 6: End-to-end and hardening
- [ ] Full pipeline verification, coverage review, Docker/CI verification, docs pass

## Known limitations / backlog
- Rule-based categories lean toward Technology (56 of 97 live articles) until AI summaries
  replace them. The worker gets through the backlog at up to 40 summaries per tick.
- The API has no read-side rate limiting or caching yet. Add both at the reverse proxy if it
  is exposed publicly.
- Rule-based categories are a fallback and misfire on some headlines. They only remain where no
  AI summary exists.
- Three of six sources provide only excerpts, so their summaries have 1–3 points and are
  labelled as excerpt-based.
- Headline-overlap clustering is conservative and misses differently-worded coverage. Upgrade
  to embedding- or entity-based clustering (future enhancement 1).
- Reuters and AP require commercial licences before they can be integrated.
- CNBC sends no HTTP validators, so it is fully downloaded every run (~20 KB).
