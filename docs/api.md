# ReplayOS API Reference

Base URL: `http://127.0.0.1:8787`

## Authentication

All `/api/*` routes require API key by default.

Use one of:
- `Authorization: Bearer <token>`
- `X-API-Key: <token>`

## Public Endpoints

### `GET /health`
### `GET /livez`
### `GET /readyz`
Service health and runtime metadata.

### `GET /metrics`
Prometheus-style metrics output.

### `GET /`
Web UI dashboard.

## Timeline

### `POST /api/events`
Ingest timeline event.

Request:
```json
{
  "source": "manual",
  "title": "Launch Plan",
  "content": "Ship ReplayOS production baseline",
  "metadata": {"priority": "high"}
}
```

### `GET /api/events/recent?limit=20&source=demo&from_ts=...&to_ts=...`
Fetch latest events with optional filters:
- `source`
- `from_ts` (ISO8601)
- `to_ts` (ISO8601)

### `GET /api/events/by-id?id=123`
Fetch a single event by ID.

### `GET /api/search?q=...&limit=10&source=...&from_ts=...&to_ts=...`
Full-text timeline search with optional source/time filters.

## Ask

### `POST /api/ask`
Context-grounded QA over timeline.

Request:
```json
{"question":"Summarize my timeline briefly","top_k":5}
```

Response includes:
- `answer`
- `references`
- `retrieval_mode` (`search` or `recent_fallback`)
- `error` (provider/network issue)

## Actions

### `POST /api/actions/create-note`
GhostRun + execute path.

### `POST /api/actions/undo`
Undo by `undo_token`.

## Data Policy

### `GET /api/data/export?event_limit=10000&action_limit=10000`
Export events/actions/connector runs as JSON.

### `POST /api/data/delete`
Delete by cutoff timestamp or all (if policy allows).

Request examples:
```json
{"before_ts":"2026-03-01T00:00:00+00:00"}
```
```json
{"all":true}
```

### `POST /api/data/retention/apply`
Apply retention policy.

Request:
```json
{"days":30}
```

## Alerts and Metrics

### `GET /api/admin/alerts`
Current error-rate alarm status.

## Connectors

### `GET /api/connectors`
List connectors with:
- `configured`
- `required_env_keys`
- `missing_env_keys`
- `last_run`

### `POST /api/connectors/sync`
Sync configured connectors into timeline.

Request:
```json
{"limit_per_connector":20}
```

### `GET /api/connectors/runs?limit=20&connector_id=slack`
List recent connector sync runs, optionally filtered by connector.

## Status Codes

- `200` success
- `201` created
- `400` validation
- `401` auth failed
- `404` not found
- `409` policy conflict
- `413` request too large
- `429` rate limited
- `500` server error
