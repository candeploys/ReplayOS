from pathlib import Path
import tempfile
import unittest

from replayos.config import (
    AlertingConfig,
    AppConfig,
    AuthConfig,
    DataPolicyConfig,
    LimitsConfig,
    ObservabilityConfig,
    PluginConfig,
    ProviderConfig,
    RuntimeConfig,
    SafetyConfig,
    ServerConfig,
)
from replayos.db import ReplayDB
from replayos.providers import BaseProvider, ProviderResponse
from replayos.services import ReplayService


class DummyProvider(BaseProvider):
    name = "dummy"

    def generate(self, prompt: str) -> ProviderResponse:
        return ProviderResponse(provider="dummy", model="dummy", text="ok", error=None)


class ServiceTests(unittest.TestCase):
    def test_create_note_and_undo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = ReplayDB(root / "replayos.db")
            cfg = AppConfig(
                provider=ProviderConfig(
                    default="local_qwen",
                    local_base_url="http://localhost:11434",
                    local_model="qwen",
                    claude_model="claude",
                    openai_model="gpt",
                ),
                safety=SafetyConfig(require_ghost_run=True, require_approval_for_high_risk=True),
                server=ServerConfig(host="127.0.0.1", port=8787),
                auth=AuthConfig(require_api_key=True, allow_localhost_without_key=False, api_keys=("k",)),
                limits=LimitsConfig(
                    max_request_bytes=1_048_576,
                    default_search_limit=10,
                    max_search_limit=100,
                    default_recent_limit=20,
                    max_recent_limit=200,
                    default_top_k=5,
                    max_top_k=20,
                    rate_limit_requests=120,
                    rate_limit_window_seconds=60,
                ),
                observability=ObservabilityConfig(log_level="INFO", log_json=True),
                runtime=RuntimeConfig(environment="test", provider_timeout_seconds=10),
                alerting=AlertingConfig(error_rate_threshold=0.2, error_window_seconds=300, min_requests_for_alarm=20),
                data_policy=DataPolicyConfig(default_retention_days=30, allow_full_delete=True),
                plugins=PluginConfig(directories=()),
                anthropic_api_key="",
                openai_api_key="",
            )
            service = ReplayService(db=db, provider=DummyProvider(), config=cfg, notes_dir=root / "notes")

            preview = service.create_note("Title", "Body", dry_run=True, approved=False)
            self.assertTrue(preview["ok"])
            self.assertTrue(preview["dry_run"])

            executed = service.create_note("Title", "Body", dry_run=False, approved=True)
            self.assertTrue(executed["ok"])
            self.assertIn("undo_token", executed)

            undone = service.undo(executed["undo_token"])
            self.assertTrue(undone["ok"])

            db.close()

    def test_ask_falls_back_to_recent_when_search_misses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = ReplayDB(root / "replayos.db")
            cfg = AppConfig(
                provider=ProviderConfig(
                    default="local_qwen",
                    local_base_url="http://localhost:11434",
                    local_model="qwen",
                    claude_model="claude",
                    openai_model="gpt",
                ),
                safety=SafetyConfig(require_ghost_run=True, require_approval_for_high_risk=True),
                server=ServerConfig(host="127.0.0.1", port=8787),
                auth=AuthConfig(require_api_key=True, allow_localhost_without_key=False, api_keys=("k",)),
                limits=LimitsConfig(
                    max_request_bytes=1_048_576,
                    default_search_limit=10,
                    max_search_limit=100,
                    default_recent_limit=20,
                    max_recent_limit=200,
                    default_top_k=5,
                    max_top_k=20,
                    rate_limit_requests=120,
                    rate_limit_window_seconds=60,
                ),
                observability=ObservabilityConfig(log_level="INFO", log_json=True),
                runtime=RuntimeConfig(environment="test", provider_timeout_seconds=10),
                alerting=AlertingConfig(error_rate_threshold=0.2, error_window_seconds=300, min_requests_for_alarm=20),
                data_policy=DataPolicyConfig(default_retention_days=30, allow_full_delete=True),
                plugins=PluginConfig(directories=()),
                anthropic_api_key="",
                openai_api_key="",
            )
            service = ReplayService(db=db, provider=DummyProvider(), config=cfg, notes_dir=root / "notes")
            service.ingest_event(
                source="demo",
                title="Sprint Update",
                content="Completed onboarding and fixed timeline indexing.",
                metadata={},
            )

            result = service.ask("summarize my timeline briefly", top_k=5)
            self.assertEqual(result["retrieval_mode"], "recent_fallback")
            self.assertGreaterEqual(len(result["references"]), 1)
            db.close()


if __name__ == "__main__":
    unittest.main()
