"""Ollama server settings for this machine's tier, and starting / restarting Ollama.

``ald setup`` (and therefore the one-line installers) and ``ald work`` call :func:`ensure`, which

* computes the wanted server environment (``OLLAMA_NUM_PARALLEL`` from the registry's tier hint,
  ``OLLAMA_FLASH_ATTENTION=1`` on GPUs, ``OLLAMA_KEEP_ALIVE``),
* persists it the way each OS expects:
    - Windows: user environment variables (``setx``), read by the Ollama tray app / ``ollama serve``;
    - macOS: ``launchctl setenv`` (re-applied by every ``ald work`` start because it does not survive a reboot);
    - Linux: a systemd drop-in for the system ``ollama.service`` (needs root: ``sudo -n``, never a prompt),
      otherwise ``<config>/ollama.env`` used when ald itself starts ``ollama serve``,
* and restarts Ollama when its running settings differ (Linux reads them from ``/proc``; elsewhere a
  marker file in the data dir records what was applied).

Inference never depends on these values (pins fix the model, prompt and options); they only change how
many requests Ollama runs at once and how long a model stays loaded.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

import httpx

from . import config as cfgmod

KEEP_ALIVE = "30m"  # unload 30 min after the last request: frees VRAM when ald is idle or stopped
DROPIN = Path("/etc/systemd/system/ollama.service.d/ald.conf")
Log = Callable[[str], None]


def wanted_env(num_parallel: int | None, accel: str) -> dict[str, str]:
    env = {"OLLAMA_NUM_PARALLEL": str(max(1, int(num_parallel or 1))), "OLLAMA_KEEP_ALIVE": KEEP_ALIVE}
    if accel in ("cuda", "metal", "rocm"):
        env["OLLAMA_FLASH_ATTENTION"] = "1"
    return env


def _marker() -> Path:
    return cfgmod.data_dir() / "ollama_env.json"


def env_file() -> Path:
    return cfgmod.config_dir() / "ollama.env"


def _run(cmd: list[str], timeout: float = 60) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as e:
        return subprocess.CompletedProcess(cmd, 127, "", str(e))


def up(url: str = "http://127.0.0.1:11434", timeout: float = 2.0) -> bool:
    try:
        return httpx.get(url.rstrip("/") + "/api/version", timeout=timeout).status_code == 200
    except httpx.HTTPError:
        return False


def wait_up(url: str, seconds: float) -> bool:
    t0 = time.time()
    while time.time() - t0 < seconds:
        if up(url):
            return True
        time.sleep(1.0)
    return up(url)


# --------------------------------------------------------------------------- locating / processes
def ollama_exe() -> str | None:
    exe = shutil.which("ollama")
    if exe:
        return exe
    if sys.platform == "win32":
        cand = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
        return str(cand) if cand.exists() else None
    for cand in (str(Path.home() / ".local/ollama/bin/ollama"), "/usr/local/bin/ollama", "/opt/homebrew/bin/ollama", "/Applications/Ollama.app/Contents/Resources/ollama",
                 str(Path.home() / "Applications/Ollama.app/Contents/Resources/ollama")):
        if Path(cand).exists():
            return cand
    return None


def _brew() -> str | None:
    """Homebrew, also when launchd's minimal PATH hides it (Apple Silicon /opt/homebrew, Intel /usr/local)."""
    b = shutil.which("brew")
    if b:
        return b
    for cand in ("/opt/homebrew/bin/brew", "/usr/local/bin/brew"):
        if Path(cand).exists():
            return cand
    return None


def _brew_ollama() -> str | None:
    b = _brew()
    return b if b and _run([b, "list", "ollama"]).returncode == 0 else None


def _win_app() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama app.exe"


def _own_ollama_procs() -> list[Any]:
    import psutil
    me = None
    try:
        me = psutil.Process().username()
    except Exception:  # noqa: BLE001
        pass
    out = []
    for p in psutil.process_iter(["name", "username", "cmdline"]):
        try:
            name = (p.info["name"] or "").lower()
            if not name.startswith("ollama"):
                continue
            if me and p.info["username"] and p.info["username"] != me:
                continue
            out.append(p)
        except Exception:  # noqa: BLE001
            continue
    return out


