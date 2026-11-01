"""Terminal views: ``ald status`` (this machine), ``ald fleet`` (all workers), ``ald config`` (settings menu)."""

from __future__ import annotations

import datetime as _dt
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

import httpx
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import CLIENT_VERSION
from . import config as cfgmod
from .config import Config, read_json
from .scheduler import GB, StorageManager, fmt_bytes, fmt_duration

SPARK = "▁▂▃▄▅▆▇█"
SPARK_ASCII = " .:-=+*#"


def _unicode_ok() -> bool:
    """Legacy Windows consoles (cp1252 / cp437) cannot print block characters."""
    import sys
    enc = (getattr(sys.stdout, "encoding", None) or "").lower().replace("-", "")
    return enc.startswith("utf")
STATE_STYLE = {"paused": "yellow", "working": "green", "idle": "yellow", "waiting_gpu_lock": "cyan", "outside_hours": "blue",
               "no_stages": "red", "stopped": "red", "starting": "cyan"}


def sparkline(vals: list[float]) -> str:
    if not vals:
        return ""
    hi = max(vals) or 1
    g = SPARK if _unicode_ok() else SPARK_ASCII
    return "".join(g[min(len(g) - 1, int(v / hi * (len(g) - 1)))] if v else " " for v in vals)


def bar(parts: list[tuple[float, str]], width: int = 30) -> Text:
    total = sum(v for v, _ in parts) or 1
    t = Text()
    used = 0
    uni = _unicode_ok()
    ascii_glyph = {"green": "#", "cyan": "=", "grey37": ".", "red": "x"}
    for i, (v, style) in enumerate(parts):
        n = round(v / total * width) if i < len(parts) - 1 else width - used
        n = max(0, min(n, width - used))
        t.append(("█" if uni else ascii_glyph.get(style, "#")) * n, style=style)
        used += n
    return t


def ago(ts: float | str | None, now: float | None = None) -> str:
    if ts is None:
        return "never"
    if isinstance(ts, str):
        try:
            ts = _dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return ts
    s = max(0.0, (now or time.time()) - float(ts))
    return f"{s:.0f}s ago" if s < 120 else f"{s / 60:.0f}m ago" if s < 7200 else f"{s / 3600:.1f}h ago"


# --------------------------------------------------------------------------- ald status
_PING_CACHE: dict[str, Any] = {}


def _ping(url: str | None) -> dict[str, Any] | None:
    if not url:
        return None
    hit = _PING_CACHE.get(url)
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    try:
        p = httpx.get(url.rstrip("/") + "/v1/ping", timeout=5).json()
    except (httpx.HTTPError, ValueError):
        p = None
    _PING_CACHE[url] = (time.time(), p)
    return p


def _ollama_ps(url: str) -> list[dict[str, Any]] | None:
    try:
        return httpx.get(url.rstrip("/") + "/api/ps", timeout=2).json().get("models", [])
    except (httpx.HTTPError, ValueError):
        return None


def local_summary(cfg: Config) -> dict[str, Any]:
    from . import service as svc
    from .keepawake import battery_info
    from .results import Outbox
    root = cfgmod.data_dir()
    st = read_json(root / "state.json", {}) or {}
    ok, why = svc.verify(root / "state.json")
    rep = st.get("report") or {}
    alive = ok or "has not reached the coordinator" in why  # process up, coordinator contact pending
    storage = StorageManager(root, budget_bytes=int(cfg.disk_budget_gb * GB) if cfg.disk_budget_gb else None)
    n_out, out_bytes = Outbox(root).size()
    ping = _ping(cfg.coordinator_url)
    from .updater import decide
    upd = decide(ping, current=CLIENT_VERSION) if ping else None
    return {
        "worker_running": ok, "worker_detail": why, "state": rep.get("state") if alive else "not running",
        "pid": st.get("pid"), "service": st.get("service"), "last_contact": st.get("last_contact"),
        "keep_awake": bool(rep.get("keep_awake")) if alive else False,
        "battery": battery_info(), "tier": st.get("tier") or cfg.tier, "stages": st.get("stages") or [],
        "excluded": st.get("excluded") or {}, "gpu": rep.get("gpu"), "ollama_models": _ollama_ps(cfg.ollama_url),
        "jobs": st.get("held_jobs") or [], "concurrency": st.get("concurrency") or {},
        "rates_pph": {s: round(r * 3600) for s, r in (st.get("rates_pps") or {}).items()},
        "passages_done_session": st.get("passages_done"), "disk": storage.report(),
        "outbox": {"entries": n_out, "bytes": out_bytes},
        "client_version": CLIENT_VERSION, "running_version": st.get("client_version"),
        "latest_version": ping.get("latest_client_version") if ping else None,
        "update_available": bool(upd and upd.update_available), "coordinator": cfg.coordinator_url,
        "name": cfg.name, "worker_id": cfg.worker_id, "gpu_lock": cfg.gpu_lock, "active_hours": cfg.active_hours,
        "data_dir": str(root), "paused": cfgmod.pause_marker().exists(),
    }


