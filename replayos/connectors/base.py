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

    def required_env_keys(self) -> tuple[str, ...]:
        return ()

    def is_configured(self, env: dict[str, str]) -> bool:
        return False

    def pull_events(self, env: dict[str, str], limit: int = 20) -> list[dict]:
        raise NotImplementedError

    def doctor(self, env: dict[str, str]) -> dict:
        required = list(self.required_env_keys())
        missing = [key for key in required if not str(env.get(key, "")).strip()]
        return {
            "id": self.connector_id,
            "name": self.display_name,
            "configured": self.is_configured(env),
            "required_env_keys": required,
            "missing_env_keys": missing,
        }