def _server_procs() -> list[Any]:
    """Our user's ``ollama serve`` processes (not runners)."""
    out = []
    for p in _own_ollama_procs():
        try:
            cl = [c.lower() for c in (p.info["cmdline"] or [])]
        except Exception:  # noqa: BLE001
            continue
        if "serve" in cl:
            out.append(p)
    return out


def _proc_env(p: Any) -> dict[str, str] | None:
    try:
        return dict(p.environ())
    except Exception:  # noqa: BLE001
        return None


def _systemd_ollama() -> bool:
    if not sys.platform.startswith("linux") or not shutil.which("systemctl"):
        return False
    r = _run(["systemctl", "is-active", "ollama"])
    return r.stdout.strip() in ("active", "activating")


def _detach_kw() -> dict[str, Any]:
    kw: dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                          "close_fds": True}
    if sys.platform == "win32":
        kw["creationflags"] = (getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                               | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        kw["start_new_session"] = True
    return kw


def windows_session_id() -> int | None:
    """0 = services session (SSH, S4U tasks): no desktop, the Ollama tray app cannot start there."""
    try:
        import ctypes
        sid = ctypes.c_ulong()
        if ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(sid)):
            return int(sid.value)
    except Exception:  # noqa: BLE001
        pass
    return None


def start(env: dict[str, str], log: Log, *, prefer_app: bool = True, url: str = "http://127.0.0.1:11434") -> str:
    """Start Ollama with ``env`` applied. Returns what was started ('' if nothing could be)."""
    child_env = {**os.environ, **env}
    if sys.platform == "win32":
        app = _win_app()
        if prefer_app and app.exists() and windows_session_id() not in (0, None):
            subprocess.Popen([str(app)], env=child_env, **_detach_kw())
            if wait_up(url, 20):
                return f'"{app}"'
            log("[ollama] the Ollama app did not start the server; starting `ollama serve` instead")
    elif sys.platform == "darwin":
        b = _brew_ollama()
        if b:
            _run([b, "services", "restart", "ollama"])
            return "brew services restart ollama"
        for app in ("/Applications/Ollama.app", str(Path.home() / "Applications/Ollama.app")):
            if Path(app).exists():
                _run(["open", "-a", app])
                return f"open -a {app}"
    else:
        if _systemd_ollama() or (DROPIN.exists() and shutil.which("systemctl")):
            r = _run(["sudo", "-n", "systemctl", "restart", "ollama"])
            if r.returncode == 0:
                return "sudo systemctl restart ollama"
    exe = ollama_exe()
    if not exe:
        return ""
    logf = cfgmod.data_dir() / "logs" / "ollama.log"
    logf.parent.mkdir(parents=True, exist_ok=True)
    kw = _detach_kw()
    fh = open(logf, "ab")
    kw["stdout"] = kw["stderr"] = fh
    try:
        subprocess.Popen([exe, "serve"], env=child_env, **kw)
    finally:
        fh.close()
    return f"{exe} serve (log: {logf})"


def stop(log: Log) -> bool:
    """Stop our user's Ollama (tray app + server + runners). False if Ollama is a system service."""
    b = _brew_ollama() if sys.platform == "darwin" else None
    if b:
        _run([b, "services", "stop", "ollama"])
    if sys.platform == "darwin":
        _run(["osascript", "-e", 'tell application "Ollama" to quit'])
    procs = _own_ollama_procs()
    if not procs:
        return not _systemd_ollama()
    for p in procs:
        try:
            p.terminate()
        except Exception:  # noqa: BLE001
            pass
    import psutil
    _gone, alive = psutil.wait_procs(procs, timeout=10)
    for p in alive:
        try:
            p.kill()
        except Exception:  # noqa: BLE001
            pass
    return True


# --------------------------------------------------------------------------- persisting
def _persist_windows(env: dict[str, str], log: Log) -> bool:
    changed = False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            cur = {}
            for name in env:
                try:
                    cur[name] = str(winreg.QueryValueEx(k, name)[0])
                except OSError:
                    cur[name] = None
    except Exception:  # noqa: BLE001
        cur = {n: None for n in env}
    for name, val in env.items():
        if cur.get(name) != val:
            r = _run(["setx", name, val])
            log(f"[ollama] setx {name} {val} -> {r.returncode}")
            changed = True
    return changed


def _persist_macos(env: dict[str, str], log: Log) -> bool:
    changed = False
    for name, val in env.items():
        if _run(["launchctl", "getenv", name]).stdout.strip() != val:
            _run(["launchctl", "setenv", name, val])
            log(f"[ollama] launchctl setenv {name} {val}")
            changed = True
    return changed


