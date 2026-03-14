from __future__ import annotations

from pathlib import Path
import json

from replayos.connectors.base import BaseConnector


class LocalJSONConnector(BaseConnector):
    connector_id = "local_json"
    display_name = "Local JSON File"

    def required_env_keys(self) -> tuple[str, ...]:
        return ("LOCAL_JSON_EVENTS_PATH",)

    def is_configured(self, env: dict[str, str]) -> bool:
        path = env.get("LOCAL_JSON_EVENTS_PATH", "").strip()
        return bool(path and Path(path).expanduser().exists())

    def pull_events(self, env: dict[str, str], limit: int = 20) -> list[dict]:
        file_path = Path(env.get("LOCAL_JSON_EVENTS_PATH", "").strip()).expanduser()
        if not file_path.exists():
            return []

        payload = json.loads(file_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise RuntimeError("LOCAL_JSON_EVENTS_PATH must contain a JSON array")

        events: list[dict] = []
        for item in payload[:limit]:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source", self.connector_id)).strip() or self.connector_id
            title = str(item.get("title", "Local JSON event")).strip() or "Local JSON event"
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            metadata["connector"] = self.connector_id
            events.append(
                {
                    "source": source,
                    "title": title[:300],
                    "content": content,
                    "metadata": metadata,
                }
            )
        return events


def build_connector() -> BaseConnector:
    return LocalJSONConnector()
