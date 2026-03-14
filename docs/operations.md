# ReplayOS Operations Guide

## Process Control

```bash
make run-bg
make status
make stop
```

## Service Management

User-level service install (auto-detect launchd/systemd-user):

```bash
make service-install
make service-status
make service-uninstall
```

Equivalent scripts:
- `scripts/service/install.sh`
- `scripts/service/status.sh`
- `scripts/service/uninstall.sh`

## Database Lifecycle

```bash
make backup
make migrate
make vacuum
```

Restore:

```bash
make restore INPUT=backups/replayos-YYYYMMDDTHHMMSSZ.db
```

## Data Governance

- Export: `GET /api/data/export`
- Retention: `POST /api/data/retention/apply`
- Delete: `POST /api/data/delete`

## Monitoring

- Metrics endpoint: `GET /metrics`
- Alert status: `GET /api/admin/alerts`

Recommended watches:
- `replayos_alert_active`
- `replayos_error_rate_window`
- `replayos_provider_errors_total`

## Connector Operations

List connectors:
```bash
make list-connectors
```

Validate connector configuration:
```bash
make connector-doctor
```

Sync connectors:
```bash
make sync-connectors
```

Read connector run history:
```bash
curl -sS http://127.0.0.1:8787/api/connectors/runs?limit=20 \
  -H "Authorization: Bearer <token>"
```

## Capture and Timeline Ingestion

Run capture daemon (macOS):
```bash
make capture-daemon
```

Run capture daemon with privacy mode and app filtering:
```bash
python3 -m replayos.cli --config config/replayos.toml --env .env capture-daemon \
  --privacy-mode \
  --include-app "Google Chrome" \
  --exclude-app "1Password"
```

Import browser history:
```bash
make import-browser-history
```

Direct CLI example:
```bash
python3 -m replayos.cli --config config/replayos.toml --env .env import-browser-history \
  --browser safari --browser chrome --limit 200 --since-days 14
```
