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
SERVICE_DEF_VERSION = 2  # bump when the unit / plist / task definition changes; workers refresh it themselves
LABEL = "org.ald.worker"
TASK = "ald-worker"

Runner = Callable[[list[str]], subprocess.CompletedProcess]


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              stdin=subprocess.DEVNULL)
    except OSError as e:  # e.g. no systemctl in a container
        return subprocess.CompletedProcess(cmd, 127, "", f"{cmd[0]}: {e.strerror or e}")


def ald_executable() -> str:
    exe = shutil.which("ald")
    if exe:
        return exe
    # Fall back to `python -m ald` from this interpreter.
    return sys.executable


def work_command(extra: list[str] | None = None) -> list[str]:
    exe = ald_executable()
    base = [exe] if exe != sys.executable else [exe, "-m", "ald"]
    return base + ["work", "--service"] + (extra or [])  # other settings come from the config (`ald config`)


def windows_command(extra: list[str] | None = None, python: str | None = None) -> list[str]:
    """``pythonw.exe -m ald work ...`` from ald's own environment: no console window (a console window
    would pop up at every logon and closing it would kill the worker)."""
    py = Path(python or sys.executable)
    pyw = py.with_name("pythonw.exe")
    exe = str(pyw if pyw.exists() or python else py)
    return [exe, "-m", "ald", "work", "--service"] + (extra or [])


def _xml_escape(s: str) -> str:
    from xml.sax.saxutils import escape
    return escape(s, {'"': "&quot;"})


