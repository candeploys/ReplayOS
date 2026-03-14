from __future__ import annotations

from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from xml.etree import ElementTree as ET

from replayos.connectors.base import BaseConnector


class RSSConnector(BaseConnector):
    connector_id = "rss"
    display_name = "RSS Feed"

    def required_env_keys(self) -> tuple[str, ...]:
        return ("RSS_CONNECTOR_FEED_URL",)

    def is_configured(self, env: dict[str, str]) -> bool:
        return bool(env.get("RSS_CONNECTOR_FEED_URL", "").strip())

    def pull_events(self, env: dict[str, str], limit: int = 20) -> list[dict]:
        feed_url = env.get("RSS_CONNECTOR_FEED_URL", "").strip()
        if not feed_url:
            return []

        req = Request(feed_url, method="GET", headers={"User-Agent": "ReplayOS/1.0"})
        try:
            with urlopen(req, timeout=20) as resp:
                raw = resp.read()
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"RSS HTTP {exc.code}: {body}") from exc
        except URLError as exc:
            raise RuntimeError(f"RSS network error: {exc.reason}") from exc

        root = ET.fromstring(raw)
        channel = root.find("channel")
        if channel is None:
            return []

        events: list[dict] = []
        for item in channel.findall("item")[:limit]:
            title = (item.findtext("title") or "RSS item").strip()
            link = (item.findtext("link") or "").strip()
            description = (item.findtext("description") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            events.append(
                {
                    "source": "rss",
                    "title": title[:300],
                    "content": f"{description}\n\nLink: {link}\nPublished: {pub_date}".strip(),
                    "metadata": {"connector": self.connector_id, "link": link, "published": pub_date},
                }
            )
        return events


def build_connector() -> BaseConnector:
    return RSSConnector()
