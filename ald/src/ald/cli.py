"""``ald`` command line."""

from __future__ import annotations

import datetime as _dt
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import threading
from importlib import resources
from pathlib import Path
from typing import Any, Callable, Optional

import httpx
import typer
from rich.console import Console
from rich.table import Table

from . import CLIENT_VERSION
from . import config as cfgmod
from . import service as svc
from .backend.ollama import BackendError, OllamaBackend
from .client import CoordinatorClient, CoordinatorError
from .config import Config, read_json
from .hw import detect
from .registry import Registry, RegistryError, digests_match, version_in_range
from .scheduler import GB, StorageManager, fmt_bytes, fmt_duration

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="Worker client for the distributed passage-labeling system.")
service_app = typer.Typer(no_args_is_help=True, help="Background service (resume work after reboot).")
app.add_typer(service_app, name="service")
console = Console()
err = Console(stderr=True)

SHARD_IN_BYTES = int(1.5 * 1024 ** 2)
SHARD_OUT_BYTES = int(2.0 * 1024 ** 2)
DOCTOR_RESERVE_GB = 20


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def make_logger(log_path: Path | None) -> Callable[[str], None]:
    lock = threading.Lock()
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        line = f"{_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
        with lock:
            err.print(line, markup=False, highlight=False)
            if log_path is not None:
                try:
                    if log_path.exists() and log_path.stat().st_size > 10 * 1024 ** 2:
                        cfgmod.replace_with_retry(log_path, log_path.with_suffix(".log.1"))
                    with open(log_path, "a", encoding="utf-8", newline="\n") as f:
                        f.write(line + "\n")
                except OSError:
                    pass
    return log


def _client(cfg: Config, url: str | None = None) -> CoordinatorClient | None:
    u = url or cfg.coordinator_url
    return CoordinatorClient(u, cfg.token) if u else None


def load_registry(cfg: Config, path: Optional[Path] = None, url: str | None = None,
                  quiet: bool = False) -> tuple[Registry, str]:
    if path:
        return Registry.load(path), str(path)
    c = _client(cfg, url)
    if c is not None:
        try:
            raw, _etag = c.registry()
            if raw:
                return Registry.from_dict(raw), f"{c.base_url}v1/registry"
        except (CoordinatorError, httpx.HTTPError, RegistryError) as e:
            if not quiet:
                err.print(f"[yellow]registry fetch failed: {e}[/yellow]")
    cached = read_json(cfgmod.data_dir() / "registry.json")
    if cached and cached.get("registry"):
        return Registry.from_dict(cached["registry"]), "cached registry.json"
    text = resources.files("ald.data").joinpath("models.v1.example.json").read_text(encoding="utf-8")
    if not quiet:
        err.print("[yellow]using the bundled EXAMPLE registry (placeholder models)[/yellow]")
    return Registry.from_dict(json.loads(text)), "bundled example"


def _parse_stages(stages: Optional[str]) -> list[str] | None:
    if not stages:
        return None
    return [s.strip() for s in stages.replace(" ", ",").split(",") if s.strip()]


