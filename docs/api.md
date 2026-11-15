# API

Base path: `/api`. All responses are JSON.

**Envelope**

```json
{ "data": {}, "meta": {} }
{ "error": { "code": "not_found", "message": "Human-readable message" } }
```

## Endpoints

### `GET /api/health`
Liveness and database readiness.

| Status | Meaning                                       |
| ------ | --------------------------------------------- |
| 200    | `{"status":"ok","database":"ok","timestamp"}` |
| 503    | `{"status":"degraded","database":"unavailable",...}` |

Endpoints for articles, categories, sources, briefing and summary regeneration are added in
Milestone 4 and will be documented here as they land.
