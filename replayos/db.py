from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
import json
import shutil
import sqlite3


DB_SCHEMA_VERSION = 1


@dataclass
class EventRecord:
    id: int
    ts: str
    source: str
    title: str
    content: str
    metadata: dict


class ReplayDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.fts_enabled = True
        self._configure_pragmas()
        self._init_schema()

    def _configure_pragmas(self) -> None:
        cur = self.conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        self.conn.commit()

    def _init_schema(self) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER NOT NULL
            )
            """
        )
        cur.execute("SELECT COUNT(*) AS n FROM schema_version")
        row = cur.fetchone()
        if int(row["n"]) == 0:
            cur.execute("INSERT INTO schema_version(version) VALUES (?)", (DB_SCHEMA_VERSION,))
        else:
            cur.execute("UPDATE schema_version SET version = ?", (DB_SCHEMA_VERSION,))

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_source ON events(source)")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                action_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                undo_token TEXT NOT NULL UNIQUE
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_actions_ts ON actions(ts DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_actions_status ON actions(status)")

        try:
            cur.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
                    title,
                    content,
                    content='events',
                    content_rowid='id'
                )
                """
            )
            cur.execute(
                """
                CREATE TRIGGER IF NOT EXISTS events_ai AFTER INSERT ON events BEGIN
                    INSERT INTO events_fts(rowid, title, content)
                    VALUES (new.id, new.title, new.content);
                END;
                """
            )
            cur.execute(
                """
                CREATE TRIGGER IF NOT EXISTS events_ad AFTER DELETE ON events BEGIN
                    INSERT INTO events_fts(events_fts, rowid, title, content)
                    VALUES ('delete', old.id, old.title, old.content);
                END;
                """
            )
            cur.execute(
                """
                CREATE TRIGGER IF NOT EXISTS events_au AFTER UPDATE ON events BEGIN
                    INSERT INTO events_fts(events_fts, rowid, title, content)
                    VALUES ('delete', old.id, old.title, old.content);
                    INSERT INTO events_fts(rowid, title, content)
                    VALUES (new.id, new.title, new.content);
                END;
                """
            )
        except sqlite3.OperationalError:
            self.fts_enabled = False

        self.conn.commit()

    def get_schema_version(self) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT version FROM schema_version LIMIT 1")
        row = cur.fetchone()
        return int(row["version"]) if row else DB_SCHEMA_VERSION

    def close(self) -> None:
        self.conn.close()

    def backup_to(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        dest = sqlite3.connect(str(output_path))
        try:
            self.conn.backup(dest)
        finally:
            dest.close()

    def restore_from_file(self, input_path: Path) -> None:
        if not input_path.exists():
            raise FileNotFoundError(f"Backup file not found: {input_path}")
        self.close()
        shutil.copy2(input_path, self.db_path)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.fts_enabled = True
        self._configure_pragmas()
        self._init_schema()

    def vacuum(self) -> None:
        self.conn.execute("VACUUM")
        self.conn.commit()

    def insert_event(
        self,
        source: str,
        title: str,
        content: str,
        metadata: dict | None = None,
    ) -> int:
        source = source.strip()
        title = title.strip()
        content = content.strip()
        if not source or not title or not content:
            raise ValueError("source, title, and content are required")

        ts = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(metadata or {}, ensure_ascii=True)

        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO events (ts, source, title, content, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ts, source, title, content, payload),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def search_events(self, query: str, limit: int = 10) -> list[EventRecord]:
        query = query.strip()
        if not query:
            return []

        cur = self.conn.cursor()
        if self.fts_enabled:
            try:
                cur.execute(
                    """
                    SELECT e.id, e.ts, e.source, e.title, e.content, e.metadata_json,
                           bm25(events_fts) AS rank
                    FROM events_fts
                    JOIN events e ON e.id = events_fts.rowid
                    WHERE events_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (query, limit),
                )
            except sqlite3.OperationalError:
                self._search_like(cur, query, limit)
        else:
            self._search_like(cur, query, limit)

        return self._rows_to_events(cur.fetchall())

    def _search_like(self, cur: sqlite3.Cursor, query: str, limit: int) -> None:
        wildcard = f"%{query}%"
        cur.execute(
            """
            SELECT id, ts, source, title, content, metadata_json
            FROM events
            WHERE title LIKE ? OR content LIKE ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            (wildcard, wildcard, limit),
        )

    def recent_events(self, limit: int = 20) -> list[EventRecord]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT id, ts, source, title, content, metadata_json
            FROM events
            ORDER BY ts DESC
            LIMIT ?
            """,
            (limit,),
        )
        return self._rows_to_events(cur.fetchall())

    def export_data(self, event_limit: int = 10_000, action_limit: int = 10_000) -> dict:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT id, ts, source, title, content, metadata_json
            FROM events
            ORDER BY ts DESC
            LIMIT ?
            """,
            (event_limit,),
        )
        events = [
            {
                "id": int(r["id"]),
                "ts": str(r["ts"]),
                "source": str(r["source"]),
                "title": str(r["title"]),
                "content": str(r["content"]),
                "metadata": json.loads(str(r["metadata_json"] or "{}")),
            }
            for r in cur.fetchall()
        ]

        cur.execute(
            """
            SELECT id, ts, action_type, payload_json, status, undo_token
            FROM actions
            ORDER BY ts DESC
            LIMIT ?
            """,
            (action_limit,),
        )
        actions = [
            {
                "id": int(r["id"]),
                "ts": str(r["ts"]),
                "action_type": str(r["action_type"]),
                "payload": json.loads(str(r["payload_json"] or "{}")),
                "status": str(r["status"]),
                "undo_token": str(r["undo_token"]),
            }
            for r in cur.fetchall()
        ]

        return {
            "schema_version": self.get_schema_version(),
            "event_count": len(events),
            "action_count": len(actions),
            "events": events,
            "actions": actions,
        }

    def delete_before(self, before_ts: str) -> dict:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM events WHERE ts < ?", (before_ts,))
        deleted_events = int(cur.rowcount)
        cur.execute("DELETE FROM actions WHERE ts < ?", (before_ts,))
        deleted_actions = int(cur.rowcount)
        self.conn.commit()
        return {"deleted_events": deleted_events, "deleted_actions": deleted_actions}

    def delete_all(self) -> dict:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM events")
        deleted_events = int(cur.rowcount)
        cur.execute("DELETE FROM actions")
        deleted_actions = int(cur.rowcount)
        self.conn.commit()
        return {"deleted_events": deleted_events, "deleted_actions": deleted_actions}

    def log_action(self, action_type: str, payload: dict, status: str, undo_token: str) -> int:
        ts = datetime.now(timezone.utc).isoformat()
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO actions (ts, action_type, payload_json, status, undo_token)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ts, action_type, json.dumps(payload, ensure_ascii=True), status, undo_token),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def update_action_status(self, undo_token: str, status: str) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            UPDATE actions
            SET status = ?
            WHERE undo_token = ?
            """,
            (status, undo_token),
        )
        self.conn.commit()

    def get_action_by_undo_token(self, undo_token: str) -> dict | None:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT id, ts, action_type, payload_json, status, undo_token
            FROM actions
            WHERE undo_token = ?
            LIMIT 1
            """,
            (undo_token,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": int(row["id"]),
            "ts": str(row["ts"]),
            "action_type": str(row["action_type"]),
            "payload": json.loads(str(row["payload_json"])),
            "status": str(row["status"]),
            "undo_token": str(row["undo_token"]),
        }

    def _rows_to_events(self, rows: list[sqlite3.Row]) -> list[EventRecord]:
        return [
            EventRecord(
                id=int(row["id"]),
                ts=str(row["ts"]),
                source=str(row["source"]),
                title=str(row["title"]),
                content=str(row["content"]),
                metadata=json.loads(str(row["metadata_json"] or "{}")),
            )
            for row in rows
        ]