def install_hint(os_name: str) -> tuple[str, list[str]]:
    if os_name == "windows":
        if (Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe").exists():
            return "(Ollama is installed but did not start; start the Ollama app, then re-run)", []
        return "winget install --silent Ollama.Ollama", ["winget", "install", "--id", "Ollama.Ollama", "-e",
                                                          "--source", "winget", "--silent",
                                                          "--accept-package-agreements",
                                                          "--accept-source-agreements", "--disable-interactivity"]
    if os_name == "macos":
        if shutil.which("brew"):
            return "brew install ollama && brew services start ollama", ["brew", "install", "ollama"]
        return ("download https://ollama.com/download/Ollama-darwin.zip and move Ollama.app to /Applications",
                [])
    return ("curl -fsSL https://ollama.com/install.sh | sh   (the script uses sudo to install a system service)",
            ["sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh"])


def start_ollama(os_name: str, env: dict[str, str] | None = None) -> str:
    """Best-effort start of a local Ollama server; returns what we did."""
    from . import ollama_env
    return ollama_env.start(env or {}, log=lambda m: None)


def _wait_for_ollama(backend: OllamaBackend, seconds: float = 20.0) -> bool:
    import time
    t0 = time.time()
    while time.time() - t0 < seconds:
        if backend.available():
            return True
        time.sleep(1.0)
    return False


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------

@app.command()
def doctor(
    coordinator: Optional[str] = typer.Option(None, "--coordinator", help="Coordinator base URL."),
    bench: bool = typer.Option(False, "--bench", help="Run the ~60 s Ollama benchmark."),
    seconds: float = typer.Option(60.0, "--seconds", help="Benchmark budget (total)."),
    registry_path: Optional[Path] = typer.Option(None, "--registry", help="Local models.v1.json."),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output."),
    save: bool = typer.Option(True, "--save/--no-save", help="Remember tier + benchmark in config."),
    levels: Optional[str] = typer.Option(None, "--levels", help="Concurrency levels to benchmark, e.g. 1,2,4,6,8."),
    bench_stages: Optional[str] = typer.Option(None, "--stages", help="Benchmark only these stages (default: the "
                                               "tier's main stages)."),
    gpu_lock: Optional[str] = typer.Option(None, "--gpu-lock", envvar="ALD_GPU_LOCK",
                                           help="Benchmark only if this flock(2) lock is free (never waits); "
                                                "unload the models afterwards."),
) -> None:
    """Detect hardware, pick a tier, test bandwidth and (optionally) benchmark."""
    cfg = Config.load()
    data = cfgmod.data_dir()
    hw = detect(data)
    reg, reg_src = load_registry(cfg, registry_path, coordinator, quiet=as_json)
    tier = reg.select_tier(hw.usable_vram_gb)
    report: dict[str, Any] = {"client_version": CLIENT_VERSION, "hardware": hw.to_json(), "tier": tier["name"],
                              "allowed_stages": reg.allowed_stages(tier["name"]), "registry": reg_src,
                              "num_parallel_hint": reg.num_parallel_hint(tier["name"])}

    url = coordinator or cfg.coordinator_url
    client = CoordinatorClient(url, cfg.token) if url else None
    status = None
    if client is not None:
        try:
            report["ping"] = client.ping()
        except (CoordinatorError, httpx.HTTPError) as e:
            report["ping"] = {"error": str(e)}
        try:
            report["bandwidth"] = client.bwtest()
        except (CoordinatorError, httpx.HTTPError) as e:
            report["bandwidth"] = {"error": str(e)}
        try:
            status = client.status()
        except (CoordinatorError, httpx.HTTPError) as e:
            report["status_error"] = str(e)

    backend = OllamaBackend(cfg.ollama_url)
    try:
        report["ollama_version"] = backend.version()
    except BackendError:
        report["ollama_version"] = None

    storage = StorageManager(data, budget_bytes=int(cfg.disk_budget_gb * GB) if cfg.disk_budget_gb else None)
    free = shutil.disk_usage(str(data)).free
    shards_fit = max(0, int((free - DOCTOR_RESERVE_GB * GB) // (SHARD_IN_BYTES + SHARD_OUT_BYTES)))
    report["disk"] = {"free_gb": round(free / GB, 1), "reserve_gb": DOCTOR_RESERVE_GB,
                      "shards_fit_free_minus_reserve": shards_fit,
                      "budget_gb": round(storage.budget_bytes() / GB, 2),
                      "shards_fit_budget": storage.plan(10 ** 9).jobs}

    if bench:
        from .bench import eta_for_share, run_bench
        from .gpulock import GpuLock
        lock = GpuLock(gpu_lock, log=lambda m: None)
        if report["ollama_version"] is None:
            err.print("[red]Ollama is not running; `ald setup` first.[/red]")
        elif not lock.try_acquire():
            err.print(f"[yellow]GPU lock {gpu_lock} is held by another program: benchmark skipped "
                      f"(ald work auto-tunes instead).[/yellow]")
            report["bench_skipped"] = f"gpu lock {gpu_lock} busy"
        else:
            from .bench import LEVELS, default_bench_stages
            lv = tuple(int(x) for x in levels.split(",")) if levels else LEVELS
            sel = _parse_stages(bench_stages) or default_bench_stages(reg, tier["name"])
            res = run_bench(backend, reg, [s for s in sel if s in reg.stages], total_seconds=seconds, levels=lv,
                            accel=hw.accel, log=(lambda m: None) if as_json else (lambda m: err.print(m)))
            for s, r in res.items():
                if "passages_per_hour" in r:
                    r["eta"] = eta_for_share(status or report.get("ping"), s, r["passages_per_hour"])
            report["bench"] = res
            if lock.enabled:
                for st_name in res:
                    try:
                        backend.unload(reg.stages[st_name].model_ref)
                    except BackendError:
                        pass
                lock.release()
            if save:
                cfg.bench = {**(cfg.bench or {}),
                             **{s: {k: r[k] for k in ("best_concurrency", "passages_per_hour", "tok_s")}
                                for s, r in res.items() if "best_concurrency" in r}}
    if save and (cfg.coordinator_url or cfg.token or bench):
        cfg.update(tier=tier["name"], **({"bench": cfg.bench} if bench else {}))

    if as_json:
        console.print_json(json.dumps(report, default=str))
        return
    _print_doctor(report)


def _print_doctor(r: dict[str, Any]) -> None:
    hw = r["hardware"]
    t = Table(title=f"ald doctor (client {r['client_version']})", show_header=False)
    t.add_column("item", style="bold")
    t.add_column("value")
    t.add_row("OS / arch", f"{hw['os']} {hw['os_release']} / {hw['arch']}")
    t.add_row("CPU", f"{hw['cpu_model']} ({hw['cpu_cores_physical']} cores / {hw['cpu_cores_logical']} threads)")
    t.add_row("RAM", f"{hw['ram_gb']:.1f} GB")
    t.add_row("GPU", hw["gpu_summary"])
    t.add_row("Usable VRAM", f"{hw['usable_vram_gb']:.1f} GB ({hw['accel']})")
    d = r["disk"]
    t.add_row("Disk free", f"{d['free_gb']} GB at {hw['disk_path']}")
    t.add_row("Shards that fit", f"{d['shards_fit_free_minus_reserve']} (free - {d['reserve_gb']} GB reserve); "
                                 f"{d['shards_fit_budget']} within the {d['budget_gb']} GB budget")
    t.add_row("Ollama", r.get("ollama_version") or "[red]not running / not installed[/red]")
    t.add_row("Registry", r["registry"])
    t.add_row("Tier", f"[bold green]{r['tier']}[/bold green]  stages: {', '.join(r['allowed_stages']) or '-'}")
    if r.get("num_parallel_hint"):
        t.add_row("Ollama parallel", f"registry suggests OLLAMA_NUM_PARALLEL={r['num_parallel_hint']} "
                                     f"(set it in the Ollama server's environment, then restart Ollama)")
    if "ping" in r:
        t.add_row("Coordinator", json.dumps(r["ping"]))
    bw = r.get("bandwidth")
    if bw:
        t.add_row("Bandwidth", f"{bw['mbit_s']:.0f} Mbit/s ({bw['bytes'] / 1e6:.1f} MB in {bw['seconds']:.1f}s)"
                  if "mbit_s" in bw else f"[yellow]{bw.get('error')}[/yellow]")
    if r.get("status_error") and "401" not in r["status_error"]:  # /v1/status is admin-only; ping has the queue
        t.add_row("Queue status", f"[yellow]unavailable: {r['status_error']}[/yellow]")
    for n in hw.get("notes") or []:
        t.add_row("note", n)
    console.print(t)
    b = r.get("bench")
    if b:
        bt = Table(title="Benchmark (real stage prompt, bundled sample passages)")
        for c in ("stage", "concurrency", "passages", "tok/s", "passages/h", "mean latency", "valid", "errors"):
            bt.add_column(c)
        for s, res in b.items():
            for lv in res.get("levels", []):
                best = lv["concurrency"] == res.get("best_concurrency")
                bt.add_row(s, f"{lv['concurrency']}{' *' if best else ''}", str(lv["passages"]), str(lv["tok_s"]),
                           f"{lv['passages_per_hour']:.0f}", f"{lv['mean_latency_s']}s",
                           str(lv["valid_rate"]), str(lv["errors"]))
            if "error" in res:
                bt.add_row(s, "-", "-", "-", "-", "-", "-", res["error"][:40])
        console.print(bt)
        et = Table(title="ETA for this worker's share")
        for c in ("stage", "passages/h", "remaining passages", "active workers", "my share", "ETA"):
            et.add_column(c)
        for s, res in b.items():
            e = res.get("eta") or {}
            et.add_row(s, f"{res.get('passages_per_hour', 0):.0f}", str(e.get("remaining_passages", "-")),
                       str(e.get("active_workers", "-")), str(e.get("my_share_passages", "-")),
                       f"{e['eta_hours']} h" if e.get("eta_hours") is not None else "- (queue status unavailable)")
        console.print(et)


# --------------------------------------------------------------------------
# setup
# --------------------------------------------------------------------------

@app.command()
def setup(
    yes: bool = typer.Option(False, "--yes", "-y", help="Non-interactive: install/pull without asking."),
    registry_path: Optional[Path] = typer.Option(None, "--registry"),
    stages: Optional[str] = typer.Option(None, "--stages", help="Comma-separated subset of stages."),
    tier_override: Optional[str] = typer.Option(None, "--tier"),
    ollama_env: bool = typer.Option(True, "--ollama-env/--no-ollama-env",
                                    help="Set OLLAMA_NUM_PARALLEL / OLLAMA_FLASH_ATTENTION / OLLAMA_KEEP_ALIVE for "
                                         "this tier (persistently) and restart Ollama if they changed."),
) -> None:
    """Check/install Ollama, then pull and verify the pinned models for your tier."""
    cfg = Config.load()
    hw = detect()
    backend = OllamaBackend(cfg.ollama_url)
    reg, src = load_registry(cfg, registry_path)
    tier = tier_override or cfg.tier or reg.select_tier(hw.usable_vram_gb)["name"]
    from . import ollama_env as oenv
    want_env = oenv.tier_env(reg, tier, hw.accel, cfg.host_prompt_cache_mb)
    if not backend.available():
        started = start_ollama(hw.os, want_env if cfg.manage_ollama else None)
        if started and _wait_for_ollama(backend, 45):
            console.print(f"Started Ollama: {started}")
    if not backend.available():
        hint, cmd = install_hint(hw.os)
        console.print(f"[yellow]Ollama is not reachable at {cfg.ollama_url}.[/yellow]")
        console.print(f"Install it with:\n  [bold]{hint}[/bold]")
        if not cmd:
            raise typer.Exit(1)
        if hw.os == "linux":
            console.print("[yellow]The official installer asks for sudo to create a system service.[/yellow]")
        if yes or typer.confirm(f"Run `{' '.join(cmd)}` now?", default=False):
            rc = subprocess.run(cmd).returncode
            if rc != 0:
                console.print(f"[red]installer exited with {rc}[/red]")
                raise typer.Exit(rc)
            if hw.os == "macos" and shutil.which("brew"):
                subprocess.run(["brew", "services", "start", "ollama"])
            start_ollama(hw.os, want_env if cfg.manage_ollama else None)
            if not _wait_for_ollama(backend, 60):
                console.print("[red]Ollama installed but not reachable yet; start it and re-run `ald setup`.[/red]")
                raise typer.Exit(1)
        else:
            raise typer.Exit(1)
    if ollama_env and cfg.manage_ollama:
        rep = oenv.ensure(want_env, url=cfg.ollama_url, log=lambda m: console.print(m, markup=False, highlight=False))
        console.print("Ollama settings for tier " + tier + ": " + " ".join(f"{k}={v}" for k, v in want_env.items())
                      + (" (restarted Ollama)" if rep["restarted"] else ""))
        if rep.get("hint"):
            console.print(f"[yellow]To apply them to the Ollama system service run:[/yellow]\n  {rep['hint']}")
        if not _wait_for_ollama(backend, 30):
            console.print("[red]Ollama is not reachable after applying its settings; start it and re-run.[/red]")
            raise typer.Exit(1)
    ver = backend.version(refresh=True)
    wanted = reg.allowed_stages(tier)
    sel = _parse_stages(stages)
    if sel:
        wanted = [s for s in wanted if s in sel]
    console.print(f"Ollama {ver}; registry {reg.version} ({src}); tier {tier}; stages {', '.join(wanted) or '-'}")
    ok = True
    pulled: set[str] = set()
    for s in wanted:
        st = reg.stages[s]
        if not version_in_range(ver, st.version_range):
            console.print(f"[red]{s}: Ollama {ver} is outside the pinned range {st.version_range}; "
                          f"install a matching Ollama version.[/red]")
            ok = False
            continue
        d = backend.local_digest(st.model_ref)
        if d is None or not digests_match(d, st.model_digest):
            if st.model_ref not in pulled:
                if not (yes or typer.confirm(f"Pull {st.model_ref} (~{st.model_size_gb} GB) for {s}?", default=True)):
                    ok = False
                    continue
                last = {"status": ""}

                def prog(ev: dict[str, Any]) -> None:
                    msg = ev.get("status", "")
                    if ev.get("total") and ev.get("completed"):
                        msg += f" {ev['completed'] / ev['total']:.0%}"
                    if msg != last["status"]:
                        last["status"] = msg
                        err.print(f"  {st.model_ref}: {msg}", highlight=False)
                try:
                    backend.pull(st.model_ref, prog)
                except BackendError as e:
                    console.print(f"[red]{s}: pull failed: {e}[/red]")
                    ok = False
                    continue
                pulled.add(st.model_ref)
            d = backend.local_digest(st.model_ref)
        if d is None or not digests_match(d, st.model_digest):
            console.print(f"[red]{s}: {st.model_ref} digest {str(d)[:16]} != pinned {st.model_digest[:16]} "
                          f"(registry may still hold placeholders)[/red]")
            ok = False
        else:
            console.print(f"[green]{s}: {st.model_ref} digest verified ({st.model_digest[:12]})[/green]")
    if cfg.tier != tier:
        cfg.update(tier=tier)
    if not ok:
        raise typer.Exit(1)


# --------------------------------------------------------------------------
# join / status / sync
# --------------------------------------------------------------------------

@app.command()
def join(
    url: str = typer.Argument(..., help="Coordinator base URL."),
    invite: str = typer.Argument(..., help="Single-use invite code."),
    name: Optional[str] = typer.Option(None, "--name", help="Display name (default: hostname)."),
    force: bool = typer.Option(False, "--force", help="Re-join even if a token is already saved."),
) -> None:
    """Trade an invite for a worker token (saved in your user config, chmod 600)."""
    cfg = Config.load()
    if cfg.token and cfg.coordinator_url and cfg.coordinator_url.rstrip("/") == url.rstrip("/") and not force:
        console.print(f"Already joined {url} as {cfg.name} ({cfg.worker_id}); use --force to re-join.")
        return
    hw = detect()
    reg, _ = load_registry(Config(coordinator_url=url), None, url, quiet=True)
    tier = reg.select_tier(hw.usable_vram_gb)["name"]
    info = {"name": name or socket.gethostname(), "os": hw.os, "arch": hw.arch, "gpu": hw.gpu_summary,
            "vram_gb": hw.usable_vram_gb, "ram_gb": hw.ram_gb, "tier": tier}
    c = CoordinatorClient(url)
    try:
        resp = c.join(invite, info)
    except (CoordinatorError, httpx.HTTPError) as e:
        console.print(f"[red]join failed: {e}[/red]")
        raise typer.Exit(1)
    p = cfg.update(coordinator_url=url.rstrip("/"), token=resp["token"], worker_id=resp.get("worker_id"),
                   name=info["name"], tier=tier)
    console.print(f"[green]Joined as {cfg.name} (worker {cfg.worker_id}, tier {tier}). Token saved to {p}[/green]")


@app.command()
def status(
    watch: bool = typer.Option(False, "--watch", "-w", help="Refresh every 5 s (Ctrl-C to quit)."),
    as_json: bool = typer.Option(False, "--json"),
    local: bool = typer.Option(True, "--local", hidden=True, help="(default; kept for compatibility)"),
    details: bool = typer.Option(False, "--details", help="Also list jobs on disk and outbox entries."),
) -> None:
    """This machine: is the worker running, keep-awake, power, GPU, current job, throughput, disk, version."""
    from . import ui
    cfg = Config.load()
    if as_json:
        console.print_json(ui.to_json(ui.local_summary(cfg)))
        return
    if not watch:
        console.print(ui.render_status(ui.local_summary(cfg)))
        if details:
            _status_local(cfg, False)
        return
    import time
    from rich.live import Live
    with Live(ui.render_status(ui.local_summary(cfg)), console=console, refresh_per_second=1) as live:
        try:
            while True:
                time.sleep(5)
                live.update(ui.render_status(ui.local_summary(Config.load())))
        except KeyboardInterrupt:
            pass


@app.command()
def fleet(
    watch: bool = typer.Option(False, "--watch", "-w", help="Refresh every 30 s (Ctrl-C to quit)."),
    as_json: bool = typer.Option(False, "--json"),
    token: Optional[str] = typer.Option(None, "--token", help="Viewer or admin token (default: ALD_VIEWER_TOKEN, "
                                        "ALD_ADMIN_TOKEN, ~/.config/ald-viewer.json, ~/.config/ald-admin.json)."),
    url: Optional[str] = typer.Option(None, "--url", help="Coordinator URL (default: from the token file or config)."),
) -> None:
    """All workers: status, throughput, queue progress per stage and wave, fleet passages/h, ETA."""
    from . import ui
    furl, tok = ui.fleet_token(token)
    base = (url or furl or Config.load().coordinator_url or "").rstrip("/")
    if not base or not tok:
        console.print("[red]need a coordinator URL and a viewer token (ask the admin for one: "
                      "POST /v1/admin/viewer_token)[/red]")
        raise typer.Exit(1)

    def get() -> dict[str, Any]:
        r = httpx.get(f"{base}/v1/fleet", headers={"Authorization": f"Bearer {tok}"}, timeout=30)
        if r.status_code != 200:
            raise CoordinatorError(r.status_code, r.text[:200])
        return r.json()

    try:
        data = get()
    except (CoordinatorError, httpx.HTTPError) as e:
        console.print(f"[red]fleet: {e}[/red]")
        raise typer.Exit(1)
    if as_json:
        console.print_json(json.dumps(data))
        return
    if not watch:
        console.print(ui.render_fleet(data))
        return
    import time
    from rich.live import Live
    with Live(ui.render_fleet(data), console=console, refresh_per_second=1) as live:
        try:
            while True:
                time.sleep(30)
                try:
                    live.update(ui.render_fleet(get()))
                except (CoordinatorError, httpx.HTTPError):
                    pass
        except KeyboardInterrupt:
            pass


config_app = typer.Typer(invoke_without_command=True, help="View and change ald's settings (menu, or show/set).")
app.add_typer(config_app, name="config")


@config_app.callback()
def config_cmd(ctx: typer.Context) -> None:
    """Interactive settings menu (`ald config show` / `ald config set KEY VALUE` for scripts)."""
    if ctx.invoked_subcommand is not None:
        return
    from rich.prompt import Prompt
    from . import ui
    if not sys.stdin or not sys.stdin.isatty():
        console.print(ui.render_config(Config.load()))
        console.print("(not a terminal: use `ald config set KEY VALUE`)")
        return
    ui.config_menu(console, lambda q: Prompt.ask(q, default="", show_default=False, console=console), svc.restart)


@config_app.command("show")
def config_show(as_json: bool = typer.Option(False, "--json")) -> None:
    from . import ui
    cfg = Config.load()
    if as_json:
        console.print_json(json.dumps({k: getattr(cfg, k) for k, _l, _t in ui.SETTINGS}))
    else:
        console.print(ui.render_config(cfg))


@config_app.command("set")
def config_set(key: str = typer.Argument(...), value: str = typer.Argument("", help="Empty = default."),
               restart: bool = typer.Option(False, "--restart", help="Restart the background worker.")) -> None:
    from . import ui
    kinds = {k: t for k, _l, t in ui.SETTINGS}
    if key not in kinds:
        console.print(f"[red]unknown setting {key}; one of: {', '.join(kinds)}[/red]")
        raise typer.Exit(2)
    cfg = Config.load()
    try:
        v = ui.parse_setting(kinds[key], value) if value != "" or kinds[key] != "bool" else True
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(2)
    cfg.update(**{key: v})
    console.print(f"{key} = {ui.fmt_setting(v)}")
    if key in ("schedule", "active_hours"):
        from .scheduler import legacy_hours_to_schedule
        for m in svc.sync_wake(cfg.schedule or legacy_hours_to_schedule(cfg.active_hours)):
            console.print(m, markup=False)
    if restart:
        for m in svc.restart():
            console.print(m, markup=False)


def _status_local(cfg: Config, as_json: bool) -> None:
    from .results import JobStore, Outbox, Checkpoint
    root = cfgmod.data_dir()
    storage = StorageManager(root, budget_bytes=int(cfg.disk_budget_gb * GB) if cfg.disk_budget_gb else None)
    ob = Outbox(root)
    n, size = ob.size()
    store = JobStore(root)
    jobs = []
    for d, meta in store.iter_jobs():
        jobs.append({"job_id": meta.get("job_id"), "stage": meta.get("stage"), "state": meta.get("state"),
                     "lines": len(Checkpoint(d).load()), "n_todo": meta.get("n_todo")})
    state = read_json(root / "state.json", {}) or {}
    rep = {"data_dir": str(root), "disk": storage.report(), "outbox": {"entries": n, "bytes": size,
           "items": [{"job_id": e.job_id, "partial": e.partial, "attempts": e.meta.get("attempts"),
                      "last_error": e.meta.get("last_error")} for e in ob.entries()]},
           "jobs": jobs, "worker_state": state, "config": {"coordinator": cfg.coordinator_url, "tier": cfg.tier,
                                                           "name": cfg.name, "worker_id": cfg.worker_id}}
    if as_json:
        console.print_json(json.dumps(rep, default=str))
        return
    t = Table(title=f"Local state ({root})", show_header=False)
    t.add_column("k", style="bold")
    t.add_column("v")
    d = rep["disk"]
    t.add_row("Disk used by ald", fmt_bytes(d["used_bytes"]))
    t.add_row("Disk budget", f"{fmt_bytes(d['budget_bytes'])} (available {fmt_bytes(d['available_bytes'])}, "
                             f"free {fmt_bytes(d['free_bytes'])}, reserve {fmt_bytes(d['reserve_bytes'])})")
    t.add_row("Outbox", f"{n} pending upload(s), {fmt_bytes(size)}")
    t.add_row("Coordinator", str(cfg.coordinator_url))
    t.add_row("Tier", str(state.get("tier") or cfg.tier))
    t.add_row("Stages", ", ".join(state.get("stages") or []) or "-")
    rates = state.get("rates_pps") or {}
    t.add_row("Throughput", ", ".join(f"{s}: {r * 3600:.0f}/h" for s, r in rates.items()) or "-")
    for hj in state.get("held_jobs") or []:
        t.add_row("Job", f"{hj['job_id']} {hj['stage']} {hj['progress']:.0%} ETA {fmt_duration(hj.get('remaining_s'))}")
    console.print(t)
    if jobs:
        jt = Table(title="Jobs on disk")
        for c in ("job", "stage", "state", "lines", "todo"):
            jt.add_column(c)
        for j in jobs:
            jt.add_row(str(j["job_id"]), str(j["stage"]), str(j["state"]), str(j["lines"]), str(j["n_todo"]))
        console.print(jt)
    for it in rep["outbox"]["items"]:
        console.print(f"  outbox: {it['job_id']} {'partial' if it['partial'] else 'final'} "
                      f"attempts={it['attempts']} {it['last_error'] or ''}")


@app.command("sync-now")
def sync_now() -> None:
    """Upload everything in the outbox (and interrupted jobs) right now."""
    cfg = Config.load()
    w = _make_worker(cfg, background=False, auto_update=False, auto_pull=False)
    try:
        w.refresh_registry(force=True)
    except Exception:  # noqa: BLE001
        pass
    if w._registry is not None:
        w.recover_interrupted()
    counts = w.flush_outbox(force=True)
    n, size = w.outbox.size()
    console.print(f"acked {counts['acked']}, rejected {counts['rejected']}, still pending {n} ({fmt_bytes(size)})")


@app.command("self-update")
def self_update() -> None:
    """Upgrade ald (wraps `uv tool upgrade ald`)."""
    uv = shutil.which("uv")
    if not uv:
        console.print("[red]uv not found; install it from https://docs.astral.sh/uv/ first[/red]")
        raise typer.Exit(1)
    cfg = Config.load()
    wheel = None
    c = _client(cfg)
    if c is not None:
        try:
            wheel = c.ping().get("wheel_url")
        except (CoordinatorError, httpx.HTTPError):
            pass
    from .updater import uv_install_cmd
    cmd = uv_install_cmd(wheel, uv)
    console.print("$ " + " ".join(cmd))
    raise typer.Exit(subprocess.run(cmd).returncode)


@app.command()
def pause() -> None:
    """Pause work: the worker finishes nothing new, uploads what it has, frees the GPU, and stays paused
    (also across restarts and updates) until `ald resume`."""
    import time
    m = cfgmod.pause_marker()
    m.parent.mkdir(parents=True, exist_ok=True)
    m.write_text(f"paused {time.strftime('%Y-%m-%d %H:%M:%S')}\n", encoding="utf-8")
    console.print("paused: the worker uploads partial results and frees the GPU within ~10 s. `ald resume` continues.")


@app.command()
def resume() -> None:
    """Resume work after `ald pause`."""
    m = cfgmod.pause_marker()
    if m.exists():
        m.unlink()
        console.print("resumed: the worker continues within ~10 s.")
    else:
        console.print("not paused.")


@app.command()
def version() -> None:
    """Print the client version."""
    print(CLIENT_VERSION)


@app.command()
def pins(registry_path: Optional[Path] = typer.Option(None, "--registry")) -> None:
    """Print the pin objects for POST /v1/admin/pin (admin helper)."""
    reg, _ = load_registry(Config.load(), registry_path, quiet=True)
    console.print_json(json.dumps([st.pin_object() for st in reg.stages.values()]))


# --------------------------------------------------------------------------
# work
# --------------------------------------------------------------------------

def _make_worker(cfg: Config, **kw: Any):
    from .worker import Worker
    if not cfg.coordinator_url or not cfg.token:
        console.print("[red]not joined; run `ald join URL INVITE --name NAME` first[/red]")
        raise typer.Exit(1)
    root = cfgmod.data_dir()
    log = kw.pop("log", None) or make_logger(root / "logs" / "worker.log")
    client = CoordinatorClient(cfg.coordinator_url, cfg.token)
    backend = OllamaBackend(cfg.ollama_url)
    hw = kw.pop("hw", None) or detect()
    kw.setdefault("manage_ollama", cfg.manage_ollama)
    return Worker(cfg, client, backend, data_root=root, hw=hw, log=log, **kw)


def _install_signal_handlers(worker: Any) -> None:
    hits = {"n": 0}

    def handler(signum: int, _frame: Any) -> None:
        hits["n"] += 1
        if hits["n"] >= 2:
            raise KeyboardInterrupt
        worker.log(f"[signal] {signal.Signals(signum).name}: stopping; uploading partial results and "
                   f"releasing leases (press Ctrl-C again to force)")
        worker.stop.set()

    for name in ("SIGINT", "SIGTERM", "SIGHUP", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is not None:
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):
                pass
    if sys.platform == "win32":
        _install_windows_ctrl_handler(worker)


_WIN_HANDLER: Any = None


def _install_windows_ctrl_handler(worker: Any) -> None:
    """Console close / logoff / shutdown: Windows gives us a few seconds."""
    global _WIN_HANDLER
    try:
        import ctypes
        from ctypes import wintypes
        HANDLER = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

        def on_event(ctrl: int) -> bool:
            if ctrl in (2, 5, 6):  # CLOSE, LOGOFF, SHUTDOWN
                worker.stop.set()
                worker.shutdown_done.wait(4.5)
                return True
            return False  # let Python's SIGINT/SIGBREAK handlers run

        _WIN_HANDLER = HANDLER(on_event)
        ctypes.windll.kernel32.SetConsoleCtrlHandler(_WIN_HANDLER, True)
    except Exception:  # noqa: BLE001
        pass


@app.command()
def work(
    max_concurrency: Optional[int] = typer.Option(None, "--max-concurrency",
                                                  help="Upper bound for auto-tuned concurrency (config; default 8)."),
    keep_awake: Optional[bool] = typer.Option(None, "--keep-awake/--allow-sleep",
                                              help="Prevent system sleep while working (config; default on)."),
    stages: Optional[str] = typer.Option(None, "--stages", help="Comma-separated subset of allowed stages (config)."),
    active_hours: Optional[str] = typer.Option(None, "--active-hours",
                                               help="Legacy: only work HH:MM-HH:MM daily (use --schedule)."),
    schedule: Optional[str] = typer.Option(None, "--schedule",
                                           help='Weekly windows (config), e.g. "mon-fri 21:00-05:00,07:00-15:00; '
                                                'sat-sun 21:00-05:00". Local time; spans may cross midnight.'),
    until: Optional[str] = typer.Option(None, "--until", help="Stop leasing near HH:MM (local time)."),
    hours: Optional[float] = typer.Option(None, "--hours", help="Run for N hours."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the plan without leasing."),
    no_auto_update: bool = typer.Option(False, "--no-auto-update", help="Do not self-update."),
    disk_budget_gb: Optional[float] = typer.Option(None, "--disk-budget-gb", help="Cap ald's disk use."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Non-interactive (accepted for service use)."),
    gpu_lock: Optional[str] = typer.Option(None, "--gpu-lock", envvar="ALD_GPU_LOCK",
                                           help="Share the GPU via flock(2) on PATH: hold it per shard, unload the "
                                                "model before releasing when others wait (Linux/macOS; no-op on Windows)."),
    service_mode: bool = typer.Option(False, "--service", hidden=True, help="Started by `ald service`."),
) -> None:
    """Lease jobs and label passages until stopped."""
    from .keepawake import KeepAwake
    from .scheduler import RunWindow
    cfg = Config.load()
    # Command-line options override the saved settings (`ald config`), which the service relies on.
    if disk_budget_gb is not None:
        cfg.disk_budget_gb = disk_budget_gb
    window = RunWindow.from_args(until, hours)
    argv = sys.argv[1:]
    w = _make_worker(cfg, stages=_parse_stages(stages) or cfg.stages,
                     max_concurrency=max_concurrency or cfg.max_concurrency or 8, window=window,
                     auto_update=cfg.auto_update and not no_auto_update, argv=argv, auto_pull=not dry_run,
                     gpu_lock=gpu_lock or cfg.gpu_lock, service_mode=service_mode,
                     active_hours=active_hours or cfg.active_hours,
                     schedule=schedule or (None if active_hours else cfg.schedule))
    keep_awake = cfg.keep_awake if keep_awake is None else keep_awake
    if dry_run:
        try:
            w.refresh_registry(force=True)
            w.resolve_stages()
        except RuntimeError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)
        _print_plan(w.plan(), w)
        return
    _install_signal_handlers(w)
    with KeepAwake(keep_awake, log=w.log) as ka:
        w.keep_awake = ka
        try:
            w.run()
        except KeyboardInterrupt:
            w.log("[signal] forced exit; checkpoints are on disk and will be uploaded at next start")
            w.shutdown(flush_timeout_s=3)


def _print_plan(p: Any, w: Any) -> None:
    t = Table(title="ald work --dry-run", show_header=False)
    t.add_column("k", style="bold")
    t.add_column("v")
    t.add_row("Tier", p.tier)
    t.add_row("Stages", ", ".join(p.stages) or "[red]none[/red]")
    for s, why in p.excluded.items():
        t.add_row(f"  excluded {s}", why)
    for s in p.stages:
        st = w.registry.stages[s]
        t.add_row(f"  {s}", f"model {st.model_ref}; need {w.fit.need_gb(st, 1):.1f} GB @c=1 of "
                            f"{w.fit.capacity_gb:.1f} GB; start c={p.concurrency.get(s)} (max "
                            f"{w.tuners[s].max_c}); ~{p.passages_per_hour.get(s) or '?'} passages/h; "
                            f"lease {p.lease_size.get(s)} job(s)")
    d = p.disk
    t.add_row("Disk", f"used {fmt_bytes(d['used_bytes'])}, budget {fmt_bytes(d['budget_bytes'])}, "
                      f"available {fmt_bytes(d['available_bytes'])}")
    t.add_row("Jobs that fit", str(w.storage.plan(10 ** 6).jobs))
    n, size = w.outbox.size()
    t.add_row("Outbox", f"{n} pending ({fmt_bytes(size)})")
    if p.deadline:
        t.add_row("Window ends", _dt.datetime.fromtimestamp(p.deadline).strftime("%Y-%m-%d %H:%M"))
    console.print(t)


# --------------------------------------------------------------------------
# service
# --------------------------------------------------------------------------

@service_app.command("install")
def service_install(extra: Optional[str] = typer.Option(None, "--args", help="Extra args for `ald work`.")) -> None:
    """Install (or rewrite) and start the background service that runs `ald work`."""
    msgs = svc.install(extra=extra.split() if extra else None)
    from .scheduler import legacy_hours_to_schedule
    _c = Config.load()
    msgs += svc.sync_wake(_c.schedule or legacy_hours_to_schedule(_c.active_hours))
    cfgmod.atomic_write_json(cfgmod.data_dir() / "service_def.json",
                             {"version": svc.SERVICE_DEF_VERSION, "client_version": CLIENT_VERSION})
    for m in msgs:
        console.print(m, markup=False, highlight=False)
    if any(m.startswith("FAILED") for m in msgs) or any(" -> 127" in m for m in msgs) or \
            any("enable --now" in m and " -> 0" not in m for m in msgs):
        raise typer.Exit(1)


@service_app.command("verify")
def service_verify(wait: float = typer.Option(0.0, "--wait", help="Keep checking for up to N seconds.")) -> None:
    """Exit 0 if the worker process is alive and has reached the coordinator."""
    import time
    t0 = time.time()
    while True:
        ok, msg = svc.verify(cfgmod.data_dir() / "state.json")
        if ok or time.time() - t0 >= wait:
            break
        time.sleep(5)
    console.print(("[green]OK[/green] " if ok else "[red]NOT OK[/red] ") + msg)
    raise typer.Exit(0 if ok else 1)


@service_app.command("uninstall")
def service_uninstall() -> None:
    for m in svc.uninstall():
        console.print(m)


@service_app.command("status")
def service_status() -> None:
    console.print(svc.status(), markup=False, highlight=False)


@service_app.command("restart")
def service_restart() -> None:
    """Restart the background worker (e.g. after `ald config`)."""
    for m in svc.restart():
        console.print(m)


def main() -> None:
    # Under pythonw.exe (the Windows Scheduled Task) there is no console: sys.stdout/stderr are None.
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if stream is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
        else:
            try:  # never crash on a character the console code page cannot show
                stream.reconfigure(errors="replace")
            except (AttributeError, ValueError):
                pass
    app()


if __name__ == "__main__":
    main()
