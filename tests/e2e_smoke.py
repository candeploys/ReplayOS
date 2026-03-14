from __future__ import annotations

from pathlib import Path
import json
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def write_config(path: Path, port: int) -> None:
    path.write_text(
        f"""
[provider]
default = "local_qwen"

[provider.local_qwen]
base_url = "http://127.0.0.1:9"
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
port = {port}

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
rate_limit_requests = 500
rate_limit_window_seconds = 60

[observability]
log_level = "INFO"
log_json = false

[runtime]
environment = "test"
provider_timeout_seconds = 2

[alerting]
error_rate_threshold = 0.20
error_window_seconds = 300
min_requests_for_alarm = 1

[data_policy]
default_retention_days = 30
allow_full_delete = true

[plugins]
directories = []
""".strip(),
        encoding="utf-8",
    )


def write_env(path: Path) -> str:
    token = "e2e-token"
    path.write_text(
        f"""REPLAYOS_API_KEYS={token}
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
REPLAYOS_ENV=test
""",
        encoding="utf-8",
    )
    return token


def http_json(method: str, url: str, token: str | None = None, payload: dict | None = None) -> tuple[int, dict]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        headers["Content-Type"] = "application/json"

    req = Request(url, data=body, method=method, headers=headers)
    try:
        with urlopen(req, timeout=10) as res:
            text = res.read().decode("utf-8")
            return res.status, json.loads(text)
    except HTTPError as exc:
        text = exc.read().decode("utf-8")
        return exc.code, json.loads(text)


def http_text(url: str) -> tuple[int, str]:
    req = Request(url, method="GET")
    with urlopen(req, timeout=10) as res:
        return res.status, res.read().decode("utf-8")


def wait_health(base_url: str, timeout_seconds: int = 15) -> None:
    started = time.time()
    while time.time() - started < timeout_seconds:
        try:
            status, _ = http_json("GET", f"{base_url}/health")
            if status == 200:
                return
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.2)
    raise RuntimeError("server did not become healthy in time")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cfg = root / "replayos.toml"
        env = root / ".env"
        db = root / "replayos.db"
        notes = root / "notes"
        port = free_port()
        base = f"http://127.0.0.1:{port}"

        write_config(cfg, port)
        token = write_env(env)

        cmd = [
            sys.executable,
            "-m",
            "replayos.cli",
            "--config",
            str(cfg),
            "--env",
            str(env),
            "--db",
            str(db),
            "--notes-dir",
            str(notes),
            "run",
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        try:
            wait_health(base)

            status, _ = http_json("GET", f"{base}/api/search?q=test")
            assert status == 401, f"expected 401 for unauth search, got {status}"

            status, payload = http_json(
                "POST",
                f"{base}/api/events",
                token=token,
                payload={
                    "source": "e2e",
                    "title": "E2E Event",
                    "content": "ReplayOS smoke test event",
                    "metadata": {"test": True},
                },
            )
            assert status == 201 and payload.get("ok") is True
            event_id = int(payload.get("id", 0))
            assert event_id > 0

            status, payload = http_json("GET", f"{base}/api/search?q=ReplayOS", token=token)
            assert status == 200 and isinstance(payload.get("items"), list)

            status, payload = http_json("GET", f"{base}/api/search?q=ReplayOS&source=e2e", token=token)
            assert status == 200 and isinstance(payload.get("items"), list)

            status, payload = http_json("GET", f"{base}/api/events/recent?source=e2e&limit=5", token=token)
            assert status == 200 and isinstance(payload.get("items"), list)

            status, payload = http_json("GET", f"{base}/api/events/by-id?id={event_id}", token=token)
            assert status == 200 and payload.get("ok") is True and payload.get("event", {}).get("id") == event_id

            status, payload = http_json(
                "POST",
                f"{base}/api/ask",
                token=token,
                payload={"question": "Summarize", "top_k": 3},
            )
            assert status == 200 and payload.get("ok") is True

            status, payload = http_json("GET", f"{base}/api/connectors", token=token)
            assert status == 200 and payload.get("ok") is True

            status, payload = http_json("GET", f"{base}/api/connectors/runs?limit=5", token=token)
            assert status == 200 and payload.get("ok") is True and isinstance(payload.get("runs"), list)

            status, payload = http_json(
                "POST",
                f"{base}/api/actions/create-note",
                token=token,
                payload={"title": "E2E", "body": "Dry run", "dry_run": True},
            )
            assert status == 200 and payload.get("ok") is True and payload.get("dry_run") is True

            status, payload = http_json(
                "POST",
                f"{base}/api/actions/create-note",
                token=token,
                payload={"title": "E2E", "body": "Execute", "approved": True},
            )
            assert status == 200 and payload.get("ok") is True
            undo_token = payload.get("undo_token")
            assert isinstance(undo_token, str) and undo_token

            status, payload = http_json(
                "POST",
                f"{base}/api/actions/undo",
                token=token,
                payload={"undo_token": undo_token},
            )
            assert status == 200 and payload.get("ok") is True

            status, payload = http_json("GET", f"{base}/api/data/export", token=token)
            assert status == 200 and payload.get("ok") is True and "events" in payload

            status, payload = http_json(
                "POST",
                f"{base}/api/data/retention/apply",
                token=token,
                payload={"days": 3650},
            )
            assert status == 200 and payload.get("ok") is True

            status, payload = http_json("GET", f"{base}/api/admin/alerts", token=token)
            assert status == 200 and payload.get("ok") is True

            status, metrics_text = http_text(f"{base}/metrics")
            assert status == 200 and "replayos_http_requests_total" in metrics_text

            print("E2E smoke test passed")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    main()
