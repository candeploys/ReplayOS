from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4
import json
import logging
import mimetypes
import time

from .config import AppConfig
from .connectors.base import BaseConnector
from .metrics import MetricsStore
from .security import APIKeyAuth, SlidingWindowRateLimiter, parse_api_key_from_headers
from .services import ReplayService


@dataclass(frozen=True)
class ServerContext:
    service: ReplayService
    config: AppConfig
    auth: APIKeyAuth
    limiter: SlidingWindowRateLimiter
    metrics: MetricsStore
    connectors: list[BaseConnector]
    connector_env: dict[str, str]
    web_dir: Path
    logger: logging.Logger


class ReplayHandler(BaseHTTPRequestHandler):
    context: ServerContext | None = None

    def _json(self, code: int, payload: dict, request_id: str, extra_headers: dict[str, str] | None = None) -> None:
        body_payload = dict(payload)
        body_payload.setdefault("request_id", request_id)
        body = json.dumps(body_payload, ensure_ascii=True).encode("utf-8")
        self._send_bytes(code, body, "application/json", extra_headers)

    def _text(self, code: int, text: str, content_type: str, extra_headers: dict[str, str] | None = None) -> None:
        body = text.encode("utf-8")
        self._send_bytes(code, body, content_type, extra_headers)

    def _send_bytes(
        self,
        code: int,
        body: bytes,
        content_type: str,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _request_id(self) -> str:
        header_value = self.headers.get("X-Request-ID", "").strip()
        if header_value:
            return header_value[:100]
        return str(uuid4())

    def _read_json(self, max_bytes: int) -> dict:
        raw_len = self.headers.get("Content-Length", "0")
        length = int(raw_len) if raw_len.isdigit() else 0
        if length > max_bytes:
            raise OverflowError(f"Request body too large (>{max_bytes} bytes)")

        data = self.rfile.read(length) if length > 0 else b"{}"
        if len(data) > max_bytes:
            raise OverflowError(f"Request body too large (>{max_bytes} bytes)")

        try:
            decoded = json.loads(data.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid JSON body") from exc

        if not isinstance(decoded, dict):
            raise ValueError("JSON body must be an object")
        return decoded

    def _auth_and_rate_limit(self, path: str, request_id: str) -> tuple[bool, dict]:
        context = self.context
        if context is None:
            return False, {"status": 500, "payload": {"error": "Server is not initialized"}}

        client_ip = self.client_address[0] if self.client_address else "unknown"
        is_api_path = path.startswith("/api/")

        if is_api_path:
            header_token = parse_api_key_from_headers(dict(self.headers.items()))
            auth = context.auth.validate(header_token=header_token, client_ip=client_ip)
            if not auth.allowed:
                context.logger.warning(
                    "Unauthorized request",
                    extra={
                        "request_id": request_id,
                        "path": path,
                        "method": self.command,
                        "status": 401,
                        "client_ip": client_ip,
                    },
                )
                return False, {"status": 401, "payload": {"error": "Unauthorized", "reason": auth.reason}}

        rate = context.limiter.check(key=client_ip)
        if not rate.allowed:
            context.logger.warning(
                "Rate limit exceeded",
                extra={
                    "request_id": request_id,
                    "path": path,
                    "method": self.command,
                    "status": 429,
                    "client_ip": client_ip,
                },
            )
            return (
                False,
                {
                    "status": 429,
                    "payload": {"error": "Too many requests"},
                    "headers": {"Retry-After": str(rate.retry_after_seconds)},
                },
            )

        return True, {}

    def do_GET(self) -> None:  # noqa: N802
        started = time.perf_counter()
        request_id = self._request_id()
        status = 500
        path_for_log = self.path

        try:
            if self.context is None:
                status = 500
                self._json(status, {"error": "Server is not initialized"}, request_id=request_id)
                return

            parsed = urlparse(self.path)
            path_for_log = parsed.path
            allowed, rejection = self._auth_and_rate_limit(parsed.path, request_id)
            if not allowed:
                status = rejection.get("status", 500)
                self._json(
                    status,
                    rejection.get("payload", {"error": "Rejected"}),
                    request_id=request_id,
                    extra_headers=rejection.get("headers"),
                )
                return

            if parsed.path in {"/", "/index.html", "/app.js", "/styles.css"}:
                status = self._serve_web_asset(parsed.path)
                return

            if parsed.path == "/metrics":
                alert = self.context.metrics.alert_snapshot(
                    threshold=self.context.config.alerting.error_rate_threshold,
                    window_seconds=self.context.config.alerting.error_window_seconds,
                    min_requests=self.context.config.alerting.min_requests_for_alarm,
                )
                metrics_text = self.context.metrics.render_prometheus(
                    threshold=self.context.config.alerting.error_rate_threshold,
                    window_seconds=self.context.config.alerting.error_window_seconds,
                    min_requests=self.context.config.alerting.min_requests_for_alarm,
                )
                status = 200
                self._text(200, metrics_text, "text/plain; version=0.0.4")
                if alert.active:
                    self.context.logger.warning(
                        "Error-rate alarm active",
                        extra={
                            "request_id": request_id,
                            "error_rate": round(alert.error_rate, 6),
                            "threshold": alert.threshold,
                            "window_seconds": alert.window_seconds,
                            "total_requests": alert.total_requests,
                            "error_requests": alert.error_requests,
                        },
                    )
                return

            if parsed.path in {"/health", "/livez", "/readyz"}:
                status = 200
                self._json(
                    status,
                    {
                        "ok": True,
                        "service": "replayos",
                        "environment": self.context.config.runtime.environment,
                        "provider": self.context.config.provider.default,
                    },
                    request_id=request_id,
                )
                return

            if parsed.path == "/api/search":
                q = parse_qs(parsed.query)
                query = q.get("q", [""])[0].strip()
                limit_str = q.get("limit", [str(self.context.config.limits.default_search_limit)])[0]
                limit = int(limit_str) if limit_str.isdigit() else self.context.config.limits.default_search_limit
                items = self.context.service.search(query, limit=limit)
                status = 200
                self._json(status, {"items": items}, request_id=request_id)
                return

            if parsed.path == "/api/events/recent":
                q = parse_qs(parsed.query)
                limit_str = q.get("limit", [str(self.context.config.limits.default_recent_limit)])[0]
                limit = int(limit_str) if limit_str.isdigit() else self.context.config.limits.default_recent_limit
                items = self.context.service.recent(limit=limit)
                status = 200
                self._json(status, {"items": items}, request_id=request_id)
                return

            if parsed.path == "/api/data/export":
                q = parse_qs(parsed.query)
                event_limit = int(q.get("event_limit", ["10000"])[0]) if q.get("event_limit", [""])[0].isdigit() else 10000
                action_limit = int(q.get("action_limit", ["10000"])[0]) if q.get("action_limit", [""])[0].isdigit() else 10000
                out = self.context.service.export_data(event_limit=event_limit, action_limit=action_limit)
                status = 200
                self._json(status, {"ok": True, **out}, request_id=request_id)
                return

            if parsed.path == "/api/admin/alerts":
                alert = self.context.metrics.alert_snapshot(
                    threshold=self.context.config.alerting.error_rate_threshold,
                    window_seconds=self.context.config.alerting.error_window_seconds,
                    min_requests=self.context.config.alerting.min_requests_for_alarm,
                )
                status = 200
                self._json(
                    status,
                    {
                        "ok": True,
                        "active": alert.active,
                        "error_rate": alert.error_rate,
                        "threshold": alert.threshold,
                        "window_seconds": alert.window_seconds,
                        "total_requests": alert.total_requests,
                        "error_requests": alert.error_requests,
                    },
                    request_id=request_id,
                )
                return

            if parsed.path == "/api/connectors":
                connectors = [
                    {
                        "id": c.connector_id,
                        "name": c.display_name,
                        "configured": c.is_configured(self.context.connector_env),
                    }
                    for c in self.context.connectors
                ]
                status = 200
                self._json(status, {"ok": True, "connectors": connectors}, request_id=request_id)
                return

            status = 404
            self._json(status, {"error": "Not found"}, request_id=request_id)
        except ValueError as exc:
            status = 400
            self._json(status, {"error": str(exc)}, request_id=request_id)
        except Exception as exc:  # noqa: BLE001
            status = 500
            self._json(status, {"error": f"Unhandled server error: {exc}"}, request_id=request_id)
        finally:
            self._log_request(status, started, request_id, path_for_log)

    def do_POST(self) -> None:  # noqa: N802
        started = time.perf_counter()
        request_id = self._request_id()
        status = 500
        path_for_log = self.path

        try:
            if self.context is None:
                status = 500
                self._json(status, {"error": "Server is not initialized"}, request_id=request_id)
                return

            parsed = urlparse(self.path)
            path_for_log = parsed.path
            allowed, rejection = self._auth_and_rate_limit(parsed.path, request_id)
            if not allowed:
                status = rejection.get("status", 500)
                self._json(
                    status,
                    rejection.get("payload", {"error": "Rejected"}),
                    request_id=request_id,
                    extra_headers=rejection.get("headers"),
                )
                return

            body = self._read_json(max_bytes=self.context.config.limits.max_request_bytes)

            if parsed.path == "/api/events":
                source = str(body.get("source", "")).strip()
                title = str(body.get("title", "")).strip()
                content = str(body.get("content", "")).strip()
                metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
                out = self.context.service.ingest_event(
                    source=source,
                    title=title,
                    content=content,
                    metadata=metadata,
                )
                status = 201
                self._json(status, {"ok": True, **out}, request_id=request_id)
                return

            if parsed.path == "/api/ask":
                question = str(body.get("question", "")).strip()
                top_k_raw = body.get("top_k", self.context.config.limits.default_top_k)
                top_k = int(top_k_raw) if isinstance(top_k_raw, int) or str(top_k_raw).isdigit() else self.context.config.limits.default_top_k
                if not question:
                    status = 400
                    self._json(status, {"error": "question is required"}, request_id=request_id)
                    return
                out = self.context.service.ask(question=question, top_k=top_k)
                if out.get("error"):
                    self.context.metrics.observe_provider_error()
                status = 200
                self._json(status, {"ok": True, **out}, request_id=request_id)
                return

            if parsed.path == "/api/actions/create-note":
                title = str(body.get("title", "")).strip()
                note_body = str(body.get("body", "")).strip()
                dry_run = bool(body.get("dry_run", False))
                approved = bool(body.get("approved", False))
                if not title or not note_body:
                    status = 400
                    self._json(status, {"error": "title and body are required"}, request_id=request_id)
                    return
                out = self.context.service.create_note(
                    title=title,
                    body=note_body,
                    dry_run=dry_run,
                    approved=approved,
                )
                status = 200 if out.get("ok") else 409
                self._json(status, out, request_id=request_id)
                return

            if parsed.path == "/api/actions/undo":
                undo_token = str(body.get("undo_token", "")).strip()
                if not undo_token:
                    status = 400
                    self._json(status, {"error": "undo_token is required"}, request_id=request_id)
                    return
                out = self.context.service.undo(undo_token)
                status = 200 if out.get("ok") else 404
                self._json(status, out, request_id=request_id)
                return

            if parsed.path == "/api/data/delete":
                before_ts = str(body.get("before_ts", "")).strip() or None
                delete_all = bool(body.get("all", False))
                out = self.context.service.delete_data(before_ts=before_ts, delete_all=delete_all)
                status = 200 if out.get("ok") else 409
                self._json(status, out, request_id=request_id)
                return

            if parsed.path == "/api/data/retention/apply":
                days_raw = body.get("days")
                days = int(days_raw) if isinstance(days_raw, int) or str(days_raw).isdigit() else None
                out = self.context.service.apply_retention(days=days)
                status = 200 if out.get("ok") else 400
                self._json(status, out, request_id=request_id)
                return

            if parsed.path == "/api/connectors/sync":
                limit_raw = body.get("limit_per_connector", 20)
                limit = int(limit_raw) if isinstance(limit_raw, int) or str(limit_raw).isdigit() else 20
                out = self.context.service.sync_connectors(
                    connectors=self.context.connectors,
                    connector_env=self.context.connector_env,
                    limit_per_connector=max(1, min(limit, 200)),
                )
                status = 200
                self._json(status, out, request_id=request_id)
                return

            status = 404
            self._json(status, {"error": "Not found"}, request_id=request_id)
        except OverflowError as exc:
            status = 413
            self._json(status, {"error": str(exc)}, request_id=request_id)
        except ValueError as exc:
            status = 400
            self._json(status, {"error": str(exc)}, request_id=request_id)
        except Exception as exc:  # noqa: BLE001
            status = 500
            self._json(status, {"error": f"Unhandled server error: {exc}"}, request_id=request_id)
        finally:
            self._log_request(status, started, request_id, path_for_log)

    def _serve_web_asset(self, path: str) -> int:
        if self.context is None:
            self._json(500, {"error": "Server is not initialized"}, request_id=self._request_id())
            return 500

        target = "index.html" if path in {"/", "/index.html"} else path.lstrip("/")
        file_path = (self.context.web_dir / target).resolve()
        web_root = self.context.web_dir.resolve()

        if not str(file_path).startswith(str(web_root)) or not file_path.exists():
            self._json(404, {"error": "Asset not found"}, request_id=self._request_id())
            return 404

        mime, _ = mimetypes.guess_type(str(file_path))
        mime = mime or "application/octet-stream"
        self._send_bytes(200, file_path.read_bytes(), mime)
        return 200

    def _log_request(self, status: int, started: float, request_id: str, path_for_log: str) -> None:
        if self.context is None:
            return

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        client_ip = self.client_address[0] if self.client_address else "unknown"

        self.context.metrics.observe_request(
            method=self.command,
            path=path_for_log,
            status=status,
            duration_ms=duration_ms,
        )

        self.context.logger.info(
            "HTTP request",
            extra={
                "request_id": request_id,
                "path": path_for_log,
                "method": self.command,
                "status": status,
                "duration_ms": duration_ms,
                "client_ip": client_ip,
            },
        )

    def log_message(self, fmt: str, *args) -> None:
        return


def run_http_server(
    service: ReplayService,
    config: AppConfig,
    connectors: list[BaseConnector] | None = None,
    connector_env: dict[str, str] | None = None,
    web_dir: Path | None = None,
) -> None:
    logger = logging.getLogger("replayos.http")
    context = ServerContext(
        service=service,
        config=config,
        auth=APIKeyAuth(config.auth),
        limiter=SlidingWindowRateLimiter(
            max_requests=config.limits.rate_limit_requests,
            window_seconds=config.limits.rate_limit_window_seconds,
        ),
        metrics=MetricsStore(),
        connectors=connectors or [],
        connector_env=connector_env or {},
        web_dir=web_dir or (Path(__file__).resolve().parent.parent / "web"),
        logger=logger,
    )

    ReplayHandler.context = context
    httpd = ThreadingHTTPServer((config.server.host, config.server.port), ReplayHandler)

    logger.info(
        "ReplayOS server starting",
        extra={
            "host": config.server.host,
            "port": config.server.port,
            "provider": config.provider.default,
            "environment": config.runtime.environment,
            "connectors": [c.connector_id for c in context.connectors],
        },
    )

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("ReplayOS shutdown requested")
    finally:
        httpd.server_close()
        logger.info("ReplayOS server stopped")
