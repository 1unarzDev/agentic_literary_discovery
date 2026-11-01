"""Draw a stratified QA sample of synced results and write a review packet.

Strata = era (1800-1849 / 1850-1884 / 1885-1929, from the work's year) x predicted class x risk.
"risk" items (low confidence, quote_status not exact/normalized, schema failure) form their own
sub-strata and are oversampled by --risk-factor. Every row carries its stratum population N_h and
sample size n_h, so per-stratum error rates can be re-weighted to population estimates
(design weight = N_h / n_h).

Only split='discovery' rows are ever read (passages / works are filtered on split; results come
from the discovery-only sync).

Outputs (data/work/qa/, never committed):
  <stage>_<ts>.jsonl   one record per sampled item, with blank review_* fields to fill in
  <stage>_<ts>.md      readable packet (metadata, model output, passage with quote marked)
For label-type stages the .md also carries cross-model agreement (label vs alt_label /
baseline_small on shared passages) by field and era, computed on ALL shared rows, not the sample.

usage (from repo root):
  uv run --with pandas,duckdb,pyarrow python -I analysis/qa_sample.py --stage label --n 80 --seed 1
  ... --stage workcheck --n 60 --seed 1
  ... --stage label --reuse data/work/qa/label_<ts>.jsonl --pin <new_pin_prefix>   # same items, new pin (A/B)
"""
from __future__ import annotations

import argparse
import glob
import gzip
import json
import math
import sys
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
from workcheck_rule import KEEP_FORMS, catalog_signal  # noqa: E402
WORK = ROOT / "data/work"
DB = WORK / "ald.duckdb"
QA = WORK / "qa"
LABEL_STAGES = ("label", "alt_label", "baseline_small")
STAGES = ("workcheck",) + LABEL_STAGES
GOOD_QUOTE = {"exact", "normalized"}
ERAS = [(1800, 1849, "1800-1849"), (1850, 1884, "1850-1884"), (1885, 1929, "1885-1929")]
FIELDS = ["has_obstacle", "primary_domain", "domain_set", "locus", "failure_cause", "night_function"]


def era_of(year) -> str:
    if year is None or (isinstance(year, float) and math.isnan(year)):
        return "unknown"
    for lo, hi, name in ERAS:
        if lo <= year <= hi:
            return name
    return "out_of_range"


def parse(s):
    try:
        o = json.loads(s) if s else None
    except Exception:  # noqa: BLE001
        return None
    return o if isinstance(o, dict) else None


def load_results(stage: str, pin: str | None) -> pd.DataFrame:
    con = duckdb.connect(str(DB), read_only=True)
    df = con.execute("SELECT passage_id, pin_hash, job_id, worker_id, valid_schema, output_json, "
                     "quote_status, error, created FROM results WHERE stage = ?", [stage]).df()
    con.close()
    if df.empty:
        raise SystemExit(f"no synced results for stage={stage}")
    if pin == "all":
        pass
    elif pin:
        df = df[df.pin_hash.str.startswith(pin)]
    else:  # default: the pin with most rows
        top = df.pin_hash.value_counts().index[0]
        df = df[df.pin_hash == top]
    return df.reset_index(drop=True)


def predicted_class(stage: str, o: dict | None, valid) -> str:
    if o is None or valid is False:
        return "SCHEMA_FAIL"
    if stage == "workcheck":
        return str(o.get("form", "?"))
    h = o.get("has_obstacle")
    if h != "yes":
        return str(h)
    d = o.get("domains") or []
    return d[0] if d else "yes_no_domain"


def works_meta(ids: set[str]) -> pd.DataFrame:
    w = pd.read_parquet(WORK / "works.parquet",
                        columns=["work_id", "Title", "Authors", "Subjects", "LoCC", "Bookshelves",
                                 "year", "decade", "split"])
    w = w[w.work_id.isin(ids) & (w.split == "discovery")]
    return w.drop(columns="split")


def passage_texts(ids: list[str]) -> pd.DataFrame:
    con = duckdb.connect()
    con.execute("CREATE TEMP TABLE want(id VARCHAR)")
    con.executemany("INSERT INTO want VALUES (?)", [(i,) for i in ids])
    df = con.execute(f"""SELECT passage_id, work_id, decade AS p_decade, stratum, text, ctx_before, ctx_after
        FROM read_parquet('{WORK / 'passages.parquet'}')
        WHERE split = 'discovery' AND passage_id IN (SELECT id FROM want)""").df()
    con.close()
    return df


