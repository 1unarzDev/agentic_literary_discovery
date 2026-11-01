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


# ---------------------------------------------------------------- waves
def build_waves(works: pd.DataFrame, passages: pd.DataFrame) -> list[dict]:
    """Return list of wave dicts: {wave, stage, split, priority, items}"""
    rng = np.random.default_rng(SEED)
    p = passages.copy()
    p["r"] = rng.random(len(p))
    rnd = p[p.stratum == "random"].sort_values("r")
    rnd["k"] = rnd.groupby("work_id").cumcount()
    enr = p[p.stratum != "random"]
    waves = [
        {"wave": "w00_workcheck", "stage": "workcheck", "items": workcheck_items(works), "priority": 10},
        {"wave": "w01_disc_rand_a", "stage": "label", "items": rnd[(rnd.split == "discovery") & (rnd.k < 12)], "priority": 20},
        {"wave": "w02_conf_rand_a", "stage": "label", "items": rnd[(rnd.split == "confirmation") & (rnd.k < 12)], "priority": 21},
        {"wave": "w03_disc_enrich", "stage": "label", "items": enr[enr.split == "discovery"], "priority": 22},
        {"wave": "w04_conf_enrich", "stage": "label", "items": enr[enr.split == "confirmation"], "priority": 23},
        {"wave": "w05_disc_rand_b", "stage": "label", "items": rnd[(rnd.split == "discovery") & (rnd.k >= 12)], "priority": 24},
        {"wave": "w06_conf_rand_b", "stage": "label", "items": rnd[(rnd.split == "confirmation") & (rnd.k >= 12)], "priority": 25},
        {"wave": "w07_cloze", "stage": "cloze", "items": cloze_items(works), "priority": 30},
        {"wave": "w08_alt_label", "stage": "alt_label",
         "items": rnd[(rnd.split == "discovery") & (rnd.k < 12)].sample(frac=0.10, random_state=SEED), "priority": 40},
    ]
    for w in waves:
        if isinstance(w["items"], pd.DataFrame):
            cols = ["passage_id", "work_id", "decade", "stratum", "text", "ctx_before", "ctx_after", "text_sha256", "split"]
            w["items"] = w["items"][cols].to_dict("records")
    return waves


def shard_wave(w: dict) -> list[dict]:
    """Shuffle across decades, cut into shards per split; returns job specs with local shard paths."""
    rng = np.random.default_rng(int(hashlib.sha256(f"{SEED}:{w['wave']}".encode()).hexdigest()[:12], 16))
    jobs = []
    for split in ("discovery", "confirmation"):
        its = [i for i in w["items"] if i["split"] == split]
        if not its:
            continue
        order = rng.permutation(len(its))
        size = SHARD_SIZE[w["stage"]]
        for s in range(0, len(its), size):
            chunk = [its[i] for i in order[s:s + size]]
            sid = f"{w['wave']}_{split[:4]}_{s // size:05d}"
            path = SHARDS / w["wave"] / f"{sid}.jsonl.gz"
            path.parent.mkdir(parents=True, exist_ok=True)
            buf = io.BytesIO()
            with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as g:
                for it in chunk:
                    g.write((json.dumps({k: v for k, v in it.items() if k != "split"}, ensure_ascii=False) + "\n").encode())
            path.write_bytes(buf.getvalue())
            dup = f"dup_{sid}" if rng.random() < DUP_RATE else None
            decades = sorted({int(i["decade"]) for i in chunk})
            base = {"stage": w["stage"], "wave": w["wave"], "shard_key": f"shards/{w['wave']}/{sid}.jsonl.gz",
                    "n_passages": len(chunk), "split": split, "priority": w["priority"], "dup_group": dup,
                    "local": str(path), "decades": decades}
            jobs.append({**base, "job_id": sid})
            if dup:
                jobs.append({**base, "job_id": sid + "_dup"})
    return jobs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["plan", "push"])
    ap.add_argument("--waves", default="")
    a = ap.parse_args()
    works = pd.read_parquet(WORK / "works.parquet")
    works = works[works.decade.between(1800, 1920)]
    passages = pd.read_parquet(WORK / "passages.parquet")
    waves = build_waves(works, passages)
    sel = set(a.waves.split(",")) if a.waves else None
    alljobs = []
    for w in waves:
        if sel and w["wave"] not in sel and w["wave"][:3] not in sel:
            continue
        jobs = shard_wave(w)
        alljobs += jobs
        print(f"{w['wave']:18s} stage={w['stage']:9s} items={len(w['items']):7d} jobs={len(jobs):5d}")
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
