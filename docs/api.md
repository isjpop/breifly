# API

Base path `/api`. All responses are JSON. A machine-readable OpenAPI 3.1 document is served at
**`GET /api/openapi.json`**. It is generated from the same Pydantic models the endpoints return,
and a test fails if any route is missing from it.

## Conventions

**Envelope**

```json
{ "data": ..., "meta": { ... } }
{ "error": { "code": "validation_error", "message": "Human-readable", "details": { "per_page": "..." } } }
```

**Status codes**

| Code | `error.code` | When |
| ---- | ------------ | ---- |
| 400 | `validation_error` | A query parameter is invalid. `details` maps each field to its problem |
| 400 | `invalid_id` | The path identifier is not a UUID |
| 401 | `unauthorized` | Admin endpoint without a valid bearer token |
| 403 | `admin_api_disabled` | Admin endpoint while `ADMIN_API_TOKEN` is unset |
| 404 | `not_found` | Unknown article or route |
| 405 | `method_not_allowed` | Wrong HTTP method |
| 409 | `conflict` | That article is already being regenerated |
| 429 | `rate_limited` | Regeneration limit or cooldown (see `Retry-After`) |
| 502 | `summary_failed` | The AI provider gave no valid summary (any previous summary is kept) |
| 503 | `database_unavailable`, `ai_unavailable`, `ai_rate_limited` | A dependency is down |
| 500 | `internal_error` | Unexpected error. Details are logged, never returned |

**Pagination:** `page` (1–1000, default 1) and `per_page` (1–100, default 20). Paged responses
include `meta.pagination = {page, per_page, total, total_pages}`.

**Unknown query parameters** are ignored (e.g. cache-busters). Known ones are strictly validated.

**Timestamps** are ISO 8601 in UTC. **Links** (`url`, `image_url`, `homepage_url`) are
emitted only when they are absolute `http(s)` URLs, otherwise `null`. The original publisher
is always included as `source`.

## Objects

**ArticleCard** (lists, top, search, briefing)

```json
{
  "id": "uuid",
  "title": "Original publisher headline",
  "url": "https://publisher.example/article",
  "source": { "slug": "the-verge", "name": "The Verge" },
  "author": "Jane Reporter",
  "published_at": "2026-11-14T21:44:44Z",
  "first_seen_at": "2026-11-14T22:07:54Z",
  "category": { "slug": "technology", "label": "Technology" },
  "importance_score": 7.53,
  "image_url": "https://cdn.example/thumb.jpg",
  "description": "Publisher teaser, up to 300 chars",
  "summary": {
    "status": "succeeded",
    "headline": "AI headline",
    "bullet_points": ["up to 3 on cards"],
    "why_it_matters": "One sentence.",
    "source_coverage": "article_text",
    "limitations": null
  },
  "related_count": 2
}
```

- `summary` is `null` until a summary has been attempted.
- `summary.status` is one of:
  - `succeeded`
  - `insufficient_content`: the feed has too little text; show `description` and `limitations` instead
  - `failed`
- `summary.source_coverage` is `article_text` (3–5 points) or `excerpt` (1–3 points, based on
  the publisher's teaser only).
- `related_count` is the number of other publishers' articles grouped into the same story.

**ArticleDetail** is an ArticleCard plus:
- `content_availability`
- `tags`
- the full `summary` (all bullets, plus `key_entities`, `model_name` and `generated_at`)
- `related`: a list of `{id, title, url, source, published_at}`

## Endpoints

### `GET /api/health`
`200 {"status":"ok","database":"ok"}`, or `503` with `"status":"degraded"` when the database is
unreachable.

### `GET /api/articles`
| Param | Values |
| ----- | ------ |
| `category` | `finance`, `technology`, `business`, `science`, `breaking_news` |
| `source` | Source slug(s), comma-separated or repeated |
| `from`, `to` | `YYYY-MM-DD` or ISO datetime. A bare `to` date includes that whole day. Applies to publication time (first-seen time when the feed had no date) |
| `sort` | `importance` (default) or `recent` |
| `page`, `per_page` | Pagination |

### `GET /api/articles/top`
The highest-ranked stories, **one per story**: when several publishers cover one event, only
the best-ranked article appears, with `related_count` set.
Params: `limit` (1–50, default 10) and `hours` (1–168, default 24).

### `GET /api/articles/search?q=`
Full-text search, English stemming. It covers:
- the headline, description and feed text
- the AI headline, takeaways, why-it-matters and **key entities**, so company and person names
  match even when the feed text is short
- the publisher name

`q` is 2–200 chars and supports web-search syntax: `"exact phrase"`, `-exclude`, `OR`.
`sort` is `relevance` (default) or `recent`. Paginated. Hostile input (SQL fragments, `%`,
tsquery operators) is treated as plain text.

### `GET /api/articles/{id}`
An ArticleDetail. Returns `400 invalid_id` for a malformed UUID and `404` if the article is unknown.

### `POST /api/articles/{id}/summarize` (admin)
Regenerates one article's summary synchronously and returns the ArticleDetail.

- **Auth:** `Authorization: Bearer $ADMIN_API_TOKEN`, compared in constant time. With no token
  configured the endpoint returns `403` (it fails closed).
- **Limits:**
  - at most `REGENERATE_MAX_PER_MINUTE` (default 5) per minute **across all API processes**,
    counted from the usage ledger in the database
  - a per-article cooldown of `REGENERATE_COOLDOWN_SECONDS` (default 60)
  - one regeneration at a time per article (`409`)
- **Provider call:** one attempt, no retries, with an `API_LLM_TIMEOUT_SECONDS` (25 s) timeout.
- **Failure:** `502`, and any previously valid summary is kept.

```bash
curl -X POST -H "Authorization: Bearer $ADMIN_API_TOKEN" \
  http://localhost:8000/api/articles/<uuid>/summarize
```

### `GET /api/categories`
All five categories, in display order, with `article_count` (articles first seen in the last 7 days).

### `GET /api/sources`
The configured publishers, each with `default_category`, `credibility_weight`, `is_active`,
`last_successful_fetch_at` and `last_fetch_status`. Fetch error messages are internal and are
not exposed.

### `GET /api/briefing/today`
```json
{
  "generated_at": "...",
  "last_updated_at": "end of the latest successful ingestion run",
  "window_start": "...",
  "window_hours": 24,
  "top_stories": [ArticleCard × ≤5],
  "sections": [{ "category": {"slug","label"}, "articles": [ArticleCard × ≤6] }]
}
```
- **"Today"** is a rolling 24 h window (`BRIEFING_WINDOW_HOURS`). If it holds fewer than 5
  stories, it widens to `BRIEFING_FALLBACK_WINDOW_HOURS` (72 h), and `window_hours` says which
  window was used.
- **Ranking:** top stories are ranked by importance, one per story.
- **Sections:** each section excludes the top stories and their related coverage, and empty
  sections are omitted.
