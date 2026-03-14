# ReplayOS Architecture

ReplayOS is a local-first memory + safe-action runtime with production controls.

## Core Runtime

1. API Edge (`replayos/server.py`)
- Auth guard (API key)
- Rate limiting
- Request-size limits
- Static web UI serving
- Metrics and alert endpoints

2. Service Layer (`replayos/services.py`)
- Ingest/search/ask
- GhostRun actions + undo
- Data policy operations (export/delete/retention)
- Connector sync orchestration

3. Storage Layer (`replayos/db.py`)
- SQLite (WAL mode)
- FTS5 search with fallback
- Action ledger
- Backup/restore + vacuum utilities

4. Model Layer (`replayos/providers.py`)
- Local Qwen
- Claude API
- OpenAI API
- Retry/backoff and timeout

5. Observability (`replayos/metrics.py`, `replayos/observability.py`)
- Prometheus-compatible `/metrics`
- Error-rate alert state (`/api/admin/alerts`)
- Structured request logging

## Launch-Critical Features

- `run-bg/stop/status` process control
- launchd/systemd-user service install/uninstall
- DB backup/restore/migrate/vacuum commands
- E2E smoke test for auth/ask/action/undo/metrics/data policy

## Super-Project Layer

- Capture daemon (`replayos/capture_daemon.py`) for automatic timeline ingestion on macOS
- Connector SDK + built-in Gmail/Slack/Notion connectors
- Plugin loader from `plugins/`
- Browser dashboard (`web/`) for timeline, ask, actions, connectors, retention, metrics
- Demo pack (`scripts/demo_one_command.sh`, `demo/README.md`)

## Data Governance

- Export endpoint for portability
- Retention apply endpoint
- Delete endpoint with policy gate (`allow_full_delete`)

## Configuration Domains

- `[provider]`
- `[safety]`
- `[auth]`
- `[limits]`
- `[alerting]`
- `[data_policy]`
- `[plugins]`
