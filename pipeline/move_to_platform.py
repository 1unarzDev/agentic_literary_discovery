"""Move queued DISCOVERY jobs from the Cloudflare coordinator to the research platform, one batch at a time.

Atomic per batch: the platform accepts the batch (all-or-nothing) BEFORE the same job ids are closed on
Cloudflare (`/v1/admin/close_jobs`). Confirmation never moves (owner key ceremony first). Kept on Cloudflare:
jobs with partial uploads (their skip-ids live there) and dup twins whose sibling is not also moving.
Resumable: data/work/platform_move/moved.jsonl. Tokens are read from files and never printed.

  uv run --project ald python -I pipeline/move_to_platform.py setup          # registry, release, installers, pins
  uv run --project ald python -I pipeline/move_to_platform.py move [--waves ...] [--limit N]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ald/src"))
sys.path.insert(0, str(ROOT))
import httpx  # noqa: E402

from pipeline.export_for_platform import R2, d1  # noqa: E402
from pipeline.platform_jobs import check_jobs, rc_job  # noqa: E402

PLATFORM = "https://research.lunarz.dev"
ALD = f"{PLATFORM}/p/ald"
TOK = Path.home() / ".config/research-cluster"
STATE = ROOT / "data/work/platform_move"
# Wave order = ALD-internal priority (lower first). All ALD jobs are class "background": strictly below crane.
WAVES = {"v09b_w01_disc_rand_a": 900, "v09b_w05_disc_rand_b": 910, "v09b_w08_alt_label": 920,
         "v09b_w09_baseline_small": 930, "v09b_w07_cloze": 940, "v09b_w03_disc_enrich": 950}
SEC_PER_PASSAGE = {"label": 1.8, "alt_label": 2.8, "baseline_small": 1.0, "cloze": 0.3}
PURPOSE = {"label": "Label obstacle features in ~400 Discovery-split passages with the frozen gemma4 v0.9 label pin.",
           "alt_label": "Second-model (qwen3.5 9B) labels for Discovery passages: model-robustness check.",
           "baseline_small": "Small-model (qwen3.5 4B) baseline labels for Discovery passages.",
           "cloze": "Cloze memorization probe on Discovery passages (does the model know the book?)."}


def tok(name: str) -> str:
    return (TOK / f"ald-{name}.token").read_text().strip()


def retry(fn, what: str, attempts: int = 6):
    """Transient platform edge errors (502/503/504, timeouts): back off and retry."""
    for i in range(attempts):
        try:
            r = fn()
            if r.status_code not in (429, 502, 503, 504):
                return r
        except httpx.TransportError:
            r = None
        time.sleep(min(60, 3 * 2 ** i))
    if r is None:
        raise SystemExit(f"{what}: unreachable")
    return r


def ok(r: httpx.Response) -> dict:
    if r.status_code >= 300:
        raise SystemExit(f"{r.request.method} {r.request.url.path} -> {r.status_code}: {r.text[:400]}")
    return r.json() if r.content else {}


def cf_admin() -> httpx.Client:
    c = json.loads((Path.home() / ".config/ald-admin.json").read_text())
    return httpx.Client(base_url=c["url"].rstrip("/"), timeout=120, headers={"Authorization": f"Bearer {c['admin_token']}"})


def setup() -> None:
    adm_ald = httpx.Client(base_url=ALD, timeout=120, headers={"Authorization": f"Bearer {tok('admin')}"})
    adm = httpx.Client(base_url=PLATFORM, timeout=300, headers={"Authorization": f"Bearer {tok('admin')}"})
    sub = httpx.Client(base_url=PLATFORM, timeout=120, headers={"Authorization": f"Bearer {tok('submitter')}"})
    reg = httpx.get("https://ald-coordinator.lunarzdev.workers.dev/v1/registry", timeout=60).content
    print("registry:", ok(adm_ald.put("/v1/admin/registry", content=reg, headers={"content-type": "application/json"})))
    import re
    ver = re.search(r'__version__\s*=\s*"([^"]+)"', (ROOT / "ald/src/ald/__init__.py").read_text()).group(1)
    whl = ROOT / f"ald/dist/ald-{ver}-py3-none-any.whl"
    r = adm.put(f"/v1/projects/ald/dist/{whl.name}", content=whl.read_bytes())
    print("wheel:", r.status_code, "(409 = already uploaded)" if r.status_code == 409 else "")
    print("release:", ok(adm.put("/v1/projects/ald/releases/ald", json={"version": ver, "min_version": "0.1.23", "file": whl.name})))
    for name in ("install.sh", "install.ps1"):
        body = (ROOT / "ald/install" / name).read_text().replace("__COORDINATOR_URL__", "__RC_BASE_URL__")
        print(name, adm.put(f"/v1/projects/ald/install/{name}", content=body.encode()).status_code)
    pins = d1("SELECT pin_hash, stage, model_ref, model_digest, prompt_hash, schema_hash, options_json FROM pins WHERE active = 1")
    for p in pins:
        r = sub.post("/v1/projects/ald/pins", json={"pin_hash": p["pin_hash"], "model_digest": p["model_digest"],
                                                     "model_ref": p["model_ref"], "prompt_hash": p["prompt_hash"],
                                                     "schema_hash": p["schema_hash"], "options": json.loads(p["options_json"])})
        print("pin", p["stage"], p["pin_hash"][:12], r.status_code)


def candidates(waves: list[str]) -> list[dict]:
    wl = ",".join(f"'{w}'" for w in waves)
    rows = d1(f"""SELECT j.job_id, j.stage, j.wave, j.split, j.shard_key, j.pin_hash, j.n_passages, j.dup_group, j.cell,
                         s.content_sha256 AS sha, s.size,
                         EXISTS(SELECT 1 FROM job_partials p WHERE p.job_id = j.job_id) AS has_partials,
                         (SELECT COUNT(*) FROM jobs t WHERE t.dup_group = j.dup_group AND t.job_id <> j.job_id
                             AND (t.status <> 'queued' OR t.split <> 'discovery'
                                  OR EXISTS(SELECT 1 FROM job_partials p2 WHERE p2.job_id = t.job_id))) AS twin_blocked
                    FROM jobs j JOIN shards s ON s.shard_key = j.shard_key
                   WHERE j.status = 'queued' AND j.split = 'discovery' AND j.wave IN ({wl})
                   ORDER BY j.wave, j.job_id""")
    return [r for r in rows if not r["has_partials"] and not (r["dup_group"] and r["twin_blocked"])]


def move(waves: list[str], limit: int, batch: int) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    moved_p = STATE / "moved.jsonl"
    done = {json.loads(l)["job_id"] for l in moved_p.read_text().splitlines()} if moved_p.exists() else set()
    sub = httpx.Client(base_url=PLATFORM, timeout=300, headers={"Authorization": f"Bearer {tok('submitter')}"})
    cf = cf_admin()
    r2 = R2()
    uploaded: set[str] = set()
    todo = [c for c in candidates(waves) if c["job_id"] not in done]
    if limit:
        todo = todo[:limit]
    # keep dup twins in the same batch
    groups: dict[str, list[dict]] = {}
    for c in todo:
        groups.setdefault(c["dup_group"] or c["job_id"], []).append(c)
    chunks, cur = [], []
    for g in groups.values():
        if cur and len(cur) + len(g) > batch:
            chunks.append(cur)
            cur = []
        cur += g
    if cur:
        chunks.append(cur)
    per_wave: dict[str, int] = {}
    for ch in chunks:
        jobs = []
        for c in ch:
            if c["sha"] not in uploaded:
                body = r2.get(c["shard_key"])
                if body is None or hashlib.sha256(body).hexdigest() != c["sha"]:
                    raise SystemExit(f"shard {c['shard_key']} missing or sha mismatch")
                r = retry(lambda: sub.put(f"/v1/projects/ald/inputs/{c['sha']}", content=body), "input upload")
                if r.status_code >= 300:
                    raise SystemExit(f"input upload {c['shard_key']}: {r.status_code} {r.text[:200]}")
                uploaded.add(c["sha"])
            jobs.append(rc_job(job_id=c["job_id"], stage=c["stage"], wave=c["wave"], split=c["split"],
                               pin_hash=c["pin_hash"], shard_sha256=c["sha"], shard_size=c["size"],
                               n_items=c["n_passages"], campaign=c["wave"], purpose=PURPOSE[c["stage"]],
                               est_seconds=int(c["n_passages"] * SEC_PER_PASSAGE[c["stage"]]),
                               dup_group=c["dup_group"], cell=c["cell"], priority=WAVES[c["wave"]],
                               vram_gb=10.0 if c["stage"] in ("label", "cloze") else (8.5 if c["stage"] == "alt_label" else 5.0),
                               seal_id=None))
        check_jobs(jobs)
        # all-or-nothing; ids are idempotent, so a retry after an unseen success returns "exists"
        res = ok(retry(lambda: sub.post("/v1/projects/ald/jobs", json={"jobs": jobs}), "submit"))
        ids = [j["job_id"] for j in jobs]
        closed = set(ok(retry(lambda: cf.post("/v1/admin/close_jobs", json={"job_ids": ids}), "close")).get("closed") or [])
        with open(moved_p, "a", encoding="utf-8") as f:
            for c in ch:
                f.write(json.dumps({"job_id": c["job_id"], "wave": c["wave"], "at": time.time(),
                                    "closed_on_cf": c["job_id"] in closed}) + "\n")
                per_wave[c["wave"]] = per_wave.get(c["wave"], 0) + 1
        raced = [i for i in ids if i not in closed]
        print(f"batch of {len(ids)} accepted by the platform ({len(res.get('jobs', []))}), closed on Cloudflare: "
              f"{len(closed)}" + (f"; NOT closed (finished/leased on CF meanwhile, dedup in sync): {raced}" if raced else ""),
              flush=True)
    print("moved per wave:", json.dumps(per_wave))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["setup", "move", "plan"])
    ap.add_argument("--waves", default=",".join(WAVES))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batch", type=int, default=100)
    a = ap.parse_args()
    waves = [w for w in a.waves.split(",") if w]
    if a.cmd == "setup":
        setup()
    elif a.cmd == "plan":
        c = candidates(waves)
        by: dict[str, int] = {}
        for x in c:
            by[x["wave"]] = by.get(x["wave"], 0) + 1
        print(json.dumps(by, indent=1), "total", len(c))
    else:
        move(waves, a.limit, a.batch)


if __name__ == "__main__":
    main()
