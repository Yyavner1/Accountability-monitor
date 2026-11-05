"""First-run launcher — the double-clickable entry point.

When a user runs the packaged app with no arguments, this:
  1. ensures a config.json exists in the app's data directory,
  2. registers the background agent to start automatically (best effort),
  3. opens the local settings page in their browser.

So a non-technical user downloads one file, opens it, fills in the settings
page, and is done — no Terminal, no editing files. Running with a subcommand
(`monitor`, `settings`) dispatches to that piece instead, which is what the
autostart service invokes.

Packaged with PyInstaller (see packaging/), this becomes a single executable
per OS. Run from source with:  python3 -m accountability_monitor.app
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


def data_dir() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "AccountabilityMonitor"
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AccountabilityMonitor"
    else:
        base = Path.home() / ".local" / "share" / "accountability-monitor"
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_path() -> Path:
    return data_dir() / "config.json"


def _bundled_example() -> Path | None:
    # config.example.json ships next to the package or inside the PyInstaller bundle.
    candidates = [
        Path(getattr(sys, "_MEIPASS", "")) / "config.example.json",
        Path(__file__).resolve().parent.parent / "config.example.json",
    ]
    for c in candidates:
        if c and c.exists():
            return c
    return None


def ensure_config() -> Path:
    cfg = config_path()
    if cfg.exists():
        return cfg
    example = _bundled_example()
    if example:
        shutil.copy(example, cfg)
    else:
        cfg.write_text(json.dumps({
            "partner_email": "", "sender_email": "", "smtp_password": "",
            "smtp_host": "smtp.gmail.com", "smtp_port": 465,
            "capture_interval_seconds": 120, "idle_threshold_seconds": 60,
            "nsfw_score_threshold": 0.80, "summary_frequency": "daily",
            "daily_summary_hour": 21, "blur_flagged_captures": True,
            "retention_days": 14, "alert_cooldown_seconds": 900,
            "capture_failure_threshold": 3, "watch_site_filter": True,
            "screenshot_dir": str(data_dir() / "captures"),
            "healthcheck_url": "", "server_url": "", "device_api_key": "",
        }, indent=2) + "\n")
    return cfg


def setup_autostart() -> bool:
    """Best-effort: register the agent to run at login. Never fatal."""
    try:
        if sys.platform == "darwin":
            return _autostart_launchd()
        if sys.platform.startswith("win"):
            return _autostart_windows()
        return _autostart_systemd()
    except Exception:
        return False


def _self_cmd(sub: str) -> list[str]:
    # When frozen by PyInstaller, sys.executable IS the app; otherwise use python -m.
    if getattr(sys, "frozen", False):
        return [sys.executable, sub]
    return [sys.executable, "-m", "accountability_monitor.app", sub]


def _autostart_launchd() -> bool:
    import subprocess
    plist = Path.home() / "Library" / "LaunchAgents" / "com.accountability.monitor.plist"
    plist.parent.mkdir(parents=True, exist_ok=True)
    args = "".join(f"\n    <string>{a}</string>" for a in _self_cmd("monitor"))
    plist.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.accountability.monitor</string>
  <key>ProgramArguments</key><array>{args}
  </array>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
</dict></plist>
""")
    subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
    subprocess.run(["launchctl", "load", str(plist)], capture_output=True)
    return True


def _autostart_windows() -> bool:
    import subprocess
    exe = _self_cmd("monitor")
    cmd = " ".join(f'"{a}"' for a in exe)
    subprocess.run([
        "schtasks", "/Create", "/TN", "AccountabilityMonitor", "/SC", "ONLOGON",
        "/TR", cmd, "/F", "/RL", "LIMITED",
    ], capture_output=True)
    return True


def _autostart_systemd() -> bool:
    import subprocess
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    exec_line = " ".join(_self_cmd("monitor"))
    (unit_dir / "accountability-monitor.service").write_text(f"""[Unit]
Description=Accountability screen monitor
After=graphical-session.target
[Service]
Type=simple
ExecStart={exec_line}
Restart=always
RestartSec=10
[Install]
WantedBy=default.target
""")
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    subprocess.run(
        ["systemctl", "--user", "enable", "--now", "accountability-monitor.service"],
        capture_output=True,
    )
    return True


def first_run() -> int:
    cfg = ensure_config()
    setup_autostart()
    # Open the settings page so the user can fill things in.
    # Absolute import (not relative): when frozen by PyInstaller this file runs as
    # __main__ with no parent package, so `from . import webui` would fail.
    from accountability_monitor import webui

    print("Goonmaster 7000 is set up. Opening the settings page...")
    return webui.main(["--config", str(cfg)])


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    sub = argv[0] if argv else ""
    cfg = str(config_path())
    if sub == "monitor":
        from accountability_monitor import monitor
        return monitor.main(["--config", cfg, *argv[1:]])
    if sub == "settings":
        from accountability_monitor import webui
        return webui.main(["--config", cfg, *argv[1:]])
    # No subcommand: first-run / open settings.
    return first_run()


if __name__ == "__main__":
    raise SystemExit(main())
