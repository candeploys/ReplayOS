from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import subprocess
import time
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


def run_capture_daemon(
    api_base_url: str,
    api_key: str,
    interval_seconds: int = 15,
    capture_screenshot: bool = False,
    screenshot_dir: Path | None = None,
) -> None:
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")

    api_base_url = api_base_url.rstrip("/")
    screenshot_dir = screenshot_dir or Path("captures")
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    print(f"Capture daemon started. Target API: {api_base_url}")
    print(f"Interval: {interval_seconds}s")
    if capture_screenshot:
        print(f"Screenshots enabled: {screenshot_dir}")

    while True:
        try:
            payload = _build_capture_event(capture_screenshot=capture_screenshot, screenshot_dir=screenshot_dir)
            _post_event(api_base_url=api_base_url, api_key=api_key, payload=payload)
            print(f"[{datetime.now(timezone.utc).isoformat()}] Captured: {payload['title']}")
        except Exception as exc:  # noqa: BLE001
            print(f"Capture error: {exc}")

        time.sleep(interval_seconds)


def _build_capture_event(capture_screenshot: bool, screenshot_dir: Path) -> dict:
    app_name = _run_osascript(
        'tell application "System Events" to get name of first application process whose frontmost is true'
    ).strip()
    window_title = _run_osascript(
        'tell application "System Events" to tell (first application process whose frontmost is true) to get name of front window'
    ).strip()

    browser_url = ""
    if app_name == "Safari":
        browser_url = _run_osascript('tell application "Safari" to get URL of front document').strip()
    elif app_name == "Google Chrome":
        browser_url = _run_osascript('tell application "Google Chrome" to get URL of active tab of front window').strip()

    metadata = {
        "connector": "capture_daemon",
        "front_app": app_name,
        "window_title": window_title,
    }

    if browser_url:
        metadata["url"] = browser_url

    content_parts = [f"Front app: {app_name}", f"Window: {window_title}"]
    if browser_url:
        content_parts.append(f"URL: {browser_url}")

    if capture_screenshot:
        file_name = f"capture-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.png"
        screenshot_path = screenshot_dir / file_name
        _run_command(["screencapture", "-x", str(screenshot_path)])
        metadata["screenshot_path"] = str(screenshot_path)

    return {
        "source": "capture_daemon",
        "title": f"Active window: {app_name}",
        "content": "\n".join(content_parts),
        "metadata": metadata,
    }


def _post_event(api_base_url: str, api_key: str, payload: dict) -> None:
    url = f"{api_base_url}/api/events"
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    req = Request(url, data=data, headers=headers, method="POST")

    try:
        with urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            parsed = json.loads(body)
            if not parsed.get("ok"):
                raise RuntimeError(f"ReplayOS ingest failed: {parsed}")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from exc


def _run_osascript(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _run_command(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)} :: {result.stderr.strip()}")
