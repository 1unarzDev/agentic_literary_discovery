"""Build shards + jobs from data/work/{works,passages}.parquet and push them to the coordinator.

Admin config (NOT in repo): ~/.config/ald-admin.json  {"url": "...", "admin_token": "..."}

usage:
  uv run python -I pipeline/make_jobs.py plan              # print wave plan, write shards locally
  uv run python -I pipeline/make_jobs.py push [--waves 0,1]  # upload registry, pins, shards, jobs
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "data/work"
SHARDS = WORK / "shards"
SEED = 20261031
SHARD_SIZE = {"workcheck": 200, "label": 400, "alt_label": 400, "cloze": 500}
DUP_RATE = 0.05


def admin() -> tuple[str, dict]:
    cfg = json.loads((Path.home() / ".config/ald-admin.json").read_text())
    return cfg["url"].rstrip("/"), {"Authorization": f"Bearer {cfg['admin_token']}"}


def registry() -> dict:
    return json.loads((ROOT / "registry/models.v1.json").read_text(encoding="utf-8"))


def canon(o) -> str:
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def pin_for(stage: str, reg: dict) -> dict:
    """Must match ald.registry hashing: prompt_hash = sha256(canon{template, codebook_version, schema, options})."""
    s = reg["stages"][stage]
    sys.path.insert(0, str(ROOT / "ald/src"))
    from ald.registry import compute_pin  # single source of truth for hashing
    return compute_pin(stage, s)


# ---------------------------------------------------------------- item builders
def workcheck_items(works: pd.DataFrame) -> list[dict]:
    items = []
    for r in works.itertuples():
        t = (WORK / "clean" / f"{r.pg_id}.txt").read_text(encoding="utf-8")
        words = t.split()
        # skip probable front matter: start at first paragraph after 300 words if a 'CHAPTER' marker exists
        m = re.search(r"\n\s*(CHAPTER|Chapter|BOOK|Book|PART|I\.)\s", t[:40000])
        start = len(t[: m.start()].split()) if m else 0
        txt = " ".join(words[start:start + 1500])
        items.append({"passage_id": f"{r.work_id}_wc", "work_id": r.work_id, "decade": int(r.decade),
                      "stratum": "workcheck", "text": txt, "ctx_before": "", "ctx_after": "",
                      "subjects": str(r.Subjects)[:400], "split": r.split,
                      "text_sha256": hashlib.sha256(txt.encode()).hexdigest()})
    return items


NAME_RE = re.compile(r"(?<![.!?\"“]\s)(?<!^)\b([A-Z][a-z]{2,})\b")
STOP = set("The This That There Then When What Where Which While With Without Mrs Miss Lady Lord Sir Mister Madame Monsieur God Heaven Christmas Sunday Monday Tuesday Wednesday Thursday Friday Saturday January February March April June July August September October November December English London Paris France England America Chapter".split())


def cloze_items(works: pd.DataFrame, per_work: int = 3) -> list[dict]:
    items = []
    for r in works.itertuples():
        t = (WORK / "clean" / f"{r.pg_id}.txt").read_text(encoding="utf-8")
        cnt = Counter(m.group(1) for m in NAME_RE.finditer(t) if m.group(1) not in STOP)
        names = [n for n, c in cnt.most_common(30) if c >= 15]
        rng = np.random.default_rng(int(hashlib.sha256(f"{SEED}:cloze:{r.work_id}".encode()).hexdigest()[:12], 16))
        sents = [s for s in re.split(r"(?<=[.!?])\s+", t) if 15 <= len(s.split()) <= 60]
        cands = [s for s in sents if sum(1 for n in names if re.search(rf"\b{n}\b", s)) == 1]
        if not cands:
            continue
        for j in rng.choice(len(cands), size=min(per_work, len(cands)), replace=False):
            s = cands[j]
            n = next(n for n in names if re.search(rf"\b{n}\b", s))
            masked = re.sub(rf"\b{n}\b", "[MASK]", s)
            items.append({"passage_id": f"{r.work_id}_cz{j}", "work_id": r.work_id, "decade": int(r.decade),
                          "stratum": "cloze", "text": masked, "ctx_before": "", "ctx_after": "",
                          "answer_sha256": hashlib.sha256(n.encode()).hexdigest(), "split": r.split,
                          "text_sha256": hashlib.sha256(masked.encode()).hexdigest()})
    return items


# ---------------------------------------------------------------- waves (streamed via DuckDB; never loads all text)
import duckdb  # noqa: E402

PCOLS = "passage_id, work_id, decade, stratum, text, ctx_before, ctx_after, text_sha256, split"
LABEL_WAVES = [  # (wave, split, predicate on ranked passages, priority)
    ("w01_disc_rand_a", "discovery", "stratum='random' AND k < 12", 20),
    ("w02_conf_rand_a", "confirmation", "stratum='random' AND k < 12", 21),
    ("w03_disc_enrich", "discovery", "stratum<>'random'", 22),
    ("w04_conf_enrich", "confirmation", "stratum<>'random'", 23),
    ("w05_disc_rand_b", "discovery", "stratum='random' AND k >= 12", 24),
    ("w06_conf_rand_b", "confirmation", "stratum='random' AND k >= 12", 25),
]


def ranked_view(con, exclude_works: set[str]) -> None:
    con.execute(f"""CREATE OR REPLACE TEMP VIEW ranked AS
        SELECT *, row_number() OVER (PARTITION BY work_id, stratum='random'
                                     ORDER BY hash(passage_id || '{SEED}')) - 1 AS k
        FROM read_parquet('{WORK / "passages.parquet"}')""")
    con.execute("CREATE OR REPLACE TEMP TABLE excluded(work_id VARCHAR)")
    if exclude_works:
        con.executemany("INSERT INTO excluded VALUES (?)", [(w,) for w in exclude_works])


def write_shards(wave: str, stage: str, priority: int, rows_iter, split: str) -> list[dict]:
    rng = np.random.default_rng(int(hashlib.sha256(f"{SEED}:{wave}:{split}".encode()).hexdigest()[:12], 16))
    size = SHARD_SIZE[stage]
    jobs, chunk, n = [], [], 0
    def flush():
        nonlocal chunk, n
        if not chunk:
            return
        sid = f"{wave}_{split[:4]}_{n:05d}"
        path = SHARDS / wave / f"{sid}.jsonl.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as g:
            for it in chunk:
                g.write((json.dumps({k: v for k, v in it.items() if k != "split"}, ensure_ascii=False) + "\n").encode())
        path.write_bytes(buf.getvalue())
        dup = f"dup_{sid}" if rng.random() < DUP_RATE else None
        base = {"stage": stage, "wave": wave, "shard_key": f"shards/{wave}/{sid}.jsonl.gz", "n_passages": len(chunk),
                "split": split, "priority": priority, "dup_group": dup, "local": str(path),
                "decades": sorted({int(i["decade"]) for i in chunk})}
        jobs.append({**base, "job_id": sid})
        if dup:
            jobs.append({**base, "job_id": sid + "_dup"})
        chunk, n = [], n + 1
    for it in rows_iter:
        chunk.append(it)
        if len(chunk) >= size:
            flush()
    flush()
    return jobs


def iter_query(con, sql: str, batch: int = 2000):
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    while True:
        rows = cur.fetchmany(batch)
        if not rows:
            return
        for r in rows:
            d = dict(zip(cols, r))
            d["decade"] = int(d["decade"])
            yield d


def build_jobs(works: pd.DataFrame, waves: set[str] | None, exclude_works: set[str]) -> list[dict]:
    con = duckdb.connect()
    con.execute("SET memory_limit='4GB'; SET threads=8")
    ranked_view(con, exclude_works)
    alljobs = []
    def want(w):
        return waves is None or w in waves or w[:3] in waves
    if want("w00_workcheck"):
        items = workcheck_items(works)
        for split in ("discovery", "confirmation"):
            alljobs += write_shards("w00_workcheck", "workcheck", 10, (i for i in items if i["split"] == split), split)
    for wave, split, pred, prio in LABEL_WAVES:
        if not want(wave):
            continue
        sql = (f"SELECT {PCOLS} FROM ranked WHERE split='{split}' AND ({pred}) "
               f"AND work_id NOT IN (SELECT work_id FROM excluded) ORDER BY hash(passage_id || '{wave}')")
        alljobs += write_shards(wave, "label", prio, iter_query(con, sql), split)
    if want("w07_cloze"):
        items = cloze_items(works[~works.work_id.isin(exclude_works)])
        for split in ("discovery", "confirmation"):
            alljobs += write_shards("w07_cloze", "cloze", 30, (i for i in items if i["split"] == split), split)
    if want("w08_alt_label"):
        sql = (f"SELECT {PCOLS} FROM ranked WHERE split='discovery' AND stratum='random' AND k < 12 "
               f"AND work_id NOT IN (SELECT work_id FROM excluded) AND hash(passage_id || 'alt') % 10 = 0 "
               f"ORDER BY hash(passage_id || 'w08')")
        alljobs += write_shards("w08_alt_label", "alt_label", 40, iter_query(con, sql), "discovery")
    return alljobs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["plan", "push"])
    ap.add_argument("--waves", default="")
    ap.add_argument("--exclude-from-workcheck", default="", help="parquet with work_id, keep")
    a = ap.parse_args()
    works = pd.read_parquet(WORK / "works.parquet")
    works = works[works.decade.between(1800, 1920)]
    sel = set(a.waves.split(",")) if a.waves else None
    excl: set[str] = set()
    if a.exclude_from_workcheck:
        wc = pd.read_parquet(a.exclude_from_workcheck)  # columns: work_id, keep(bool)
        excl = set(wc.loc[~wc.keep, "work_id"])
        print("excluding", len(excl), "works failing workcheck")
    alljobs = build_jobs(works, sel, excl)
    for (wave, stage), g in pd.DataFrame(alljobs).groupby(["wave", "stage"]):
        print(f"{wave:18s} stage={stage:9s} passages={int(g.n_passages.sum()):7d} jobs={len(g):5d}")
    (WORK / "jobs_plan.json").write_text(json.dumps(alljobs), encoding="utf-8")
    if a.cmd == "plan":
        return
    url, h = admin()
    reg = registry()
    with httpx.Client(timeout=120, headers=h) as c:
        c.put(f"{url}/v1/admin/registry", content=json.dumps(reg).encode(), headers={"Content-Type": "application/json"}).raise_for_status()
        pins = {}
        for stage in {j["stage"] for j in alljobs}:
            pin = pin_for(stage, reg)
            c.post(f"{url}/v1/admin/pin", json=pin).raise_for_status()
            pins[stage] = pin["pin_hash"]
        uploaded = set()
        for j in alljobs:
            if j["shard_key"] in uploaded:
                continue
            wave, sid = j["wave"], Path(j["shard_key"]).name.replace(".jsonl.gz", "")
            c.put(f"{url}/v1/admin/shard/{wave}/{sid}", content=Path(j["local"]).read_bytes(),
                  headers={"X-Split": j["split"], "X-N-Passages": str(j["n_passages"]),
                           "X-Decades": ",".join(map(str, j["decades"]))}).raise_for_status()
            uploaded.add(j["shard_key"])
        for i in range(0, len(alljobs), 500):
            batch = [{k: j[k] for k in ("job_id", "stage", "wave", "shard_key", "n_passages", "split", "dup_group", "priority")}
                     | {"pin_hash": pins[j["stage"]]} for j in alljobs[i:i + 500]]
            c.post(f"{url}/v1/admin/jobs", json={"jobs": batch}).raise_for_status()
    print("pushed", len(alljobs), "jobs")


if __name__ == "__main__":
    main()
