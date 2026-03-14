from pathlib import Path
import tempfile
import unittest

from replayos.config import load_config


BASE_CONFIG = """
[provider]
default = "local_qwen"

[provider.local_qwen]
base_url = "http://localhost:11434"
model = "qwen2.5:7b"

[provider.claude_api]
model = "claude-sonnet-4"

[provider.openai_api]
model = "gpt-5-mini"

[safety]
require_ghost_run = true
require_approval_for_high_risk = true

[server]
host = "127.0.0.1"
port = 8787

[auth]
require_api_key = true
allow_localhost_without_key = false
api_keys = []

[limits]
max_request_bytes = 1048576
default_search_limit = 10
max_search_limit = 100
default_recent_limit = 20
max_recent_limit = 200
default_top_k = 5
max_top_k = 20
rate_limit_requests = 120
rate_limit_window_seconds = 60

[observability]
log_level = "INFO"
log_json = true

[runtime]
environment = "production"
provider_timeout_seconds = 60
""".strip()


class ConfigTests(unittest.TestCase):
    def test_load_config_with_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = root / "replayos.toml"
            env = root / ".env"

            cfg.write_text(BASE_CONFIG, encoding="utf-8")
            env.write_text("REPLAYOS_API_KEYS=test-key\n", encoding="utf-8")

            loaded = load_config(cfg, env)
            self.assertEqual(loaded.provider.default, "local_qwen")
            self.assertEqual(loaded.auth.api_keys, ("test-key",))
            self.assertTrue(loaded.auth.require_api_key)
            self.assertGreater(loaded.data_policy.default_retention_days, 0)
            self.assertGreater(loaded.alerting.error_rate_threshold, 0)

    def test_load_config_requires_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = root / "replayos.toml"
            env = root / ".env"

            cfg.write_text(BASE_CONFIG, encoding="utf-8")
            env.write_text("", encoding="utf-8")

            with self.assertRaises(ValueError):
                load_config(cfg, env)


if __name__ == "__main__":
    unittest.main()
