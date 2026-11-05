"""Re-shard the remaining QUEUED jobs of a wave down to passages the registered analysis needs.

Needed = split_v2 == 'confirmation' (or the wave's split) AND primary_v2_capv2 (registered primary set).
Reads only job membership (shard files + queued job ids), never results (sealed-safe).

usage:
  uv run --project ald --with pandas,duckdb,numpy,pyarrow python -I pipeline/reshard_primary.py \
      --wave v09b_w02_conf_rand_a --new-wave v09b_w02p_conf_primary --split confirmation --priority 9 [--push]
"""
from __future__ import annotations

import argparse
import gzip
import json
import subprocess
import sys
from pathlib import Path

import duckdb
import httpx
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
import make_jobs as mj  # noqa: E402  (write_shards, admin, registry, pin_for)


def queued_jobs(wave: str) -> list[str]:
    out = subprocess.run(["npx", "wrangler", "d1", "execute", "ald-coordinator", "--remote", "--json", "--command",
                          f"SELECT job_id FROM jobs WHERE wave='{wave}' AND status='queued'"],
                         cwd=ROOT / "coordinator", capture_output=True, text=True, check=True).stdout
    return [r["job_id"] for r in json.loads(out)[0]["results"]]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wave", required=True)
    ap.add_argument("--new-wave", required=True)
    ap.add_argument("--split", default="confirmation")
    ap.add_argument("--priority", type=int, default=9)
    ap.add_argument("--stage", default="label")
    ap.add_argument("--push", action="store_true")
    a = ap.parse_args()

    q = queued_jobs(a.wave)
    rows = []
    for j in q:
        if j.endswith("_dup"):
            continue  # twins re-created by write_shards
        for line in gzip.open(ROOT / "data/work/shards" / a.wave / f"{j}.jsonl.gz", "rt", encoding="utf-8"):
            rows.append(json.loads(line))
    items = pd.DataFrame(rows).drop_duplicates("passage_id")
    w = pd.read_parquet(ROOT / "data/work/works_v2.parquet")
    col = "primary_v2_capv2" if "primary_v2_capv2" in w.columns else "primary_v2"
    keep = set(w.loc[(w.split_v2 == a.split) & (w[col] == True), "work_id"])  # noqa: E712
    need = items[items.work_id.isin(keep)].copy()
    need["split"] = a.split
    print(f"queued jobs {len(q)} | unique passages {len(items)} | needed {len(need)} ({len(need)/len(items):.0%})")

    need = need.sample(frac=1, random_state=mj.SEED)  # shuffle across decades
    jobs = mj.write_shards(a.new_wave, a.stage, a.priority, need.to_dict("records"), a.split)
    print(f"new wave {a.new_wave}: {len(jobs)} jobs ({sum(j['n_passages'] for j in jobs)} passages incl. twins)")
    if not a.push:
        return
    url, h = mj.admin()
    reg = mj.registry()
    pin = mj.pin_for(a.stage, reg)["pin_hash"]
    with httpx.Client(timeout=120, headers=h) as c:
        for j in jobs:
            if j["job_id"].endswith("_dup"):
                continue
            sid = Path(j["shard_key"]).name.replace(".jsonl.gz", "")
            c.put(f"{url}/v1/admin/shard/{a.new_wave}/{sid}", content=Path(j["local"]).read_bytes(),
                  headers={"X-Split": a.split, "X-N-Passages": str(j["n_passages"]),
                           "X-Decades": ",".join(map(str, j["decades"]))}).raise_for_status()
        for i in range(0, len(jobs), 500):
            batch = [{k: j[k] for k in ("job_id", "stage", "wave", "shard_key", "n_passages", "split", "dup_group", "priority")}
                     | {"pin_hash": pin} for j in jobs[i:i + 500]]
            c.post(f"{url}/v1/admin/jobs", json={"jobs": batch}).raise_for_status()
        # only after the new jobs exist: close the old queued ones (leased ones finish normally)
        closed = 0
        for i in range(0, len(q), 400):
            r = c.post(f"{url}/v1/admin/close_jobs", json={"job_ids": q[i:i + 400]})
            r.raise_for_status()
            closed += len(r.json().get("closed", []))
    print(f"pushed {len(jobs)} new jobs; closed {closed} old queued jobs")


if __name__ == "__main__":
    main()
