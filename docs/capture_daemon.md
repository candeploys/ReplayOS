# Capture Daemon (macOS)

ReplayOS includes an automatic capture daemon:
- detects frontmost app/window
- captures browser URL for supported browsers (Safari, Chrome, Brave, Edge, Arc)
- supports include/exclude app filters
- supports privacy mode (redacts title/URL)
- optionally captures screenshots
- ingests events into `/api/events`

## Run

```bash
python3 -m replayos.cli --config config/replayos.toml --env .env capture-daemon --interval 15
```

## Privacy Mode

```bash
python3 -m replayos.cli --config config/replayos.toml --env .env capture-daemon \
  --privacy-mode
```

## App Filtering

Only include specific apps:

```bash
python3 -m replayos.cli --config config/replayos.toml --env .env capture-daemon \
  --include-app "Google Chrome" --include-app "Terminal"
```

Exclude specific apps:

```bash
python3 -m replayos.cli --config config/replayos.toml --env .env capture-daemon \
  --exclude-app "1Password"
```

## Screenshots

```bash
python3 -m replayos.cli --config config/replayos.toml --env .env capture-daemon \
  --capture-screenshot --screenshot-dir captures
```

## Browser History Import

ReplayOS can import past browser visits to bootstrap timeline memory:

```bash
python3 -m replayos.cli --config config/replayos.toml --env .env import-browser-history \
  --browser all --limit 100 --since-days 30
```

Supported browser IDs:
- `safari`
- `chrome`
- `brave`
- `edge`
- `all`

## Requirements

- macOS
- `osascript`
- for screenshots: built-in `screencapture`
- API key in `REPLAYOS_API_KEYS`

## Notes

- ensure ReplayOS server is running before daemon/import commands
- if privacy mode is enabled, URL and window title are redacted before ingestion
