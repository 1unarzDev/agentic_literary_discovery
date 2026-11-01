"""``ald doctor --bench``: the real stage prompt on bundled sample passages."""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from importlib import resources
from typing import Any, Callable

from .backend.ollama import BackendError, OllamaBackend
from .inference import run_passage
from .registry import Registry, Stage
from .scheduler import DEFAULT_PASSAGES_PER_JOB

LEVELS = (1, 4, 8)


def sample_passages() -> list[dict[str, Any]]:
    text = resources.files("ald.data").joinpath("sample_passages.jsonl").read_text(encoding="utf-8")
    return [json.loads(l) for l in text.splitlines() if l.strip()]


def bench_level(backend: OllamaBackend, stage: Stage, passages: list[dict[str, Any]], concurrency: int,
                seconds: float, *, digest: str, backend_version: str) -> dict[str, Any]:
    done = 0
    gen = 0
    prompt = 0
    lat: list[float] = []
    valid = 0
    errors = 0
    i = 0
    t0 = time.perf_counter()
    deadline = t0 + seconds
    lock = threading.Lock()

    def one(p: dict[str, Any]) -> dict[str, Any]:
        return run_passage(backend, stage, p, pin_hash=stage.pin_hash(digest), model_digest=digest,
                           backend_version=backend_version)

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        inflight = set()
        while True:
            now = time.perf_counter()
            while len(inflight) < concurrency and now < deadline:
                inflight.add(ex.submit(one, passages[i % len(passages)]))
                i += 1
            if not inflight:
                break
            finished, inflight = wait(inflight, timeout=max(0.1, deadline - now) if now < deadline else None,
                                      return_when=FIRST_COMPLETED)
            for f in finished:
                try:
                    line = f.result()
                except BackendError:
                    errors += 1
                    continue
                with lock:
                    done += 1
                    gen += line["gen_tokens"]
                    prompt += line["prompt_tokens"]
                    lat.append(line["latency_ms"] / 1000)
                    valid += bool(line["valid_schema"])
            if time.perf_counter() >= deadline and not inflight:
                break
    wall = max(time.perf_counter() - t0, 1e-6)
    return {
        "concurrency": concurrency,
        "passages": done,
        "wall_s": round(wall, 2),
        "tok_s": round(gen / wall, 1),
        "passages_per_hour": round(done / wall * 3600, 0),
        "mean_latency_s": round(sum(lat) / len(lat), 2) if lat else None,
        "valid_rate": round(valid / done, 3) if done else None,
        "prompt_tokens_mean": round(prompt / done, 0) if done else None,
        "errors": errors,
    }


def run_bench(backend: OllamaBackend, registry: Registry, stages: list[str], *, total_seconds: float = 60.0,
              levels: tuple[int, ...] = LEVELS, accel: str | None = None,
              log: Callable[[str], None] = print) -> dict[str, Any]:
    passages = sample_passages()
    runnable = []
    for s in stages:
        st = registry.stages[s]
        d = backend.local_digest(st.model_ref)
        if d is None:
            log(f"[bench] {s}: model {st.model_ref} not pulled; run `ald setup` first. Skipping.")
            continue
        runnable.append((st, d))
    out: dict[str, Any] = {}
    if not runnable:
        return out
    per = total_seconds / (len(runnable) * len(levels))
    bv = backend.backend_version(accel)
    gpu = accel not in (None, "cpu")
    for st, d in runnable:
        if gpu:
            # A second resident model splits this one onto the CPU (~8x slower).
            gone = backend.unload_others({st.model_ref})
            if gone:
                log(f"[bench] unloaded resident model(s): {', '.join(gone)}")
        log(f"[bench] {st.name}: loading {st.model_ref} ...")
        try:
            run_passage(backend, st, passages[0], pin_hash="warmup", model_digest=d, backend_version=bv)
        except BackendError as e:
            log(f"[bench] {st.name}: warm-up failed: {e}")
            out[st.name] = {"error": str(e)}
            continue
        frac = backend.residency(st.model_ref) if gpu else None
        if frac is not None and frac < 0.99:
            log(f"[bench] WARNING: {st.model_ref} is only {frac:.0%} on GPU (rest on CPU); "
                f"results will be slow. Close other GPU apps / models and re-run.")
        res = []
        for c in levels:
            log(f"[bench] {st.name}: concurrency {c} for {per:.0f}s")
            res.append(bench_level(backend, st, passages, c, per, digest=d, backend_version=bv))
        best = max(res, key=lambda r: r["passages_per_hour"])
        out[st.name] = {"levels": res, "best_concurrency": best["concurrency"],
                        "passages_per_hour": best["passages_per_hour"], "tok_s": best["tok_s"],
                        "gpu_fraction": None if frac is None else round(frac, 3)}
    return out


def eta_for_share(status: dict[str, Any] | None, stage: str, my_pph: float | None, tier: str | None = None,
                  passages_per_job: int = DEFAULT_PASSAGES_PER_JOB) -> dict[str, Any]:
    """This worker's share of the remaining queue for ``stage``: remaining
    passages split evenly across workers active in the last hour (+ us)."""
    if not status or not my_pph:
        return {"eta_hours": None}
    q = (status.get("queue") or {}).get(stage) or {}
    remaining_jobs = int(q.get("queued", 0)) + int(q.get("leased", 0))
    remaining = remaining_jobs * passages_per_job
    workers = status.get("workers") or []
    active = [w for w in workers if (w.get("passages_1h") or 0) > 0]
    n = max(1, len(active) + 1)
    share = remaining / n
    return {"remaining_jobs": remaining_jobs, "remaining_passages": remaining, "active_workers": len(active),
            "my_share_passages": int(share), "eta_hours": round(share / my_pph, 1) if my_pph else None,
            "fleet_eta_hours": (status.get("eta_hours") or {}).get(stage)}
