"""Does the worker's ConcurrencyTuner converge near the best concurrency on this machine?

Runs the real stage prompt on the bundled sample passages against the local Ollama, with exactly the
scheduling the worker uses (in-flight requests = tuner.current, tuner.observe(latency, gen_tokens) per
completion), starting from --start. Prints the concurrency trajectory and the throughput per level.

  python tune_check.py --registry models.v1.json --stage label --passages 160 --start 1 --max 8

(Linux box shared with another study: run it under `flock /tmp/aacv_gpu.lock ...`.)
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from ald.backend.ollama import OllamaBackend
from ald.bench import sample_passages
from ald.inference import run_passage
from ald.registry import Registry
from ald.scheduler import ConcurrencyTuner


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", required=True)
    ap.add_argument("--stage", default="label")
    ap.add_argument("--passages", type=int, default=160)
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--max", type=int, default=8)
    ap.add_argument("--ollama", default="http://127.0.0.1:11434")
    ap.add_argument("--unload-after", action="store_true", help="unload the model at the end")
    a = ap.parse_args()
    reg = Registry.from_dict(json.loads(Path(a.registry).read_text(encoding="utf-8")))
    st = reg.stages[a.stage]
    be = OllamaBackend(a.ollama)
    digest = be.local_digest(st.model_ref)
    bv = be.backend_version("gpu")
    ps = sample_passages()
    tuner = ConcurrencyTuner(start=a.start, max_c=a.max)
    run_passage(be, st, ps[0], pin_hash="warmup", model_digest=digest, backend_version=bv)  # load
    frac = be.residency(st.model_ref)
    traj = []
    per_level = defaultdict(lambda: [0, 0.0])  # c -> [passages, busy wall seconds]
    t0 = time.perf_counter()
    last = t0
    done = submitted = 0
    with ThreadPoolExecutor(max_workers=a.max) as ex:
        inflight = {}
        while done < a.passages:
            while submitted < a.passages and len(inflight) < tuner.current:
                f = ex.submit(run_passage, be, st, ps[submitted % len(ps)], pin_hash="tune",
                              model_digest=digest, backend_version=bv)
                inflight[f] = tuner.current
                submitted += 1
            fin, _ = wait(list(inflight), return_when=FIRST_COMPLETED)
            now = time.perf_counter()
            for f in fin:
                inflight.pop(f)
                line = f.result()
                c = tuner.current
                per_level[c][0] += 1
                per_level[c][1] += now - last
                last = now
                tuner.observe(line["latency_ms"] / 1000.0, int(line.get("gen_tokens") or 0))
                done += 1
                traj.append(tuner.current)
    wall = time.perf_counter() - t0
    if a.unload_after:
        be.unload(st.model_ref)
    print(json.dumps({
        "stage": a.stage, "model": st.model_ref, "gpu_fraction": frac, "passages": done, "wall_s": round(wall, 1),
        "passages_per_hour_overall": round(done / wall * 3600),
        "final_concurrency": tuner.current,
        "tuner_tput_tok_s_by_c": {c: round(v, 1) for c, v in sorted(tuner.tput.items())},
        "passages_per_hour_by_c": {c: round(n / s * 3600) for c, (n, s) in sorted(per_level.items()) if s > 0},
        "completions_at_c": dict(sorted(Counter(traj).items())),
        "events": tuner.events,
        "trajectory": "".join(str(min(c, 9)) for c in traj),
    }, indent=1))


if __name__ == "__main__":
    main()
