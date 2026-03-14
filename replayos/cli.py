from __future__ import annotations

from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import secrets
import signal
import subprocess
import sys
import time

from .capture_daemon import run_capture_daemon
from .browser_history import import_browser_history
from .config import load_config, load_env_file
from .connectors.registry import all_connectors
from .db import ReplayDB
from .observability import configure_logging
from .providers import build_provider
from .service_manager import ServicePaths, install_user_service, service_status, uninstall_user_service
from .services import ReplayService
from .server import run_http_server


def _build_service(config_path: Path, env_path: Path, db_path: Path, notes_dir: Path) -> tuple[ReplayService, ReplayDB]:
    config = load_config(config_path=config_path, env_path=env_path)
    db = ReplayDB(db_path)
    provider = build_provider(config)
    service = ReplayService(db=db, provider=provider, config=config, notes_dir=notes_dir)
    return service, db


def _load_runtime_env(env_path: Path) -> dict[str, str]:
    env = load_env_file(env_path)
    merged = dict(env)
    merged.update(os.environ)
    return merged


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _parse_first_api_key(value: str) -> str:
    for token in value.split(","):
        token = token.strip()
        if token:
            return token
    return ""


def main() -> None:
    parser = ArgumentParser(prog="replayos", description="ReplayOS runtime CLI")
    parser.add_argument("--config", default="config/replayos.toml", help="Path to TOML config")
    parser.add_argument("--env", default=".env", help="Path to .env file")
    parser.add_argument("--db", default="data/replayos.db", help="Path to SQLite DB")
    parser.add_argument("--notes-dir", default="notes", help="Directory for generated note actions")
    parser.add_argument("--pid-file", default="data/replayos.pid", help="PID file path for run-bg/stop/status")
    parser.add_argument("--log-file", default="data/replayos.log", help="Log file path for run-bg")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Validate config and print provider summary")
    sub.add_parser("doctor", help="Run runtime checks and print warnings")
    sub.add_parser("run", help="Run HTTP API server")
    sub.add_parser("run-bg", help="Run server in background")
    sub.add_parser("stop", help="Stop background server")
    sub.add_parser("status", help="Print background server status")
    sub.add_parser("generate-api-key", help="Generate a secure API key")

    p_backup = sub.add_parser("backup-db", help="Create SQLite backup")
    p_backup.add_argument("--output", default="", help="Backup output path (.db)")

    p_restore = sub.add_parser("restore-db", help="Restore SQLite backup")
    p_restore.add_argument("--input", required=True, help="Input backup .db path")

    sub.add_parser("migrate-db", help="Apply DB migrations/schema init")
    sub.add_parser("vacuum-db", help="Run SQLite VACUUM")

    sub.add_parser("install-service", help="Install user service (launchd/systemd-user)")
    sub.add_parser("uninstall-service", help="Uninstall user service")
    sub.add_parser("service-status", help="Check service status")

    p_seed = sub.add_parser("seed-demo", help="Insert demo events")
    p_seed.add_argument("--count", type=int, default=5)

    p_ask = sub.add_parser("ask", help="Ask a question against timeline context")
    p_ask.add_argument("question", help="Question text")

    p_sync = sub.add_parser("sync-connectors", help="Sync configured connectors")
    p_sync.add_argument("--limit", type=int, default=20, help="Per-connector item limit")

    sub.add_parser("list-connectors", help="List built-in and plugin connectors")
    sub.add_parser("connector-doctor", help="Validate connector configuration and missing env keys")

    p_capture = sub.add_parser("capture-daemon", help="Run macOS capture daemon")
    p_capture.add_argument("--interval", type=int, default=15, help="Capture interval in seconds")
    p_capture.add_argument("--api-base-url", default="", help="Override ReplayOS API base URL")
    p_capture.add_argument("--capture-screenshot", action="store_true", help="Capture screenshots with each event")
    p_capture.add_argument("--screenshot-dir", default="captures", help="Directory for screenshots")
    p_capture.add_argument("--privacy-mode", action="store_true", help="Redact window title and URL in captures")
    p_capture.add_argument("--include-app", action="append", default=[], help="Only capture this app (repeatable)")
    p_capture.add_argument("--exclude-app", action="append", default=[], help="Skip this app (repeatable)")

    p_hist = sub.add_parser("import-browser-history", help="Import browser history into timeline")
    p_hist.add_argument("--api-base-url", default="", help="Override ReplayOS API base URL")
    p_hist.add_argument("--browser", action="append", default=[], help="Browser id: safari/chrome/brave/edge/all")
    p_hist.add_argument("--limit", type=int, default=100, help="Max history rows per browser")
    p_hist.add_argument("--since-days", type=int, default=30, help="Only import visits newer than N days")
    p_hist.add_argument("--privacy-mode", action="store_true", help="Redact URL/title content in imported rows")

    args = parser.parse_args()

    config_path = Path(args.config)
    env_path = Path(args.env)
    db_path = Path(args.db)
    notes_dir = Path(args.notes_dir)
    pid_file = Path(args.pid_file)
    log_file = Path(args.log_file)

    if args.command == "generate-api-key":
        print(secrets.token_urlsafe(32))
        return

    config = load_config(config_path=config_path, env_path=env_path)
    configure_logging(level=config.observability.log_level, json_output=config.observability.log_json)

    if args.command == "check":
        print("ReplayOS configuration OK")
        print(f"Environment: {config.runtime.environment}")
        print(f"Provider: {config.provider.default}")
        print(f"Server: {config.server.host}:{config.server.port}")
        print(f"Auth required: {config.auth.require_api_key}")
        print(f"API keys configured: {len(config.auth.api_keys)}")
        print(f"Plugin dirs: {len(config.plugins.directories)}")
        return

    if args.command == "doctor":
        warnings: list[str] = []

        if config.provider.default in {"claude_api", "openai_api"} and config.runtime.provider_timeout_seconds < 30:
            warnings.append("provider_timeout_seconds is low for remote provider; consider >= 30")

        if not config.auth.require_api_key:
            warnings.append("auth.require_api_key=false (not recommended for production)")

        if config.auth.require_api_key and not config.auth.api_keys and not config.auth.allow_localhost_without_key:
            warnings.append("No API keys configured while auth is required")

        if config.runtime.environment.lower() in {"dev", "development"}:
            warnings.append("runtime.environment is development")

        if not config.data_policy.allow_full_delete:
            warnings.append("data_policy.allow_full_delete=false (safe default)")

        print("ReplayOS doctor report")
        if warnings:
            for item in warnings:
                print(f"- WARNING: {item}")
        else:
            print("- No critical warnings")
        return

    if args.command == "status":
        if not pid_file.exists():
            print(f"Not running (pid file not found: {pid_file})")
            return
        raw = pid_file.read_text(encoding="utf-8").strip()
        if not raw.isdigit():
            print(f"Invalid pid file content: {pid_file}")
            return
        pid = int(raw)
        if _pid_is_running(pid):
            print(f"Running (pid={pid})")
        else:
            print(f"Not running (stale pid file: {pid_file})")
        return

    if args.command == "stop":
        if not pid_file.exists():
            print(f"No pid file at {pid_file}")
            return
        raw = pid_file.read_text(encoding="utf-8").strip()
        if not raw.isdigit():
            raise RuntimeError(f"Invalid pid file content: {pid_file}")
        pid = int(raw)
        if not _pid_is_running(pid):
            print(f"Process not running (pid={pid})")
            pid_file.unlink(missing_ok=True)
            return
        os.kill(pid, signal.SIGTERM)
        for _ in range(30):
            if not _pid_is_running(pid):
                break
            time.sleep(0.1)
        if _pid_is_running(pid):
            os.kill(pid, signal.SIGKILL)
        pid_file.unlink(missing_ok=True)
        print(f"Stopped ReplayOS (pid={pid})")
        return

    if args.command == "run-bg":
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        if pid_file.exists():
            raw = pid_file.read_text(encoding="utf-8").strip()
            if raw.isdigit() and _pid_is_running(int(raw)):
                print(f"Already running (pid={raw})")
                return
            pid_file.unlink(missing_ok=True)

        cmd = [
            sys.executable,
            "-m",
            "replayos.cli",
            "--config",
            str(config_path),
            "--env",
            str(env_path),
            "--db",
            str(db_path),
            "--notes-dir",
            str(notes_dir),
            "run",
        ]

        with log_file.open("a", encoding="utf-8") as log_fp:
            proc = subprocess.Popen(
                cmd,
                stdout=log_fp,
                stderr=log_fp,
                start_new_session=True,
            )

        pid_file.write_text(str(proc.pid), encoding="utf-8")
        time.sleep(0.4)
        if _pid_is_running(proc.pid):
            print(f"ReplayOS started in background (pid={proc.pid})")
            print(f"Log file: {log_file}")
        else:
            raise RuntimeError(f"ReplayOS failed to start. Check log: {log_file}")
        return

    if args.command == "service-status":
        print(service_status())
        return

    if args.command == "install-service":
        message = install_user_service(
            ServicePaths(
                config_path=config_path.resolve(),
                env_path=env_path.resolve(),
                db_path=db_path.resolve(),
                notes_dir=notes_dir.resolve(),
                log_path=log_file.resolve(),
            )
        )
        print(message)
        return

    if args.command == "uninstall-service":
        print(uninstall_user_service())
        return

    runtime_env = _load_runtime_env(env_path)
    connectors = all_connectors(config.plugins.directories)

    if args.command == "list-connectors":
        for connector in connectors:
            configured = connector.is_configured(runtime_env)
            print(f"- {connector.connector_id}: {connector.display_name} (configured={configured})")
        return

    if args.command == "connector-doctor":
        report = [connector.doctor(runtime_env) for connector in connectors]
        configured = sum(1 for item in report if item.get("configured"))
        print(
            json.dumps(
                {
                    "ok": True,
                    "total_connectors": len(report),
                    "configured_connectors": configured,
                    "connectors": report,
                },
                indent=2,
            )
        )
        return

    if args.command == "capture-daemon":
        api_key = _parse_first_api_key(runtime_env.get("REPLAYOS_API_KEYS", ""))
        if not api_key:
            raise RuntimeError("REPLAYOS_API_KEYS is required for capture-daemon")

        api_base_url = args.api_base_url.strip() or f"http://{config.server.host}:{config.server.port}"
        run_capture_daemon(
            api_base_url=api_base_url,
            api_key=api_key,
            interval_seconds=max(1, int(args.interval)),
            capture_screenshot=bool(args.capture_screenshot),
            screenshot_dir=Path(args.screenshot_dir),
            privacy_mode=bool(args.privacy_mode),
            include_apps=tuple(args.include_app),
            exclude_apps=tuple(args.exclude_app),
        )
        return

    if args.command == "import-browser-history":
        api_key = _parse_first_api_key(runtime_env.get("REPLAYOS_API_KEYS", ""))
        if not api_key:
            raise RuntimeError("REPLAYOS_API_KEYS is required for import-browser-history")

        api_base_url = args.api_base_url.strip() or f"http://{config.server.host}:{config.server.port}"
        selected = tuple(args.browser) if args.browser else ("all",)
        out = import_browser_history(
            api_base_url=api_base_url,
            api_key=api_key,
            browsers=selected,
            limit_per_browser=max(1, min(int(args.limit), 500)),
            since_days=max(1, min(int(args.since_days), 3650)),
            privacy_mode=bool(args.privacy_mode),
        )
        print(json.dumps(out, indent=2))
        return

    if args.command == "backup-db":
        output = args.output.strip()
        if not output:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            output = f"backups/replayos-{ts}.db"
        out_path = Path(output)

        db = ReplayDB(db_path)
        try:
            db.backup_to(out_path)
        finally:
            db.close()

        print(f"Backup created: {out_path}")
        return

    if args.command == "restore-db":
        input_path = Path(args.input)
        db = ReplayDB(db_path)
        try:
            db.restore_from_file(input_path)
        finally:
            db.close()
        print(f"Database restored from: {input_path}")
        return

    if args.command == "migrate-db":
        db = ReplayDB(db_path)
        try:
            print(f"Migration complete. Schema version: {db.get_schema_version()}")
        finally:
            db.close()
        return

    if args.command == "vacuum-db":
        db = ReplayDB(db_path)
        try:
            db.vacuum()
        finally:
            db.close()
        print("VACUUM complete")
        return

    service, db = _build_service(config_path=config_path, env_path=env_path, db_path=db_path, notes_dir=notes_dir)

    try:
        if args.command == "seed-demo":
            count = max(1, min(int(args.count), 50))
            for idx in range(1, count + 1):
                service.ingest_event(
                    source="demo",
                    title=f"Sample Event {idx}",
                    content=(
                        f"This is synthetic timeline event {idx}. "
                        "Project codename is ReplayOS and priority is safety-first automation."
                    ),
                    metadata={"index": idx},
                )
            print(f"Inserted {count} demo events")
            return

        if args.command == "ask":
            out = service.ask(question=str(args.question), top_k=config.limits.default_top_k)
            print(json.dumps(out, indent=2))
            return

        if args.command == "sync-connectors":
            out = service.sync_connectors(
                connectors=connectors,
                connector_env=runtime_env,
                limit_per_connector=max(1, min(int(args.limit), 200)),
            )
            print(json.dumps(out, indent=2))
            return

        if args.command == "run":
            run_http_server(
                service=service,
                config=config,
                connectors=connectors,
                connector_env=runtime_env,
            )
            return
    finally:
        db.close()


if __name__ == "__main__":
    main()