def render_status(s: dict[str, Any]) -> Panel:
    t = Table.grid(padding=(0, 2))
    t.add_column(style="bold", no_wrap=True)
    t.add_column()
    style = STATE_STYLE.get(str(s["state"]), "red")
    t.add_row("Worker", Text.assemble((f"{s['state']}", f"bold {style}"),
                                      f"  {s['worker_detail']}" if not s["worker_running"] else
                                      f"  pid {s['pid']}{' (service)' if s['service'] else ''}"))
    if s.get("paused"):
        t.add_row("Paused", Text("yes: `ald resume` to continue", "bold yellow"))
    t.add_row("Coordinator", f"{s['coordinator']}  last contact {ago(s['last_contact'])}")
    t.add_row("Keep-awake", Text("held", "green") if s["keep_awake"] else Text("not held", "yellow"))
    b = s["battery"] or {}
    t.add_row("Power", "desktop (no battery)" if b.get("percent") is None else
              f"battery {b['percent']}% {'plugged in' if b.get('plugged') else '[yellow]on battery[/yellow]'}")
    t.add_row("Tier / GPU", f"{s['tier']}  {s['gpu'] or ''}")
    t.add_row("Stages", ", ".join(s["stages"]) or "[red]none[/red]")
    for k, v in (s["excluded"] or {}).items():
        if "not requested" not in v:
            t.add_row("", f"[dim]excluded {k}: {v}[/dim]")
    models = s["ollama_models"]
    if models is None:
        t.add_row("Ollama", "[red]not reachable[/red]")
    else:
        t.add_row("Ollama", ", ".join(
            f"{m.get('name')} {100 * (m.get('size_vram') or 0) / max(1, m.get('size') or 1):.0f}% on GPU"
            for m in models) or "no model loaded")
    if s["jobs"]:
        for j in s["jobs"]:
            t.add_row("Job", Text.assemble(f"{j['job_id']} ({j['stage']}) ", bar(
                [(j["progress"], "green"), (1 - j["progress"], "grey37")], 20),
                f" {j['progress']:.0%}  ETA {fmt_duration(j.get('remaining_s'))}"))
    else:
        t.add_row("Job", "-")
    t.add_row("Throughput", ", ".join(f"{k}: {v}/h (c={s['concurrency'].get(k, '?')})"
                                      for k, v in s["rates_pph"].items()) or "-")
    d = s["disk"]
    t.add_row("Disk", f"{fmt_bytes(d['used_bytes'])} used of {fmt_bytes(d['budget_bytes'])} budget "
                      f"(free {fmt_bytes(d['free_bytes'])}, reserve {fmt_bytes(d['reserve_bytes'])})")
    o = s["outbox"]
    t.add_row("Outbox", f"{o['entries']} pending upload(s), {fmt_bytes(o['bytes'])}")
    v = f"{s['client_version']}"
    if s["running_version"] and s["running_version"] != s["client_version"]:
        v += f" (worker runs {s['running_version']})"
    if s["update_available"]:
        v += f"  [yellow]update {s['latest_version']} available (installs itself between jobs)[/yellow]"
    elif s["latest_version"]:
        v += "  (latest)"
    t.add_row("Version", v)
    extra = []
    if s["gpu_lock"]:
        extra.append(f"gpu-lock {s['gpu_lock']}")
    if s["active_hours"]:
        extra.append(f"active hours {s['active_hours']}")
    if extra:
        t.add_row("Settings", "; ".join(extra))
    return Panel(t, title=f"ald status - {s['name'] or ''}", subtitle=s["data_dir"], expand=False)


