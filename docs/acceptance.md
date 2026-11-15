# MVP acceptance audit

Each MVP criterion from the project brief, with the evidence that it is met. "Live" means
verified against real publisher feeds, a real PostgreSQL database and the real Gemini API.
"CI" means verified by GitHub Actions. Audited 2026-11-15.

| # | Criterion | Status | Evidence |
| - | --------- | ------ | -------- |
| 1 | At least five news sources integrated | ✅ 6 | CNBC, Bloomberg, TechCrunch, The Verge, Ars Technica, MIT Technology Review. **Live:** a fresh-database run fetched all 6 (6/6 ok, 95 articles). Reuters and AP need commercial licences ([architecture.md](architecture.md#news-sources)). |
| 2 | Articles fetched automatically | ✅ | The `worker` service runs `ingest worker` every 15 min, with advisory-lock overlap prevention and graceful SIGTERM. **Live:** a worker tick ran sync → ingest → process and then stopped cleanly. Tests: `test_scheduler.py`, `test_cli.py`. |
| 3 | Normalized and stored in PostgreSQL | ✅ | `normalizer.py` strips HTML, validates URLs and dates, and caps lengths. Schema built through Alembic migrations, with a test that migrations match the models. Tests: `test_normalizer.py`, `test_pipeline.py`, `test_migrations.py`. |
| 4 | Duplicate articles detected | ✅ | Five levels: exact URL, normalized URL, GUID, content hash, headline similarity. **Live:** the second run stored 0 new articles, all 95 URLs are unique, and coverage of the same event from different outlets is grouped rather than deleted. Tests: `test_deduplicator.py`, `test_pipeline.py`. |
| 5 | Articles categorized | ✅ | Keyword rules for every article, then a validated AI category. **Live:** 95/95 categorized. Tests: `test_categorizer.py`, `test_summary_schema.py`. |
| 6 | Summaries contain 3–5 bullet points | ✅ *(deliberate refinement)* | Full-text articles: 3–5, enforced by validation. Excerpt-only feeds: 1–3, labelled "Excerpt", because padding a 150-character teaser to five points would mean inventing facts, which the brief forbids. Headline-only articles get no model call. Tests: `test_summary_schema.py`, `test_summarizer.py`. |
| 7 | Summaries saved and reused | ✅ | Stored in `summaries`; reads never call the LLM. Test `test_summaries_are_reused_not_regenerated`: a second run made 0 calls. |
| 8 | Articles ranked by importance | ✅ | A configurable weighted model: impact 35%, significance 30%, credibility 20%, recency 15%. Re-ranked every tick. Top stories put AI-assessed stories first and show one per story cluster. Tests: `test_ranking.py`, `test_processing.py`, `test_api_articles.py`. |
| 9 | Daily briefing endpoint works | ✅ | `GET /api/briefing/today`. **Live** over HTTP: 5 top stories, 5 sections and the last-updated time. **CI:** dev and production smoke tests. Tests: `test_api_articles.py`. |
| 10 | Frontend displays articles and summaries | ✅ | Briefing, category, article and search pages. **Live:** screenshots at 1280 px and 390 px, both themes, against real data; zero console errors under the production CSP. 52 frontend tests. |
| 11 | Category filtering works | ✅ | `?category=` in the API and `/category/:slug` in the UI. Tests: `test_api_articles.py::test_category_filter`, `CategoryPage.test.tsx`. |
| 12 | Original publication links work | ✅ | Every card and detail page links to the publisher in a new tab with `noopener noreferrer`, and URLs are validated on both server and client. Tests: `ArticleCard.test.tsx`, `ArticlePage.test.tsx`, `test_api_articles.py::test_cards_expose_safe_links…`. |
| 13 | Loading and error states | ✅ | Skeletons, empty states, and errors with retry on every data view. Tests cover each state on every page. |
| 14 | Backend and frontend tests pass | ✅ | Backend: 234 tests, 95.6% coverage (CI requires 80%). Frontend: 52 tests, 95% coverage (CI requires 80% lines / 75% branches). Lint and type checks clean on both. |
| 15 | Docker Compose starts the dev environment | ✅ (CI) | **CI:** images build, `docker compose up --wait db backend`, health, source sync, processing and the briefing endpoint. The production stack (nginx, SPA, proxy, CSP) smoke test was added in Milestone 6 and is verified on the next push. Docker is not installed on the development machine. |
| 16 | GitHub Actions runs successfully | ✅ | Phases 1–4 passed all jobs (backend, frontend, docker); Phase 5 was in progress at audit time. |
| 17 | README explains setup and usage | ✅ | [README.md](../README.md), [development.md](development.md), [api.md](api.md). |

Criterion 18 in the brief, the end-to-end pipeline, was verified **live** on an empty database:
publisher feeds → fetch → normalize → deduplicate → categorize → rank → Gemini summaries →
PostgreSQL → Flask API → Vite proxy → React dashboard, through the real worker code path.

## Security checklist (brief §14)

| Requirement | Implementation |
| ----------- | -------------- |
| Credentials in env vars, never committed | `.env` gitignored; `.env.example` documents every variable; the API key is a `SecretStr` (masked in logs) |
| Validate external responses | Feeds are size-capped and parse-checked; LLM output is schema-validated before storage |
| Transactions | One transaction per source; savepoints per insert; per-article commits in processing |
| Timeouts and retries with backoff | Feeds and the LLM both; `Retry-After` honoured; config errors not retried |
| Prevent duplicate ingestion | Five-level dedup plus a unique constraint on the normalized URL |
| Indexes, pagination | B-tree, expression and GIN full-text indexes (query plan tested); all lists paginated |
| Limit AI requests | Throttle, per-run budget, circuit breakers, attempt cap, admin-only regeneration with database-backed rate limits |
| Log failures, no internal errors to users | Structured logging; generic error envelope; provider and DB details never returned |
| Validate external URLs before rendering | http(s)-only, checked on server output and again in the client |
| Article text not interpreted as instructions | JSON-encoded, `<`-escaped `<article>` block; untrusted-data system rule; no tools; strict schema |
| External links distinct from app routes | ↗ marker, new tab, `noopener noreferrer`, screen-reader note |
| Usable during outages | One publisher failing doesn't affect the others; AI outages leave articles readable with publisher descriptions |
| Web hardening | Strict CSP (`script-src 'self'`), nosniff, frame denial, referrer policy on API and web; 16 KB request cap; production config refuses default DB URL or short admin token |
