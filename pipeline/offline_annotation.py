"""Offline annotation round-trip for annotators who use their own software.

  export-key     -> data/work/annotation/offline/key_review_items.{jsonl,csv}   (60 practice/cert/retake items + draft key)
  export-expert  -> data/work/annotation/offline/expert_items.{jsonl,csv}        (from ann_items.json, role expert1)
  validate FILE  -> checks a returned CSV/JSONL against docs/expert_annotation_instructions.md, prints problems
  import FILE    -> validated rows -> data/work/annotation/offline/returned_<kind>.parquet (+ maps item_id back)

Items are BLIND: opaque item_id, passage + context only (no title/author/date/passage id).
The item_id -> passage_id map stays private in data/work/annotation/offline/_map.json (never sent out).

usage: uv run --with pandas,duckdb,pyarrow python -I pipeline/offline_annotation.py export-key
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ANN = ROOT / "data/work/annotation"
OFF = ANN / "offline"
MAP = OFF / "_map.json"
SALT = "offline-2026-11"

DOMAINS = ["DISTANCE_TRAVEL", "COMMUNICATION_INFORMATION", "DARKNESS_VISIBILITY", "ILLNESS_BODY_DEATH",
           "MONEY_PROPERTY_LAW", "SOCIAL_RANK_CONVENTION", "INTERPERSONAL_CONFLICT", "INNER_STATE",
           "NATURE_WEATHER", "OTHER"]
LOCI = ["material_external", "social_institutional", "internal_psychological"]
CAUSES = ["infrastructure", "accidental_loss", "intentional_withholding", "misinterpretation", "success_resolution", "none"]
HAS = ["yes", "no", "cant_tell"]
KEY_COLS = ["item_id", "annotator", "decision", "has_obstacle", "domain", "locus", "failure_cause", "evidence", "note", "seconds"]
EXP_COLS = ["item_id", "annotator", "has_obstacle", "domain", "locus", "failure_cause", "evidence", "note", "seconds"]


def oid(prefix: str, pid: str) -> str:
    return prefix + hashlib.sha256(f"{SALT}:{pid}".encode()).hexdigest()[:10]


def load_map() -> dict:
    return json.loads(MAP.read_text()) if MAP.exists() else {}


def save_map(m: dict) -> None:
    OFF.mkdir(parents=True, exist_ok=True)
    MAP.write_text(json.dumps(m, indent=1))


def passages(ids: list[str]) -> pd.DataFrame:
    con = duckdb.connect()
    con.execute("CREATE TEMP TABLE w(id VARCHAR)")
    con.executemany("INSERT INTO w VALUES (?)", [(i,) for i in ids])
    return con.execute(f"SELECT passage_id, text, ctx_before, ctx_after FROM read_parquet('{ROOT}/data/work/passages.parquet') "
                       "WHERE passage_id IN (SELECT id FROM w)").df()


def write_items(rows: list[dict], name: str, cols: list[str]) -> None:
    OFF.mkdir(parents=True, exist_ok=True)
    with open(OFF / f"{name}.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(OFF / f"{name}.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})
    print(f"wrote {len(rows)} items -> {OFF / name}.jsonl / .csv")


def export_key() -> None:
    ref = json.loads((ANN / "practice_ref.json").read_text())
    items = [(s, it) for s in ("practice", "cert", "retake") for it in ref[s]]
    tx = passages([it["passage_id"] for _, it in items]).set_index("passage_id")
    m = load_map()
    rows = []
    for k, (s, it) in enumerate(items, 1):
        i = oid("kr_", it["passage_id"])
        m[i] = {"passage_id": it["passage_id"], "set": f"key_{s}"}
        r = tx.loc[it["passage_id"]]
        d = it["reference"]
        rows.append({"item_id": i, "order": k, "ctx_before": r.ctx_before, "passage": r.text, "ctx_after": r.ctx_after,
                     "draft_has_obstacle": "cant_tell" if d.get("has_obstacle") == "insufficient_context" else d.get("has_obstacle"),
                     "draft_domain": d.get("domain") or "", "draft_locus": d.get("locus") or "",
                     "draft_failure_cause": d.get("failure_cause") or "", "draft_rationale": it.get("rationale", "")})
    save_map(m)
    write_items(rows, "key_review_items", ["item_id", "order", "ctx_before", "passage", "ctx_after", "draft_has_obstacle",
                                           "draft_domain", "draft_locus", "draft_failure_cause", "draft_rationale"])
    template(KEY_COLS, "key_review_RETURN_TEMPLATE.csv", [r["item_id"] for r in rows])


def export_expert(annotator: str = "expert1") -> None:
    src = ANN / "ann_items.json"
    if not src.exists():
        sys.exit("ann_items.json not built yet (built on Nov 5 by analysis/build_annotation_queues.py build)")
    items = [it for it in json.loads(src.read_text())["items"] if annotator in it.get("assign", [])]
    m = load_map()
    rows = []
    for k, it in enumerate(items, 1):
        i = oid("ex_", it["passage_id"])
        m[i] = {"passage_id": it["passage_id"], "set": it.get("set", "audit"), "server_item_id": it["item_id"]}
        rows.append({"item_id": i, "order": k, "ctx_before": it["ctx_before"], "passage": it["text"], "ctx_after": it["ctx_after"]})
    save_map(m)
    write_items(rows, "expert_items", ["item_id", "order", "ctx_before", "passage", "ctx_after"])
    template(EXP_COLS, "expert_RETURN_TEMPLATE.csv", [r["item_id"] for r in rows])


def template(cols: list[str], name: str, ids: list[str]) -> None:
    with open(OFF / name, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for i in ids:
            w.writerow({"item_id": i})


def read_any(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in (".jsonl", ".ndjson"):
        return pd.DataFrame([json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()])
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def validate(path: Path) -> tuple[pd.DataFrame, list[str]]:
    df = read_any(path).fillna("")
    for c in df.columns:
        df[c] = df[c].astype(str).str.strip()
    kind = "key" if "decision" in df.columns else "expert"
    need = KEY_COLS if kind == "key" else EXP_COLS
    errs = [f"missing column: {c}" for c in need if c not in df.columns and c not in ("evidence", "note", "seconds")]
    if errs:
        return df, errs
    m = load_map()
    for n, r in df.iterrows():
        row = f"row {n + 2} ({r.get('item_id', '?')})"
        if r["item_id"] not in m:
            errs.append(f"{row}: unknown item_id")
        if not r.get("annotator"):
            errs.append(f"{row}: annotator is empty")
        if kind == "key":
            if r["decision"] not in ("agree", "correct"):
                errs.append(f"{row}: decision must be agree or correct")
            if r["decision"] == "agree":
                continue
            if not r.get("note"):
                errs.append(f"{row}: a corrected answer needs a note")
        h, d, l, fc = r["has_obstacle"], r["domain"], r["locus"], r["failure_cause"]
        if h not in HAS:
            errs.append(f"{row}: has_obstacle must be one of {HAS}")
            continue
        if h == "yes":
            if d not in DOMAINS:
                errs.append(f"{row}: domain must be one of {DOMAINS}")
            if l not in LOCI:
                errs.append(f"{row}: locus must be one of {LOCI}")
            if d == "COMMUNICATION_INFORMATION" and fc not in CAUSES:
                errs.append(f"{row}: failure_cause required for COMMUNICATION_INFORMATION, one of {CAUSES}")
            if d != "COMMUNICATION_INFORMATION" and fc:
                errs.append(f"{row}: failure_cause only allowed when domain is COMMUNICATION_INFORMATION")
        elif d or l or fc:
            errs.append(f"{row}: leave domain/locus/failure_cause empty when has_obstacle is {h}")
        if r.get("seconds") and not r["seconds"].replace(".", "", 1).isdigit():
            errs.append(f"{row}: seconds must be a number")
    dup = df.item_id[df.item_id.duplicated()].unique()
    errs += [f"duplicate item_id: {i}" for i in dup]
    return df, errs


def import_file(path: Path) -> None:
    df, errs = validate(path)
    if errs:
        print("\n".join(errs[:50]))
        sys.exit(f"{len(errs)} problem(s); nothing imported")
    m = load_map()
    df["passage_id"] = df.item_id.map(lambda i: m[i]["passage_id"])
    df["set"] = df.item_id.map(lambda i: m[i]["set"])
    kind = "key" if "decision" in df.columns else "expert"
    out = OFF / f"returned_{kind}_{path.stem}.parquet"
    df.to_parquet(out, index=False)
    print(f"imported {len(df)} rows -> {out}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "export-key":
        export_key()
    elif cmd == "export-expert":
        export_expert(sys.argv[2] if len(sys.argv) > 2 else "expert1")
    elif cmd == "validate":
        _, e = validate(Path(sys.argv[2]))
        print("\n".join(e) if e else "OK: file is valid")
    elif cmd == "import":
        import_file(Path(sys.argv[2]))
    else:
        print(__doc__)
