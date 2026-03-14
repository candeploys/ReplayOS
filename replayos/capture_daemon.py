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
    privacy_mode: bool = False,
    include_apps: tuple[str, ...] = (),
    exclude_apps: tuple[str, ...] = (),
) -> None:
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")

    api_base_url = api_base_url.rstrip("/")
    screenshot_dir = screenshot_dir or Path("captures")
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    print(f"Capture daemon started. Target API: {api_base_url}")
    print(f"Interval: {interval_seconds}s")
    print(f"Privacy mode: {'on' if privacy_mode else 'off'}")
    if include_apps:
        print(f"Include apps: {', '.join(include_apps)}")
    if exclude_apps:
        print(f"Exclude apps: {', '.join(exclude_apps)}")
    if capture_screenshot:
        print(f"Screenshots enabled: {screenshot_dir}")

    include_set = _normalize_app_filters(include_apps)
    exclude_set = _normalize_app_filters(exclude_apps)

    while True:
        try:
            payload, skipped_reason = _build_capture_event(
                capture_screenshot=capture_screenshot,
                screenshot_dir=screenshot_dir,
                privacy_mode=privacy_mode,
                include_apps=include_set,
                exclude_apps=exclude_set,
            )
            if payload is None:
                print(f"[{datetime.now(timezone.utc).isoformat()}] Capture skipped: {skipped_reason}")
                time.sleep(interval_seconds)
                continue
            _post_event(api_base_url=api_base_url, api_key=api_key, payload=payload)
            print(f"[{datetime.now(timezone.utc).isoformat()}] Captured: {payload['title']}")
        except Exception as exc:  # noqa: BLE001
            print(f"Capture error: {exc}")

        time.sleep(interval_seconds)


def _build_capture_event(
    capture_screenshot: bool,
    screenshot_dir: Path,
    privacy_mode: bool,
    include_apps: set[str],
    exclude_apps: set[str],
) -> tuple[dict | None, str | None]:
    app_name = _front_app_name() or "Unknown"
    app_key = app_name.strip().lower()
    if include_apps and app_key not in include_apps:
        return None, f"front app '{app_name}' is not in include list"
    if app_key in exclude_apps:
        return None, f"front app '{app_name}' is excluded"

    window_title = _front_window_title() or "(untitled window)"
    browser_url = _front_browser_url(app_name)

    metadata = {
        "connector": "capture_daemon",
        "front_app": app_name,
        "privacy_mode": bool(privacy_mode),
    }

    safe_window_title = "[redacted]" if privacy_mode else window_title
    metadata["window_title"] = safe_window_title

    content_parts = [f"Front app: {app_name}", f"Window: {safe_window_title}"]
    if browser_url and not privacy_mode:
        metadata["url"] = browser_url
        content_parts.append(f"URL: {browser_url}")
    elif browser_url and privacy_mode:
        content_parts.append("URL: [redacted]")

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
    }, None


def _front_app_name() -> str:
    return _run_osascript(
        'tell application "System Events" to get name of first application process whose frontmost is true'
    ).strip()


def _front_window_title() -> str:
    return _run_osascript(
        'tell application "System Events" to tell (first application process whose frontmost is true) to get name of front window'
    ).strip()


def _front_browser_url(app_name: str) -> str:
    scripts = {
        "safari": 'tell application "Safari" to get URL of front document',
        "google chrome": 'tell application "Google Chrome" to get URL of active tab of front window',
        "brave browser": 'tell application "Brave Browser" to get URL of active tab of front window',
        "microsoft edge": 'tell application "Microsoft Edge" to get URL of active tab of front window',
        "arc": 'tell application "Arc" to get URL of active tab of front window',
    }
    script = scripts.get(app_name.strip().lower())
    if not script:
        return ""
    return _run_osascript(script).strip()


def _normalize_app_filters(values: tuple[str, ...]) -> set[str]:
    cleaned: set[str] = set()
    for item in values:
        text = str(item).strip().lower()
        if text:
            cleaned.add(text)
    return cleaned


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
