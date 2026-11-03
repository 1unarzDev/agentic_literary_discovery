"""Check the research platform's ALD compat API (https://research.lunarz.dev/p/ald) with throwaway test workers.

Discovery-only TEST campaign "wtest" (ids wtest_compat_<stamp>_*), throwaway pin, synthetic passages; no GPU.
The test workers live in memory only (no config files are written). Tokens are read from
~/.config/research-cluster/ald-*.token and never printed.

  uv run --project ald python -I pipeline/platform_compat_check.py
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import secrets
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ald/src"))
import httpx  # noqa: E402

from ald.client import CoordinatorClient, CoordinatorError  # noqa: E402

sys.path.insert(0, str(ROOT))
from pipeline.platform_jobs import check_jobs  # noqa: E402

PLATFORM = "https://research.lunarz.dev"
ALD = f"{PLATFORM}/p/ald"
TOK = Path.home() / ".config/research-cluster"
results: list[tuple[str, bool, str]] = []


def tok(name: str) -> str:
    return (TOK / f"ald-{name}.token").read_text().strip()


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))


def gz_lines(rows: list[dict]) -> bytes:
    return gzip.compress("".join(json.dumps(r) + "\n" for r in rows).encode(), mtime=0)


def main() -> None:
    stamp = time.strftime("%m%d%H%M%S")
    sub = httpx.Client(base_url=PLATFORM, timeout=60, headers={"Authorization": f"Bearer {tok('submitter')}"})
    adm = httpx.Client(base_url=ALD, timeout=60, headers={"Authorization": f"Bearer {tok('admin')}"})

    ping = httpx.get(f"{ALD}/v1/ping", timeout=30).json()
    check("ping: ok + project ald", ping.get("ok") and ping.get("project") == "ald", f"sealed_recipient={ping.get('sealed_recipient')}")

    # ---- test input, pin, jobs (discovery only)
    passages = [{"passage_id": f"wtest_{stamp}_p{i}", "work_id": "wtest", "decade": 1850, "stratum": "random",
                 "text": f"Synthetic test passage {i}.", "ctx_before": "", "ctx_after": ""} for i in range(6)]
    shard = gz_lines(passages)
    sha = hashlib.sha256(shard).hexdigest()
    r = sub.put(f"/v1/projects/ald/inputs/{sha}", content=shard)
    check("input upload", r.status_code in (200, 201), str(r.status_code))
    pin_hash = secrets.token_hex(32)
    digest = "sha256:" + secrets.token_hex(32)
    r = sub.post("/v1/projects/ald/pins", json={"pin_hash": pin_hash, "model_digest": digest, "model_ref": "wtest:compat"})
    check("pin register", r.status_code in (200, 201), str(r.status_code))
    ids = {"a": f"wtest_compat_{stamp}_a", "t1": f"wtest_compat_{stamp}_t1", "t2": f"wtest_compat_{stamp}_t2"}

    def job(jid: str, twin: bool) -> dict:
        return {"schema": "rc-job/1", "job_id": jid, "kind": "ald-shard",
                "purpose": "ALD compat-API test (synthetic passages, test campaign; safe to ignore).",
                "est_seconds": 30, "submitter": "fiction-obstacles-research-plan", "campaign": "wtest",
                "priority_class": "background", "priority": 1, "needs": {"gpu": False}, "preemptible": True,
                **({"anti_affinity": {"keys": [f"dup:wtest_{stamp}"], "scope": "worker"}} if twin else {}),
                "pin": {"pin_hash": pin_hash}, "inputs": [{"name": "shard", "sha256": sha, "size": len(shard)}],
                "items": {"count": len(passages), "id_field": "passage_id"},
                "spec": {"stage": "label", "wave": "wtest", "split": "discovery"}, "outputs": {"class": "summary"}}

    batch = [job(ids["a"], False), job(ids["t1"], True), job(ids["t2"], True)]
    check_jobs(batch)
    r = sub.post("/v1/projects/ald/jobs", json={"jobs": batch})
    check("jobs submit", r.status_code in (200, 201), f"{r.status_code} {r.text[:120]}")

    # ---- two throwaway workers (memory only)
    workers = []
    for n in (1, 2):
        inv = adm.post("/v1/admin/invite").json()["invite"]
        w = CoordinatorClient(ALD).join(inv, {"name": f"wtest-compat-{stamp}-{n}", "os": "linux", "arch": "x86_64",
                                              "gpu": "none", "vram_gb": 16.0, "ram_gb": 32.0, "tier": "t16"})
        workers.append((w["worker_id"], CoordinatorClient(ALD, w["token"])))
    check("join x2 via admin invite", len(workers) == 2)
    (_w1, c1), (_w2, c2) = workers

    def lease(c: CoordinatorClient, n: int) -> list[dict]:
        return [j for j in c.lease("t16", ["label"], n) if j["job_id"].startswith(f"wtest_compat_{stamp}")]

    got1 = lease(c1, 3)
    mine1 = {j["job_id"] for j in got1}
    check("lease: worker 1 gets job a and exactly ONE twin", ids["a"] in mine1 and len(mine1 & {ids["t1"], ids["t2"]}) == 1,
          ",".join(sorted(mine1)))
    check("lease: directive + split fields present", all("split" in j for j in got1) and c1.last_directive is not None,
          f"directive={c1.last_directive}")
    ja = next(j for j in got1 if j["job_id"] == ids["a"])
    dest = Path("/tmp") / f"wtest_compat_{stamp}.jsonl.gz"
    c1.download_shard(ja, dest)
    check("shard download (holder) matches input", hashlib.sha256(dest.read_bytes()).hexdigest() == sha)
    dest.unlink(missing_ok=True)
    try:
        c2.download_shard(ja, Path("/tmp") / f"wtest_compat_{stamp}_x")
        check("shard: non-holder refused", False)
    except CoordinatorError as e:
        check("shard: non-holder refused", e.status == 403, str(e.status))

    def lines(pids):
        return gz_lines([{"passage_id": p, "stage": "label", "pin_hash": pin_hash, "model_digest": digest,
                          "output": {"has_obstacle": "no", "confidence": 0.9}, "valid_schema": True} for p in pids])

    def put(c, jid, body, partial=False, pin=pin_hash):
        h = {"X-Content-Sha256": hashlib.sha256(body).hexdigest(), "X-Pin-Hash": pin, "X-Model-Digest": digest,
             "X-Backend-Version": "test", "X-Stats": json.dumps({"n_ok": 2, "n_flagged": 0, "wall_s": 1})}
        return c.put_result(jid, body, h, partial=partial)

    pids = [p["passage_id"] for p in passages]
    try:
        put(c1, ids["a"], lines(pids[:2]), pin="f" * 64)
        check("412 on wrong pin", False)
    except CoordinatorError as e:
        check("412 on wrong pin", e.status == 412, str(e.status))
    r = put(c1, ids["a"], lines(pids[:2]), partial=True)
    check("partial upload stored", r.get("status") == "stored", json.dumps(r)[:100])
    c1.release([ids["a"]])
    again = [j for j in lease(c1, 3) if j["job_id"] == ids["a"]]
    skip = set((again[0] if again else {}).get("skip_passage_ids") or [])
    check("re-lease carries skip_passage_ids of the partial", skip == set(pids[:2]), f"{len(skip)} ids")
    full = lines(pids)
    r = put(c1, ids["a"], full)
    check("full upload stored", r.get("status") == "stored", r.get("status"))
    r = put(c1, ids["a"], full)
    check("same bytes again -> duplicate", r.get("status") in ("duplicate", "late_duplicate"), r.get("status"))
    try:
        put(c2, ids["a"], full)
        check("403 for a worker that never leased the job", False)
    except CoordinatorError as e:
        check("403 for a worker that never leased the job", e.status == 403, str(e.status))

    # dup twins: the other twin goes to worker 2, never to worker 1
    other = ({ids["t1"], ids["t2"]} - mine1).pop()
    l1 = {j["job_id"] for j in lease(c1, 3)}
    check("twin anti-affinity: worker 1 never gets the second twin", other not in l1, ",".join(sorted(l1)) or "-")
    l2 = {j["job_id"] for j in lease(c2, 3)}
    check("twin goes to worker 2", other in l2, ",".join(sorted(l2)) or "-")
    hb = c2.heartbeat(list(l2), {"tok_s": 0})
    check("heartbeat extends + carries directive", other in (hb.get("extended") or []) and "directive" in hb, json.dumps(hb)[:120])
    c1.release(list(l1 | (mine1 - {ids["a"]})))
    c2.release(list(l2))

    n_ok = sum(ok for _n, ok, _d in results)
    print(f"\n{n_ok}/{len(results)} checks passed; test workers: {[w for w, _c in workers]} (campaign wtest)")
    sys.exit(0 if n_ok == len(results) else 1)


if __name__ == "__main__":
    main()
