"""``ald work --gpu-lock``: flock(2) sharing of one GPU with other programs."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

import pytest

from ald.gpulock import GpuLock, parse_waiters
from conftest import make_passages

posix = pytest.mark.skipif(sys.platform == "win32", reason="flock is POSIX-only")
linux = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="/proc/locks is Linux-only")

PROC_LOCKS = """\
1: POSIX  ADVISORY  WRITE 900 00:25:111 0 EOF
29: FLOCK  ADVISORY  WRITE 334421 00:25:84393 0 EOF
29: -> FLOCK  ADVISORY  WRITE 334472 00:25:84393 0 EOF
29:  -> FLOCK  ADVISORY  WRITE 334473 00:25:84393 0 EOF
30: FLOCK  ADVISORY  WRITE 5 00:25:7 0 EOF
"""


def test_parse_waiters():
    assert parse_waiters(PROC_LOCKS, 84393) == 2
    assert parse_waiters(PROC_LOCKS, 7) == 0
    assert parse_waiters(PROC_LOCKS, 111) == 0  # POSIX lock with no waiters
    assert parse_waiters("", 1) == 0


def test_disabled_on_windows_and_without_path(tmp_path):
    logs = []
    lk = GpuLock(tmp_path / "l", platform="win32", log=logs.append)
    assert not lk.enabled and lk.acquire() and not lk.held and lk.waiters() is None
    assert any("not supported" in m for m in logs)
    assert not GpuLock(None).enabled


def _holder(path, seconds: float) -> subprocess.Popen:
    """Another process taking the lock with a blocking flock(LOCK_EX), like `flock PATH cmd`."""
    code = ("import fcntl,os,sys,time; fd=os.open(sys.argv[1],os.O_RDWR|os.O_CREAT); "
            "fcntl.flock(fd,fcntl.LOCK_EX); print('locked',flush=True); time.sleep(float(sys.argv[2]))")
    return subprocess.Popen([sys.executable, "-c", code, str(path), str(seconds)], stdout=subprocess.PIPE, text=True)


@posix
def test_acquire_waits_for_other_holder_and_stop_aborts(tmp_path):
    path = tmp_path / "gpu.lock"
    p = _holder(path, 30)
    assert p.stdout.readline().strip() == "locked"
    logs = []
    lk = GpuLock(path, log=logs.append, poll_s=0.05)
    stop = threading.Event()
    threading.Timer(0.3, stop.set).start()
    t0 = time.time()
    assert lk.acquire(stop) is False and not lk.held  # stopped while waiting
    assert time.time() - t0 >= 0.25 and any("waiting" in m for m in logs)
    p.kill()
    p.wait()
    assert lk.acquire() and lk.held
    lk.release()
    assert not lk.held


@linux
def test_waiters_detected_from_proc_locks(tmp_path):
    path = tmp_path / "gpu.lock"
    lk = GpuLock(path, poll_s=0.05)
    assert lk.acquire()
    assert lk.waiters() == 0
    p = _holder(path, 0)  # blocks in flock(LOCK_EX) behind us
    try:
        for _ in range(100):
            if lk.waiters():
                break
            time.sleep(0.05)
        assert lk.waiters() == 1
    finally:
        lk.release()
        assert p.stdout.readline().strip() == "locked"  # it got the lock once we released
        p.wait(timeout=10)


# --------------------------------------------------------------------------- worker integration

def _label_pin(env):
    return env.registry.stages["label"].pin_hash()


@posix
def test_worker_holds_lock_per_shard_and_unloads_when_idle(env, tmp_path):
    path = tmp_path / "gpu.lock"
    env.coord.add_job("job-a", "label", _label_pin(env), make_passages("a", 3))
    env.coord.add_job("job-b", "label", _label_pin(env), make_passages("b", 3))
    held_during_chat = []

    def on_chat(body, n):
        fd = os.open(path, os.O_RDWR)
        try:
            import fcntl
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                held_during_chat.append(False)
                fcntl.flock(fd, fcntl.LOCK_UN)
            except BlockingIOError:
                held_during_chat.append(True)
        finally:
            os.close(fd)

    env.ollama.on_chat = on_chat
    w = env.make_worker(gpu_lock=str(path))
    w.run()
    assert env.coord.state == {"job-a": "done", "job-b": "done"}
    assert held_during_chat and all(held_during_chat)  # inference only ever ran under the lock
    assert not w.gpu_lock.held  # released after each shard / at exit
    # Nobody was waiting, so the model stayed loaded between shards and was unloaded once idle.
    label_model = env.registry.stages["label"].model_ref
    assert env.ollama.unloads.count(label_model) == 1
    assert any("worker idle" in m for m in env.logs)


@posix
def test_worker_unloads_before_release_when_someone_waits(env, tmp_path, monkeypatch):
    path = tmp_path / "gpu.lock"
    env.coord.add_job("job-a", "label", _label_pin(env), make_passages("a", 2))
    w = env.make_worker(gpu_lock=str(path))
    order = []
    real_release = w.gpu_lock.release
    monkeypatch.setattr(w.gpu_lock, "waiters", lambda: 1)
    monkeypatch.setattr(w.gpu_lock, "release", lambda: (order.append("release"), real_release())[1])
    real_unload = w.backend.unload
    monkeypatch.setattr(w.backend, "unload", lambda m: (order.append(f"unload {m}"), real_unload(m))[1])
    w.run()
    label_model = env.registry.stages["label"].model_ref
    assert env.coord.state == {"job-a": "done"}
    assert order[:2] == [f"unload {label_model}", "release"]
    assert any("waiting for the GPU lock" in m for m in env.logs)


def test_no_gpu_lock_means_no_unloads(env):
    env.coord.add_job("job-a", "label", _label_pin(env), make_passages("a", 2))
    w = env.make_worker()
    w.run()
    assert env.coord.state == {"job-a": "done"}
    assert env.registry.stages["label"].model_ref not in env.ollama.unloads


@posix
def test_try_acquire_never_waits(tmp_path):
    path = tmp_path / "gpu.lock"
    p = _holder(path, 30)
    assert p.stdout.readline().strip() == "locked"
    lk = GpuLock(path)
    t0 = time.time()
    assert lk.try_acquire() is False and time.time() - t0 < 1
    p.kill()
    p.wait()
    assert lk.try_acquire() is True and lk.held
    lk.release()


@posix
def test_worker_waits_for_lock_before_leasing(env, tmp_path):
    """While another process holds the lock, the worker holds no lease."""
    path = tmp_path / "gpu.lock"
    env.coord.add_job("job-a", "label", _label_pin(env), make_passages("a", 2))
    p = _holder(path, 30)
    assert p.stdout.readline().strip() == "locked"
    w = env.make_worker(gpu_lock=str(path))
    w.gpu_lock.poll_s = 0.05
    t = threading.Thread(target=w.run)
    t.start()
    for _ in range(100):
        if w.activity == "waiting_gpu_lock":
            break
        time.sleep(0.02)
    time.sleep(0.2)
    assert w.activity == "waiting_gpu_lock" and env.coord.state == {"job-a": "queued"}
    p.kill()
    p.wait()
    t.join(timeout=20)
    assert env.coord.state == {"job-a": "done"} and not w.gpu_lock.held


@posix
def test_prefetched_job_handed_back_when_lock_taken(env, tmp_path, monkeypatch):
    path = tmp_path / "gpu.lock"
    env.coord.add_job("job-a", "label", _label_pin(env), make_passages("a", 2))
    w = env.make_worker(gpu_lock=str(path))
    w.startup()
    [hj] = w.lease_jobs()
    w._queue.clear()
    monkeypatch.setattr(w.gpu_lock, "try_acquire", lambda: False)
    assert w.run_job(hj) == "gpu_busy"
    assert env.coord.state == {"job-a": "queued"}


@posix
def test_update_applied_while_waiting_for_lock(env, tmp_path):
    path = tmp_path / "gpu.lock"
    p = _holder(path, 30)
    assert p.stdout.readline().strip() == "locked"
    env.coord.ping_resp.update({"latest_client_version": "99.0.0", "wheel_url": "http://coord.test/dist/x.whl"})
    w = env.make_worker(gpu_lock=str(path), auto_update=True)
    w.gpu_lock.poll_s = 0.01
    w.run()  # reexec is recorded (not performed) by the fixture, then the idle worker exits
    p.kill()
    p.wait()
    assert env.reexec_calls, env.logs[-5:]
