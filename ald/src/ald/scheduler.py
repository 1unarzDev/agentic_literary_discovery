"""Scheduling policies for ``ald work``: storage, hardware fit, concurrency,
timing. Pure logic with injectable clocks / disk-usage functions so it can be
unit-tested; the worker loop (``worker.py``) wires these together.

Nothing here ever changes the model of a stage: pins are fixed. Hardware
pressure only changes *how many* passages run at once or *which* allowed
stages this machine takes.
"""

from __future__ import annotations

import datetime as _dt
import math
import os
import random
import shutil
import time
from collections import namedtuple
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from .registry import Stage

GB = 1024 ** 3
MB = 1024 ** 2

DiskUsage = namedtuple("DiskUsage", "total used free")
DiskUsageFn = Callable[[str], Any]

# Contract: shards are ~500 passages, ~1.5 MB gzip in. Results are a bit
# smaller per passage but we budget conservatively for checkpoint + gz copy.
DEFAULT_PASSAGES_PER_JOB = 500
SHARD_BYTES_PER_PASSAGE = int(1.5 * MB / 500)
RESULT_BYTES_PER_PASSAGE = int(2.0 * MB / 500)  # checkpoint jsonl + outbox gz


class Clock:
    """Wall + monotonic clock with an interruptible sleep."""

    def time(self) -> float:
        return time.time()

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float, stop: Any = None) -> bool:
        """Sleep; return True if interrupted by ``stop`` (a threading.Event)."""
        if seconds <= 0:
            return bool(stop and stop.is_set())
        if stop is not None:
            return bool(stop.wait(seconds))
        time.sleep(seconds)
        return False


class Backoff:
    """Exponential backoff with full jitter."""

    def __init__(self, base: float = 2.0, cap: float = 300.0, rng: random.Random | None = None):
        self.base, self.cap = base, cap
        self.attempt = 0
        self.rng = rng or random.Random()

    def next(self) -> float:
        hi = min(self.cap, self.base * (2 ** self.attempt))
        self.attempt += 1
        return self.rng.uniform(hi / 2, hi)

    def reset(self) -> None:
        self.attempt = 0


# --------------------------------------------------------------------------
# 1. Storage
# --------------------------------------------------------------------------

def dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.stat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


@dataclass
class StoragePlan:
    jobs: int
    available_bytes: int
    per_job_bytes: int
    paused: bool
    reason: str = ""


