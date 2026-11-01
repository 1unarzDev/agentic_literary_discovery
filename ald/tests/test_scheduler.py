import datetime as dt
import os
import time

import pytest

from ald.registry import Registry
from ald.scheduler import (
    GB, MB, Backoff, ConcurrencyTuner, HardwareFit, RateTracker, RunWindow, StorageManager, lease_size,
    should_prefetch,
)
from conftest import DU, FakeClock


# --- storage ------------------------------------------------------------------

def mk_storage(tmp_path, free_gb, used_bytes=0, **kw):
    state = {"free": free_gb * GB, "used": used_bytes}
    sm = StorageManager(tmp_path, disk_usage=lambda p: DU(1000 * GB, 0, state["free"]),
                        used_fn=lambda: state["used"], **kw)
    return sm, state


def test_default_budget_is_min_free_minus_reserve_and_10gb(tmp_path):
    sm, _ = mk_storage(tmp_path, 100)
    assert sm.budget_bytes() == 10 * GB
    sm, _ = mk_storage(tmp_path, 25)
    assert sm.budget_bytes() == 5 * GB
    sm, _ = mk_storage(tmp_path, 15)
    assert sm.budget_bytes() == 0


def test_budget_counts_own_usage(tmp_path):
    # ald already uses 3 GB; free is 30 GB -> hard limit 3+30-20 = 13, soft 10.
    sm, _ = mk_storage(tmp_path, 30, used_bytes=3 * GB)
    assert sm.budget_bytes() == 10 * GB
    assert sm.available_bytes() == 7 * GB


def test_configured_budget(tmp_path):
    sm, _ = mk_storage(tmp_path, 100, budget_bytes=2 * GB)
    assert sm.budget_bytes() == 2 * GB


def test_plan_leases_only_what_fits_and_pauses(tmp_path):
    per = StorageManager.job_bytes(500)
    sm, st = mk_storage(tmp_path, 20, budget_bytes=None)
    st["free"] = 20 * GB + 3 * per + per // 2  # room for 3 jobs above the reserve
    p = sm.plan(8)
    assert p.jobs == 3 and not p.paused
    # A model still to be pulled eats into the projection.
    assert sm.plan(8, extra_bytes=2 * per).jobs == 1
    st["free"] = 20 * GB + per // 2
    p = sm.plan(2)
    assert p.jobs == 0 and p.paused and "paused" in p.reason
    st["free"] = 40 * GB  # space returns -> resume
    assert sm.plan(2).jobs == 2


def test_model_fits(tmp_path):
    sm, st = mk_storage(tmp_path, 30)
    assert sm.model_fits(9.0)
    assert not sm.model_fits(11.0)


def test_evict_lru_until_enough(tmp_path):
    from ald.scheduler import dir_size
    files = []
    for i in range(4):
        p = tmp_path / f"s{i}.gz"
        p.write_bytes(b"x" * 10)
        t = time.time() - 1000 + i * 100
        os.utime(p, (t, t))
        files.append(p)
    # Budget 40 bytes, 40 used -> nothing available; need 20 -> two oldest go.
    sm = StorageManager(tmp_path, budget_bytes=40, reserve_bytes=0, disk_usage=lambda p: DU(1, 0, 10 ** 12),
                        used_fn=lambda: dir_size(tmp_path))
    removed = sm.evict(list(reversed(files)), need_bytes=20)
    assert [p.name for p in removed] == ["s0.gz", "s1.gz"]
    assert files[2].exists() and files[3].exists()


def test_report_shape(tmp_path):
    sm, _ = mk_storage(tmp_path, 50)
    r = sm.report()
    assert {"used_bytes", "budget_bytes", "available_bytes", "free_bytes", "reserve_bytes"} <= set(r)


# --- hardware fit ---------------------------------------------------------------

