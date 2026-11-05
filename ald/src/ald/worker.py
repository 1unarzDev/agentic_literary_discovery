"""``ald work``: lease -> download -> infer -> verify -> checkpoint -> upload.

Durability model
----------------
* Every completed passage is appended to ``jobs/<job>/checkpoint.jsonl``
  immediately (fsync every 20 lines).
* A finished job becomes one final blob in the on-disk outbox; an interrupted
  job (Ctrl-C, SIGTERM, console close / logoff / shutdown, deadline, revoked,
  lease lost while offline, pin retired, stage demoted) becomes a PARTIAL blob
  (``PUT /v1/result/<job>?partial=1``) and the lease is released.
* At startup, before leasing, interrupted jobs found on disk (crash / power
  loss) are turned into partial blobs, released, and the outbox is flushed. A
  background thread keeps flushing with backoff + jitter while the network is
  down. Local files are deleted only after HTTP 200.
* Leases may carry ``skip_passage_ids`` (covered by an earlier partial
  upload); those passages are neither run nor included in the final blob.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sys
import random
import threading
import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx

from . import CLIENT_VERSION
from .backend.ollama import BackendError, BackendOOM, BackendUnavailable, OllamaBackend
from .client import CoordinatorClient, CoordinatorError, UpgradeRequired
from .config import Config, atomic_write_json, read_json
from .hw import HardwareInfo
from .inference import is_flagged, run_passage
from .registry import Registry, RegistryError, Stage, digests_match, version_in_range
from .results import JobStore, Outbox, encode_jsonl_gz, read_jsonl_gz, sha256_bytes
from .scheduler import (
    DEFAULT_PASSAGES_PER_JOB, GB, Backoff, Clock, ConcurrencyTuner, HardwareFit, PlanSummary, RateTracker,
    RunWindow, StorageManager, lease_size, should_prefetch,
)
from .gpulock import GpuLock
from .scheduler import in_schedule, next_schedule_change
from .updater import Updater, decide

LEASE_TTL_S = 600.0
HEARTBEAT_S = 60.0
REGISTRY_POLL_S = 300.0
PING_POLL_S = 300.0
FLUSH_POLL_S = 30.0
GPU_YIELD_S = 2.0              # --gpu-lock: pause between shards when nobody waited recently
GPU_YIELD_CONTENDED_S = 30.0   # ... when the lock was contended in the last GPU_CONTENDED_WINDOW_S
GPU_YIELD_UNKNOWN_S = 20.0     # ... where waiters cannot be detected (macOS)
GPU_CONTENDED_WINDOW_S = 900.0
DESKTOP_VRAM_BASELINE_GB = 1.5  # VRAM other programs may hold without lowering ald's plan
WAIT_FILE_MAX_AGE_S = 600.0  # <data>/gpu.wait older than this is stale
RAM_BACKOFF_S = 600.0  # after a low-memory interrupt: no new lease for 10 min (then reserve + model needed)
IDLE_HEARTBEAT_S = 300.0  # self-report while holding nothing (fleet view); cheap on D1 writes
STATE_SAVE_S = 15.0
MAX_PASSAGE_ERRORS = 2
OOM_DEMOTE_AFTER = 2  # OOMs at concurrency 1 before the stage is demoted


def parse_ts(v: Any, default: float) -> float:
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v) / 1000.0 if v > 1e12 else float(v)
    try:
        s = str(v).replace("Z", "+00:00")
        return _dt.datetime.fromisoformat(s).timestamp()
    except ValueError:
        try:
            return parse_ts(float(v), default)
        except ValueError:
            return default


def is_network_error(e: BaseException) -> bool:
    return isinstance(e, httpx.TransportError)


@dataclass
class HeldJob:
    job: dict[str, Any]
    lease_expires: float
    revoked: threading.Event = field(default_factory=threading.Event)
    started: bool = False
    progress: float = 0.0
    remaining_s: float | None = None

    @property
    def job_id(self) -> str:
        return self.job["job_id"]

    @property
    def stage(self) -> str:
        return self.job["stage"]

    @property
    def pin_hash(self) -> str:
        return self.job["pin_hash"]


class Worker:
    def __init__(
        self,
        cfg: Config,
        client: CoordinatorClient,
        backend: OllamaBackend,
        *,
        data_root: Path,
        hw: HardwareInfo,
        tier: str | None = None,
        stages: list[str] | None = None,
        max_concurrency: int = 8,
        clock: Clock | None = None,
        storage: StorageManager | None = None,
        updater: Updater | None = None,
        auto_update: bool = True,
        auto_pull: bool = True,
        window: RunWindow | None = None,
        argv: list[str] | None = None,
        log: Callable[[str], None] = print,
        background: bool = True,
        exit_when_idle: bool = False,
        idle_polls_before_exit: int = 1,
        rng: random.Random | None = None,
        registry: Registry | None = None,
        gpu_lock: str | None = None,
        service_mode: bool = False,
        manage_ollama: bool = False,
        active_hours: str | None = None,
        schedule: str | None = None,
        gpu_used_fn: Callable[[], float | None] | None = None,
        ram_available_fn: Callable[[], float] | None = None,
        gpu_procs_fn: Callable[[], dict[int, float] | None] | None = None,
    ):
        self.cfg = cfg
        self.client = client
        self.backend = backend
        self.root = Path(data_root)
        self.hw = hw
        self.tier = tier or cfg.tier
        self.requested = stages
        self.max_concurrency = max(1, max_concurrency)
        self.clock = clock or Clock()
        self.storage = storage or StorageManager(
            self.root, budget_bytes=int(cfg.disk_budget_gb * GB) if cfg.disk_budget_gb else None)
        self.updater = updater or Updater(self.root / "update_state.json", log=log)
        self.auto_update = auto_update
        self.auto_pull = auto_pull
        self.window = window or RunWindow(None, self.clock)
        self.argv = argv or []
        self.log = log
        self.background = background
        self.exit_when_idle = exit_when_idle
        self.idle_polls_before_exit = idle_polls_before_exit
        self.rng = rng or random.Random()

        self.store = JobStore(self.root)
        self.outbox = Outbox(self.root)
        self.fit = HardwareFit(usable_vram_gb=hw.usable_vram_gb, ram_gb=hw.ram_gb, accel=hw.accel)
        self.rates = RateTracker(initial={s: float(b.get("passages_per_hour", 0)) / 3600.0
                                          for s, b in (cfg.bench or {}).items() if b.get("passages_per_hour")})
        self.tuners: dict[str, ConcurrencyTuner] = {}
        self.stop = threading.Event()
        self.shutdown_done = threading.Event()
        self._lease_lock = threading.Lock()
        self._queue: deque[HeldJob] = deque()
        self._current: HeldJob | None = None
        self._prefetching = False
        self._offline = False
        self._registry = registry
        self._registry_etag: str | None = None
        self._registry_changed = registry is not None
        self.active_pins: dict[str, str] = {}
        self.local_digests: dict[str, str] = {}
        self.stages: list[str] = []
        self.excluded: dict[str, str] = {}
        self._update_required = False
        self._last_registry_poll = -1e18
        self._last_ping = -1e18
        self._last_heartbeat = self.clock.monotonic()
        self._last_flush = -1e18
        self._oom_at_one: dict[str, int] = {}
        self._residency_retry: dict[str, bool] = {}
        self._threads: list[threading.Thread] = []
        self.passages_done = 0
        self.uploaded: list[dict[str, Any]] = []  # for status / tests
        self._lease_backoff = Backoff(base=5, cap=600, rng=self.rng)
        self._backend_version_cache: str | None = None
        self.gpu_lock = GpuLock(gpu_lock, log=log)
        self._gpu_models_loaded = False
        self.service_mode = service_mode
        self.updater.service_mode = service_mode
        self.manage_ollama = manage_ollama
        self.active_hours = active_hours
        from .scheduler import legacy_hours_to_schedule
        self.schedule = schedule or legacy_hours_to_schedule(active_hours)
        if gpu_used_fn is None:
            from .hw import gpu_memory_used_gb
            gpu_used_fn = gpu_memory_used_gb
        self.gpu_used_fn = gpu_used_fn
        if gpu_procs_fn is None:
            from .hw import gpu_process_memory_gb
            gpu_procs_fn = gpu_process_memory_gb
        self.gpu_procs_fn = gpu_procs_fn
        if ram_available_fn is None:
            import psutil
            ram_available_fn = lambda: float(psutil.virtual_memory().available)  # noqa: E731
        self.ram_available_fn = ram_available_fn
        self.activity = "starting"
        self.last_quality: dict[str, Any] | None = None
        self.sealed_recipient: str | None = None
        self.sealed_blocked: str | None = None
        self.directive: dict[str, Any] | None = None
        self.client_factory: Callable[[str], CoordinatorClient] = lambda url: CoordinatorClient(url, cfg.token)
        self.next_window: float | None = None
        self.keep_awake: Any = None  # KeepAwake (set by `ald work`)
        self.last_contact: float | None = None
        self.gpu_fraction: dict[str, float] = {}
        self._last_idle_hb = -1e18
        self._last_state_save = -1e18
        self._last_ollama_ensure = -1e18

    # ------------------------------------------------------------------
    # Registry / pins
    # ------------------------------------------------------------------
    @property
    def registry(self) -> Registry:
        if self._registry is None:
            raise RuntimeError("registry not loaded")
        return self._registry

    def _registry_cache_path(self) -> Path:
        return self.root / "registry.json"

    def refresh_registry(self, force: bool = False) -> bool:
        """Poll GET /v1/registry with If-None-Match. Returns True if a new
        registry was installed (hot reload)."""
        now = self.clock.monotonic()
        if not force and now - self._last_registry_poll < REGISTRY_POLL_S:
            return False
        self._last_registry_poll = now
        try:
            raw, etag = self.client.registry(self._registry_etag if self._registry else None)
        except (CoordinatorError, httpx.TransportError) as e:
            if self._registry is None:
                cached = read_json(self._registry_cache_path())
                if cached:
                    self.log(f"[registry] coordinator unreachable ({e}); using cached registry")
                    self._install_registry(Registry.from_dict(cached["registry"]), cached.get("etag"))
                    return True
            self.log(f"[registry] poll failed: {e}")
            return False
        self.last_contact = self.clock.time()
        if raw is None:
            return False
        try:
            reg = Registry.from_dict(raw)
        except RegistryError as e:
            self.log(f"[registry] coordinator served an invalid registry, keeping current one: {e}")
            return False
        if self._registry is not None and reg.content_hash == self._registry.content_hash:
            self._registry_etag = etag
            return False
        old = self._registry.version if self._registry else None
        self._install_registry(reg, etag)
        atomic_write_json(self._registry_cache_path(), {"etag": etag, "registry": raw})
        if old is not None:
            self.log(f"[registry] hot-reloaded {old} -> {reg.version}")
        return True

    def _install_registry(self, reg: Registry, etag: str | None) -> None:
        self._registry = reg
        self._registry_etag = etag
        self._registry_changed = True
        # Pins are recomputed by resolve_stages() against local digests; until
        # then, only pins that the registry itself defines are active.
        self.active_pins = reg.active_pins()

    def backend_version(self) -> str:
        if self._backend_version_cache is None:
            self._backend_version_cache = self.backend.backend_version(self.hw.accel)
        return self._backend_version_cache

    def resolve_stages(self) -> list[str]:
        """tier -> allowed stages -> requested -> registry -> HW fit -> Ollama
        version -> model present with pinned digest (pull if allowed)."""
        reg = self.registry
        self._registry_changed = False
        excluded: dict[str, str] = {}
        tier = self.tier or reg.select_tier(self.hw.usable_vram_gb)["name"]
        self.tier = tier
        allowed = reg.allowed_stages(tier)
        if self.requested:
            for s in allowed:
                if s not in self.requested:
                    excluded[s] = "not requested (--stages)"
            for s in self.requested:
                if s not in allowed:
                    excluded[s] = f"not allowed for tier {tier}"
            allowed = [s for s in allowed if s in self.requested]
        self.measure_foreign_vram()
        if self.manage_ollama:  # we set OLLAMA_NUM_PARALLEL (tier hint, reduced if it does not fit)
            self.fit.server_slots = self.effective_parallel(reg, tier, allowed)
        fit_ok, why = self.fit.filter_stages(reg.stages[s] for s in allowed)
        excluded.update(why)
        try:
            ver = self.backend.version(refresh=True)
        except BackendError as e:
            for s in fit_ok:
                excluded[s] = f"Ollama unavailable: {e}"
            self.stages, self.excluded = [], excluded
            return []
        ok: list[str] = []
        digests: dict[str, str] = {}
        for s in fit_ok:
            st = reg.stages[s]
            if not version_in_range(ver, st.version_range):
                excluded[s] = f"Ollama {ver} outside {st.version_range}"
                continue
            d = self.backend.local_digest(st.model_ref)
            if d is None and self.auto_pull:
                if not self.storage.model_fits(st.model_size_gb):
                    excluded[s] = f"model {st.model_ref} ({st.model_size_gb} GB) does not fit on disk"
                    continue
                self.log(f"[setup] pulling {st.model_ref} for stage {s} ...")
                try:
                    self.backend.pull(st.model_ref)
                    d = self.backend.local_digest(st.model_ref)
                except BackendError as e:
                    excluded[s] = f"pull failed: {e}"
                    continue
            if d is None:
                excluded[s] = f"model {st.model_ref} not pulled (run `ald setup`)"
                continue
            if not digests_match(d, st.model_digest):
                excluded[s] = f"local digest {d[:12]} != pinned {st.model_digest[:12]}"
                continue
            if not reg.pin_is_active(st.pin_hash(st.model_digest)):
                excluded[s] = "pin not in registry active_pins (stale)"
                continue
            digests[s] = st.model_digest
            ok.append(s)
        self.local_digests = digests
        self.active_pins = {reg.stages[s].pin_hash(digests[s]): s for s in ok}
        self.stages, self.excluded = ok, excluded
        for s in ok:
            st = reg.stages[s]
            cap = max(1, self.fit.max_concurrency(st, self.max_concurrency))
            # Start at the tier's server parallelism (what Ollama can actually run at once); the tuner then
            # moves up or down. A saved benchmark only decides the start when the tier has no hint.
            hint = reg.num_parallel_hint(tier)
            start = int(hint or (self.cfg.bench or {}).get(s, {}).get("best_concurrency", 2))
            if s not in self.tuners:
                self.tuners[s] = ConcurrencyTuner(start=min(start, cap), max_c=cap, clock=self.clock)
            else:
                self.tuners[s].set_max(cap)
        return ok

    def expected_pin(self, stage: str) -> str | None:
        st = self.registry.stages.get(stage)
        d = self.local_digests.get(stage)
        if st is None or d is None:
            return None
        return st.pin_hash(d)

    # ------------------------------------------------------------------
    # Upload / outbox
    # ------------------------------------------------------------------
    def _put(self, job_id: str, body: bytes, headers: dict[str, str], partial: bool) -> dict[str, Any]:
        return self.client.put_result(job_id, body, headers, partial=partial)

    def _on_ack(self, e: Any, resp: dict[str, Any]) -> None:
        held = {j.job_id for j in self._held()}
        self.uploaded.append({"job_id": e.job_id, "partial": e.partial, "status": resp.get("status"),
                              "n_lines": e.meta.get("n_lines")})
        self.log(f"[upload] {e.job_id} {'partial' if e.partial else 'final'} "
                 f"({e.meta.get('n_lines')} lines): {resp.get('status', 'ok')}")
        if e.job_id not in held:
            self.store.remove_job(e.job_id)

    def _on_reject(self, e: Any, reason: str) -> None:
        self.log(f"[upload] {e.job_id} rejected ({reason}); kept in outbox/rejected")
        if e.job_id not in {j.job_id for j in self._held()}:
            self.store.remove_job(e.job_id)

    def flush_outbox(self, force: bool = False) -> dict[str, int]:
        if not self.outbox.entries():
            return {"acked": 0, "rejected": 0, "deferred": 0}
        jitter = self.rng

        def backoff(n: int) -> float:
            hi = min(600.0, 5.0 * (2 ** n))
            return jitter.uniform(hi / 2, hi)

        counts = self.outbox.flush(self._put, now=self.clock.time(), on_ack=self._on_ack,
                                   on_reject=self._on_reject, backoff=backoff, force=force,
                                   is_network_error=is_network_error)
        self._last_flush = self.clock.monotonic()
        return counts

    @staticmethod
    def quality(lines: list[dict[str, Any]]) -> dict[str, Any]:
        """Schema failures (after the retry), unverifiable evidence quotes, retries, and one sample error.
        Rows without an evidence quote (e.g. lean anyOf "no obstacle" rows) are not evidence failures."""
        schema = [l for l in lines if not l.get("valid_schema", False)]
        sample = next((str(l.get("error"))[:200] for l in schema if l.get("error")), None)
        return {"n_schema_invalid": len(schema),
                "n_evidence_unverified": sum(1 for l in lines if "evidence_unverified" in (l.get("flags") or [])),
                "n_retried": sum(1 for l in lines if "retried" in (l.get("flags") or [])),
                **({"schema_error_sample": sample} if sample else {})}

    @staticmethod
    def _blind_stats(lines: list[dict[str, Any]], wall_s: float) -> dict[str, Any]:
        """SEALED split: counts and timing only. Flag / schema / quote / retry rates and generated tokens track
        the outcome (no-obstacle rows carry no quote and are short), so they never leave the machine."""
        return {"n_lines": len(lines), "wall_s": round(wall_s, 2)}

    def _stats(self, lines: list[dict[str, Any]], wall_s: float) -> dict[str, Any]:
        gen = sum(int(l.get("gen_tokens", 0) or 0) for l in lines)
        prompt = sum(int(l.get("prompt_tokens", 0) or 0) for l in lines)
        flagged = sum(1 for l in lines if is_flagged(l))
        return {"n_ok": len(lines) - flagged, "n_flagged": flagged,
                "tok_s": round(gen / wall_s, 2) if wall_s > 0 else 0.0, "wall_s": round(wall_s, 2),
                "prompt_tokens": prompt, "gen_tokens": gen, **self.quality(lines)}

    def _enqueue_result(self, job_id: str, lines: list[dict[str, Any]], meta: dict[str, Any], partial: bool) -> None:
        body = encode_jsonl_gz(lines)
        seal: dict[str, str] = {}
        if (meta.get("job") or {}).get("split") == "confirmation" and self.sealed_recipient:
            # Sealed split on a client-side-sealing coordinator: only ciphertext leaves this machine.
            from . import sealed
            from .client import encode_passage_ids
            plain = body
            body = sealed.encrypt(plain, self.sealed_recipient)
            seal = {**sealed.seal_headers(plain, body), "X-Passage-Ids": encode_passage_ids(plain)}
        headers = {
            "X-Content-Sha256": sha256_bytes(body),
            "X-Pin-Hash": meta["pin_hash"],
            "X-Model-Digest": meta["model_digest"],
            "X-Backend-Version": meta["backend_version"],
            "X-Stats": json.dumps((self._blind_stats if (meta.get("job") or {}).get("split") == "confirmation"
                                   else self._stats)(lines, float(meta.get("wall_s", 0.0))), separators=(",", ":")),
            **seal,
        }
        if not partial:
            # A final blob supersedes any not-yet-acked partial of the same job.
            for e in self.outbox.entries():
                if e.job_id == job_id and e.partial:
                    self.outbox.remove(e)
        self.outbox.add(job_id, body, headers, partial=partial, n_lines=len(lines), created=self.clock.time())
        meta["state"] = "queued_partial" if partial else "queued_final"
        self.store.write_meta(job_id, meta)

    # ------------------------------------------------------------------
    # Recovery
    # ------------------------------------------------------------------
    def recover_interrupted(self) -> int:
        """Jobs left on disk by a crash / power loss -> partial (or final, if
        complete) outbox entries + release. Returns number recovered."""
        held = {j.job_id for j in self._held()}
        n = 0
        to_release: list[str] = []
        for d, meta in list(self.store.iter_jobs()):
            job_id = meta.get("job_id")
            if not job_id or job_id in held:
                continue
            if meta.get("state") not in ("active", "leased"):
                continue
            ck = self.store.checkpoint(job_id).load()
            skip = set(meta.get("skip_passage_ids") or [])
            order = meta.get("order") or list(ck.keys())
            lines = [ck[p] for p in order if p in ck and p not in skip and ck[p].get("pin_hash") == meta["pin_hash"]]
            expected = int(meta.get("n_todo", -1))
            complete = expected >= 0 and len(lines) >= expected
            if lines:
                self._enqueue_result(job_id, lines, meta, partial=not complete)
                self.log(f"[recover] {job_id}: {len(lines)} lines from checkpoint -> "
                         f"{'final' if complete else 'partial'} upload queued")
            else:
                self.store.remove_job(job_id)
            if not complete:
                to_release.append(job_id)
            n += 1
        if to_release:
            self.flush_outbox(force=True)
            self._release(to_release)
        return n

    def _release(self, job_ids: list[str]) -> None:
        if not job_ids:
            return
        try:
            self.client.release(job_ids)
            self.log(f"[lease] released {', '.join(job_ids)}")
        except (CoordinatorError, httpx.TransportError) as e:
            self.log(f"[lease] release failed ({e}); leases will expire on their own")

    # ------------------------------------------------------------------
    # Leasing
    # ------------------------------------------------------------------
    def _held(self) -> list[HeldJob]:
        out = list(self._queue)
        if self._current is not None:
            out.append(self._current)
        return out

    def _lease_count(self) -> int:
        from .keepawake import battery_ok
        ok, msg = battery_ok()
        if not ok:
            self.log(f"[power] {msg}")
            return 0
        rates = [self.rates.rate(s) for s in self.stages if self.rates.rate(s)]
        rate = min(rates) if rates else None
        n = lease_size(rate, ttl_s=LEASE_TTL_S)
        plan = self.storage.plan(n)
        if plan.paused:
            # Try to make room from caches before pausing.
            self.storage.evict(self._evictable(), plan.per_job_bytes)
            plan = self.storage.plan(n)
        if plan.paused:
            self.log(f"[disk] {plan.reason}")
        return plan.jobs

    def _evictable(self) -> list[Path]:
        held = {j.job_id for j in self._held()}
        pending = {e.job_id for e in self.outbox.entries()}
        out: list[Path] = []
        held_names = {self.store.shard_path(h).name for h in held}
        if self.store.shards_dir.exists():
            out.extend(p for p in self.store.shards_dir.iterdir() if p.name not in held_names)
        if self.outbox.rejected.exists():
            out.extend(self.outbox.rejected.iterdir())
        logs = self.root / "logs"
        if logs.exists():
            out.extend(p for p in logs.iterdir() if p.suffix != ".log")
        pending_names = {self.store.shard_path(j).name for j in pending}
        return [p for p in out if p.name not in pending_names]

    def lease_jobs(self) -> list[HeldJob]:
        """Lease, verify pins, download shards. Refused jobs are released."""
        with self._lease_lock:
            if self.stop.is_set() or not self.stages:
                return []
            exp_job_s = None
            rates = [self.rates.rate(s) for s in self.stages if self.rates.rate(s)]
            if rates:
                exp_job_s = DEFAULT_PASSAGES_PER_JOB / min(rates)
            if not self.window.allow_new_lease(exp_job_s):
                return []
            # Registry check on every lease (cheap with ETag).
            self._last_registry_poll = -1e18
            if self.refresh_registry():
                self.resolve_stages()
                if not self.stages:
                    return []
            n = self._lease_count()
            if n <= 0:
                return []
            accepted: list[HeldJob] = []
            refused: list[str] = []
            # Refused jobs stay leased by us until the end of this call, so a
            # retry gets past them instead of being handed the same job again.
            for _attempt in range(3):
                try:
                    ram_ok = getattr(self, "_ram_ok_stages", None)
                    lease_stages = [x for x in self.stages if ram_ok is None or x in ram_ok] or self.stages
                    jobs = self.client.lease(self.tier, lease_stages, n)
                    self._take_directive(getattr(self.client, "last_directive", None))
                    self._offline = False
                    self.last_contact = self.clock.time()
                except UpgradeRequired as e:
                    self._update_required = True
                    if isinstance(e.body, dict) and e.body.get("min_client_version"):
                        self._last_decision = decide(e.body)
                    self.log("[lease] coordinator requires a newer client (426)")
                    break
                except httpx.TransportError as e:
                    self._offline = True
                    self.log(f"[lease] network error: {e}")
                    break
                except CoordinatorError as e:
                    unknown = self._unknown_stages(e)
                    if unknown:
                        # Coordinator does not (yet) serve these stages: lease the rest.
                        for u in unknown:
                            self.excluded[u] = "coordinator does not know this stage"
                        self.stages = [x for x in self.stages if x not in unknown]
                        self.log(f"[lease] coordinator rejected stage(s) {', '.join(unknown)}; "
                                 f"leasing {', '.join(self.stages) or 'nothing'}")
                        if self.stages:
                            continue
                    else:
                        self.log(f"[lease] {e}")
                    break
                now = self.clock.time()
                for j in jobs:
                    stage = j.get("stage")
                    exp = self.expected_pin(stage) if stage else None
                    if exp is None or j.get("pin_hash") != exp:
                        self.log(f"[pin] refusing {j.get('job_id')}: job pin {str(j.get('pin_hash'))[:12]} != "
                                 f"local {(exp or 'none')[:12]} for stage {stage}")
                        refused.append(j["job_id"])
                        continue
                    hj = HeldJob(job=j, lease_expires=parse_ts(j.get("lease_expires"), now + LEASE_TTL_S))
                    try:
                        self.client.download_shard(j, self.store.shard_path(hj.job_id))
                    except (CoordinatorError, httpx.TransportError, OSError) as e:
                        self.log(f"[shard] download failed for {hj.job_id}: {e}")
                        refused.append(hj.job_id)
                        continue
                    accepted.append(hj)
                if accepted or not jobs or not refused:
                    break
            if refused:
                self._release(refused)
            self._queue.extend(accepted)
            return accepted

    @staticmethod
    def _unknown_stages(e: CoordinatorError) -> list[str]:
        msg = str(e)
        if e.status != 400 or "unknown stage" not in msg:
            return []
        tail = msg.split(":", 2)[-1]
        return [x.strip() for x in tail.split(",") if x.strip()]

    def _prefetch_async(self) -> None:
        if self._prefetching or self._queue or self.stop.is_set():
            return
        self._prefetching = True

        def go() -> None:
            try:
                self.lease_jobs()
            finally:
                self._prefetching = False

        if self.background:
            t = threading.Thread(target=go, name="ald-prefetch", daemon=True)
            t.start()
        else:
            go()

    # ------------------------------------------------------------------
    # Heartbeat (background)
    # ------------------------------------------------------------------
    def report(self) -> dict[str, Any]:
        """Self-report for the fleet view (heartbeat stats) and `ald status`."""
        from .keepawake import battery_info
        cur = self._current
        stage = cur.stage if cur else None
        rate = self.rates.rate(stage) if stage else None
        bat = battery_info()
        return {
            "tok_s": round(self._recent_tok_s(), 2), "passages_done": self.passages_done,
            "state": self.activity, "stage": stage, "job_id": cur.job_id if cur else None,
            "progress": round(cur.progress, 3) if cur else None,
            "concurrency": self.tuners[stage].current if stage in self.tuners else None,
            "passages_per_hour": round(rate * 3600) if rate else None,
            "keep_awake": bool(self.keep_awake.alive()) if self.keep_awake is not None else False,
            "battery_percent": bat.get("percent"), "power_plugged": bat.get("plugged"),
            "gpu_fraction": self.gpu_fraction.get(stage) if stage else None,
            "gpu": self.hw.gpu_summary[:120], "client_version": CLIENT_VERSION, "service": self.service_mode,
            "gpu_lock": bool(self.gpu_lock.enabled),
            "next_window": (next_schedule_change(self.schedule, self.clock.time())
                            if self.schedule and not in_schedule(self.schedule, self.clock.time()) else None),
            "may_sleep": bool(self.keep_awake is not None and getattr(self.keep_awake, "enabled", False)
                              and not self.keep_awake.alive()),
            "quality_stage": (self.last_quality or {}).get("stage"),
            "schema_fail_rate": (self.last_quality or {}).get("schema_fail_rate"),
            "evidence_fail_rate": (self.last_quality or {}).get("evidence_fail_rate"),
        }

    def heartbeat_once(self) -> dict[str, Any] | None:
        held = self._held()
        now_m = self.clock.monotonic()
        if not held and now_m - self._last_idle_hb < IDLE_HEARTBEAT_S:
            return None
        if not held:
            self._last_idle_hb = now_m
        ids = [j.job_id for j in held]
        stats = self.report()
        try:
            resp = self.client.heartbeat(ids, stats)
            self._take_directive((resp or {}).get("directive") or (resp or {}).get("scheduler"))
            yielded = set((resp or {}).get("yield") or []) & set(ids)
            if yielded and not self.directive:  # the platform asked these held jobs to yield
                self._take_directive({"gpu": "yield", "until": None, "reason": f"yield requested for {sorted(yielded)}"})
            self._offline = False
            self.last_contact = self.clock.time()
        except httpx.TransportError as e:
            self._offline = True
            self.log(f"[heartbeat] network error ({e}); working offline while leases are valid")
            return None
        except CoordinatorError as e:
            self.log(f"[heartbeat] {e}")
            return None
        now = self.clock.time()
        ext = set(resp.get("extended") or [])
        rev = set(resp.get("revoked") or [])
        for j in held:
            if j.job_id in ext:
                j.lease_expires = max(j.lease_expires, now + LEASE_TTL_S)
            if j.job_id in rev:
                j.revoked.set()
                self.log(f"[heartbeat] {j.job_id} revoked by coordinator; abandoning")
        # Drop revoked jobs that have not started.
        for j in [q for q in list(self._queue) if q.revoked.is_set()]:
            try:
                self._queue.remove(j)
            except ValueError:  # popped by the main thread meanwhile
                continue
            self.store.remove_job(j.job_id)
        return resp

    _tok_window: deque

    def _recent_tok_s(self) -> float:
        win = getattr(self, "_tok_window", None)
        if not win:
            return 0.0
        now = self.clock.monotonic()
        while win and now - win[0][0] > 300:
            win.popleft()
        if len(win) < 2:
            return 0.0
        span = max(win[-1][0] - win[0][0], 1e-6)
        return sum(t for _, t in win) / span

    def _bg_loop(self) -> None:
        while not self.stop.is_set():
            now = self.clock.monotonic()
            try:
                if now - self._last_heartbeat >= HEARTBEAT_S:
                    self._last_heartbeat = now
                    self.heartbeat_once()
                if now - self._last_state_save >= STATE_SAVE_S:
                    self._last_state_save = now
                    self._save_state()
                if now - self._last_flush >= FLUSH_POLL_S:
                    self._last_flush = now
                    if self.outbox.entries():
                        self.flush_outbox()
                if now - self._last_registry_poll >= REGISTRY_POLL_S:
                    self.refresh_registry()
            except Exception as e:  # noqa: BLE001 - background thread must survive
                self.log(f"[bg] {type(e).__name__}: {e}")
            self.stop.wait(1.0)

    # ------------------------------------------------------------------
    # Running one job
    # ------------------------------------------------------------------
    _ram_avail_gb: float = 0.0

    def ram_low(self, factor: float = 1.0) -> bool:
        """Available system RAM below ``factor`` x min_free_ram_gb (default 8 GB, `ald config`)."""
        limit = float(self.cfg.min_free_ram_gb or 0) * factor
        if limit <= 0:
            return False
        try:
            self._ram_avail_gb = self.ram_available_fn() / GB
        except Exception:  # noqa: BLE001
            return False
        return self._ram_avail_gb < limit

    # -- host RAM prediction ------------------------------------------------------------------------
    def _footprints(self) -> dict[str, float]:
        if not hasattr(self, "_footprint_cache"):
            self._footprint_cache = read_json(self.root / "ram_footprint.json", {}) or {}
        return self._footprint_cache

    def model_ram_gb(self, st: Stage) -> float:
        """System RAM the model takes when Ollama loads it: learned on this machine from the last load,
        else ~0.8 x model size (mapped weights touched while uploading to the GPU, buffers)."""
        v = self._footprints().get(st.model_ref)
        return float(v) if v is not None else round(0.8 * st.model_size_gb, 2)

    def _learn_footprint(self, st: Stage, before_gb: float) -> None:
        try:
            after = self.ram_available_fn() / GB
        except Exception:  # noqa: BLE001
            return
        used = round(max(0.0, before_gb - after), 2)
        fp = self._footprints()
        old = fp.get(st.model_ref)
        # A smaller reading can be noise (other programs freed memory meanwhile): keep the max of recent loads.
        fp[st.model_ref] = round(max(used, 0.75 * old) if old else used, 2) if used > 0.2 else (old or used)
        try:
            atomic_write_json(self.root / "ram_footprint.json", fp)
        except OSError:
            pass
        self.log(f"[ram] loading {st.model_ref} took {used:.1f} GB of system RAM (planning with {fp[st.model_ref]:.1f} GB)")

    def _loaded_models(self) -> set[str]:
        try:
            return {m.get("name") or m.get("model") for m in self.backend.ps()}
        except BackendError:
            return set()

    def ram_blocked(self) -> str | None:
        """Why not to lease right now (None = go): below the reserve; a model load would push available
        RAM below the reserve; or still backing off after a low-memory interrupt."""
        reserve = float(self.cfg.min_free_ram_gb or 0)
        if reserve <= 0:
            return None
        try:
            avail = self.ram_available_fn() / GB
        except Exception:  # noqa: BLE001
            return None
        self._ram_avail_gb = avail
        if avail < reserve:
            return f"only {avail:.1f} GB of system RAM available (< {reserve:g} GB reserve)"
        loaded = self._loaded_models()
        now = self.clock.monotonic()
        fp = self._footprints()
        ok: list[str] = []
        worst = 0.0
        for name in self.stages:
            st = self.registry.stages.get(name) if self._registry else None
            if st is None:
                continue
            if any(self.backend.same_model(m, st.model_ref) for m in loaded):
                ok.append(name)  # already resident: no further RAM to find
                continue
            need = self.model_ram_gb(st)
            worst = max(worst, need)
            # Learned: the load must leave the reserve. Unlearned: one measured probe load while above it.
            if st.model_ref not in fp or avail - need >= reserve:
                ok.append(name)
        if now < getattr(self, "_ram_backoff_until", -1e18):
            return f"backing off after a low-memory interrupt ({(self._ram_backoff_until - now) / 60:.0f} min left)"
        if getattr(self, "_ram_backoff_until", None) is not None:
            if avail < reserve + max(worst, 0.5):
                return (f"{avail:.1f} GB available; after a low-memory interrupt waiting for "
                        f"{reserve + max(worst, 0.5):.1f} GB (reserve + model)")
            self._ram_backoff_until = None  # recovered
        if self.stages and not ok:
            return (f"loading any model would leave less than the {reserve:g} GB reserve "
                    f"({avail:.1f} GB available; smallest model needs ~"
                    f"{min(self.model_ram_gb(self.registry.stages[s]) for s in self.stages):.1f} GB)")
        self._ram_ok_stages = ok if len(ok) < len(self.stages) else None
        return None

    def paused(self) -> bool:
        return (self.root / "paused").exists()  # = config.pause_marker() for the real data dir

    def _interrupt_reason(self, hj: HeldJob) -> str | None:
        if self.stop.is_set():
            return "stopped"
        now = self.clock.monotonic()
        if now - getattr(self, "_last_pause_check", -1e18) >= 5.0:
            self._last_pause_check = now
            if self.paused():
                return "paused"
            # Platform directive semantics (SPEC §7.3): "yield" = hand the GPU back soon: upload a partial if
            # the shard is less than half done, else finish it. "pause" (also drains) = start nothing new, but
            # let the current shard finish. Either way the run loop then unloads and stops leasing.
            if (self.directive or {}).get("gpu") == "yield" and self.directive_hold() and hj.progress < 0.5:
                return "scheduler_yield"
            # Hand the job back well before the host runs out of memory (other programs may be growing).
            if self.ram_low(factor=0.75):
                self.log(f"[ram] {self._ram_avail_gb:.1f} GB available: interrupting {hj.job_id}; "
                         f"backing off {RAM_BACKOFF_S / 60:.0f} min")
                self._ram_backoff_until = self.clock.monotonic() + RAM_BACKOFF_S
                return "low_memory"
        if hj.revoked.is_set():
            return "revoked"
        if self.window.expired():
            return "window_end"
        if hj.pin_hash not in self.active_pins:
            return "pin_retired"
        if hj.stage not in self.stages:
            return "stage_demoted"
        if self._offline and self.clock.time() > hj.lease_expires:
            return "lease_lost"
        return None

    def run_job(self, hj: HeldJob) -> str:
        """Returns 'done' or the interrupt reason."""
        self._current = hj
        hj.started = True
        try:
            # --gpu-lock: the lock covers this shard's inference (heartbeats keep the lease alive meanwhile).
            # --gpu-lock: the run loop waits for the lock BEFORE leasing, so no job is held while waiting.
            # A prefetched job that finds the lock taken (someone was waiting) goes straight back.
            if self.gpu_lock.enabled and not self.gpu_lock.held:
                rem = getattr(self, "_gpu_yield_until", -1e18) - self.clock.monotonic()
                if rem > 5:  # a long (contended) yield: do not sit on a leased job meanwhile
                    self.log(f"[gpu-lock] yielding {rem:.0f}s to other GPU users; handing {hj.job_id} back")
                    self.store.remove_job(hj.job_id)
                    self._release([hj.job_id])
                    return "gpu_yield"
                self._gpu_yield_wait()
            if not self.gpu_lock.try_acquire():
                self.log(f"[gpu-lock] {self.gpu_lock.path} taken by another process; handing {hj.job_id} back")
                self.store.remove_job(hj.job_id)
                self._release([hj.job_id])
                return "gpu_busy"
            self._gpu_models_loaded = True
            self.activity = "working"
            return self._run_job(hj)
        finally:
            self._current = None
            self._release_gpu_lock(after_shard=True)

    def ensure_model_context(self, st: Stage) -> bool:
        """Two stages may share a model with different pinned num_ctx (e.g. label and cloze). Ollama keeps
        the loaded context size, so a resident copy with another num_ctx is unloaded before this job: one
        model never runs with two num_ctx values at once. Returns True if it unloaded."""
        try:
            ctx = self.backend.loaded_context(st.model_ref)
        except BackendError:
            return False
        if ctx is None or ctx == st.num_ctx:
            return False
        self.log(f"[gpu] {st.model_ref} is loaded with num_ctx {ctx}; stage {st.name} pins {st.num_ctx}: reloading")
        try:
            self.backend.unload(st.model_ref)
        except BackendError:
            return False
        return True

    def _unload_stage_models(self, why: str) -> None:
        if self._registry is None:
            return
        models = {self.registry.stages[s].model_ref for s in self.stages if s in self.registry.stages}
        gone = []
        for m in self.backend.ps():
            name = m.get("name") or m.get("model")
            if name and any(self.backend.same_model(name, k) for k in models):
                try:
                    self.backend.unload(name)
                    gone.append(name)
                except BackendError:
                    pass
        self._gpu_models_loaded = False
        if gone:
            self.log(f"[gpu-lock] unloaded {', '.join(gone)} ({why})")

    def _release_gpu_lock(self, after_shard: bool = False) -> None:
        if not self.gpu_lock.held:
            return
        now = self.clock.monotonic()
        if self.gpu_lock.waited_last:
            self._gpu_contended_at = now
        # Unload BEFORE releasing, so the next holder never loads next to our model.
        n = self.gpu_lock.waiters()
        if n:
            self._gpu_contended_at = now
            self._unload_stage_models(f"{n} process(es) waiting for the GPU lock")
        self.gpu_lock.release()
        if not after_shard:
            return
        # flock(2) is not FIFO: re-locking right away beats a blocked waiter that the kernel just woke.
        if n:
            self._gpu_handover(n)
        recent = now - getattr(self, "_gpu_contended_at", -1e18) < GPU_CONTENDED_WINDOW_S
        if n is None:  # waiters cannot be detected here (macOS): always leave a real gap
            yield_s = GPU_YIELD_UNKNOWN_S
        else:
            yield_s = GPU_YIELD_CONTENDED_S if recent else GPU_YIELD_S
        self._gpu_yield_until = self.clock.monotonic() + yield_s

    def _gpu_handover(self, n: int) -> None:
        """A waiter exists: wait (up to 60 s) until it actually holds the lock, then queue behind it."""
        self.log(f"[gpu-lock] yielding {self.gpu_lock.path} to {n} waiting process(es)")
        t0 = self.clock.monotonic()
        while self.clock.monotonic() - t0 < 60 and not self.stop.is_set():
            if self.gpu_lock.held_by_other():
                return
            if self.clock.sleep(0.5, self.stop):
                return

    def _gpu_yield_wait(self) -> None:
        rem = getattr(self, "_gpu_yield_until", -1e18) - self.clock.monotonic()
        if rem > 0:
            self.clock.sleep(rem, self.stop)

    def _idle_gpu_unload(self) -> None:
        """With --gpu-lock, free the VRAM when there is nothing to do (also covers OSes where lock
        waiters cannot be detected)."""
        if self.gpu_lock.enabled and self._gpu_models_loaded:
            self._unload_stage_models("worker idle")

    def _run_job(self, hj: HeldJob) -> str:
        st: Stage = self.registry.stages[hj.stage]
        digest = self.local_digests[hj.stage]
        passages = read_jsonl_gz(self.store.shard_path(hj.job_id))
        skip = set(hj.job.get("skip_passage_ids") or [])
        order = [p["passage_id"] for p in passages]
        ck = self.store.checkpoint(hj.job_id)
        prior_meta = self.store.read_meta(self.store.job_dir(hj.job_id)) or {}
        done = {pid: l for pid, l in ck.load().items() if l.get("pin_hash") == hj.pin_hash}
        want = [p for p in passages if p["passage_id"] not in skip]
        missing_ids = {p["passage_id"] for p in want if p["passage_id"] not in done}
        cached = self.store.cached_lines(hj.pin_hash, missing_ids) if missing_ids else {}
        for pid, line in cached.items():
            if pid not in done:
                ck.append(line)
                done[pid] = line
        meta = {
            "job_id": hj.job_id, "stage": hj.stage, "pin_hash": hj.pin_hash, "model_digest": digest,
            "backend_version": self.backend_version(), "state": "active", "order": order,
            "skip_passage_ids": sorted(skip), "n_todo": len(want),
            "wall_s": float(prior_meta.get("wall_s", 0.0)), "leased_at": self.clock.time(), "job": hj.job,
        }
        self.store.write_meta(hj.job_id, meta)
        todo = deque(p for p in want if p["passage_id"] not in done)
        n_total = len(want)
        tuner = self.tuners[hj.stage]
        errors: dict[str, int] = {}
        ran = 0
        t_start = self.clock.monotonic()
        self.log(f"[job] {hj.job_id} stage={hj.stage} passages={n_total} (resume {len(done)}, skip {len(skip)}) "
                 f"c={tuner.current}")
        reason: str | None = None
        backend_backoff = Backoff(base=2, cap=120, rng=self.rng)
        ex = ThreadPoolExecutor(max_workers=self.max_concurrency, thread_name_prefix="ald-infer")
        inflight: dict[Future, dict[str, Any]] = {}
        bv = self.backend_version()
        # Between jobs: only this stage's model may stay resident on the GPU.
        if st.unload_others(self.registry.unload_others):
            self.unload_non_pinned(keep={st.model_ref})
        self.ensure_model_context(st)
        ram_before: float | None = None
        if not any(self.backend.same_model(m, st.model_ref) for m in self._loaded_models()):
            try:
                ram_before = self.ram_available_fn() / GB
            except Exception:  # noqa: BLE001
                ram_before = None
        residency_checked = False
        residency_tries = 0

        def submit(p: dict[str, Any]) -> None:
            fut = ex.submit(run_passage, self.backend, st, p, pin_hash=hj.pin_hash, model_digest=digest,
                            backend_version=bv)
            inflight[fut] = p

        try:
            while todo or inflight:
                reason = self._interrupt_reason(hj)
                if reason:
                    break
                while todo and len(inflight) < tuner.current:
                    submit(todo.popleft())
                finished, _ = wait(list(inflight), timeout=0.5, return_when=FIRST_COMPLETED)
                for f in finished:
                    p = inflight.pop(f)
                    pid = p["passage_id"]
                    try:
                        line = f.result()
                    except BackendOOM as e:
                        self.log(f"[backend] OOM at c={tuner.current}: {e}")
                        if tuner.current <= 1:
                            self._oom_at_one[hj.stage] = self._oom_at_one.get(hj.stage, 0) + 1
                            if self._oom_at_one[hj.stage] >= OOM_DEMOTE_AFTER:
                                self._demote(hj.stage, "OOM at concurrency 1")
                        tuner.on_error(oom=True)
                        todo.appendleft(p)
                        continue
                    except BackendUnavailable as e:
                        todo.appendleft(p)
                        self.ensure_ollama(min_interval_s=60.0)  # e.g. Ollama died with the session that started it
                        delay = backend_backoff.next()
                        self.log(f"[backend] unavailable ({e}); retrying in {delay:.0f}s")
                        self.clock.sleep(delay, self.stop)
                        continue
                    except BackendError as e:
                        errors[pid] = errors.get(pid, 0) + 1
                        tuner.on_error(oom=False)
                        if errors[pid] <= MAX_PASSAGE_ERRORS:
                            todo.append(p)
                            continue
                        line = self._error_line(st, p, hj.pin_hash, digest, str(e))
                    backend_backoff.reset()
                    if ram_before is not None:
                        self._learn_footprint(st, ram_before)
                        ram_before = None
                    if not residency_checked and residency_tries < 20:
                        residency_tries += 1
                        residency_checked = self.check_residency(hj.stage) == "ok"
                    ck.append(line)
                    done[pid] = line
                    ran += 1
                    self.passages_done += 1
                    lat = float(line.get("latency_ms", 0)) / 1000.0
                    tuner.observe(lat, int(line.get("gen_tokens", 0) or 0))
                    if not hasattr(self, "_tok_window"):
                        self._tok_window = deque()
                    if hj.job.get("split") != "confirmation":  # gen tokens per passage would reveal output length
                        self._tok_window.append((self.clock.monotonic(), int(line.get("gen_tokens", 0) or 0)))
                hj.progress = len(done) / max(1, n_total)
                elapsed = self.clock.monotonic() - t_start
                rate = (ran / elapsed) if ran >= 5 and elapsed > 0 else self.rates.rate(hj.stage)
                hj.remaining_s = (len(todo) + len(inflight)) / rate if rate else None
                if should_prefetch(hj.progress, hj.remaining_s) and not self._update_pending():
                    self._prefetch_async()
        finally:
            ex.shutdown(wait=False, cancel_futures=True)
            ck.close()
            if ram_before is not None and reason == "low_memory":
                self._learn_footprint(st, ram_before)  # interrupted while loading: learn it anyway
        # Inference for this job is over: it is no longer "held" for heartbeats,
        # and its local files may be removed once the upload is acked.
        self._current = None
        wall = self.clock.monotonic() - t_start
        meta["wall_s"] = float(meta["wall_s"]) + wall
        if wall > 0 and ran > 0:
            self.rates.update(hj.stage, ran, wall)
        lines = [done[p] for p in order if p in done and p not in skip]
        if lines and hj.job.get("split") != "confirmation":  # quality of the sealed split is never reported
            q = self.quality(lines)
            n = len(lines)
            self.last_quality = {"stage": hj.stage, "schema_fail_rate": round(q["n_schema_invalid"] / n, 4),
                                 "evidence_fail_rate": round(q["n_evidence_unverified"] / n, 4)}
            if q["n_schema_invalid"] > max(1, 0.02 * n):
                self.log(f"[quality] {hj.job_id} stage {hj.stage} ({st.model_ref}): {q['n_schema_invalid']}/{n} "
                         f"outputs fail the schema even after the retry; first error: {q.get('schema_error_sample')}")
        if reason is None and len(lines) >= n_total:
            self._enqueue_result(hj.job_id, lines, meta, partial=False)
            self.flush_outbox(force=True)
            self._save_state()
            return "done"
        reason = reason or "incomplete"
        self.log(f"[job] {hj.job_id} interrupted ({reason}) after {len(lines)}/{n_total} passages")
        if reason == "revoked":
            # Adaptive stopping: the coordinator no longer wants this job.
            self.store.remove_job(hj.job_id)
            self._save_state()
            return reason
        if lines:
            self._enqueue_result(hj.job_id, lines, meta, partial=True)
        else:
            self.store.remove_job(hj.job_id)
        # Upload first, then release: whoever leases the job next gets the
        # uploaded passages as skip_passage_ids.
        self.flush_outbox(force=True)
        self._release([hj.job_id])
        self._save_state()
        return reason

    @staticmethod
    def _error_line(st: Stage, p: dict[str, Any], pin: str, digest: str, err: str) -> dict[str, Any]:
        return {"passage_id": p["passage_id"], "stage": st.name, "pin_hash": pin, "model_digest": digest,
                "backend_version": "", "output": None, "valid_schema": False, "evidence": [],
                "latency_ms": 0, "prompt_tokens": 0, "gen_tokens": 0, "flags": ["backend_error"],
                "error": err[:300]}

    def _demote(self, stage: str, why: str = "OOM at concurrency 1") -> None:
        self.log(f"[hw] stage {stage}: {why}; demoting this machine to its other stages "
                 f"(the pinned model is never swapped)")
        self.fit.demote(stage)
        self.stages = [s for s in self.stages if s != stage]
        self.excluded[stage] = f"demoted: {why}"
        self.active_pins = {p: s for p, s in self.active_pins.items() if s != stage}

    # ------------------------------------------------------------------
    # Updates
    # ------------------------------------------------------------------
    def _update_pending(self) -> bool:
        return self._update_required or getattr(self, "_update_available", False)

    def check_for_update(self, force: bool = False) -> None:
        """Poll /v1/ping (every PING_POLL_S): coordinator redirect, sealed recipient, client updates."""
        now = self.clock.monotonic()
        if not force and now - self._last_ping < PING_POLL_S:
            return
        self._last_ping = now
        try:
            ping = self.client.ping()
        except (CoordinatorError, httpx.TransportError):
            return
        self.last_contact = self.clock.time()
        self._apply_sealed(ping.get("sealed_recipient"))
        if ping.get("redirect") and self.follow_redirect(str(ping["redirect"])):
            return  # re-polled against the new coordinator
        if not self.auto_update:
            return
        d = decide(ping)
        self._update_available = d.update_available
        if d.required:
            self._update_required = True
        self._last_decision = d

    def maybe_apply_update(self) -> bool:
        """Between jobs: release prefetched leases, flush, install, re-exec.
        Returns True if leasing must stay paused (required update failed)."""
        if self.paused():
            return False
        if not self.auto_update or not self._update_pending():
            return self._update_required and not self.auto_update
        d = getattr(self, "_last_decision", None)
        if d is None:
            self.check_for_update(force=True)
            d = getattr(self, "_last_decision", None)
            if d is None:
                return self._update_required
        target = str(d.latest or d.minimum or "")
        if not target or not self.updater.can_attempt(target):
            return self._update_required
        # Finish line: hand back prefetched work, upload everything.
        queued = [j.job_id for j in self._queue]
        self._queue.clear()
        for jid in queued:
            self.store.remove_job(jid)
        self._release(queued)
        self.flush_outbox(force=True)
        self.updater.apply(d, self.argv)  # does not return on success
        self._update_available = False
        return self._update_required

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def startup(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if self._registry is None or not self.active_pins:
            self.refresh_registry(force=True)
        if self._registry is None:
            raise RuntimeError("no registry available (coordinator unreachable and no cached copy)")
        self.recover_interrupted()
        self.flush_outbox(force=True)
        self.check_for_update(force=True)
        self.ensure_ollama()
        self.refresh_service_definition()
        self.sync_wake_triggers()
        self.resolve_stages()
        self.unload_non_pinned()
        self._save_state()

    def keep_awake_policy(self) -> None:
        """Hold keep-awake while working, inside the schedule, or when the next window starts within
        awake_before_window_min (short gaps never sleep). For longer gaps (or while paused): report once,
        arm a wake-up for the next window, and let the computer sleep."""
        ka = self.keep_awake
        if ka is None or not getattr(ka, "enabled", False):
            return
        now = self.clock.time()
        nxt = None
        if self.paused():
            want = False
        elif in_schedule(self.schedule, now):
            want = True
        else:
            nxt = next_schedule_change(self.schedule, now)
            want = nxt is not None and nxt - now <= 60.0 * float(self.cfg.awake_before_window_min or 0)
        if want:
            ka.hold()
            return
        if not ka.alive():
            return
        self.next_window = nxt
        self.activity = "paused" if self.paused() else "outside_hours"
        self._last_idle_hb = -1e18  # tell the fleet now: absence until the next window is expected
        try:
            self.heartbeat_once()
        except Exception:  # noqa: BLE001
            pass
        if nxt and sys.platform != "win32":  # Windows: the ald-wake task (service.sync_wake) wakes the PC
            from . import service as svc
            msg = svc.schedule_wake_at(nxt)
            if msg:
                self.log(f"[wake] {msg}")
        ka.release()
        when = _dt.datetime.fromtimestamp(nxt).strftime("%a %H:%M") if nxt else "resume"
        self.log(f"[keep-awake] next window {when} is more than {self.cfg.awake_before_window_min} min away: "
                 f"the computer may sleep until then")

    def sync_wake_triggers(self) -> None:
        """Windows: (re)create the wake task whenever the schedule differs from the last one applied."""
        if not self.service_mode or sys.platform != "win32":
            return
        from . import service as svc
        marker = self.root / "wake_schedule.json"
        if (read_json(marker, {}) or {}).get("schedule") == (self.schedule or ""):
            return
        try:
            for m in svc.sync_wake(self.schedule):
                self.log(f"[wake] {m}")
            atomic_write_json(marker, {"schedule": self.schedule or ""})
        except Exception as e:  # noqa: BLE001
            self.log(f"[wake] could not set up wake-ups: {e}")

    # ------------------------------------------------------------------
    # Migration: coordinator redirect, sealed recipient, scheduler directive
    # ------------------------------------------------------------------
    def _apply_sealed(self, offered: str | None) -> None:
        from . import sealed
        try:
            self.sealed_recipient = sealed.resolve_recipient(offered)
            self.sealed_blocked = None
        except sealed.SealedKeyMismatch as e:
            self.sealed_recipient = None
            if self.sealed_blocked != str(e):
                self.log(f"[sealed] REFUSING to work for this coordinator: {e}")
            self.sealed_blocked = str(e)

    def follow_redirect(self, target: str) -> bool:
        """The coordinator moved (docs/migration_plan.md section 2.1). Returns True if we switched."""
        target = target.rstrip("/")
        cur = (self.cfg.coordinator_url or "").rstrip("/")
        if not target.startswith(("https://", "http://")) or target == cur:
            return False
        guard_p = self.root / "redirect_state.json"
        guard = read_json(guard_p, {}) or {}
        if guard.get("left") == target and self.clock.time() - float(guard.get("at", 0)) < 3600:
            return False  # bounced straight back: ignore for an hour (redirect loop)
        try:
            probe = self.client_factory(target).ping()
        except Exception as e:  # noqa: BLE001
            self.log(f"[migrate] redirect to {target} not followed: target unreachable ({e})")
            return False
        if not probe.get("ok") or probe.get("project") not in (None, "ald"):
            self.log(f"[migrate] redirect to {target} not followed: not an ALD coordinator ({probe})")
            return False
        # Finish business with the old coordinator first: uploads, then hand back prefetched jobs.
        try:
            self.flush_outbox(force=True)
        except Exception:  # noqa: BLE001
            pass
        queued = [j.job_id for j in self._queue]
        self._queue.clear()
        for jid in queued:
            self.store.remove_job(jid)
        self._release(queued)
        atomic_write_json(guard_p, {"left": cur, "to": target, "at": self.clock.time()})
        try:
            self.cfg.update(coordinator_url=target)
        except OSError as e:
            self.log(f"[migrate] could not save the new coordinator URL: {e}")
        self.client = self.client_factory(target)
        self._registry_etag = None
        self._last_registry_poll = -1e18
        self._last_ping = -1e18
        self.log(f"[migrate] coordinator moved: {cur} -> {target}")
        return True

    def wait_file(self) -> Path:
        """Yield signal for other programs on every OS (Windows has no flock): while <data>/gpu.wait exists
        and was touched within the last 10 min, ald finishes its shard, unloads and does not lease."""
        return self.root / "gpu.wait"

    def wait_file_hold(self) -> str | None:
        p = self.wait_file()
        try:
            age = self.clock.time() - p.stat().st_mtime
        except OSError:
            return None
        if age > WAIT_FILE_MAX_AGE_S:
            return None  # stale (its owner crashed): ignore
        try:
            who = p.read_text(encoding="utf-8", errors="replace").strip()[:80]
        except OSError:
            who = ""
        return f"{p} present" + (f" ({who})" if who else "")

    def directive_hold(self) -> str | None:
        """The platform scheduler's GPU directive ({"gpu": run|yield|pause, "until", "reason"}): a reason not
        to lease, or None to work."""
        d = self.directive or {}
        mode = d.get("gpu")
        if mode not in ("yield", "pause"):
            return None
        until = d.get("until")
        if until:
            end = parse_ts(until, 0.0)
            if end and self.clock.time() >= end:
                self.directive = None
                return None
        return f"scheduler: {mode}" + (f" until {until}" if until else "") + (f" ({d.get('reason')})" if d.get("reason") else "")

    def _take_directive(self, d: Any) -> None:
        if isinstance(d, dict) and d.get("gpu") in ("run", "yield", "pause"):
            if d != getattr(self, "_last_directive_seen", None):  # log changes only (run arrives every minute)
                self.log(f"[scheduler] gpu={d.get('gpu')} until={d.get('until')} reason={d.get('reason')}")
            self._last_directive_seen = d
            self.directive = None if d.get("gpu") == "run" else d

    def refresh_service_definition(self) -> None:
        """After an auto-update, bring the installed unit / plist / task up to the current definition."""
        if not self.service_mode:
            return
        from . import service as svc
        marker = self.root / "service_def.json"
        if (read_json(marker, {}) or {}).get("version") == svc.SERVICE_DEF_VERSION:
            return
        try:
            msg = svc.refresh_definition()
            if msg:
                self.log(f"[service] {msg}")
            atomic_write_json(marker, {"version": svc.SERVICE_DEF_VERSION, "client_version": CLIENT_VERSION})
        except Exception as e:  # noqa: BLE001
            self.log(f"[service] could not refresh the service definition: {e}")

    def measure_foreign_vram(self) -> float:
        """VRAM held by programs other than our Ollama.

        Ollama 0.40's /api/ps size_vram covers only part of a loaded model (1.5-2.9 GB reported for gemma4
        12B while nvidia-smi shows ~10 GB), so "GPU used - size_vram" counted our own weights as foreign
        (0.1.10-0.1.17: a 3060 dropped label after every job). Instead:
        1. per-process GPU memory (nvidia-smi compute apps; Linux): foreign = used - Ollama's processes;
        2. else, only while our Ollama has NO model loaded: foreign = used; otherwise keep the last value."""
        if self.hw.accel != "cuda":
            return self.fit.foreign_gb
        used = self.gpu_used_fn()
        if used is None:
            return self.fit.foreign_gb
        foreign: float | None = None
        per_proc = self.gpu_procs_fn() if self.gpu_procs_fn else None
        if per_proc:
            ours = sum(gb for pid, gb in per_proc.items() if self._is_ollama_pid(pid))
            foreign = used - ours
        else:
            try:
                loaded = self.backend.ps()
            except BackendError:
                loaded = []
            if not loaded:
                foreign = used
        if foreign is None:
            return self.fit.foreign_gb  # a model of ours is resident: keep the last clean measurement
        # Up to ~1.5 GB is the normal desktop / display baseline (the registry figures assume it).
        foreign = max(0.0, round(foreign - DESKTOP_VRAM_BASELINE_GB, 2))
        if abs(foreign - self.fit.foreign_gb) >= 0.5:
            self.log(f"[gpu] {foreign:.1f} GB of VRAM held by other programs; planning with "
                     f"{max(0.0, self.hw.usable_vram_gb - foreign):.1f} GB")
        self.fit.foreign_gb = foreign
        return foreign

    @staticmethod
    def _is_ollama_pid(pid: int) -> bool:
        """Our Ollama server or its runner (…/lib/ollama/llama-server). Another program's llama-server
        (e.g. /app/llama-server in a container, or one we may not inspect) is foreign."""
        try:
            import psutil
            p = psutil.Process(pid)
            name = p.name().lower()
            exe = (p.exe() or "").lower().replace("\\", "/")
        except Exception:  # noqa: BLE001
            return False
        return name.startswith("ollama") or "/ollama/" in exe or "/programs/ollama/" in exe

    def _recheck_vram(self, every_s: float = 600.0) -> None:
        """Between jobs: other programs may have taken or freed VRAM; re-plan NUM_PARALLEL if it changed."""
        if not self.manage_ollama or self.hw.accel != "cuda" or self._registry is None:
            return
        now = self.clock.monotonic()
        if now - getattr(self, "_last_vram_check", -1e18) < every_s:
            return
        self._last_vram_check = now
        before = self.fit.server_slots
        self.measure_foreign_vram()
        after = self.effective_parallel(self.registry, self.tier or "", self.stages or None)
        if after != before:
            self.log(f"[gpu] NUM_PARALLEL {before} -> {after} for the VRAM other programs hold")
            self.ensure_ollama()
            self.resolve_stages()

    def effective_parallel(self, reg: Registry, tier: str, stages: list[str] | None = None) -> int | None:
        """The tier's NUM_PARALLEL hint, lowered until the largest allowed stage's KV slots fit in the VRAM
        actually free (other programs' memory excluded)."""
        hint = reg.num_parallel_hint(tier)
        if not hint:
            return None
        cands = [reg.stages[s] for s in (stages or reg.allowed_stages(tier)) if s in reg.stages]
        if not cands:
            return hint
        main = max(cands, key=lambda st: st.vram_gb_required + hint * st.kv_gb_per_slot)
        return self.fit.slots_that_fit(main, hint)

    def ensure_ollama(self, min_interval_s: float = 0.0) -> None:
        """Start Ollama if it is down and keep the tier's OLLAMA_* settings applied (see ollama_env)."""
        if not self.manage_ollama:
            return
        now = self.clock.monotonic()
        if now - self._last_ollama_ensure < min_interval_s:
            return
        self._last_ollama_ensure = now
        from . import ollama_env
        try:
            reg = self._registry
            tier = self.tier or (reg.select_tier(self.hw.usable_vram_gb)["name"] if reg else None)
            env = (ollama_env.tier_env(reg, tier, self.hw.accel, self.cfg.host_prompt_cache_mb) if (reg and tier)
                   else ollama_env.wanted_env(None, self.hw.accel, host_prompt_cache_mb=self.cfg.host_prompt_cache_mb))
            if reg and tier:
                self.measure_foreign_vram()
                np_eff = self.effective_parallel(reg, tier)
                if np_eff:
                    env["OLLAMA_NUM_PARALLEL"] = str(np_eff)
            ollama_env.ensure(env, url=self.cfg.ollama_url, log=self.log, service_mode=self.service_mode)
            self.backend._version = None
            self._backend_version_cache = None
        except Exception as e:  # noqa: BLE001 - never fatal: resolve_stages reports Ollama as unavailable
            self.log(f"[ollama] could not start/configure Ollama: {type(e).__name__}: {e}")

    # ------------------------------------------------------------------
    # GPU residency: a stray resident model splits the pinned one onto the CPU
    # (~8x slower), so keep only the model being run on the GPU.
    # ------------------------------------------------------------------
    def unload_non_pinned(self, keep: set[str] | None = None) -> list[str]:
        if self.hw.accel == "cpu" or self._registry is None:
            return []
        reg = self._registry
        if not (reg.unload_others and all(reg.stages[s].unload_others(True) for s in self.stages if s in reg.stages)):
            return []
        if keep is None:
            keep = {self.registry.stages[s].model_ref for s in self.stages}
        try:
            gone = self.backend.unload_others(keep)
        except BackendError:
            return []
        if gone:
            self.log(f"[gpu] unloaded resident model(s) to keep the pinned model fully on GPU: {', '.join(gone)}")
        return gone

    def check_residency(self, stage: str) -> str:
        """'ok' | 'unknown' | 'retry' (unloaded everything; reloads on the next
        request) | 'demoted' (still split after a clean reload)."""
        if self.hw.accel == "cpu":
            return "ok"
        st = self.registry.stages[stage]
        try:
            frac = self.backend.residency(st.model_ref)
        except BackendError:
            return "ok"
        if frac is None:
            return "unknown"  # not (yet) resident; check again on the next passage
        self.gpu_fraction[stage] = round(frac, 3)
        if frac >= 0.99:
            self._residency_retry.pop(stage, None)
            return "ok"
        if not self._residency_retry.get(stage):
            self._residency_retry[stage] = True
            self.log(f"[gpu] {st.model_ref} only {frac:.0%} on GPU; unloading other models and reloading it")
            self.unload_non_pinned(keep=set())
            return "retry"
        self.log(f"[gpu] {st.model_ref} still only {frac:.0%} on GPU after a clean reload "
                 f"(num_ctx is pinned and cannot be lowered)")
        self._demote(stage, f"model only {frac:.0%} on GPU")
        return "demoted"

    def _save_state(self) -> None:
        try:
            atomic_write_json(self.root / "state.json", {
                "updated": self.clock.time(), "tier": self.tier, "stages": self.stages,
                "excluded": self.excluded, "rates_pps": self.rates.rates,
                "concurrency": {s: t.current for s, t in self.tuners.items()},
                "held_jobs": [{"job_id": j.job_id, "stage": j.stage, "progress": round(j.progress, 3),
                               "remaining_s": j.remaining_s} for j in self._held()],
                "passages_done": self.passages_done, "client_version": CLIENT_VERSION,
                "registry_version": self._registry.version if self._registry else None,
                "pid": os.getpid(), "last_contact": self.last_contact, "report": self.report(),
                "active_hours": self.active_hours, "schedule": self.schedule, "service": self.service_mode,
                "schedule_next_change": next_schedule_change(self.schedule, self.clock.time()),
                "in_schedule": in_schedule(self.schedule, self.clock.time()),
            })
        except OSError:
            pass

    def plan(self) -> PlanSummary:
        conc, pph, lsz = {}, {}, {}
        for s in self.stages:
            conc[s] = self.tuners[s].current if s in self.tuners else 1
            r = self.rates.rate(s)
            pph[s] = round(r * 3600) if r else None
            lsz[s] = lease_size(r, ttl_s=LEASE_TTL_S)
        return PlanSummary(tier=self.tier or "?", stages=list(self.stages), excluded=dict(self.excluded),
                           concurrency=conc, disk=self.storage.report(), passages_per_hour=pph,
                           lease_size=lsz, deadline=self.window.deadline)

    def run(self) -> None:
        """Main loop. Returns on stop / window end / idle exit."""
        self.startup()
        if self.background:
            t = threading.Thread(target=self._bg_loop, name="ald-bg", daemon=True)
            t.start()
            self._threads.append(t)
        idle = 0
        try:
            while not self.stop.is_set():
                self.keep_awake_policy()
                if self.window.expired():
                    self.log("[window] run window ended")
                    break
                if self._registry_changed:
                    self.resolve_stages()
                    self.ensure_ollama()  # tier hints (NUM_PARALLEL, KV cache type) may have changed
                    self.resolve_stages()
                if self.paused():
                    if self.activity != "paused":
                        self.log("[pause] paused by `ald pause`; `ald resume` continues")
                    self.activity = "paused"
                    self._idle_gpu_unload()
                    self._release_gpu_lock()
                    self._save_state()
                    if self.exit_when_idle or self.clock.sleep(10.0, self.stop):
                        break
                    continue
                hold = (self.directive_hold() or self.wait_file_hold()
                        or (f"sealed key mismatch: {self.sealed_blocked}" if self.sealed_blocked else None))
                if hold:
                    if self.activity != "yielding":
                        self.log(f"[scheduler] not leasing: {hold}")
                    self.activity = "yielding"
                    self._unload_stage_models("scheduler directive" if self.directive else "sealed key mismatch")
                    self._release_gpu_lock()
                    self._last_idle_hb = -1e18  # ask for a fresh directive
                    self._save_state()
                    if self.exit_when_idle or self.clock.sleep(30.0, self.stop):
                        break
                    self.check_for_update()
                    continue
                why_ram = self.ram_blocked()
                if why_ram:
                    if self.activity != "low_memory":
                        self.log(f"[ram] {why_ram}: not leasing; freeing ours")
                    self.activity = "low_memory"
                    self.check_for_update()  # idle: updating is fine (never while paused)
                    self.maybe_apply_update()
                    self._unload_stage_models("low system RAM")
                    self._release_gpu_lock()
                    self._save_state()
                    if self.exit_when_idle or self.clock.sleep(60.0, self.stop):
                        break
                    continue
                if not in_schedule(self.schedule, self.clock.time()):
                    self.check_for_update()  # idle anyway: a good time to update (never while paused)
                    self.maybe_apply_update()
                    if self.activity != "outside_hours":
                        nxt = next_schedule_change(self.schedule, self.clock.time())
                        when = _dt.datetime.fromtimestamp(nxt).strftime("%a %H:%M") if nxt else "?"
                        self.log(f"[window] outside schedule '{self.schedule}'; idle until {when}")
                    self.activity = "outside_hours"
                    self._idle_gpu_unload()
                    self._save_state()
                    if self.exit_when_idle or self.clock.sleep(60.0, self.stop):
                        break
                    continue
                self._recheck_vram()
                self.check_for_update()
                paused_for_update = self.maybe_apply_update()
                if not self.stages:
                    self.activity = "no_stages"
                    self.log("[work] no runnable stages: " + "; ".join(f"{k}: {v}" for k, v in self.excluded.items()))
                    if any("Ollama unavailable" in v for v in self.excluded.values()):
                        self.ensure_ollama(min_interval_s=120.0)
                    if self.exit_when_idle:
                        break
                    if self.clock.sleep(min(300.0, self._lease_backoff.next()), self.stop):
                        break
                    self._registry_changed = True
                    continue
                if paused_for_update:
                    self.flush_outbox()
                    if self.clock.sleep(min(600.0, self._lease_backoff.next()), self.stop):
                        break
                    continue
                hj = self._queue.popleft() if self._queue else None
                if hj is None:
                    if self.gpu_lock.enabled and not self.gpu_lock.held:
                        self.activity = "waiting_gpu_lock"
                        self._save_state()
                        self._gpu_yield_wait()
                        def _abort_wait() -> bool:  # keep updating while another program holds the GPU
                            self.check_for_update()
                            return self.auto_update and self._update_pending()
                        if not self.gpu_lock.acquire(self.stop, abort=_abort_wait):
                            if self.stop.is_set():
                                break
                            continue  # an update is pending: the next loop iteration applies it
                    got = self.lease_jobs()
                    hj = self._queue.popleft() if got and self._queue else None
                if hj is None:
                    idle += 1
                    self.activity = "idle"
                    self._idle_gpu_unload()
                    self._release_gpu_lock()
                    if self.exit_when_idle and idle >= self.idle_polls_before_exit:
                        break
                    if not self.window.allow_new_lease(None):
                        break
                    delay = self._lease_backoff.next()
                    # The coordinator says when to come back (nothing leasable); D1 bills every poll.
                    ra = getattr(self.client, "last_retry_after", None)
                    if ra:
                        delay = max(delay, float(ra))
                    rem = self.window.remaining()
                    if rem is not None:
                        delay = max(0.0, min(delay, rem))
                    self.log(f"[work] nothing leased; next try in {delay:.0f}s")
                    if self.clock.sleep(delay, self.stop):
                        break
                    continue
                idle = 0
                self._lease_backoff.reset()
                if hj.revoked.is_set():
                    self.store.remove_job(hj.job_id)
                    continue
                if hj.pin_hash not in self.active_pins:
                    self.log(f"[pin] {hj.job_id}: pin retired by registry update; releasing")
                    self.store.remove_job(hj.job_id)
                    self._release([hj.job_id])
                    continue
                self.run_job(hj)
        finally:
            self.shutdown()

    def shutdown(self, flush_timeout_s: float = 20.0) -> None:
        """Release everything we hold and push what we have."""
        self.stop.set()
        queued = [j.job_id for j in self._queue]
        self._queue.clear()
        for jid in queued:
            self.store.remove_job(jid)
        self._release(queued)
        try:
            self.flush_outbox(force=True)
        except Exception as e:  # noqa: BLE001
            self.log(f"[shutdown] flush failed: {e}")
        n, size = self.outbox.size()
        if n:
            self.log(f"[shutdown] {n} upload(s) ({size / 1e6:.1f} MB) stay in the outbox; "
                     f"they are sent on the next start or `ald sync-now`")
        try:
            self._idle_gpu_unload()
        except Exception:  # noqa: BLE001
            pass
        self.gpu_lock.release()
        self.activity = "stopped"
        self._save_state()
        self.shutdown_done.set()
