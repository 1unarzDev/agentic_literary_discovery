"""Pull worker results from the coordinator into data/work/results/ (Parquet) + data/work/ald.duckdb.

- Incremental: remembers the last `created` timestamp in data/work/results/_state.json.
- Never reads sealed (confirmation) blobs; the coordinator also refuses while sealed.
- Re-verifies every evidence quote against OUR passage text (workers are not trusted).
- Dedup: per (stage, pin_hash, passage_id) keep a full result over a partial, earliest upload otherwise;
  duplicate-twin results are kept in a separate table for cross-worker agreement.
- Ignores test waves (job_id starting with 'wtest').

usage: uv run --project ald --with pandas,duckdb,pyarrow python -I pipeline/sync_results.py [--loop 600]
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
from pathlib import Path

import duckdb
import httpx
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ald/src"))
from ald.evidence import verify_quote  # noqa: E402

WORK = ROOT / "data/work"
RES = WORK / "results"
STATE = RES / "_state.json"


def cfg():
    c = json.loads((Path.home() / ".config/ald-admin.json").read_text())
    return c["url"].rstrip("/"), {"Authorization": f"Bearer {c['admin_token']}"}


def load_texts(ids: set[str]) -> dict[str, str]:
    con = duckdb.connect()
    con.execute("CREATE TEMP TABLE want(id VARCHAR)")
    con.executemany("INSERT INTO want VALUES (?)", [(i,) for i in ids])
    rows = con.execute(f"SELECT passage_id, text FROM read_parquet('{WORK / 'passages.parquet'}') "
                       "WHERE passage_id IN (SELECT id FROM want)").fetchall()
    return dict(rows)


def sync_once(c: httpx.Client, url: str) -> int:
    RES.mkdir(parents=True, exist_ok=True)
    state = json.loads(STATE.read_text()) if STATE.exists() else {"since": "1970-01-01T00:00:00Z", "seen": []}
    seen = set(state["seen"])
    r = c.get(f"{url}/v1/admin/results", params={"since": state["since"], "split": "discovery"})
    r.raise_for_status()
    rows = [x for x in r.json()["results"] if not x["job_id"].startswith("wtest")]
    new = [x for x in rows if x["r2_key"] not in seen]
    if not new:
        return 0
    recs = []
    for x in new:
        b = c.get(f"{url}/v1/admin/blob", params={"key": x["r2_key"]})
        b.raise_for_status()
        for line in gzip.decompress(b.content).decode("utf-8").splitlines():
            if not line.strip():
                continue
            o = json.loads(line)
            recs.append({"job_id": x["job_id"], "worker_id": x["worker_id"], "partial": x["partial"],
                         "created": x["created"], "stage": x["stage"], "pin_hash": x["pin_hash"],
                         "model_digest": x["model_digest"], "backend_version": x.get("backend_version"),
                         "is_dup_twin": x["job_id"].endswith("_dup"), "passage_id": o.get("passage_id"),
                         "valid_schema": o.get("valid_schema"), "output_json": json.dumps(o.get("output"), ensure_ascii=False),
                         "worker_evidence": json.dumps(o.get("evidence"), ensure_ascii=False),
                         "latency_ms": o.get("latency_ms"), "error": o.get("error")})
    df = pd.DataFrame(recs)
    # re-verify quotes on label-type stages against our own passage text
    lab = df.stage.isin(["label", "alt_label", "adjudicate"])
    texts = load_texts(set(df.loc[lab, "passage_id"]))
    status = []
    for pid, out, is_lab in zip(df.passage_id, df.output_json, lab):
        if not is_lab:
            status.append(None)
            continue
        try:
            q = (json.loads(out) or {}).get("evidence_quote") or ""
        except Exception:  # noqa: BLE001
            q = ""
        src = texts.get(pid)
        status.append("no_quote" if not q else ("no_source" if src is None else verify_quote(q, src).status))
    df["quote_status"] = status
    batch = RES / f"batch_{int(time.time())}.parquet"
    df.to_parquet(batch, index=False)
    state["seen"] = sorted(seen | {x["r2_key"] for x in new})
    state["since"] = max(x["created"] for x in new)
    STATE.write_text(json.dumps(state))
    build_views()
    return len(df)


def build_views() -> None:
    con = duckdb.connect(str(WORK / "ald.duckdb"))
    con.execute(f"""CREATE OR REPLACE VIEW raw AS SELECT * FROM read_parquet('{RES}/batch_*.parquet', union_by_name=true)""")
    # primary: one row per (stage, pin, passage); prefer non-twin full results, then earliest
    con.execute("""CREATE OR REPLACE VIEW results AS
        SELECT * EXCLUDE (rn) FROM (
          SELECT *, row_number() OVER (PARTITION BY stage, pin_hash, passage_id
                    ORDER BY is_dup_twin, partial, created) AS rn FROM raw) WHERE rn = 1""")
    con.execute("""CREATE OR REPLACE VIEW twin_pairs AS
        SELECT a.stage, a.passage_id, a.worker_id AS w1, b.worker_id AS w2, a.output_json AS o1, b.output_json AS o2
        FROM raw a JOIN raw b ON a.stage=b.stage AND a.pin_hash=b.pin_hash AND a.passage_id=b.passage_id
        AND a.worker_id < b.worker_id""")
    con.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=int, default=0, help="seconds between syncs (0 = once)")
    a = ap.parse_args()
    url, h = cfg()
    with httpx.Client(timeout=120, headers=h) as c:
        while True:
            try:
                n = sync_once(c, url)
                print(time.strftime("%H:%M:%S"), "synced", n, "rows", flush=True)
            except Exception as e:  # noqa: BLE001
                print(time.strftime("%H:%M:%S"), "sync error:", e, flush=True)
            if not a.loop:
                break
            time.sleep(a.loop)


if __name__ == "__main__":
    main()