class StorageManager:
    """Keeps ald's footprint inside a disk budget.

    budget = configured ``budget_bytes`` or ``min(free - reserve, cap)``
    (computed over the bytes ald already uses, so our own files do not shrink
    the budget as they are written). Free space never drops below ``reserve``.
    """

    def __init__(
        self,
        root: Path,
        *,
        budget_bytes: int | None = None,
        reserve_bytes: int = 20 * GB,
        cap_bytes: int = 10 * GB,
        disk_usage: DiskUsageFn = shutil.disk_usage,
        used_fn: Callable[[], int] | None = None,
    ):
        self.root = Path(root)
        self.budget_cfg = budget_bytes
        self.reserve = reserve_bytes
        self.cap = cap_bytes
        self._disk_usage = disk_usage
        self._used_fn = used_fn

    # -- measurements --------------------------------------------------
    def used_bytes(self) -> int:
        return self._used_fn() if self._used_fn else dir_size(self.root)

    def free_bytes(self) -> int:
        p = self.root
        while not p.exists() and p != p.parent:
            p = p.parent
        return int(self._disk_usage(str(p)).free)

    def budget_bytes(self) -> int:
        used, free = self.used_bytes(), self.free_bytes()
        hard = used + free - self.reserve  # never eat into the reserve
        soft = self.budget_cfg if self.budget_cfg is not None else self.cap
        return max(0, min(soft, hard))

    def available_bytes(self) -> int:
        return max(0, self.budget_bytes() - self.used_bytes())

    # -- projections -----------------------------------------------------
    @staticmethod
    def job_bytes(n_passages: int = DEFAULT_PASSAGES_PER_JOB) -> int:
        return n_passages * (SHARD_BYTES_PER_PASSAGE + RESULT_BYTES_PER_PASSAGE)

    def model_fits(self, size_gb: float, models_dir: Path | None = None) -> bool:
        """Models live in Ollama's store (often the same disk); require that
        pulling one leaves the reserve intact."""
        target = models_dir or self.root
        while not target.exists() and target != target.parent:
            target = target.parent
        free = int(self._disk_usage(str(target)).free)
        return free - size_gb * GB >= self.reserve

    def plan(self, wanted: int, n_passages: int = DEFAULT_PASSAGES_PER_JOB, extra_bytes: int = 0) -> StoragePlan:
        """How many of ``wanted`` jobs fit right now. ``extra_bytes`` is any
        other projected need (e.g. a model that still has to be pulled)."""
        per = self.job_bytes(n_passages)
        avail = self.available_bytes() - extra_bytes
        n = max(0, min(wanted, avail // per)) if per > 0 else wanted
        paused = n == 0 and wanted > 0
        reason = ""
        if paused:
            reason = (f"low disk: {avail / MB:.0f} MB available in budget, "
                      f"need {per / MB:.0f} MB per job; leasing paused")
        return StoragePlan(jobs=int(n), available_bytes=int(avail), per_job_bytes=per,
                           paused=paused, reason=reason)

    # -- eviction ----------------------------------------------------------
    def evict(self, candidates: Iterable[Path], need_bytes: int) -> list[Path]:
        """LRU-delete ``candidates`` (caches only; never outbox entries or
        active checkpoints, which the caller must exclude) until
        ``need_bytes`` are available. Returns deleted paths."""
        removed: list[Path] = []
        items = []
        for p in candidates:
            try:
                st = p.stat()
                items.append((max(st.st_atime, st.st_mtime), p, st.st_size))
            except OSError:
                continue
        items.sort(key=lambda x: x[0])
        for _t, p, _size in items:
            if self.available_bytes() >= need_bytes:
                break
            try:
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    p.unlink()
                removed.append(p)
            except OSError:
                pass
        return removed

    def report(self) -> dict[str, Any]:
        used = self.used_bytes()
        return {
            "root": str(self.root),
            "used_bytes": used,
            "budget_bytes": self.budget_bytes(),
            "available_bytes": self.available_bytes(),
            "free_bytes": self.free_bytes(),
            "reserve_bytes": self.reserve,
        }


# --------------------------------------------------------------------------
# 2. Hardware fit
# --------------------------------------------------------------------------

@dataclass
class HardwareFit:
    """Memory headroom check against the registry's per-stage requirements:
    need(stage, c) = vram_gb_required + (c - 1) * kv_gb_per_slot.

    On GPU machines the capacity is usable VRAM (Apple: ~65% of unified
    memory, already applied by hw.py). On CPU-only machines it is 70% of RAM.
    """

    usable_vram_gb: float
    ram_gb: float
    accel: str = "cpu"
    headroom_gb: float = 0.5
    unfit: set[str] = field(default_factory=set)
    # Ollama allocates KV cache for OLLAMA_NUM_PARALLEL slots; requests beyond that queue in the server and
    # cost no VRAM. Known when ald configured the server (manage_ollama), else None (= every request a slot).
    server_slots: int | None = None
    # VRAM held by other programs (games, another study's llama-server, the desktop), measured at runtime.
    foreign_gb: float = 0.0

    @property
    def capacity_gb(self) -> float:
        if self.accel == "cpu" or self.usable_vram_gb <= 0:
            return self.ram_gb * 0.7
        return max(0.0, self.usable_vram_gb - self.foreign_gb)

    def slots_that_fit(self, stage: Stage, wanted: int) -> int:
        """Largest NUM_PARALLEL <= wanted whose KV slots fit next to the other programs' VRAM (>= 1)."""
        n = max(1, wanted)
        while n > 1 and self.need_gb(stage, n) + self.headroom_gb > self.capacity_gb + 1e-9:
            n -= 1
        return n

    @staticmethod
    def need_gb(stage: Stage, concurrency: int) -> float:
        return stage.vram_gb_required + max(0, concurrency - 1) * stage.kv_gb_per_slot

    def fits(self, stage: Stage, concurrency: int = 1) -> bool:
        if stage.name in self.unfit:
            return False
        c = min(concurrency, self.server_slots) if self.server_slots else concurrency
        return self.need_gb(stage, c) + self.headroom_gb <= self.capacity_gb + 1e-9

    def max_concurrency(self, stage: Stage, cap: int) -> int:
        best = 0
        for c in range(1, max(1, cap) + 1):
            if self.fits(stage, c):
                best = c
            else:
                break
        return best

    def filter_stages(self, stages: Iterable[Stage]) -> tuple[list[str], dict[str, str]]:
        ok, why = [], {}
        for st in stages:
            if st.name in self.unfit:
                why[st.name] = "demoted: did not fit (OOM / GPU split)"
            elif not self.fits(st, 1):
                why[st.name] = (f"needs {self.need_gb(st, 1) + self.headroom_gb:.1f} GB, "
                                f"have {self.capacity_gb:.1f} GB")
            else:
                ok.append(st.name)
        return ok, why

    def demote(self, stage_name: str) -> None:
        """Called after an OOM at concurrency 1: stop taking this stage here
        (the model is never swapped for a smaller one)."""
        self.unfit.add(stage_name)


# --------------------------------------------------------------------------
# 2b. Concurrency auto-tuning (AIMD)
# --------------------------------------------------------------------------

class ConcurrencyTuner:
    """Additive-increase / multiplicative-decrease on observed throughput.

    * Every ``window`` completions, compare throughput (gen tok/s, wall) with
      the previous concurrency level. Better by >= ``gain`` -> +1; otherwise
      fall back to the best level seen and hold for ``hold_windows`` windows.
    * Per-level baseline latency is recorded the first time a level runs. A
      later window at the same level with mean latency > ``thermal_factor`` x
      baseline is treated as thermal throttling / contention -> halve.
    * OOM -> halve and lower the ceiling to the new value; other backend
      errors -> halve.
    """

    def __init__(self, start: int = 1, max_c: int = 8, *, window: int = 8, gain: float = 1.05,
                 thermal_factor: float = 2.0, hold_windows: int = 10, settle_windows: int = 1,
                 clock: Clock | None = None):
        self.max_c = max(1, max_c)
        self.current = max(1, min(start, self.max_c))
        self.window = window
        self.gain = gain
        self.thermal_factor = thermal_factor
        self.hold_windows = hold_windows
        # After every change the first window is a transient (requests started at the old level are still
        # finishing), so it is discarded. Measured on an RTX 3060: without this the tuner stopped at c=3
        # although c>=4 was ~35% faster.
        self.settle_windows = settle_windows
        self._settle = 0
        self.clock = clock or Clock()
        self.baseline_lat: dict[int, float] = {}
        self.tput: dict[int, float] = {}
        self._hold = 0
        self._reset_window()
        self.events: list[str] = []

    def _reset_window(self) -> None:
        self._n = 0
        self._tokens = 0
        self._lat = 0.0
        self._t0: float | None = None

    def set_max(self, max_c: int) -> None:
        self.max_c = max(1, max_c)
        self.current = min(self.current, self.max_c)

    def observe(self, latency_s: float, gen_tokens: int) -> None:
        now = self.clock.monotonic()
        if self._t0 is None:
            # The window starts at the first completion minus its latency.
            self._t0 = now - latency_s
        self._n += 1
        self._tokens += gen_tokens
        self._lat += latency_s
        if self._n >= self.window:
            self._evaluate(now)

    def _changed(self) -> None:
        self._settle = self.settle_windows

    def _evaluate(self, now: float) -> None:
        if self._settle > 0:
            self._settle -= 1
            self._reset_window()
            return
        c = self.current
        dt = max(now - (self._t0 or now), 1e-6)
        tput = self._tokens / dt if self._tokens else self._n / dt
        lat = self._lat / self._n
        self._reset_window()
        base = self.baseline_lat.get(c)
        if base is None:
            self.baseline_lat[c] = lat
        elif lat > self.thermal_factor * base:
            self._decrease(f"latency {lat:.2f}s > {self.thermal_factor:g}x baseline {base:.2f}s at c={c}")
            return
        prev_best = max(self.tput.values()) if self.tput else None
        self.tput[c] = tput if c not in self.tput else 0.5 * self.tput[c] + 0.5 * tput
        if self._hold > 0:
            self._hold -= 1
            return
        if prev_best is not None and c > 1 and (c - 1) in self.tput and self.tput[c] < self.tput[c - 1] * self.gain:
            best_c = max(self.tput, key=lambda k: self.tput[k])
            if best_c != c:
                self.events.append(f"plateau at c={c}; back to c={best_c}")
                self._changed()
            self.current = best_c
            self._hold = self.hold_windows
            return
        if c < self.max_c:
            self.current = c + 1
            self._changed()
            self.events.append(f"increase to c={self.current}")

    def _decrease(self, why: str) -> None:
        self.current = max(1, self.current // 2)
        self._hold = self.hold_windows
        self._reset_window()
        self._changed()
        self.events.append(f"decrease to c={self.current}: {why}")

    def on_error(self, oom: bool = False) -> None:
        if oom:
            self._decrease("OOM")
            self.max_c = max(1, self.current)
            # Forget measurements above the new ceiling.
            self.tput = {k: v for k, v in self.tput.items() if k <= self.max_c}
        else:
            self._decrease("backend error")


# --------------------------------------------------------------------------
# 3. Timing
# --------------------------------------------------------------------------

class RateTracker:
    """EWMA of passages/second per stage."""

    def __init__(self, alpha: float = 0.3, initial: dict[str, float] | None = None):
        self.alpha = alpha
        self.rates: dict[str, float] = dict(initial or {})

    def update(self, stage: str, passages: int, seconds: float) -> None:
        if passages <= 0 or seconds <= 0:
            return
        r = passages / seconds
        old = self.rates.get(stage)
        self.rates[stage] = r if old is None else (1 - self.alpha) * old + self.alpha * r

    def rate(self, stage: str) -> float | None:
        return self.rates.get(stage)

    def eta_seconds(self, stage: str, passages: int) -> float | None:
        r = self.rate(stage)
        return passages / r if r else None


def lease_size(rate_pps: float | None, *, passages_per_job: int = DEFAULT_PASSAGES_PER_JOB,
               ttl_s: float = 600.0, target_frac: float = 0.5, cap: int = 4) -> int:
    """Jobs per lease so the batch is expected to finish within
    ``target_frac`` x TTL. Always at least 1 (long jobs survive via heartbeat
    extensions)."""
    if not rate_pps or rate_pps <= 0:
        return 1
    per_job = passages_per_job / rate_pps
    return max(1, min(cap, int(math.floor(target_frac * ttl_s / per_job))))


def should_prefetch(progress: float, remaining_s: float | None, *, at_progress: float = 0.5,
                    min_lead_s: float = 120.0) -> bool:
    """Lease + download the next shard while the current one runs."""
    if progress >= at_progress:
        return True
    return remaining_s is not None and remaining_s <= min_lead_s


class RunWindow:
    """Optional ``--until HH:MM`` / ``--hours N`` window."""

    def __init__(self, deadline: float | None, clock: Clock | None = None, margin: float = 1.1):
        self.deadline = deadline
        self.clock = clock or Clock()
        self.margin = margin

    @classmethod
    def from_args(cls, until: str | None, hours: float | None, clock: Clock | None = None) -> "RunWindow":
        clock = clock or Clock()
        now = clock.time()
        deadline = None
        if hours is not None:
            deadline = now + hours * 3600
        if until:
            hh, mm = (int(x) for x in until.split(":", 1))
            if not (0 <= hh < 24 and 0 <= mm < 60):
                raise ValueError(f"bad --until {until!r}")
            local_now = _dt.datetime.fromtimestamp(now)
            target = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if target <= local_now:
                target += _dt.timedelta(days=1)
            t = target.timestamp()
            deadline = t if deadline is None else min(deadline, t)
        return cls(deadline, clock)

    def remaining(self) -> float | None:
        return None if self.deadline is None else self.deadline - self.clock.time()

    def expired(self) -> bool:
        r = self.remaining()
        return r is not None and r <= 0

    def allow_new_lease(self, expected_job_s: float | None) -> bool:
        r = self.remaining()
        if r is None:
            return True
        if r <= 0:
            return False
        if expected_job_s is None:
            return True
        return r >= expected_job_s * self.margin


@dataclass
class PlanSummary:
    tier: str
    stages: list[str]
    excluded: dict[str, str]
    concurrency: dict[str, int]
    disk: dict[str, Any]
    passages_per_hour: dict[str, float | None]
    lease_size: dict[str, int]
    deadline: float | None


def fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"


def fmt_duration(s: float | None) -> str:
    if s is None:
        return "-"
    s = int(max(0, s))
    h, rem = divmod(s, 3600)
    m, _ = divmod(rem, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m"


def in_active_hours(spec: str | None, now: float) -> bool:
    """``spec`` = "HH:MM-HH:MM" local time (may wrap midnight, e.g. "22:00-07:00"); None/"" = always."""
    if not spec:
        return True
    try:
        a, b = (x.strip() for x in spec.split("-", 1))
        ah, am = (int(x) for x in a.split(":"))
        bh, bm = (int(x) for x in b.split(":"))
    except ValueError:
        return True  # a malformed window never stops work
    t = _dt.datetime.fromtimestamp(now)
    cur, start, end = t.hour * 60 + t.minute, ah * 60 + am, bh * 60 + bm
    if start == end:
        return True
    return start <= cur < end if start < end else (cur >= start or cur < end)


# --------------------------------------------------------------------------
# Weekly schedule:  "mon-fri 21:00-05:00,07:00-15:00; sat-sun 21:00-05:00"
# --------------------------------------------------------------------------
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _parse_days(tok: str) -> list[int]:
    tok = tok.strip().lower()
    if tok in ("daily", "*", "all", "every"):
        return list(range(7))
    out: list[int] = []
    for part in tok.split(","):
        part = part.strip()
        if "-" in part:
            a, b = (x.strip()[:3] for x in part.split("-", 1))
            i, j = DAYS.index(a), DAYS.index(b)
            out.extend((i + k) % 7 for k in range((j - i) % 7 + 1))
        else:
            out.append(DAYS.index(part[:3]))
    return sorted(set(out))


def _parse_hhmm(s: str) -> int:
    hh, mm = (int(x) for x in s.strip().split(":"))
    if not (0 <= hh <= 24 and 0 <= mm < 60) or (hh == 24 and mm):
        raise ValueError(f"bad time {s!r}")
    return hh * 60 + mm


def parse_schedule(spec: str) -> list[tuple[int, int, int]]:
    """-> [(weekday 0=Mon, start_min, end_min)]. A span whose end is not after its start runs past
    midnight into the next day (e.g. "fri 21:00-05:00" covers Friday 21:00 to Saturday 05:00).
    Rules: ``<days> <HH:MM-HH:MM>[,<HH:MM-HH:MM>...]`` separated by ';'. Days: mon..sun, ranges (mon-fri,
    sat-sun), lists (mon,wed) or daily. Raises ValueError on bad syntax."""
    rules: list[tuple[int, int, int]] = []
    for clause in (c.strip() for c in spec.split(";")):
        if not clause:
            continue
        try:
            days_tok, spans_tok = clause.split(None, 1)
            days = _parse_days(days_tok)
        except ValueError as e:
            raise ValueError(f"bad schedule clause {clause!r}: expected '<days> HH:MM-HH:MM[,...]'") from e
        for span in spans_tok.replace(" ", "").split(","):
            if "-" not in span:
                raise ValueError(f"bad time span {span!r} in {clause!r}")
            a, b = span.split("-", 1)
            start, end = _parse_hhmm(a), _parse_hhmm(b)
            for d in days:
                rules.append((d, start, end))
    if not rules:
        raise ValueError("empty schedule")
    return rules


def legacy_hours_to_schedule(active_hours: str | None) -> str | None:
    return f"daily {active_hours}" if active_hours else None


def in_schedule(spec: str | None, now: float) -> bool:
    """True if local time ``now`` is inside the weekly schedule (None/"" = always). A malformed schedule
    never stops work."""
    if not spec:
        return True
    try:
        rules = parse_schedule(spec)
    except ValueError:
        return True
    t = _dt.datetime.fromtimestamp(now)
    wd, cur = t.weekday(), t.hour * 60 + t.minute
    for d, start, end in rules:
        if start == end:  # 24 h starting at `start`
            if (wd == d and cur >= start) or (wd == (d + 1) % 7 and cur < start):
                return True
        elif start < end:
            if wd == d and start <= cur < end:
                return True
        elif (wd == d and cur >= start) or (wd == (d + 1) % 7 and cur < end):
            return True
    return False


def next_schedule_change(spec: str | None, now: float) -> float | None:
    """Epoch of the next minute at which the in/out state flips (window start when outside, end when
    inside), searched up to 8 days ahead; None if it never changes."""
    if not spec:
        return None
    try:
        parse_schedule(spec)
    except ValueError:
        return None
    t0 = _dt.datetime.fromtimestamp(now).replace(second=0, microsecond=0)
    state = in_schedule(spec, now)
    for k in range(1, 8 * 24 * 60 + 1):
        t = t0 + _dt.timedelta(minutes=k)
        if in_schedule(spec, t.timestamp()) != state:
            return t.timestamp()
    return None
