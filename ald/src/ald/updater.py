"""Self-update: ``uv tool install --force <wheel_url>`` (or ``uv tool upgrade
ald``) and re-exec with the same arguments.

Loop guard: at most one attempt per target version per hour, recorded in
``<data>/update_state.json``. A failed update keeps the old version running
when the coordinator still allows it (current >= min_client_version).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import CLIENT_VERSION
from .config import atomic_write_json, read_json
from .registry import RegistryError, version_lt

ATTEMPT_COOLDOWN_S = 3600.0


@dataclass
class UpdateDecision:
    current: str
    latest: str | None
    minimum: str | None
    wheel_url: str | None
    update_available: bool
    required: bool


def decide(ping: dict[str, Any], current: str = CLIENT_VERSION) -> UpdateDecision:
    latest = ping.get("latest_client_version")
    minimum = ping.get("min_client_version")

    def lt(a: str, b: str | None) -> bool:
        if not b:
            return False
        try:
            return version_lt(a, str(b))
        except RegistryError:
            return False

    return UpdateDecision(current=current, latest=latest, minimum=minimum, wheel_url=ping.get("wheel_url"),
                          update_available=lt(current, latest), required=lt(current, minimum))


def uv_install_cmd(wheel_url: str | None, uv: str = "uv") -> list[str]:
    if wheel_url:
        return [uv, "tool", "install", "--force", "--python", "3.12", wheel_url]
    return [uv, "tool", "upgrade", "ald"]


def find_uv(which: Callable[[str], str | None] = shutil.which) -> str | None:
    """uv on PATH, else the standalone installer's default location (a Scheduled Task / launchd / systemd
    environment may not have ~/.local/bin on PATH)."""
    uv = which("uv")
    if uv:
        return uv
    for cand in (Path.home() / ".local" / "bin" / ("uv.exe" if os.name == "nt" else "uv"),
                 Path.home() / ".cargo" / "bin" / ("uv.exe" if os.name == "nt" else "uv")):
        if cand.exists():
            return str(cand)
    return None


def windows_update_script(install_cmd: list[str], relaunch: str, pid: int, log_path: Path) -> str:
    """A .cmd that waits for ``pid`` (the running worker, whose files are locked while it runs) to exit,
    runs the uv install, then relaunches the worker (old or new version) either way."""
    q = subprocess.list2cmdline
    log = f'"{log_path}"'
    return "\r\n".join([
        "@echo off",
        "setlocal",
        f"echo [%date% %time%] waiting for pid {pid} >> {log}",
        ":wait",
        f'tasklist /FI "PID eq {pid}" /NH 2>nul | find " {pid} " >nul',
        "if not errorlevel 1 ( ping -n 3 127.0.0.1 >nul & goto wait )",
        f"echo [%date% %time%] {q(install_cmd)} >> {log}",
        f"{q(install_cmd)} >> {log} 2>&1",
        f"echo [%date% %time%] uv exit %errorlevel%; relaunching >> {log}",
        f"{relaunch} >> {log} 2>&1",
        "endlocal",
        "",
    ])


def windows_relaunch_cmd(argv: list[str], service_mode: bool) -> str:
    """The .cmd line that restarts the worker: the Scheduled Task, or a new console for `ald work`."""
    if service_mode:
        from .service import TASK
        return f"schtasks /Run /TN {TASK}"
    exe = shutil.which("ald") or "ald"
    return f'start "ald" {subprocess.list2cmdline([exe] + argv)}'



def spawn_detached_windows(script: Path) -> None:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
    breakaway = 0x01000000  # CREATE_BREAKAWAY_FROM_JOB: survive the Scheduled Task's job object
    args = ["cmd.exe", "/d", "/c", str(script)]
    kw = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    try:
        subprocess.Popen(args, creationflags=flags | breakaway, **kw)
    except OSError:  # the job does not allow breakaway
        subprocess.Popen(args, creationflags=flags, **kw)


def default_reexec(argv: list[str]) -> None:
    """Replace this process with a fresh ``ald`` carrying the same args."""
    exe = shutil.which("ald") or sys.argv[0]
    args = [exe] + argv
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(args, creationflags=flags, close_fds=True)
        os._exit(0)
    os.execv(exe, args)


class Updater:
    def __init__(
        self,
        state_path: Path,
        *,
        current: str = CLIENT_VERSION,
        run: Callable[..., Any] = subprocess.run,
        reexec: Callable[[list[str]], None] = default_reexec,
        clock: Callable[[], float] | None = None,
        which: Callable[[str], str | None] = shutil.which,
        log: Callable[[str], None] = print,
        platform: str = sys.platform,
        spawn: Callable[[Path], None] = spawn_detached_windows,
        exit_fn: Callable[[int], None] = os._exit,
        service_mode: bool = False,
    ):
        import time
        self.state_path = state_path
        self.current = current
        self.run = run
        self.reexec = reexec
        self.clock = clock or time.time
        self.which = which
        self.log = log
        self.platform = platform
        self.spawn = spawn
        self.exit_fn = exit_fn
        self.service_mode = service_mode

    def _state(self) -> dict[str, Any]:
        return read_json(self.state_path, {}) or {}

    def can_attempt(self, target: str) -> bool:
        last = (self._state().get("attempts") or {}).get(target)
        return last is None or self.clock() - float(last) >= ATTEMPT_COOLDOWN_S

    def _record(self, target: str, ok: bool, detail: str) -> None:
        st = self._state()
        st.setdefault("attempts", {})[target] = self.clock()
        log = st.setdefault("log", [])
        log.append({"t": self.clock(), "from": self.current, "to": target, "ok": ok, "detail": detail[:500]})
        st["log"] = log[-50:]
        atomic_write_json(self.state_path, st)

    def apply(self, d: UpdateDecision, argv: list[str]) -> bool:
        """Install the update and re-exec. Returns False if the update was not
        attempted or failed (caller keeps running the old version if allowed).
        On success this does not return (re-exec)."""
        target = str(d.latest or d.minimum or "")
        if not target:
            return False
        if not self.can_attempt(target):
            self.log(f"[update] skipping {target}: already attempted within the last hour")
            return False
        uv = find_uv(self.which)
        if not uv:
            self._record(target, False, "uv not found on PATH")
            self.log("[update] uv not found on PATH; install uv or run `ald self-update` manually")
            return False
        cmd = uv_install_cmd(d.wheel_url, uv)
        self.log(f"[update] {self.current} -> {target}: {' '.join(cmd)}")
        if self.platform == "win32":
            return self._apply_windows(target, cmd, argv)
        try:
            p = self.run(cmd, capture_output=True, text=True, timeout=900)
            ok = getattr(p, "returncode", 1) == 0
            detail = (getattr(p, "stderr", "") or getattr(p, "stdout", "") or "").strip()
        except (OSError, subprocess.SubprocessError) as e:
            ok, detail = False, str(e)
        self._record(target, ok, detail)
        if not ok:
            self.log(f"[update] failed: {detail[:300]}")
            return False
        self.log("[update] installed; restarting with the same arguments")
        self.reexec(argv)
        return True

    def _apply_windows(self, target: str, cmd: list[str], argv: list[str]) -> bool:
        """Windows locks the files of a running Python environment, so the install cannot replace the
        tool while this process runs: hand over to a detached helper and exit."""
        script = self.state_path.parent / "update.cmd"
        log_path = self.state_path.parent / "logs" / "update.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        relaunch = windows_relaunch_cmd(argv, self.service_mode)
        script.write_text(windows_update_script(cmd, relaunch, os.getpid(), log_path), encoding="utf-8")
        try:
            self.spawn(script)
        except OSError as e:
            self._record(target, False, f"could not start the update helper: {e}")
            self.log(f"[update] could not start the update helper: {e}")
            return False
        self._record(target, True, f"deferred to {script}; log {log_path}")
        self.log(f"[update] exiting so the helper can install {target} and relaunch ({log_path})")
        self.exit_fn(0)
        return True
