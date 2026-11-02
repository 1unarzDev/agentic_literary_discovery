"""Reassign passages / results / jobs from the v1 split to split_v2 (author-group repair, docs/canon_measure.md §1).

Use from sync or analysis code:

    from pipeline.split_v2_map import SplitV2
    m = SplitV2.load()                       # reads data/work/works_v2.parquet once
    m.split_of("pg461_p00087")               # -> "discovery" | "confirmation" | None
    df = m.reassign(df)                      # adds work_id_v2, split_v2, moved (by passage_id column)

Passage ids are ``pg<pg_id>_p<idx>`` where pg_id is the work's canonical edition (build_corpus.segment_work), so
the map needs only works_v2 (pg_id -> work_id, split, split_v2), not the passage texts.

Rule (registered): a passage's split is its work's split_v2. Labels already produced for a moved work are
Discovery data from now on; nothing is relabelled and no Discovery passage ever moves to Confirmation.

CLI (metadata only: reads job status rows and shard passage ids, never result blobs):
  uv run python -I pipeline/split_v2_map.py queue-report [--jobs data/work/conf_job_status.json]
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "data/work"
PID_RE = re.compile(r"^pg(\d+)_p\d+$")
WID_RE = re.compile(r"^(w\d+)_")  # cloze / work-level item ids: w<work_root>_cz<n>


def pg_of(passage_id: str) -> int | None:
    m = PID_RE.match(str(passage_id))
    return int(m.group(1)) if m else None


@dataclass
class SplitV2:
    by_pg: dict[int, tuple[str, str, str]]  # pg_id -> (work_id, split_v1, split_v2)
    by_work: dict[str, tuple[str, str, str]] | None = None

    @classmethod
    def from_frame(cls, w: pd.DataFrame) -> "SplitV2":
        recs = list(zip(w.pg_id, w.work_id, w.split, w.split_v2))
        return cls({int(p): (wid, s1, s2) for p, wid, s1, s2 in recs}, {wid: (wid, s1, s2) for _, wid, s1, s2 in recs})

    def _rec(self, item_id: str):
        """Record for a passage id (pg<pg>_p<i>) or a work-level item id (w<id>_...)."""
        pg = pg_of(item_id)
        if pg is not None:
            return self.by_pg.get(pg)
        m = WID_RE.match(str(item_id))
        return (self.by_work or {}).get(m.group(1)) if m else None

    @classmethod
    def load(cls, path: Path | str = WORK / "works_v2.parquet") -> "SplitV2":
        return cls.from_frame(pd.read_parquet(path, columns=["pg_id", "work_id", "split", "split_v2"]))

    def split_of(self, passage_id: str) -> str | None:
        r = self._rec(passage_id)
        return r[2] if r else None

    def moved(self, passage_id: str) -> bool:
        r = self._rec(passage_id)
        return bool(r and r[1] != r[2])

    def reassign(self, df: pd.DataFrame, passage_col: str = "passage_id") -> pd.DataFrame:
        rec = [self._rec(p) for p in df[passage_col]]
        out = df.copy()
        out["work_id_v2"] = [r[0] if r else None for r in rec]
        out["split_v2"] = [r[2] if r else None for r in rec]
        out["moved"] = [bool(r and r[1] != r[2]) for r in rec]
        return out


def shard_passage_ids(path: Path) -> list[str]:
    ids = []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                ids.append(json.loads(line)["passage_id"])
    return ids


def queue_report(jobs_path: Path, m: SplitV2, groups: dict[str, str] | None = None) -> pd.DataFrame:
    """Per Confirmation job: how many of its passages belong to works now in Discovery."""
    rows = json.loads(jobs_path.read_text())
    rows = rows[0]["results"] if isinstance(rows, list) and rows and "results" in rows[0] else rows
    partial_path = jobs_path.with_name("conf_job_partials.json")
    partial = defaultdict(set)
    if partial_path.exists():
        for r in json.loads(partial_path.read_text())[0]["results"]:
            partial[r["job_id"]] |= set(json.loads(r["passage_ids_json"]))
    out = []
    for j in rows:
        local = WORK / j["shard_key"]
        if not local.exists():
            continue
        ids = shard_passage_ids(local)
        mv = [p for p in ids if m.moved(p)]
        labelled = (len(ids) if j["has_result"] else 0) + (len(partial.get(j["job_id"], ())) if not j["has_result"] else 0)
        mv_lab = (len(mv) if j["has_result"] else sum(1 for p in mv if p in partial.get(j["job_id"], ())))
        out.append({"job_id": j["job_id"], "wave": j["wave"], "stage": j["stage"], "status": j["status"],
                    "n_passages": len(ids), "n_labelled": labelled, "n_moved": len(mv), "n_moved_labelled": mv_lab,
                    "moved_works": len({m._rec(p)[0] for p in mv})})
    return pd.DataFrame(out)


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["queue-report"])
    ap.add_argument("--jobs", default=str(WORK / "conf_job_status.json"))
    a = ap.parse_args(argv)
    m = SplitV2.load()
    r = queue_report(Path(a.jobs), m)
    live = r[r.status.isin(["queued", "leased", "done"])]
    print(live.groupby(["wave", "status"])[["n_passages", "n_labelled", "n_moved", "n_moved_labelled"]].sum().to_string())
    r.to_csv(WORK / "split_v2_queue_report.csv", index=False)
    print("wrote", WORK / "split_v2_queue_report.csv")


if __name__ == "__main__":
    main(sys.argv[1:])