def _dropin_text(env: dict[str, str]) -> str:
    lines = "".join(f'Environment="{k}={v}"\n' for k, v in sorted(env.items()))
    return f"# written by `ald setup`: Ollama settings for this machine's ald tier\n[Service]\n{lines}"


def _persist_linux(env: dict[str, str], log: Log) -> tuple[bool, str | None]:
    """Returns (changed, manual_hint). The env file is always written; the system unit gets a drop-in
    when ``sudo -n`` works (root, or cached sudo credentials), else the hint says what to run."""
    f = env_file()
    text = "".join(f"{k}={v}\n" for k, v in sorted(env.items()))
    changed = not f.exists() or f.read_text(encoding="utf-8") != text
    if changed:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    if not (Path("/etc/systemd/system/ollama.service").exists() or _systemd_ollama()):
        return changed, None
    want = _dropin_text(env)
    try:
        have = DROPIN.read_text(encoding="utf-8")
    except OSError:
        have = None
    if have == want:
        return changed, None
    cmd = f"sudo mkdir -p {DROPIN.parent} && sudo cp {f.with_suffix('.conf')} {DROPIN} && " \
          f"sudo systemctl daemon-reload && sudo systemctl restart ollama"
    conf = f.with_suffix(".conf")
    conf.write_text(want, encoding="utf-8")
    ok = (_run(["sudo", "-n", "mkdir", "-p", str(DROPIN.parent)]).returncode == 0
          and _run(["sudo", "-n", "cp", str(conf), str(DROPIN)]).returncode == 0
          and _run(["sudo", "-n", "systemctl", "daemon-reload"]).returncode == 0)
    if ok:
        log(f"[ollama] wrote {DROPIN}")
        return True, None
    return changed, cmd


def _running_matches(env: dict[str, str]) -> bool | None:
    """Linux: compare a running ``ollama serve``'s environment. None if it cannot be read."""
    if not sys.platform.startswith("linux"):
        return None
    for p in _server_procs():
        penv = _proc_env(p)
        if penv is not None:
            return all(penv.get(k) == v for k, v in env.items())
    return None


# --------------------------------------------------------------------------- entry point
def ensure(env: dict[str, str], *, url: str, log: Log, restart: bool = True, start_if_down: bool = True,
           service_mode: bool = False) -> dict[str, Any]:
    """Persist ``env``, make Ollama run with it, return a report."""
    rep: dict[str, Any] = {"wanted": env, "persisted": False, "restarted": False, "started": "", "hint": None}
    os.environ.update(env)  # anything we spawn (ollama serve, the tray app) inherits it
    if sys.platform == "win32":
        rep["persisted"] = _persist_windows(env, log)
    elif sys.platform == "darwin":
        rep["persisted"] = _persist_macos(env, log)
    else:
        rep["persisted"], rep["hint"] = _persist_linux(env, log)
    marker = cfgmod.read_json(_marker(), {}) or {}
    applied = marker.get("applied") == env
    running = up(url)
    if running and restart:
        match = _running_matches(env)
        stale = (match is False) or (match is None and (not applied or rep["persisted"]))
        if stale:
            if sys.platform.startswith("linux") and _systemd_ollama():
                r = _run(["sudo", "-n", "systemctl", "restart", "ollama"])
                rep["restarted"] = r.returncode == 0
                if not rep["restarted"]:
                    rep["hint"] = rep["hint"] or "sudo systemctl restart ollama"
            elif stop(log):
                time.sleep(1.0)
                rep["started"] = start(env, log, prefer_app=not service_mode)
                rep["restarted"] = bool(rep["started"]) and wait_up(url, 60)
            if rep["restarted"]:
                log(f"[ollama] restarted with {' '.join(f'{k}={v}' for k, v in env.items())}")
    elif not running and start_if_down:
        rep["started"] = start(env, log, prefer_app=not service_mode)
        if rep["started"]:
            log(f"[ollama] started: {rep['started']}")
            wait_up(url, 60)
    if up(url) and (rep["restarted"] or rep["started"] or applied or _running_matches(env)):
        cfgmod.atomic_write_json(_marker(), {"applied": env, "at": time.time()})
    rep["up"] = up(url)
    return rep
