"""Background service so ``ald work`` resumes after reboot / logon.

* Linux:   systemd --user unit ``ald-worker.service``
* macOS:   launchd LaunchAgent ``org.ald.worker``
* Windows: Scheduled Task ``ald-worker`` at logon
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

UNIT = "ald-worker.service"
LABEL = "org.ald.worker"
TASK = "ald-worker"

Runner = Callable[[list[str]], subprocess.CompletedProcess]


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def ald_executable() -> str:
    exe = shutil.which("ald")
    if exe:
        return exe
    # Fall back to `python -m ald` from this interpreter.
    return sys.executable


def work_command(extra: list[str] | None = None) -> list[str]:
    exe = ald_executable()
    base = [exe] if exe != sys.executable else [exe, "-m", "ald"]
    return base + ["work", "--keep-awake"] + (extra or [])


def systemd_unit(cmd: list[str]) -> str:
    def q(a: str) -> str:
        return f'"{a}"' if " " in a else a
    return f"""[Unit]
Description=ald worker (distributed passage labeling)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={' '.join(q(a) for a in cmd)}
Restart=on-failure
RestartSec=30
TimeoutStopSec=90
KillSignal=SIGTERM
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
"""


def launchd_plist(cmd: list[str], log_path: Path) -> str:
    from xml.sax.saxutils import escape
    args = "\n".join(f"        <string>{escape(a)}</string>" for a in cmd)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>{LABEL}</string>
    <key>ProgramArguments</key>
    <array>
{args}
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
    <key>ThrottleInterval</key><integer>30</integer>
    <key>ProcessType</key><string>Background</string>
    <key>StandardOutPath</key><string>{escape(str(log_path))}</string>
    <key>StandardErrorPath</key><string>{escape(str(log_path))}</string>
</dict>
</plist>
"""


def _systemd_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "systemd" / "user" / UNIT


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def install(run: Runner = _run, platform: str = sys.platform, extra: list[str] | None = None) -> list[str]:
    """Install (idempotently) and start the service. Returns log lines."""
    cmd = work_command(extra)
    msgs: list[str] = []
    if platform.startswith("linux"):
        p = _systemd_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(systemd_unit(cmd), encoding="utf-8", newline="\n")
        msgs.append(f"wrote {p}")
        for c in (["systemctl", "--user", "daemon-reload"], ["systemctl", "--user", "enable", "--now", UNIT]):
            r = run(c)
            msgs.append(f"$ {' '.join(c)} -> {r.returncode} {r.stderr.strip()}")
        msgs.append("To keep it running without an open login session (start at boot): "
                    "`loginctl enable-linger $USER` (may ask for your password).")
    elif platform == "darwin":
        p = _plist_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        log = Path.home() / "Library" / "Logs" / "ald-worker.log"
        p.write_text(launchd_plist(cmd, log), encoding="utf-8", newline="\n")
        msgs.append(f"wrote {p}")
        uid = str(os.getuid())
        run(["launchctl", "bootout", f"gui/{uid}/{LABEL}"])  # idempotent re-install
        r = run(["launchctl", "bootstrap", f"gui/{uid}", str(p)])
        if r.returncode != 0:
            r = run(["launchctl", "load", "-w", str(p)])
        msgs.append(f"launchctl -> {r.returncode} {r.stderr.strip()}; log: {log}")
    elif platform == "win32":
        tr = subprocess.list2cmdline(cmd)
        c = ["schtasks", "/Create", "/TN", TASK, "/SC", "ONLOGON", "/TR", tr, "/RL", "LIMITED", "/F"]
        r = run(c)
        msgs.append(f"schtasks /Create -> {r.returncode} {(r.stdout or r.stderr).strip()}")
        r = run(["schtasks", "/Run", "/TN", TASK])
        msgs.append(f"schtasks /Run -> {r.returncode}")
    else:
        msgs.append(f"unsupported platform {platform}; run `ald work` manually")
    return msgs


def uninstall(run: Runner = _run, platform: str = sys.platform) -> list[str]:
    msgs: list[str] = []
    if platform.startswith("linux"):
        r = run(["systemctl", "--user", "disable", "--now", UNIT])
        msgs.append(f"systemctl --user disable --now -> {r.returncode}")
        p = _systemd_path()
        if p.exists():
            p.unlink()
            msgs.append(f"removed {p}")
        run(["systemctl", "--user", "daemon-reload"])
    elif platform == "darwin":
        r = run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"])
        msgs.append(f"launchctl bootout -> {r.returncode}")
        p = _plist_path()
        if p.exists():
            p.unlink()
            msgs.append(f"removed {p}")
    elif platform == "win32":
        run(["schtasks", "/End", "/TN", TASK])
        r = run(["schtasks", "/Delete", "/TN", TASK, "/F"])
        msgs.append(f"schtasks /Delete -> {r.returncode}")
    return msgs


def status(run: Runner = _run, platform: str = sys.platform) -> str:
    if platform.startswith("linux"):
        r = run(["systemctl", "--user", "status", "--no-pager", UNIT])
        return r.stdout or r.stderr
    if platform == "darwin":
        r = run(["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"])
        return r.stdout or r.stderr or "not loaded"
    if platform == "win32":
        r = run(["schtasks", "/Query", "/TN", TASK, "/V", "/FO", "LIST"])
        return r.stdout or r.stderr
    return "unsupported platform"