def windows_task_xml(cmd: list[str], user: str, *, s4u: bool, workdir: str) -> str:
    """Task Scheduler 1.2 XML. ``s4u``: run whether or not the user is signed in (also at boot), no stored
    password; otherwise run in the user's session at logon. No 72 h execution limit, runs on battery
    (ald pauses leasing itself below 30 %), restarts after failures, one instance."""
    args = subprocess.list2cmdline(cmd[1:])
    boot = ("\n    <BootTrigger><Enabled>true</Enabled><Delay>PT2M</Delay></BootTrigger>" if s4u else "")
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>ald worker: distributed passage labeling (https://github.com/1unarzDev/agentic_literary_discovery). Remove with: ald service uninstall</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled><UserId>{_xml_escape(user)}</UserId><Delay>PT1M</Delay></LogonTrigger>{boot}
    <TimeTrigger>
      <Repetition><Interval>PT10M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
      <StartBoundary>2026-01-01T00:00:00</StartBoundary><Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{_xml_escape(user)}</UserId>
      <LogonType>{"S4U" if s4u else "InteractiveToken"}</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{_xml_escape(cmd[0])}</Command>
      <Arguments>{_xml_escape(args)}</Arguments>
      <WorkingDirectory>{_xml_escape(workdir)}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def _windows_user() -> str:
    """DOMAIN\\user of this process's token. (%USERDOMAIN% is not reliable: under OpenSSH it is
    'WORKGROUP', which Task Scheduler cannot map to an account.)"""
    try:
        import ctypes
        n = ctypes.c_ulong(512)
        buf = ctypes.create_unicode_buffer(n.value)
        if ctypes.windll.secur32.GetUserNameExW(2, buf, ctypes.byref(n)):  # NameSamCompatible
            return buf.value
    except Exception:  # noqa: BLE001
        pass
    r = _run(["whoami"])
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    dom, user = os.environ.get("COMPUTERNAME", ""), os.environ.get("USERNAME", "")
    return f"{dom}\\{user}" if dom else user


def _install_windows(run: Runner, extra: list[str] | None, msgs: list[str]) -> None:
    import tempfile
    cmd = windows_command(extra)
    user = _windows_user()
    workdir = os.environ.get("USERPROFILE", str(Path.home()))
    mode = None
    for s4u in (True, False):
        xml = windows_task_xml(cmd, user, s4u=s4u, workdir=workdir)
        fd, path = tempfile.mkstemp(suffix=".xml")
        with os.fdopen(fd, "wb") as f:
            f.write(xml.encode("utf-16"))
        try:
            r = run(["schtasks", "/Create", "/TN", TASK, "/XML", path, "/F"])
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        if r.returncode == 0:
            mode = "s4u" if s4u else "logon"
            break
        msgs.append(f"schtasks /Create ({'S4U' if s4u else 'interactive'}) -> {r.returncode} "
                    f"{(r.stderr or r.stdout).strip()}")
    if mode is None:
        msgs.append("FAILED: could not create the Scheduled Task; run `ald work` manually")
        return
    if mode == "s4u":
        msgs.append(f"Scheduled Task '{TASK}' installed: starts at boot and at logon, keeps running after "
                    f"sign-out ({subprocess.list2cmdline(cmd)})")
    else:
        msgs.append(f"Scheduled Task '{TASK}' installed: runs while {user} is signed in (starts at logon). "
                    f"For start-at-boot without signing in, re-run `ald service install` from an "
                    f"Administrator PowerShell.")
    run(["schtasks", "/End", "/TN", TASK])  # an older instance would block IgnoreNew
    r = run(["schtasks", "/Run", "/TN", TASK])
    msgs.append(f"schtasks /Run -> {r.returncode}")


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
Restart=always
RestartSec=30
TimeoutStopSec=90
KillSignal=SIGTERM
Environment=PYTHONUNBUFFERED=1
Environment="PATH=%h/.local/bin:%h/.local/ollama/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

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
    <key>KeepAlive</key><true/>
    <key>ThrottleInterval</key><integer>30</integer>
    <key>ProcessType</key><string>Background</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key><string>{escape(str(Path.home()))}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
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
        _install_windows(run, extra, msgs)
    else:
        msgs.append(f"unsupported platform {platform}; run `ald work` manually")
    return msgs


def verify(state_path: Path, max_age_s: float = 90.0, contact_age_s: float = 600.0,
           now: float | None = None) -> tuple[bool, str]:
    """Is a worker process alive (state.json written recently by a live pid) and did it reach the coordinator?"""
    import json
    import time
    now = time.time() if now is None else now
    try:
        st = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False, "no worker state yet"
    pid, upd, contact = st.get("pid"), float(st.get("updated") or 0), st.get("last_contact")
    try:
        import psutil
        alive = bool(pid) and psutil.pid_exists(int(pid))
    except Exception:  # noqa: BLE001
        alive = bool(pid)
    if not alive:
        return False, f"worker process {pid} is not running"
    if now - upd > max_age_s:
        return False, f"worker state is stale ({now - upd:.0f}s old)"
    if not contact or now - float(contact) > contact_age_s:
        return False, f"worker {pid} is running but has not reached the coordinator yet"
    rep = st.get("report") or {}
    return True, (f"worker running (pid {pid}, v{st.get('client_version')}, {rep.get('state')}, "
                  f"keep-awake {'on' if rep.get('keep_awake') else 'off'}); last coordinator contact "
                  f"{now - float(contact):.0f}s ago")


def restart(run: Runner = _run, platform: str = sys.platform) -> list[str]:
    if platform.startswith("linux"):
        r = run(["systemctl", "--user", "restart", UNIT])
        return [f"systemctl --user restart {UNIT} -> {r.returncode} {r.stderr.strip()}"]
    if platform == "darwin":
        r = run(["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{LABEL}"])
        return [f"launchctl kickstart -k -> {r.returncode} {r.stderr.strip()}"]
    if platform == "win32":
        run(["schtasks", "/End", "/TN", TASK])
        r = run(["schtasks", "/Run", "/TN", TASK])
        return [f"schtasks /Run -> {r.returncode} {(r.stderr or r.stdout).strip()}"]
    return ["unsupported platform"]


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


def _extra_after_service(args: list[str]) -> list[str]:
    return args[args.index("--service") + 1:] if "--service" in args else []


def refresh_definition(run: Runner = _run, platform: str = sys.platform) -> str:
    """Rewrite the installed service definition in the current format WITHOUT restarting the running worker
    (called by a service-mode worker after an update). Keeps extra `ald work` args and, on Windows, the
    logon type. Returns a log line ('' if there is nothing to refresh)."""
    import re
    import shlex
    if platform.startswith("linux"):
        p = _systemd_path()
        if not p.exists():
            return ""
        m = re.search(r"^ExecStart=(.*)$", p.read_text(encoding="utf-8"), re.M)
        extra = _extra_after_service(shlex.split(m.group(1))) if m else []
        p.write_text(systemd_unit(work_command(extra)), encoding="utf-8", newline="\n")
        r = run(["systemctl", "--user", "daemon-reload"])
        return f"refreshed {p} (daemon-reload -> {r.returncode})"
    if platform == "darwin":
        p = _plist_path()
        if not p.exists():
            return ""
        args = re.findall(r"<string>(.*?)</string>", p.read_text(encoding="utf-8"))
        extra = _extra_after_service(args)
        p.write_text(launchd_plist(work_command(extra), Path.home() / "Library" / "Logs" / "ald-worker.log"),
                     encoding="utf-8", newline="\n")
        return f"refreshed {p} (applies at next login)"
    if platform == "win32":
        import tempfile
        r = run(["schtasks", "/Query", "/TN", TASK, "/XML"])
        if r.returncode != 0:
            return ""
        s4u = "<LogonType>S4U</LogonType>" in r.stdout
        m = re.search(r"<Arguments>(.*?)</Arguments>", r.stdout)
        extra = _extra_after_service(shlex.split(m.group(1).replace("&quot;", '"'))) if m else []
        xml = windows_task_xml(windows_command(extra), _windows_user(), s4u=s4u,
                               workdir=os.environ.get("USERPROFILE", str(Path.home())))
        fd, path = tempfile.mkstemp(suffix=".xml")
        with os.fdopen(fd, "wb") as f:
            f.write(xml.encode("utf-16"))
        try:
            r = run(["schtasks", "/Create", "/TN", TASK, "/XML", path, "/F"])  # no fallback: never downgrade
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        return f"refreshed task {TASK} ({'S4U' if s4u else 'interactive'}) -> {r.returncode}"
    return ""
