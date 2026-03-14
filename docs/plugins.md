# ReplayOS Plugin SDK

ReplayOS supports connector plugins loaded from directories listed in:
- `plugins.directories` (config TOML)
- `REPLAYOS_PLUGIN_DIRS` (env, comma-separated)

## Plugin Contract

A plugin file must define:
- `build_connector() -> BaseConnector`

`BaseConnector` methods:
- `is_configured(env: dict[str, str]) -> bool`
- `pull_events(env: dict[str, str], limit: int = 20) -> list[dict]`

Each returned event should have:
- `source`
- `title`
- `content`
- optional `metadata`

## Example

See:
- `plugins/example_connector.py`

To enable example plugin:
```bash
export EXAMPLE_CONNECTOR_ENABLED=true
python3 -m replayos.cli --config config/replayos.toml --env .env list-connectors
python3 -m replayos.cli --config config/replayos.toml --env .env sync-connectors --limit 5
```
