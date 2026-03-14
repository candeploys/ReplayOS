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

List configured connectors:
```bash
make list-connectors
```

Sync connectors:
```bash
make sync-connectors
```

## Capture Daemon

Run daemon (macOS):
```bash
make capture-daemon
```

Or with screenshots:
```bash
python3 -m replayos.cli --config config/replayos.toml --env .env capture-daemon --capture-screenshot
```