def workcheck_texts(df: pd.DataFrame) -> pd.DataFrame:
    """Workcheck item text lives only in the discovery shard that was sent to the worker."""
    want = set(df.passage_id)
    rows = []
    for job in df.job_id.unique():
        if "_disc_" not in job:  # discovery shards only
            continue
        for path in glob.glob(str(WORK / "shards" / "*" / f"{job}.jsonl.gz")):
            with gzip.open(path, "rt", encoding="utf-8") as f:
                for line in f:
                    o = json.loads(line)
                    if o["passage_id"] in want:
                        rows.append({"passage_id": o["passage_id"], "work_id": o["work_id"],
                                     "stratum": "workcheck", "text": o["text"],
                                     "ctx_before": "", "ctx_after": ""})
    return pd.DataFrame(rows).drop_duplicates("passage_id")


def annotate(stage: str, df: pd.DataFrame, low_conf: float) -> pd.DataFrame:
    outs = [parse(s) for s in df.output_json]
    df = df.assign(out=outs)
    df["pred_class"] = [predicted_class(stage, o, v) for o, v in zip(outs, df.valid_schema)]
    df["confidence"] = [(o or {}).get("confidence") for o in outs]
    risk = []
    for o, c, q, cls in zip(outs, df.confidence, df.quote_status, df.pred_class):
        r = []
        if cls == "SCHEMA_FAIL":
            r.append("schema_fail")
        if isinstance(c, (int, float)) and c < low_conf:
            r.append("low_conf")
        if stage in LABEL_STAGES and (o or {}).get("has_obstacle") == "yes" and q not in GOOD_QUOTE:
            r.append(f"quote_{q}")
        risk.append(",".join(r))
    df["risk_reasons"] = risk
    df["risk"] = df.risk_reasons != ""
    return df


def add_workcheck_risk(df: pd.DataFrame) -> pd.DataFrame:
    """Workcheck confidence is uninformative, so flag catalog-vs-model form disagreement instead."""
    cat = [catalog_signal(s, b, t) for s, b, t in zip(df.Subjects, df.Bookshelves, df.Title)]
    df["catalog_signal"] = cat
    extra = []
    for c, cls in zip(cat, df.pred_class):
        model_keep = cls in KEEP_FORMS
        cat_keep = {"fiction": True, "collection": True, "fiction_shelf": True,
                    "nonfiction": False, "verse": False, "nonfiction_shelf": False}.get(c)
        r = []
        if cat_keep is not None and cat_keep != model_keep:
            r.append(f"catalog_{c}_vs_model")
        if c == "collection" and cls == "novel_or_novella":
            r.append("collection_vs_novel")
        extra.append(",".join(r))
    df["risk_reasons"] = [",".join(x for x in (a, b) if x) for a, b in zip(df.risk_reasons, extra)]
    df["risk"] = df.risk_reasons != ""
    return df


def allocate(sizes: pd.Series, n: int, risk: pd.Series, factor: float) -> pd.Series:
    """sqrt-proportional allocation with risk up-weighting; >=1 per non-empty stratum, <= N_h."""
    score = np.sqrt(sizes.astype(float)) * np.where(risk, factor, 1.0)
    alloc = pd.Series(1, index=sizes.index)
    rest = max(n - len(sizes), 0)
    if rest:
        extra = np.floor(score / score.sum() * rest).astype(int)
        alloc = alloc + extra
        # hand out leftovers by largest score
        left = n - int(alloc.sum())
        for k in score.sort_values(ascending=False).index:
            if left <= 0:
                break
            alloc[k] += 1
            left -= 1
    alloc = np.minimum(alloc, sizes)
    # redistribute any cap shortfall to strata with spare capacity
    short = n - int(alloc.sum())
    while short > 0:
        spare = sizes - alloc
        cand = score[spare > 0].sort_values(ascending=False)
        if cand.empty:
            break
        for k in cand.index:
            if short <= 0:
                break
            alloc[k] += 1
            short -= 1
    return alloc


def draw(df: pd.DataFrame, n: int, seed: int, factor: float) -> pd.DataFrame:
    key = ["era", "pred_class", "risk"]
    sizes = df.groupby(key).size()
    risk = pd.Series([k[2] for k in sizes.index], index=sizes.index)
    alloc = allocate(sizes, n, risk, factor) if n < len(df) else sizes
    rng = np.random.default_rng(seed)
    parts = []
    for k, g in df.groupby(key):
        m = int(alloc.get(k, 0))
        if m <= 0:
            continue
        pick = g.iloc[rng.permutation(len(g))[:m]].copy()
        pick["N_h"], pick["n_h"] = len(g), m
        parts.append(pick)
    out = pd.concat(parts)
    out["design_weight"] = out.N_h / out.n_h
    return out.sample(frac=1, random_state=seed).reset_index(drop=True)