def test_fit_and_concurrency(registry_raw):
    reg = Registry.from_dict(registry_raw)
    hf = HardwareFit(usable_vram_gb=15.99, ram_gb=32, accel="cuda")
    label = reg.stages["label"]  # 10 GB + 0.5/slot
    assert hf.fits(label, 1)
    assert hf.max_concurrency(label, 8) == 8  # 10 + 7*0.5 + 0.5 = 14.0
    assert hf.max_concurrency(label, 12) == 11  # 10 + 10*0.5 + 0.5 = 15.5 <= 15.99
    assert not hf.fits(reg.stages["adjudicate"], 1)
    hf8 = HardwareFit(usable_vram_gb=8.0, ram_gb=16, accel="cuda")
    assert hf8.fits(reg.stages["workcheck"], 1)
    assert not hf8.fits(label, 1)
    ok, why = hf8.filter_stages([reg.stages["workcheck"], label])
    assert ok == ["workcheck"] and "needs" in why["label"]


def test_demote_never_swaps_model(registry_raw):
    reg = Registry.from_dict(registry_raw)
    hf = HardwareFit(usable_vram_gb=15.99, ram_gb=32, accel="cuda")
    before = reg.stages["label"].model_ref
    hf.demote("label")
    ok, why = hf.filter_stages(reg.stages.values())
    assert "label" not in ok and why["label"].startswith("demoted")
    assert "workcheck" in ok
    assert reg.stages["label"].model_ref == before


def test_cpu_capacity_uses_ram(registry_raw):
    hf = HardwareFit(usable_vram_gb=0, ram_gb=16, accel="cpu")
    assert hf.capacity_gb == pytest.approx(11.2)


# --- AIMD tuner -----------------------------------------------------------------

def feed(tuner, clock, n, latency, tokens, dt):
    for _ in range(n):
        clock.advance(dt)
        tuner.observe(latency, tokens)


def test_tuner_increases_while_throughput_grows():
    clock = FakeClock()
    t = ConcurrencyTuner(start=1, max_c=4, window=4, clock=clock, settle_windows=0)
    # Throughput grows with c: completions arrive faster at higher c.
    for c_expected in (1, 2, 3):
        assert t.current == c_expected
        feed(t, clock, 4, latency=1.0, tokens=50, dt=1.0 / t.current)
    assert t.current == 4
    feed(t, clock, 4, latency=1.0, tokens=50, dt=0.25)
    assert t.current == 4  # capped


def test_tuner_plateau_reverts_to_best():
    clock = FakeClock()
    t = ConcurrencyTuner(start=1, max_c=8, window=4, clock=clock, hold_windows=2, settle_windows=0)
    feed(t, clock, 4, 1.0, 50, 1.0)    # c=1: 50 tok/s
    assert t.current == 2
    feed(t, clock, 4, 1.0, 50, 0.5)    # c=2: 100 tok/s
    assert t.current == 3
    feed(t, clock, 4, 1.5, 50, 0.5)    # c=3: no gain
    assert t.current == 2
    assert any("plateau" in e for e in t.events)


def test_tuner_thermal_backoff():
    clock = FakeClock()
    t = ConcurrencyTuner(start=4, max_c=4, window=4, clock=clock, hold_windows=0, settle_windows=0)
    feed(t, clock, 4, 1.0, 50, 0.25)   # baseline at c=4
    assert t.current == 4
    feed(t, clock, 4, 2.5, 50, 0.6)    # latency > 2x baseline
    assert t.current == 2
    assert any("baseline" in e for e in t.events)


def test_tuner_oom_halves_and_caps():
    t = ConcurrencyTuner(start=8, max_c=8, clock=FakeClock())
    t.on_error(oom=True)
    assert t.current == 4 and t.max_c == 4
    t.on_error(oom=True)
    t.on_error(oom=True)
    t.on_error(oom=True)
    assert t.current == 1 and t.max_c == 1
    t2 = ConcurrencyTuner(start=6, max_c=8, clock=FakeClock())
    t2.on_error(oom=False)
    assert t2.current == 3 and t2.max_c == 8


