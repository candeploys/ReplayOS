# Capture Daemon (macOS)

ReplayOS includes an automatic capture daemon:
- detects frontmost application/window
- optionally captures screenshots
- ingests events into `/api/events`

Run:
```bash
python3 -m replayos.cli --config config/replayos.toml --env .env capture-daemon --interval 15
```

With screenshots:
```bash
python3 -m replayos.cli --config config/replayos.toml --env .env capture-daemon --capture-screenshot
```

Requirements:
- macOS
- `osascript` available
- for screenshots: `screencapture` utility (built-in)

Notes:
- daemon uses ReplayOS API key (`REPLAYOS_API_KEYS`)
- ensure server is running before starting daemon
