from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import json
import shutil
import sqlite3
import tempfile


@dataclass(frozen=True)
class BrowserSource:
    browser_id: str
    display_name: str
    db_path: Path


BROWSER_SOURCES: tuple[BrowserSource, ...] = (
    BrowserSource(
        browser_id="chrome",
        display_name="Google Chrome",
        db_path=Path("~/Library/Application Support/Google/Chrome/Default/History").expanduser(),
    ),
    BrowserSource(
        browser_id="brave",
        display_name="Brave",
        db_path=Path("~/Library/Application Support/BraveSoftware/Brave-Browser/Default/History").expanduser(),
    ),
    BrowserSource(
        browser_id="edge",
        display_name="Microsoft Edge",
        db_path=Path("~/Library/Application Support/Microsoft Edge/Default/History").expanduser(),
    ),
    BrowserSource(
        browser_id="safari",
        display_name="Safari",
        db_path=Path("~/Library/Safari/History.db").expanduser(),
    ),
)


def import_browser_history(
    api_base_url: str,
    api_key: str,
    browsers: tuple[str, ...] = ("all",),
    limit_per_browser: int = 100,
    since_days: int = 30,
    privacy_mode: bool = False,
) -> dict:
    if limit_per_browser <= 0:
        raise ValueError("limit_per_browser must be positive")
    if since_days <= 0:
        raise ValueError("since_days must be positive")

    selected = _select_browsers(browsers)
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)

    browser_reports: list[dict] = []
    imported_total = 0

    for source in selected:
        try:
            rows = _read_browser_rows(source, limit_per_browser)
            imported = 0
            for row in rows:
                visited_at = row["visited_at"]
                if visited_at < cutoff:
                    continue
                payload = _row_to_payload(source, row, privacy_mode=privacy_mode)
                _post_event(api_base_url=api_base_url, api_key=api_key, payload=payload)
                imported += 1
            browser_reports.append(
                {
                    "browser_id": source.browser_id,
                    "display_name": source.display_name,
                    "status": "ok",
                    "imported": imported,
                }
            )
            imported_total += imported
        except FileNotFoundError:
            browser_reports.append(
                {
                    "browser_id": source.browser_id,
                    "display_name": source.display_name,
                    "status": "skipped",
                    "imported": 0,
                    "error": f"history DB not found: {source.db_path}",
                }
            )
        except Exception as exc:  # noqa: BLE001
            browser_reports.append(
                {
                    "browser_id": source.browser_id,
                    "display_name": source.display_name,
                    "status": "error",
                    "imported": 0,
                    "error": str(exc),
                }
            )

    return {
        "ok": True,
        "imported_total": imported_total,
        "since_days": since_days,
        "limit_per_browser": limit_per_browser,
        "privacy_mode": privacy_mode,
        "browsers": browser_reports,
    }


def _select_browsers(raw: tuple[str, ...]) -> tuple[BrowserSource, ...]:
    normalized = {str(item).strip().lower() for item in raw if str(item).strip()}
    if not normalized or "all" in normalized:
        return BROWSER_SOURCES

    by_id = {item.browser_id: item for item in BROWSER_SOURCES}
    selected: list[BrowserSource] = []
    for item in normalized:
        if item not in by_id:
            raise ValueError(f"Unsupported browser: {item}")
        selected.append(by_id[item])

    selected.sort(key=lambda src: src.browser_id)
    return tuple(selected)


def _read_browser_rows(source: BrowserSource, limit: int) -> list[dict]:
    if not source.db_path.exists():
        raise FileNotFoundError(str(source.db_path))

    with tempfile.TemporaryDirectory() as tmp:
        local_db = Path(tmp) / f"{source.browser_id}-history.db"
        shutil.copy2(source.db_path, local_db)

        conn = sqlite3.connect(str(local_db))
        conn.row_factory = sqlite3.Row
        try:
            if source.browser_id == "safari":
                return _query_safari(conn, limit)
            return _query_chromium_family(conn, limit)
        finally:
            conn.close()


def _query_chromium_family(conn: sqlite3.Connection, limit: int) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT urls.url AS url, urls.title AS title, visits.visit_time AS visit_time
        FROM visits
        JOIN urls ON urls.id = visits.url
        ORDER BY visits.visit_time DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = []
    for record in cur.fetchall():
        url = str(record["url"] or "").strip()
        if not url:
            continue
        visit_raw = int(record["visit_time"] or 0)
        visited_at = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=visit_raw)
        rows.append(
            {
                "url": url,
                "title": str(record["title"] or "").strip(),
                "visited_at": visited_at,
            }
        )
    return rows


def _query_safari(conn: sqlite3.Connection, limit: int) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT hi.url AS url, hi.title AS title, hv.visit_time AS visit_time
        FROM history_visits hv
        JOIN history_items hi ON hi.id = hv.history_item
        ORDER BY hv.visit_time DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = []
    for record in cur.fetchall():
        url = str(record["url"] or "").strip()
        if not url:
            continue
        seconds = float(record["visit_time"] or 0.0)
        visited_at = datetime(2001, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds)
        rows.append(
            {
                "url": url,
                "title": str(record["title"] or "").strip(),
                "visited_at": visited_at,
            }
        )
    return rows


def _row_to_payload(source: BrowserSource, row: dict, privacy_mode: bool) -> dict:
    url = str(row.get("url", "")).strip()
    title = str(row.get("title", "")).strip()
    visited_at = row["visited_at"]

    host = urlparse(url).netloc or "unknown-host"
    safe_title = "[redacted]" if privacy_mode else (title or host)
    safe_url = "[redacted]" if privacy_mode else url

    metadata = {
        "connector": "browser_history_import",
        "browser_id": source.browser_id,
        "browser_name": source.display_name,
        "host": host,
        "url": safe_url,
        "privacy_mode": privacy_mode,
        "visited_at": visited_at.isoformat(),
    }

    content = "\n".join(
        [
            f"Browser: {source.display_name}",
            f"Title: {safe_title}",
            f"URL: {safe_url}",
            f"Visited at: {visited_at.isoformat()}",
        ]
    )

    return {
        "source": f"browser_history_{source.browser_id}",
        "title": f"Visited: {safe_title}"[:300],
        "content": content,
        "metadata": metadata,
    }


def _post_event(api_base_url: str, api_key: str, payload: dict) -> None:
    url = f"{api_base_url.rstrip('/')}/api/events"
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    req = Request(url, data=data, headers=headers, method="POST")

    try:
        with urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            parsed = json.loads(body)
            if not parsed.get("ok"):
                raise RuntimeError(f"ReplayOS ingest failed: {parsed}")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from exc
