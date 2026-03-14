from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConnectorSyncResult:
    connector_id: str
    synced: int
    skipped: bool
    error: str | None = None


class BaseConnector:
    connector_id = "base"
    display_name = "Base Connector"

    def is_configured(self, env: dict[str, str]) -> bool:
        return False

    def pull_events(self, env: dict[str, str], limit: int = 20) -> list[dict]:
        raise NotImplementedError
