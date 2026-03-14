# ReplayOS

ReplayOS is a local-first timeline memory and safe-action runtime.

It combines:
- memory: ingest, search, and recall of timeline events
- action: GhostRun preview, approval, execution, and undo
- operations: auth, rate limiting, metrics, data policy, backup/restore, and service management

---

## Table of Contents

- [What ReplayOS Solves](#what-replayos-solves)
- [Feature Set](#feature-set)
- [Architecture](#architecture)
- [Repository Structure](#repository-structure)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Run Modes](#run-modes)
- [Authentication](#authentication)
- [Web Dashboard](#web-dashboard)
- [API Usage](#api-usage)
- [Connectors and Plugin SDK](#connectors-and-plugin-sdk)
- [Capture Daemon (macOS)](#capture-daemon-macos)
- [Data Governance](#data-governance)
- [Observability and Alerts](#observability-and-alerts)
- [Database Operations](#database-operations)
- [Testing and CI](#testing-and-ci)
- [Docker Deployment](#docker-deployment)
- [Troubleshooting](#troubleshooting)
- [Security Notes](#security-notes)
- [Demo Pack](#demo-pack)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## What ReplayOS Solves

ReplayOS is designed for teams and power users who want:
- a searchable timeline of activity and events
- reliable AI answers grounded in local context
- safe automation with explicit execution controls
- production-friendly runtime operations

---

## Feature Set

### Launch-critical features

- process control: `run-bg`, `stop`, `status`
- service management: launchd (macOS) and systemd-user (Linux)
- API protection: API keys, rate limits, request-size guards
- metrics and alerts: Prometheus-compatible `/metrics`, alarm status endpoint
- data policy operations: export, retention apply, deletion (policy-gated)
- DB lifecycle: backup, restore, migrate, vacuum
- automated CI checks: unit tests + end-to-end smoke test

### Super-project layer

- automatic macOS capture daemon (privacy mode + include/exclude app filters)
- browser history bootstrap import (`safari/chrome/brave/edge`)
- built-in connectors: Gmail (IMAP), Slack, Notion
- connector plugin SDK + dynamic plugin loading + connector doctor
- browser dashboard with timeline filters, ask reference cards, connector sync runs, and GhostRun visibility
- one-command demo script + demo walkthrough

---

## Architecture

ReplayOS runtime layers:

1. API edge (`replayos/server.py`)
- auth
- rate limiting
- endpoint routing
- metrics and alert exposure
- web asset serving

2. service layer (`replayos/services.py`)
- ingest/search/ask
- GhostRun and undo
- connector sync
- data policy actions

3. storage layer (`replayos/db.py`)
- SQLite + WAL
- FTS5 search with fallback
- action ledger
- backup/restore primitives

4. provider layer (`replayos/providers.py`)
- Local Qwen
- Claude API
- OpenAI API
- retry/backoff/timeout

5. observability (`replayos/observability.py`, `replayos/metrics.py`)
- structured logs
- request counters + latency aggregates
- error-rate alert state

For detailed design docs:
- `docs/architecture.md`
- `docs/api.md`
- `docs/operations.md`

---

## Repository Structure

```text
replayos/
  .github/workflows/ci.yml
  config/
    replayos.config.example.toml
  demo/
    README.md
  docs/
    api.md
    architecture.md
    capture_daemon.md
    operations.md
    plugins.md
  plugins/
    example_connector.py
    local_json_connector.py
    rss_connector.py
  replayos/
    browser_history.py
    capture_daemon.py
    cli.py
    config.py
    connectors/
    db.py
    metrics.py
    providers.py
    security.py
    server.py
    service_manager.py
    services.py
    trust.py
  scripts/
    install.sh
    demo_one_command.sh
    run_bg.sh
    stop.sh
    status.sh
    service/
  tests/
    e2e_smoke.py
    test_*.py
  web/
    index.html
    app.js
    styles.css
```

---

## Requirements

- Python 3.11+
- macOS or Linux
- `make` (recommended)
- optional: Docker + Docker Compose

Provider-specific:
- Local Qwen: local Ollama-compatible endpoint
- Claude API: `ANTHROPIC_API_KEY`
- OpenAI API: `OPENAI_API_KEY`

---

## Installation

### 1) Clone repository

```bash
git clone https://github.com/candeploys/replayos.git
cd replayos
```

### 2) Run setup wizard

```bash
./scripts/install.sh
```

Wizard asks only:
- provider choice
- provider API key (if remote provider selected)

Everything else is written with production-safe defaults to:
- `config/replayos.toml`
- `.env`

### 3) Validate setup

```bash
make check
make doctor
```

### 4) Start server

```bash
make run
```

Open dashboard:
- `http://127.0.0.1:8787/`

---

## Configuration

Template file:
- `config/replayos.config.example.toml`

Main config groups:
- `[provider]`: model provider and model names
- `[safety]`: GhostRun and high-risk approval
- `[server]`: host and port
- `[auth]`: API key policy
- `[limits]`: request and query limits
- `[observability]`: log format and level
- `[runtime]`: environment and provider timeout
- `[alerting]`: error-rate alarm behavior
- `[data_policy]`: retention and full-delete policy
- `[plugins]`: plugin directories

`.env` keys:
- `REPLAYOS_API_KEYS`
- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `REPLAYOS_ENV`
- optional connector/plugin env vars (see below)

---

## Run Modes

### Foreground

```bash
make run
```

### Background

```bash
make run-bg
make status
make stop
```

### User service install (OS-managed)

```bash
make service-install
make service-status
make service-uninstall
```

macOS uses launchd.
Linux uses systemd user service.

---

## Authentication

All `/api/*` routes require API key by default.

Supported headers:
- `Authorization: Bearer <token>`
- `X-API-Key: <token>`

Generate new key:

```bash
python3 -m replayos.cli generate-api-key
```

Recommended after sharing key publicly:
- rotate key in `.env`
- restart service

---

## Web Dashboard

Route:
- `GET /`

Includes panels for:
- health/status
- alert state
- timeline recent items with source/time filters
- ask endpoint with clickable reference cards
- GhostRun note action + execute + last action state
- undo token action
- connector list + sync + doctor view
- connector sync run history
- export + retention apply
- metrics viewer

UI files:
- `web/index.html`
- `web/app.js`
- `web/styles.css`

---

## API Usage

### Health

```bash
curl -sS http://127.0.0.1:8787/health
```

### Ask

```bash
TOKEN='<REPLAYOS_API_KEY>'

curl -sS -X POST http://127.0.0.1:8787/api/ask \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question":"Summarize my timeline briefly","top_k":5}'
```

### Search

```bash
curl -sS "http://127.0.0.1:8787/api/search?q=ReplayOS&limit=10&source=demo" \
  -H "Authorization: Bearer $TOKEN"
```

### Recent timeline with filters

```bash
curl -sS "http://127.0.0.1:8787/api/events/recent?limit=25&source=slack&from_ts=2026-03-01T00:00:00Z" \
  -H "Authorization: Bearer $TOKEN"
```

### Fetch event by id

```bash
curl -sS "http://127.0.0.1:8787/api/events/by-id?id=1" \
  -H "Authorization: Bearer $TOKEN"
```

### GhostRun + execute + undo

```bash
curl -sS -X POST http://127.0.0.1:8787/api/actions/create-note \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Plan","body":"Draft release steps","dry_run":true}'

curl -sS -X POST http://127.0.0.1:8787/api/actions/create-note \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Plan","body":"Draft release steps","approved":true}'

curl -sS -X POST http://127.0.0.1:8787/api/actions/undo \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"undo_token":"<token>"}'
```

### Metrics and alarms

```bash
curl -sS http://127.0.0.1:8787/metrics
curl -sS http://127.0.0.1:8787/api/admin/alerts -H "Authorization: Bearer $TOKEN"
```

### Connector run history

```bash
curl -sS "http://127.0.0.1:8787/api/connectors/runs?limit=20" \
  -H "Authorization: Bearer $TOKEN"
```

### Data policy endpoints

```bash
curl -sS http://127.0.0.1:8787/api/data/export -H "Authorization: Bearer $TOKEN"

curl -sS -X POST http://127.0.0.1:8787/api/data/retention/apply \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"days":30}'

curl -sS -X POST http://127.0.0.1:8787/api/data/delete \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"before_ts":"2026-01-01T00:00:00+00:00"}'
```

Full endpoint reference:
- `docs/api.md`

---

## Connectors and Plugin SDK

### Built-in connectors

- Gmail (IMAP)
- Slack
- Notion

List and sync:

```bash
make list-connectors
make connector-doctor
make sync-connectors
```

Connector environment variables in `.env.example`:
- Gmail: `GMAIL_IMAP_USER`, `GMAIL_IMAP_APP_PASSWORD`, `GMAIL_IMAP_MAILBOX`
- Slack: `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID`
- Notion: `NOTION_API_KEY`

### Plugin SDK

- plugin docs: `docs/plugins.md`
- example plugin: `plugins/example_connector.py`
- rss plugin: `plugins/rss_connector.py`
- local json plugin: `plugins/local_json_connector.py`

A plugin provides `build_connector()` returning a `BaseConnector` implementation.

---

## Capture Daemon (macOS)

Run automatic foreground-window capture:

```bash
make capture-daemon
```

Privacy-first capture example:

```bash
python3 -m replayos.cli --config config/replayos.toml --env .env capture-daemon \
  --privacy-mode \
  --include-app "Google Chrome" \
  --exclude-app "1Password"
```

With screenshots:

```bash
python3 -m replayos.cli --config config/replayos.toml --env .env capture-daemon \
  --capture-screenshot --screenshot-dir captures
```

Bootstrap timeline from browser history:

```bash
make import-browser-history
```

Detailed notes:
- `docs/capture_daemon.md`

---

## Data Governance

ReplayOS supports three governance primitives:

1. export
- `GET /api/data/export`

2. retention apply
- `POST /api/data/retention/apply`

3. delete by policy
- `POST /api/data/delete`
- full delete is gated by `data_policy.allow_full_delete`

---

## Observability and Alerts

Metrics endpoint:
- `GET /metrics`

Important metrics:
- `replayos_http_requests_total`
- `replayos_http_request_duration_ms_sum`
- `replayos_http_request_duration_ms_count`
- `replayos_provider_errors_total`
- `replayos_error_rate_window`
- `replayos_alert_active`

Alert status endpoint:
- `GET /api/admin/alerts`

Configure in TOML:
- `[alerting].error_rate_threshold`
- `[alerting].error_window_seconds`
- `[alerting].min_requests_for_alarm`

---

## Database Operations

```bash
make backup
make migrate
make vacuum
```

Restore from backup:

```bash
make restore INPUT=backups/replayos-YYYYMMDDTHHMMSSZ.db
```

CLI equivalents:
- `python3 -m replayos.cli ... backup-db`
- `python3 -m replayos.cli ... restore-db --input ...`
- `python3 -m replayos.cli ... migrate-db`
- `python3 -m replayos.cli ... vacuum-db`

---

## Testing and CI

Run unit tests:

```bash
make test
```

Run end-to-end smoke test:

```bash
make e2e
```

CI:
- `.github/workflows/ci.yml`
- runs unit tests and e2e smoke on push/PR

---

## Docker Deployment

```bash
docker compose build
docker compose up -d
```

Container exposes:
- `127.0.0.1:8787`

---

## Troubleshooting

### Server seems stuck after `make run`

Expected behavior. `run` is foreground mode.
Use another terminal or run:

```bash
make run-bg
```

### `curl -s` returns nothing

Use `-sS` to show errors:

```bash
curl -sS http://127.0.0.1:8787/health
```

### TLS certificate errors on OpenAI/Claude

On macOS Python.org builds, install cert bundle:

```bash
/Applications/Python\ 3.14/Install\ Certificates.command
python3 -m pip install --upgrade certifi
```

### Unauthorized errors

- verify `REPLAYOS_API_KEYS` in `.env`
- pass `Authorization: Bearer <token>`
- restart service after key changes

### Connectors not syncing

- run `make list-connectors`
- run `make connector-doctor`
- confirm connector env vars are set
- run `make sync-connectors`
- inspect `GET /api/connectors/runs` for per-connector errors

---

## Security Notes

- rotate API keys regularly
- avoid committing `.env`
- prefer least-privilege credentials for connectors
- keep `allow_full_delete=false` for production
- place ReplayOS behind TLS reverse proxy when internet-facing

---

## Demo Pack

One-command local demo:

```bash
./scripts/demo_one_command.sh
```

Demo script details:
- `demo/README.md`

---

## Roadmap

- native ScreenCaptureKit-based capture daemon
- OAuth-first connector onboarding flows
- richer policy engine for action permissions
- managed deployment templates

---

## Contributing

1. fork repository
2. create feature branch
3. run `make test` and `make e2e`
4. open pull request

For larger additions, update relevant docs in `docs/`.

---

## Packaging

Create GitHub-ready zip:

```bash
./scripts/package_zip.sh
```

Output:
- `../replayos-github-ready.zip`

---

## License

MIT
