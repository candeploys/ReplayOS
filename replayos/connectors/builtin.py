from __future__ import annotations

from email.parser import BytesParser
from email.policy import default
import imaplib
import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from .base import BaseConnector


class GmailIMAPConnector(BaseConnector):
    connector_id = "gmail_imap"
    display_name = "Gmail (IMAP)"

    def required_env_keys(self) -> tuple[str, ...]:
        return ("GMAIL_IMAP_USER", "GMAIL_IMAP_APP_PASSWORD")

    def is_configured(self, env: dict[str, str]) -> bool:
        return bool(env.get("GMAIL_IMAP_USER") and env.get("GMAIL_IMAP_APP_PASSWORD"))

    def pull_events(self, env: dict[str, str], limit: int = 20) -> list[dict]:
        user = env.get("GMAIL_IMAP_USER", "").strip()
        password = env.get("GMAIL_IMAP_APP_PASSWORD", "").strip()
        if not user or not password:
            return []

        events: list[dict] = []
        mailbox = env.get("GMAIL_IMAP_MAILBOX", "INBOX")
        conn = imaplib.IMAP4_SSL("imap.gmail.com")
        try:
            conn.login(user, password)
            conn.select(mailbox, readonly=True)
            status, data = conn.search(None, "ALL")
            if status != "OK" or not data or not data[0]:
                return []

            ids = data[0].split()[-limit:]
            for msg_id in reversed(ids):
                status, payload = conn.fetch(msg_id, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])")
                if status != "OK" or not payload:
                    continue
                raw = payload[0][1] if isinstance(payload[0], tuple) and len(payload[0]) > 1 else b""
                msg = BytesParser(policy=default).parsebytes(raw)
                subject = str(msg.get("Subject", "(no subject)")).strip()
                sender = str(msg.get("From", "unknown sender")).strip()
                date = str(msg.get("Date", "unknown date")).strip()
                events.append(
                    {
                        "source": "gmail",
                        "title": subject[:300] or "(no subject)",
                        "content": f"From: {sender}\nDate: {date}",
                        "metadata": {"connector": self.connector_id, "mailbox": mailbox},
                    }
                )
            return events
        finally:
            try:
                conn.logout()
            except Exception:  # noqa: BLE001
                pass


class SlackConnector(BaseConnector):
    connector_id = "slack"
    display_name = "Slack"

    def required_env_keys(self) -> tuple[str, ...]:
        return ("SLACK_BOT_TOKEN", "SLACK_CHANNEL_ID")

    def is_configured(self, env: dict[str, str]) -> bool:
        return bool(env.get("SLACK_BOT_TOKEN") and env.get("SLACK_CHANNEL_ID"))

    def pull_events(self, env: dict[str, str], limit: int = 20) -> list[dict]:
        token = env.get("SLACK_BOT_TOKEN", "").strip()
        channel = env.get("SLACK_CHANNEL_ID", "").strip()
        if not token or not channel:
            return []

        url = f"https://slack.com/api/conversations.history?channel={channel}&limit={limit}"
        req = Request(url, headers={"Authorization": f"Bearer {token}"}, method="GET")

        try:
            with urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Slack API HTTP {exc.code}: {body}") from exc
        except URLError as exc:
            raise RuntimeError(f"Slack API network error: {exc.reason}") from exc

        if not data.get("ok"):
            raise RuntimeError(f"Slack API error: {data.get('error', 'unknown')}" )

        events: list[dict] = []
        for msg in data.get("messages", []):
            text = str(msg.get("text", "")).strip()
            ts = str(msg.get("ts", ""))
            if not text:
                continue
            title = text[:120] if len(text) > 120 else text
            events.append(
                {
                    "source": "slack",
                    "title": title,
                    "content": text,
                    "metadata": {"connector": self.connector_id, "channel": channel, "slack_ts": ts},
                }
            )
        return events


class NotionConnector(BaseConnector):
    connector_id = "notion"
    display_name = "Notion"

    def required_env_keys(self) -> tuple[str, ...]:
        return ("NOTION_API_KEY",)

    def is_configured(self, env: dict[str, str]) -> bool:
        return bool(env.get("NOTION_API_KEY"))

    def pull_events(self, env: dict[str, str], limit: int = 20) -> list[dict]:
        api_key = env.get("NOTION_API_KEY", "").strip()
        if not api_key:
            return []

        url = "https://api.notion.com/v1/search"
        payload = json.dumps({"page_size": limit}).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }
        req = Request(url, data=payload, headers=headers, method="POST")

        try:
            with urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Notion API HTTP {exc.code}: {body}") from exc
        except URLError as exc:
            raise RuntimeError(f"Notion API network error: {exc.reason}") from exc

        events: list[dict] = []
        for item in data.get("results", []):
            item_id = str(item.get("id", ""))
            obj_type = str(item.get("object", ""))
            title = "Notion item"

            if isinstance(item.get("properties"), dict):
                for prop in item["properties"].values():
                    if isinstance(prop, dict) and prop.get("type") == "title":
                        title_parts = [str(t.get("plain_text", "")) for t in prop.get("title", [])]
                        guess = "".join(title_parts).strip()
                        if guess:
                            title = guess
                            break

            events.append(
                {
                    "source": "notion",
                    "title": title[:300],
                    "content": f"Object: {obj_type}\nID: {item_id}",
                    "metadata": {"connector": self.connector_id, "notion_id": item_id},
                }
            )
        return events
