from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from datetime import datetime, timedelta, timezone
import logging
import secrets

from .db import ReplayDB
from .providers import BaseProvider
from .trust import evaluate_risk
from .config import AppConfig
from .connectors.base import BaseConnector, ConnectorSyncResult


MAX_SOURCE_LEN = 80
MAX_TITLE_LEN = 300
MAX_CONTENT_LEN = 50_000
MAX_METADATA_KEYS = 50
MAX_METADATA_VALUE_LEN = 5_000
MAX_QUESTION_LEN = 8_000
MAX_NOTE_BODY_LEN = 50_000


class ReplayService:
    def __init__(self, db: ReplayDB, provider: BaseProvider, config: AppConfig, notes_dir: Path):
        self.db = db
        self.provider = provider
        self.config = config
        self.notes_dir = notes_dir
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("replayos.service")

    def ingest_event(self, source: str, title: str, content: str, metadata: dict | None) -> dict:
        source = _clean_text(source, "source", max_len=MAX_SOURCE_LEN)
        title = _clean_text(title, "title", max_len=MAX_TITLE_LEN)
        content = _clean_text(content, "content", max_len=MAX_CONTENT_LEN)
        metadata = _sanitize_metadata(metadata or {})

        event_id = self.db.insert_event(source=source, title=title, content=content, metadata=metadata)
        return {"id": event_id}

    def search(self, query: str, limit: int = 10) -> list[dict]:
        query = _clean_text(query, "query", max_len=MAX_QUESTION_LEN)
        safe_limit = _clamp(limit, 1, self.config.limits.max_search_limit)
        rows = self.db.search_events(query, safe_limit)
        return [asdict(row) for row in rows]

    def recent(self, limit: int = 20) -> list[dict]:
        safe_limit = _clamp(limit, 1, self.config.limits.max_recent_limit)
        rows = self.db.recent_events(safe_limit)
        return [asdict(row) for row in rows]

    def ask(self, question: str, top_k: int = 5) -> dict:
        question = _clean_text(question, "question", max_len=MAX_QUESTION_LEN)
        safe_top_k = _clamp(top_k, 1, self.config.limits.max_top_k)

        hits = self.db.search_events(question, limit=safe_top_k)
        retrieval_mode = "search"
        if not hits:
            hits = self.db.recent_events(limit=safe_top_k)
            retrieval_mode = "recent_fallback"

        context_parts: list[str] = []
        references: list[dict] = []

        for idx, row in enumerate(hits, start=1):
            context_parts.append(f"[{idx}] {row.title}\n{row.content}")
            references.append({"id": row.id, "title": row.title, "source": row.source, "ts": row.ts})

        context_block = "\n\n".join(context_parts) if context_parts else "No timeline context was found."
        prompt = (
            "You are ReplayOS assistant. Answer using timeline context when relevant. "
            "Be concise and explicit about uncertainty.\n\n"
            f"Question:\n{question}\n\n"
            f"Timeline Context:\n{context_block}"
        )

        response = self.provider.generate(prompt)
        answer = response.text
        if response.error:
            self.logger.warning("Provider generation failed: %s", response.error)
            if not answer:
                answer = "I could not generate a model response right now. Please retry."

        return {
            "question": question,
            "answer": answer,
            "provider": response.provider,
            "model": response.model,
            "error": response.error,
            "retrieval_mode": retrieval_mode,
            "references": references,
        }

    def create_note(self, title: str, body: str, dry_run: bool, approved: bool) -> dict:
        action_type = "create_note"
        title = _clean_text(title, "title", max_len=MAX_TITLE_LEN)
        body = _clean_text(body, "body", max_len=MAX_NOTE_BODY_LEN)

        payload = {"title": title, "body": body}
        risk = evaluate_risk(action_type, payload)

        if self.config.safety.require_approval_for_high_risk and risk.requires_explicit_approval and not approved:
            return {
                "ok": False,
                "error": "High-risk action requires explicit approval",
                "risk": asdict(risk),
            }

        file_name = f"{_slugify(title)}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.md"
        note_path = self.notes_dir / file_name
        undo_token = secrets.token_urlsafe(18)

        preview = {
            "action": action_type,
            "note_path": str(note_path),
            "risk": asdict(risk),
            "undo_token": undo_token,
        }

        if self.config.safety.require_ghost_run and not approved and not dry_run:
            return {
                "ok": False,
                "error": "GhostRun required before execution. Retry with dry_run=true first, then approved=true.",
                "preview": preview,
            }

        if dry_run:
            return {"ok": True, "dry_run": True, "preview": preview}

        note_path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
        self.db.log_action(
            action_type=action_type,
            payload={"note_path": str(note_path)},
            status="executed",
            undo_token=undo_token,
        )

        self.logger.info("Note action executed", extra={"undo_token": undo_token, "path": str(note_path)})

        return {
            "ok": True,
            "dry_run": False,
            "note_path": str(note_path),
            "undo_token": undo_token,
            "risk": asdict(risk),
        }

    def undo(self, undo_token: str) -> dict:
        undo_token = _clean_text(undo_token, "undo_token", max_len=256)
        action = self.db.get_action_by_undo_token(undo_token)
        if not action:
            return {"ok": False, "error": "Undo token not found"}

        if action["status"] == "undone":
            return {"ok": False, "error": "Action already undone"}

        if action["action_type"] == "create_note":
            note_path = Path(action["payload"].get("note_path", ""))
            if note_path.exists():
                note_path.unlink()

            self.db.update_action_status(undo_token=undo_token, status="undone")
            rollback_token = secrets.token_urlsafe(18)
            self.db.log_action(
                action_type="undo_create_note",
                payload={"undone": undo_token},
                status="executed",
                undo_token=rollback_token,
            )
            return {"ok": True, "undone": undo_token, "rollback_token": rollback_token}

        return {"ok": False, "error": f"Undo not implemented for action type: {action['action_type']}"}

    def export_data(self, event_limit: int = 10_000, action_limit: int = 10_000) -> dict:
        return self.db.export_data(event_limit=event_limit, action_limit=action_limit)

    def delete_data(self, before_ts: str | None, delete_all: bool = False) -> dict:
        if delete_all:
            if not self.config.data_policy.allow_full_delete:
                return {
                    "ok": False,
                    "error": "Full delete is disabled by policy (data_policy.allow_full_delete=false)",
                }
            deleted = self.db.delete_all()
            return {"ok": True, **deleted}

        if not before_ts:
            return {"ok": False, "error": "before_ts is required when delete_all=false"}

        ts = _parse_iso_ts(before_ts)
        deleted = self.db.delete_before(ts)
        return {"ok": True, "before_ts": ts, **deleted}

    def apply_retention(self, days: int | None = None) -> dict:
        retention_days = days or self.config.data_policy.default_retention_days
        if retention_days <= 0:
            return {"ok": False, "error": "retention days must be positive"}

        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        cutoff_iso = cutoff.isoformat()
        deleted = self.db.delete_before(cutoff_iso)
        return {
            "ok": True,
            "retention_days": retention_days,
            "cutoff_ts": cutoff_iso,
            **deleted,
        }

    def sync_connectors(
        self,
        connectors: list[BaseConnector],
        connector_env: dict[str, str],
        limit_per_connector: int = 20,
    ) -> dict:
        results: list[ConnectorSyncResult] = []
        total_synced = 0

        for connector in connectors:
            if not connector.is_configured(connector_env):
                results.append(
                    ConnectorSyncResult(
                        connector_id=connector.connector_id,
                        synced=0,
                        skipped=True,
                        error="not_configured",
                    )
                )
                continue

            try:
                events = connector.pull_events(connector_env, limit=limit_per_connector)
                synced = 0
                for event in events:
                    self.ingest_event(
                        source=str(event.get("source", connector.connector_id)),
                        title=str(event.get("title", "Connector Event")),
                        content=str(event.get("content", "")),
                        metadata=event.get("metadata") if isinstance(event.get("metadata"), dict) else {},
                    )
                    synced += 1
                total_synced += synced
                results.append(
                    ConnectorSyncResult(
                        connector_id=connector.connector_id,
                        synced=synced,
                        skipped=False,
                        error=None,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                results.append(
                    ConnectorSyncResult(
                        connector_id=connector.connector_id,
                        synced=0,
                        skipped=False,
                        error=str(exc),
                    )
                )

        return {
            "ok": True,
            "total_synced": total_synced,
            "connectors": [asdict(item) for item in results],
        }


def _sanitize_metadata(metadata: dict) -> dict:
    if not isinstance(metadata, dict):
        return {}

    cleaned: dict[str, str | int | float | bool | None] = {}
    for idx, (key, value) in enumerate(metadata.items()):
        if idx >= MAX_METADATA_KEYS:
            break

        k = str(key).strip()
        if not k:
            continue

        if isinstance(value, (str, int, float, bool)) or value is None:
            if isinstance(value, str) and len(value) > MAX_METADATA_VALUE_LEN:
                cleaned[k] = value[:MAX_METADATA_VALUE_LEN]
            else:
                cleaned[k] = value
        else:
            cleaned[k] = str(value)[:MAX_METADATA_VALUE_LEN]
    return cleaned


def _clean_text(value: str, field: str, max_len: int) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field} is required")
    if len(text) > max_len:
        raise ValueError(f"{field} exceeds max length ({max_len})")
    return text


def _clamp(value: int, minimum: int, maximum: int) -> int:
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value


def _slugify(value: str) -> str:
    out = []
    for ch in value.lower().strip():
        if ch.isalnum():
            out.append(ch)
        elif ch in {" ", "-", "_"}:
            out.append("-")
    cleaned = "".join(out).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned or "note"


def _parse_iso_ts(value: str) -> str:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()
