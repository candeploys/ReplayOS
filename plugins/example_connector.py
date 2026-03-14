from replayos.connectors.base import BaseConnector


class ExampleConnector(BaseConnector):
    connector_id = "example"
    display_name = "Example Plugin Connector"

    def is_configured(self, env: dict[str, str]) -> bool:
        return env.get("EXAMPLE_CONNECTOR_ENABLED", "").strip().lower() in {"1", "true", "yes"}

    def pull_events(self, env: dict[str, str], limit: int = 20) -> list[dict]:
        return [
            {
                "source": "example_plugin",
                "title": "Example plugin event",
                "content": "This event comes from plugins/example_connector.py",
                "metadata": {"connector": self.connector_id},
            }
        ]


def build_connector() -> BaseConnector:
    return ExampleConnector()
