from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import platform
import subprocess
import sys


@dataclass
class ServicePaths:
    config_path: Path
    env_path: Path
    db_path: Path
    notes_dir: Path
    log_path: Path


def _mac_plist_path() -> Path:
    return Path.home() / "Library/LaunchAgents/com.replayos.server.plist"


def _linux_unit_path() -> Path:
    return Path.home() / ".config/systemd/user/replayos.service"


def install_user_service(paths: ServicePaths) -> str:
    system = platform.system().lower()
    if system == "darwin":
        return _install_launchd(paths)
    if system == "linux":
        return _install_systemd_user(paths)
    raise RuntimeError(f"Unsupported platform for service install: {system}")


def uninstall_user_service() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return _uninstall_launchd()
    if system == "linux":
        return _uninstall_systemd_user()
    raise RuntimeError(f"Unsupported platform for service uninstall: {system}")


def service_status() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return _launchd_status()
    if system == "linux":
        return _systemd_user_status()
    return "Service status not supported on this OS"


def _install_launchd(paths: ServicePaths) -> str:
    plist_path = _mac_plist_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    python_exec = Path(sys.executable).resolve()
    plist = f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\"> 
<plist version=\"1.0\"> 
<dict>
  <key>Label</key>
  <string>com.replayos.server</string>
  <key>ProgramArguments</key>
  <array>
    <string>{python_exec}</string>
    <string>-m</string>
    <string>replayos.cli</string>
    <string>--config</string>
    <string>{paths.config_path}</string>
    <string>--env</string>
    <string>{paths.env_path}</string>
    <string>--db</string>
    <string>{paths.db_path}</string>
    <string>--notes-dir</string>
    <string>{paths.notes_dir}</string>
    <string>run</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>{paths.log_path}</string>
  <key>StandardErrorPath</key>
  <string>{paths.log_path}</string>
</dict>
</plist>
"""
    plist_path.write_text(plist, encoding="utf-8")

    subprocess.run(["launchctl", "unload", str(plist_path)], check=False, capture_output=True)
    subprocess.run(["launchctl", "load", str(plist_path)], check=False, capture_output=True)
    return f"Installed launchd service at {plist_path}"


def _uninstall_launchd() -> str:
    plist_path = _mac_plist_path()
    subprocess.run(["launchctl", "unload", str(plist_path)], check=False, capture_output=True)
    if plist_path.exists():
        plist_path.unlink()
    return f"Removed launchd service {plist_path}"


def _launchd_status() -> str:
    plist_path = _mac_plist_path()
    if not plist_path.exists():
        return f"launchd service not installed ({plist_path})"

    result = subprocess.run(["launchctl", "list", "com.replayos.server"], capture_output=True, text=True)
    if result.returncode == 0:
        return "launchd service is loaded (com.replayos.server)"
    return f"launchd service installed but not loaded ({plist_path})"


def _install_systemd_user(paths: ServicePaths) -> str:
    unit_path = _linux_unit_path()
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    python_exec = Path(sys.executable).resolve()

    unit = f"""[Unit]
Description=ReplayOS Server
After=network.target

[Service]
Type=simple
WorkingDirectory={Path.cwd()}
ExecStart={python_exec} -m replayos.cli --config {paths.config_path} --env {paths.env_path} --db {paths.db_path} --notes-dir {paths.notes_dir} run
Restart=always
RestartSec=2
StandardOutput=append:{paths.log_path}
StandardError=append:{paths.log_path}

[Install]
WantedBy=default.target
"""
    unit_path.write_text(unit, encoding="utf-8")

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, capture_output=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", "replayos.service"], check=False, capture_output=True)
    return f"Installed systemd user service at {unit_path}"


def _uninstall_systemd_user() -> str:
    unit_path = _linux_unit_path()
    subprocess.run(["systemctl", "--user", "disable", "--now", "replayos.service"], check=False, capture_output=True)
    if unit_path.exists():
        unit_path.unlink()
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, capture_output=True)
    return f"Removed systemd user service {unit_path}"


def _systemd_user_status() -> str:
    result = subprocess.run(["systemctl", "--user", "is-active", "replayos.service"], capture_output=True, text=True)
    if result.returncode == 0:
        return "systemd user service is active (replayos.service)"
    unit_path = _linux_unit_path()
    if unit_path.exists():
        return f"systemd user service exists but inactive ({unit_path})"
    return f"systemd user service not installed ({unit_path})"