# ---------------------------------------------------------------- cross-model agreement
def norm_label(o: dict | None) -> dict:
    o = o or {}
    d = o.get("domains") or []
    return {"has_obstacle": o.get("has_obstacle"), "primary_domain": d[0] if d else None,
            "domain_set": frozenset(d), "locus": o.get("locus"),
            "failure_cause": o.get("failure_cause"), "night_function": o.get("night_function")}


def cross_tab(stage: str) -> str:
    con = duckdb.connect(str(DB), read_only=True)
    df = con.execute("SELECT stage, passage_id, output_json FROM results WHERE stage IN ('label','alt_label','baseline_small')").df()
    con.close()
    others = [s for s in LABEL_STAGES if s != stage]
    base = df[df.stage == stage]
    if base.empty:
        return ""
    shared = set(base.passage_id) & set(df[df.stage != stage].passage_id)
    pc = duckdb.connect()
    pc.execute("CREATE TEMP TABLE want(id VARCHAR)")
    pc.executemany("INSERT INTO want VALUES (?)", [(i,) for i in shared])
    pw = pc.execute(f"SELECT passage_id, work_id FROM read_parquet('{WORK / 'passages.parquet'}') "
                    "WHERE split='discovery' AND passage_id IN (SELECT id FROM want)").df()
    pc.close()
    lines = [f"## Cross-model agreement ({stage} vs others, all shared discovery rows)\n"]
    yrs = pd.read_parquet(WORK / "works.parquet", columns=["work_id", "year", "split"])
    yrs = yrs[yrs.split == "discovery"].set_index("work_id").year
    for o in others:
        oth = df[df.stage == o]
        m = base.merge(oth, on="passage_id", suffixes=("_a", "_b"))
        if m.empty:
            lines.append(f"- vs `{o}`: no shared passages yet\n")
            continue
        m = m.merge(pw, on="passage_id", how="inner")
        m["era"] = [era_of(yrs.get(w)) for w in m.work_id]
        a = [norm_label(parse(x)) for x in m.output_json_a]
        b = [norm_label(parse(x)) for x in m.output_json_b]
        both_yes = [x["has_obstacle"] == "yes" and y["has_obstacle"] == "yes" for x, y in zip(a, b)]
        lines.append(f"### vs `{o}` (n={len(m)} shared; both-yes n={sum(both_yes)})\n")
        lines.append("| field | scope | " + " | ".join(["all"] + [e[2] for e in ERAS]) + " |")
        lines.append("|---|---|" + "---|" * (1 + len(ERAS)))
        for f in FIELDS:
            scope = "all" if f == "has_obstacle" else "both_yes"
            row = []
            for era in ["all"] + [e[2] for e in ERAS]:
                idx = [i for i in range(len(m)) if (era == "all" or m.era.iloc[i] == era)
                       and (scope == "all" or both_yes[i])]
                if not idx:
                    row.append("–")
                    continue
                agree = np.mean([a[i][f] == b[i][f] for i in idx])
                row.append(f"{agree:.2f} (n={len(idx)})")
            lines.append(f"| {f} | {scope} | " + " | ".join(row) + " |")
        ct = pd.crosstab(pd.Series([x["has_obstacle"] for x in a], name=stage),
                         pd.Series([y["has_obstacle"] for y in b], name=o))
        lines.append("\nhas_obstacle confusion:\n\n```\n" + ct.to_string() + "\n```\n")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- packet
def mark_quote(text: str, quote: str) -> str:
    if quote and quote in text:
        return text.replace(quote, f"**>>{quote}<<**", 1)
    return text


def clip(s, n):
    s = (s or "").replace("\n", " ")
    return s if len(s) <= n else s[:n] + " …"