def test_tuner_discards_transient_window_after_change():
    """RTX 3060 / NUM_PARALLEL=4: the first window at c=4 still contains c=3 completions and looked slower,
    so the tuner stopped at 3. The settle window is ignored; the steady state at c=4 wins."""
    clock = FakeClock()
    t = ConcurrencyTuner(start=3, max_c=8, window=4, clock=clock, hold_windows=2)
    feed(t, clock, 4, 1.0, 50, 1 / 3)      # c=3 steady: 150 tok/s (no change happened yet: evaluated)
    assert t.current == 4
    feed(t, clock, 4, 1.0, 50, 1 / 2.5)    # transient at c=4: looks like 125 tok/s -> discarded
    assert t.current == 4 and 4 not in t.tput
    feed(t, clock, 4, 1.0, 50, 1 / 4.5)    # steady c=4: 225 tok/s
    assert t.current == 5


def test_fit_counts_only_server_slots():
    from ald.registry import Stage
    st = Stage("label", {"model_ref": "m", "model_digest": "d", "ollama_version_range": ">=0",
                         "vram_gb_required": 10.0, "kv_gb_per_slot": 0.35})
    f = HardwareFit(usable_vram_gb=12.0, ram_gb=16, accel="cuda")
    assert f.max_concurrency(st, 8) == 5          # every request counted as a KV slot
    f.server_slots = 4
    assert f.max_concurrency(st, 8) == 8          # beyond 4 they queue in Ollama: no extra VRAM
    f.server_slots = 8
    assert f.max_concurrency(st, 8) == 5


# --- timing ------------------------------------------------------------------------

def test_rate_ewma():
    r = RateTracker(alpha=0.5)
    assert r.rate("screen") is None
    r.update("screen", 10, 10)
    assert r.rate("screen") == 1.0
    r.update("screen", 30, 10)
    assert r.rate("screen") == 2.0
    assert r.eta_seconds("screen", 100) == 50


@pytest.mark.parametrize("rate,expected", [(None, 1), (0.1, 1), (1.0, 1), (2.0, 1), (3.4, 2), (5.0, 3), (50, 4)])
def test_lease_size_targets_half_ttl(rate, expected):
    assert lease_size(rate, passages_per_job=500, ttl_s=600, target_frac=0.5, cap=4) == expected


def test_should_prefetch():
    assert should_prefetch(0.5, None)
    assert not should_prefetch(0.2, 1000)
    assert should_prefetch(0.1, 60)


def test_run_window_hours():
    clock = FakeClock()
    w = RunWindow.from_args(None, 2.0, clock)
    assert w.allow_new_lease(3600)
    clock.advance(3600)
    assert not w.allow_new_lease(3600)  # would overrun (margin 1.1)
    assert w.allow_new_lease(1800)
    clock.advance(3601)
    assert w.expired() and not w.allow_new_lease(None)


def test_run_window_until_wraps_to_tomorrow():
    clock = FakeClock()
    now = dt.datetime.fromtimestamp(clock.time())
    past = (now - dt.timedelta(hours=1)).strftime("%H:%M")
    w = RunWindow.from_args(past, None, clock)
    assert 22 * 3600 < w.remaining() <= 24 * 3600
    with pytest.raises(ValueError):
        RunWindow.from_args("25:00", None, clock)


def test_no_window():
    w = RunWindow(None, FakeClock())
    assert w.allow_new_lease(10 ** 9) and not w.expired()


def test_backoff_grows_with_jitter():
    import random
    b = Backoff(base=2, cap=60, rng=random.Random(1))
    xs = [b.next() for _ in range(8)]
    assert all(0 < x <= 60 for x in xs)
    assert xs[5] > xs[0]
    b.reset()
    assert b.next() <= 2
