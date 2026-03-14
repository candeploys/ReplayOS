# ReplayOS Plugin SDK

ReplayOS supports connector plugins loaded from directories listed in:
- `plugins.directories` (config TOML)
- `REPLAYOS_PLUGIN_DIRS` (env, comma-separated)

## Plugin Contract

A plugin file must define:
- `build_connector() -> BaseConnector`

`BaseConnector` methods:
- `required_env_keys(self) -> tuple[str, ...]`
- `is_configured(env: dict[str, str]) -> bool`
- `pull_events(env: dict[str, str], limit: int = 20) -> list[dict]`
- `doctor(env: dict[str, str]) -> dict`

Each returned event should have:
- `source`
- `title`
- `content`
- optional `metadata`

## Built-in Plugin Examples

- `plugins/example_connector.py`
- `plugins/rss_connector.py`
- `plugins/local_json_connector.py`

## Validate Connector Setup

```bash
python3 -m replayos.cli --config config/replayos.toml --env .env connector-doctor
```

## Sync Plugin Data

```bash
python3 -m replayos.cli --config config/replayos.toml --env .env sync-connectors --limit 5
```

## Example Env Vars

```bash
EXAMPLE_CONNECTOR_ENABLED=true
RSS_CONNECTOR_FEED_URL=https://example.com/feed.xml
LOCAL_JSON_EVENTS_PATH=/absolute/path/events.json
```