# --------------------------------------------------------------------------- ald fleet
def fleet_token(explicit: str | None = None) -> tuple[str | None, str | None]:
    """(url, token): --token / ALD_VIEWER_TOKEN / ALD_ADMIN_TOKEN, else ~/.config/ald-viewer.json or ald-admin.json."""
    url = None
    tok = explicit or os.environ.get("ALD_VIEWER_TOKEN") or os.environ.get("ALD_ADMIN_TOKEN")
    for name, key in (("ald-viewer.json", "viewer_token"), ("ald-admin.json", "admin_token")):
        d = read_json(Path.home() / ".config" / name, {}) or {}
        url = url or d.get("url")
        if not tok and d.get(key):
            tok = d[key]
    return url, tok


def render_fleet(f: dict[str, Any]) -> Group:
    now = time.time()
    w = Table(title="Workers", expand=False)
    for c in ("name", "os", "tier", "GPU", "status", "stage", "progress", "passages/h", "tok/s", "1h", "24h",
              "awake", "power", "ver", "last seen"):
        w.add_column(c, no_wrap=c in ("name", "status", "last seen"))
    for x in f.get("workers") or []:
        r = x.get("report") or {}
        try:
            age = now - _dt.datetime.fromisoformat(str(x.get("last_seen")).replace("Z", "+00:00")).timestamp()
        except ValueError:
            age = 1e9
        state = r.get("state") or "?"
        if age > 900:
            state, style = "silent", "red"
        else:
            style = STATE_STYLE.get(state, "white")
        bp = r.get("battery_percent")
        power = "AC" if bp is None else f"{bp}%{'' if r.get('power_plugged') else ' bat'}"
        w.add_row(str(x.get("name")), str(x.get("os")), str(x.get("tier")), str(x.get("gpu") or "")[:28],
                  Text(state, style), str(r.get("stage") or "-"),
                  f"{r['progress']:.0%}" if r.get("progress") is not None else "-",
                  str(r.get("passages_per_hour") or "-"), str(x.get("tok_s") or "-"),
                  str(x.get("passages_1h")), str(x.get("passages_24h")),
                  "yes" if r.get("keep_awake") else "-", power, str(r.get("client_version") or x.get("client_version")),
                  ago(x.get("last_seen"), now))
    q = Table(title="Queue by stage (jobs; bar = passages done/leased/queued/dead)", expand=False)
    for c in ("stage", "progress", "done", "leased", "queued", "dead", "remaining passages", "fleet/h", "ETA"):
        q.add_column(c)
    rem = f.get("remaining_passages") or {}
    pph = f.get("fleet_passages_per_hour") or {}
    eta = f.get("eta_hours") or {}
    pas: dict[str, dict[str, float]] = {}
    for wv in f.get("waves") or []:
        d = pas.setdefault(wv["stage"], {})
        for k, v in (wv.get("passages") or {}).items():
            d[k] = d.get(k, 0) + (v or 0)
    for stage, v in (f.get("queue") or {}).items():
        if not any(v.get(k) for k in ("done", "leased", "queued", "dead")):
            continue
        p = pas.get(stage, {})
        q.add_row(stage, bar([(p.get("done", 0), "green"), (p.get("leased", 0), "cyan"),
                              (p.get("queued", 0), "grey37"), (p.get("dead", 0), "red")]),
                  str(v.get("done", 0)), str(v.get("leased", 0)), str(v.get("queued", 0)), str(v.get("dead", 0)),
                  str(rem.get(stage, 0)), str(pph.get(stage, 0)),
                  "-" if eta.get(stage) is None else f"{eta[stage]} h")
    wt = Table(title="Waves", expand=False)
    for c in ("wave", "stage", "progress", "done/total passages"):
        wt.add_column(c)
    for wv in f.get("waves") or []:
        p = wv.get("passages") or {}
        total = sum(v for k, v in p.items() if k != "closed")
        if not total:
            continue
        wt.add_row(wv["wave"], wv["stage"], bar([(p.get("done", 0), "green"), (p.get("leased", 0), "cyan"),
                                                 (p.get("queued", 0), "grey37"), (p.get("dead", 0), "red")], 24),
                   f"{p.get('done', 0)}/{total}")
    hourly = [h["passages"] for h in f.get("hourly_passages") or []]
    qual = []
    for r in f.get("quality_24h") or []:
        n = (r.get("n_ok") or 0) + (r.get("n_flagged") or 0)
        if n:
            qual.append(f"{r['stage']}: {r.get('n_flagged') or 0}/{n} flagged "
                        f"({100 * (r.get('n_flagged') or 0) / n:.1f}%: schema failures + unverified quotes)")
    foot = Text.assemble(("Fleet passages/hour, last 24 h: ", "bold"), sparkline(hourly),
                         f"  (now {hourly[-1] if hourly else 0}, peak {max(hourly) if hourly else 0})\n",
                         ("Quality, 24 h: ", "bold"), "; ".join(qual) or "no results yet",
                         f"\nGenerated {f.get('generated')}  sealed={f.get('sealed')}")
    return Group(w, q, wt, foot)