def write_packet(stage: str, s: pd.DataFrame, path: Path, header: str, xtab: str) -> None:
    L = [f"# QA packet: {stage}\n", header, ""]
    L.append("Strata (era x class x risk), N_h = population, n_h = sampled:\n")
    st = s.groupby(["era", "pred_class", "risk"]).agg(N_h=("N_h", "first"), n_h=("n_h", "first")).reset_index()
    L.append("```\n" + st.to_string(index=False) + "\n```\n")
    if xtab:
        L.append(xtab)
    for i, r in s.iterrows():
        o = r.out or {}
        L.append(f"---\n## [{i + 1}] `{r.passage_id}`  era={r.era}  class={r.pred_class}"
                 + (f"  RISK={r.risk_reasons}" if r.risk else ""))
        L.append(f"*{clip(r.Title, 120)}* — {clip(r.Authors, 80)} ({r.year if pd.notna(r.year) else '?'}); "
                 f"LoCC {r.LoCC}; stratum {r.stratum}")
        L.append(f"Subjects: {clip(r.Subjects, 300)}")
        if stage == "workcheck":
            L.append(f"Bookshelves: {clip(r.Bookshelves, 200)}  | catalog_signal: {r.catalog_signal}")
        L.append("\n```json\n" + json.dumps(o, ensure_ascii=False, indent=1) + "\n```")
        if stage in LABEL_STAGES:
            L.append(f"quote_status: `{r.quote_status}`")
            L.append(f"\n> CTX BEFORE: {clip(r.ctx_before, 700)}\n")
            L.append("PASSAGE:\n\n" + mark_quote(r.text or "", o.get("evidence_quote") or "") + "\n")
            L.append(f"> CTX AFTER: {clip(r.ctx_after, 500)}\n")
        else:
            L.append("\nOPENING:\n\n" + clip(r.text, 2500) + "\n")
        L.append("Review: ok? ____ errors: ________________________________\n")
    path.write_text("\n".join(L), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", required=True, choices=STAGES)
    ap.add_argument("--n", type=int, default=80)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--pin", default=None, help="pin_hash prefix, 'all', or default = pin with most rows")
    ap.add_argument("--low-conf", type=float, default=0.7)
    ap.add_argument("--risk-factor", type=float, default=3.0, help="allocation multiplier for risk sub-strata")
    ap.add_argument("--reuse", default=None, help="previous QA .jsonl: take exactly its passage_ids (A/B)")
    ap.add_argument("--db", default=None, help="alternate DuckDB (testing)")
    a = ap.parse_args()
    if a.db:
        global DB
        DB = Path(a.db)

    df = load_results(a.stage, a.pin)
    df = annotate(a.stage, df, a.low_conf)
    df["work_id"] = df.passage_id.str.replace(r"_wc$", "", regex=True) if a.stage == "workcheck" else None
    if a.stage != "workcheck":
        txt = passage_texts(df.passage_id.tolist())
    else:
        txt = workcheck_texts(df)
        txt = txt.drop(columns="work_id")
    df = df.drop(columns="work_id") if a.stage != "workcheck" else df
    df = df.merge(txt, on="passage_id", how="inner")  # inner = discovery-only guard
    meta = works_meta(set(df.work_id))
    df = df.merge(meta, on="work_id", how="inner")
    df["era"] = [era_of(y if pd.notna(y) else d) for y, d in zip(df.year, df.decade)]
    if a.stage == "workcheck":
        df = add_workcheck_risk(df)

    if a.reuse:
        ids = [json.loads(l)["passage_id"] for l in Path(a.reuse).read_text(encoding="utf-8").splitlines() if l.strip()]
        s = df.set_index("passage_id").loc[[i for i in ids if i in set(df.passage_id)]].reset_index()
        s["N_h"], s["n_h"], s["design_weight"] = np.nan, np.nan, np.nan
        missing = len(ids) - len(s)
        if missing:
            print(f"warning: {missing} reused ids have no result under this pin")
    else:
        s = draw(df, a.n, a.seed, a.risk_factor)

    QA.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%S")
    stem = QA / f"{a.stage}_{ts}"
    keep = ["passage_id", "work_id", "era", "year", "stratum", "pred_class", "risk", "risk_reasons",
            "confidence", "quote_status", "valid_schema", "error", "pin_hash", "job_id", "worker_id",
            "N_h", "n_h", "design_weight", "catalog_signal", "Title", "Authors", "Subjects", "LoCC", "Bookshelves",
            "text", "ctx_before", "ctx_after"]
    with open(f"{stem}.jsonl", "w", encoding="utf-8") as f:
        for r in s.to_dict("records"):
            rec = {k: (None if isinstance(r.get(k), float) and math.isnan(r.get(k)) else r.get(k)) for k in keep}
            rec["output"] = r["out"]
            rec.update({"review_ok": None, "review_errors": [], "review_notes": "", "review_ref": {}})
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    header = (f"pin `{s.pin_hash.iloc[0][:12] if len(s) else '?'}`; population {len(df)} rows; sample {len(s)}; "
              f"seed {a.seed}; risk factor {a.risk_factor}; low-conf < {a.low_conf}; "
              f"risk rows in population {int(df.risk.sum())}" + (f"; REUSED ids from {a.reuse}" if a.reuse else ""))
    xtab = cross_tab(a.stage) if a.stage in LABEL_STAGES else ""
    write_packet(a.stage, s, Path(f"{stem}.md"), header, xtab)
    print(header)
    print("class counts (population):", df.pred_class.value_counts().to_dict())
    print("wrote", f"{stem}.jsonl", f"{stem}.md")
    if xtab:
        print(xtab)


if __name__ == "__main__":
    main()