# --------------------------------------------------------------------------- ald config
SETTINGS: list[tuple[str, str, str]] = [
    # key, label, kind
    ("name", "Display name (re-join to change it on the coordinator)", "str"),
    ("disk_budget_gb", "Disk budget for ald (GB; empty = 10 GB, always keeps 20 GB free)", "float"),
    ("active_hours", "Work only between HH:MM-HH:MM daily (empty = always)", "hours"),
    ("max_concurrency", "Max concurrent requests (empty = 8; auto-tuned below it)", "int"),
    ("stages", "Stages subset, comma-separated (empty = all allowed for the tier)", "list"),
    ("gpu_lock", "GPU lock file shared with other programs (Linux/macOS; empty = none)", "str"),
    ("auto_update", "Install updates automatically", "bool"),
    ("keep_awake", "Keep the computer awake while working (off = allow sleep)", "bool"),
]


def parse_setting(kind: str, raw: str) -> Any:
    raw = raw.strip()
    if kind == "bool":
        if raw.lower() in ("1", "y", "yes", "true", "on"):
            return True
        if raw.lower() in ("0", "n", "no", "false", "off"):
            return False
        raise ValueError("answer yes or no")
    if raw == "" or raw.lower() in ("none", "-"):
        return None
    if kind == "int":
        v = int(raw)
        if v < 1:
            raise ValueError("must be >= 1")
        return v
    if kind == "float":
        v = float(raw)
        if v <= 0:
            raise ValueError("must be > 0")
        return v
    if kind == "list":
        return [x.strip() for x in raw.replace(" ", ",").split(",") if x.strip()]
    if kind == "hours":
        from .scheduler import in_active_hours
        a, b = raw.split("-", 1)
        for part in (a, b):
            hh, mm = (int(x) for x in part.strip().split(":"))
            if not (0 <= hh < 24 and 0 <= mm < 60):
                raise ValueError("use HH:MM-HH:MM")
        in_active_hours(raw, time.time())
        return raw
    return raw


def fmt_setting(v: Any) -> str:
    if v is None:
        return "[dim](default)[/dim]"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, list):
        return ", ".join(v)
    return str(v)


def render_config(cfg: Config) -> Table:
    t = Table(title=f"ald settings ({cfgmod.config_path()})", show_lines=False)
    t.add_column("#", justify="right")
    t.add_column("setting")
    t.add_column("value")
    for i, (k, label, _kind) in enumerate(SETTINGS, 1):
        t.add_row(str(i), label, fmt_setting(getattr(cfg, k)))
    return t


def config_menu(console: Console, ask: Callable[[str], str], restart: Callable[[], list[str]]) -> bool:
    """Interactive loop. Returns True if anything changed."""
    cfg = Config.load()
    changed = False
    while True:
        console.print(render_config(cfg))
        choice = ask("Number to change, [bold]s[/bold] save and quit, [bold]q[/bold] quit without saving").strip().lower()
        if choice in ("s", "save"):
            if changed:
                cfg.save()
                console.print(f"[green]saved {cfgmod.config_path()}[/green]")
                if ask("Restart the background worker now so it uses them? [Y/n]").strip().lower() in ("", "y", "yes"):
                    for m in restart():
                        console.print(m, markup=False)
            return changed
        if choice in ("q", "quit", ""):
            return False
        try:
            key, label, kind = SETTINGS[int(choice) - 1]
        except (ValueError, IndexError):
            console.print("[red]pick a number from the list[/red]")
            continue
        raw = ask(f"{label}\n  current: {fmt_setting(getattr(cfg, key))}; new value (empty = default)")
        try:
            setattr(cfg, key, parse_setting(kind, raw) if not (kind == "bool" and raw.strip() == "") else
                    (True if key in ("auto_update", "keep_awake") else None))
            changed = True
        except ValueError as e:
            console.print(f"[red]{e}[/red]")


def to_json(obj: Any) -> str:
    return json.dumps(obj, default=str, indent=2)
