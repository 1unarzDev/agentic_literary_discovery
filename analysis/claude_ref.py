"""Claude reference-label set on DISCOVERY random passages (codebook v0.9).

Purpose: measure where the production labeller (Gemma 4 12B, pin 41ca3c7d) and the alt labeller
(Qwen 9B, pin ca0c1188) err, against a stronger LLM reader (Claude), and whether that error is
DIFFERENTIAL between canonical and popular works (which would bias the TWO FICTIONS gap) or
between eras (H1). Claude labels are an LLM reference, NOT human gold.

DISCOVERY ONLY. The frame is built from works_v2.split_v2 == 'discovery' and passages.stratum ==
'random'; result rows are joined to that frame inside DuckDB before any output_json is read.

Subcommands (from repo root):
  uv run --with pandas,duckdb,pyarrow python -I analysis/claude_ref.py sample [--seed S] [--per-cell 200]
  uv run --with pandas,duckdb,pyarrow,rapidfuzz python -I analysis/claude_ref.py verify
  uv run --with pandas,duckdb,pyarrow,rapidfuzz python -I analysis/claude_ref.py analyze [--B 2000]

Design (sample): cells = era (E/M/L by year_v2, else year) x canonical (2), registered primary set
(primary_v2_capv2), Gemma v0.9 valid labels only. Each cell gets min(per_cell, N_cell) items. Within
a cell, passages with a Qwen alt label form a sub-stratum that receives up to half the cell budget
(all of them if fewer); the rest come from the no-Qwen sub-stratum. Every item carries N_h, n_h and
its inclusion probability pi = n_h / N_h, so cell estimates are design-unbiased with w = 1/pi.

Outputs (data/work/claude_ref/, never committed):
  sample.parquet      passage_id, item_id, work_id, author_group, era, canonical, qwen, N_h, n_h, pi, seed
  sample_meta.json    seed, snapshot counts, cell table
  codebook_v09.txt    the codebook block, byte for byte from docs/codebook.md
  in/batch_<k>.txt    blind labelling packets: opaque item id + context + passage only
  batch_<k>.jsonl     Claude labels (written by the labelling agents)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "data" / "work"
OUT = WORK / "claude_ref"
GEMMA_PIN = "41ca3c7d"
QWEN_PIN = "ca0c1188"
# few-shot passages quoted in the codebook: never score on them
EXCLUDE = {"pg8938_p00080", "pg72909_p00168"}
ERAS = ["E", "M", "L"]
LOCI = ["material_external", "social_institutional", "internal_psychological"]
BATCH = 50


def era_of(year) -> np.ndarray:
    y = np.asarray(year, dtype=float)
    return np.where(y < 1850, "E", np.where(y < 1885, "M", "L"))


def codebook_block() -> str:
    md = (ROOT / "docs" / "codebook.md").read_text()
    m = re.search(r"```text\n(.*?)```", md, re.S)
    return m.group(1)


def frame(con) -> pd.DataFrame:
    w = pd.read_parquet(WORK / "works_v2.parquet",
                        columns=["work_id", "split_v2", "primary_v2_capv2", "year", "year_v2",
                                 "author_group", "canonical", "Title", "author_name"])
    w = w[(w.split_v2 == "discovery") & (w.primary_v2_capv2.fillna(False).astype(bool))].copy()
    w["year_used"] = w.year_v2.where(w.year_v2.notna(), w.year)
    w = w[w.year_used.notna() & (w.year_used >= 1800) & (w.year_used <= 1929)]
    w["era"] = era_of(w.year_used)
    w["canonical"] = w.canonical.fillna(False).astype(bool)
    con.register("dw", w[["work_id"]])
    con.execute("""create temp table fr as
        select p.passage_id, p.work_id from 'data/work/passages.parquet' p join dw using(work_id)
        where p.stratum = 'random' and p.split = 'discovery'""")
    g = con.sql(f"""select r.passage_id from results r join fr using(passage_id)
        where r.stage = 'label' and r.pin_hash like '{GEMMA_PIN}%' and r.valid_schema""").df()
    q = con.sql(f"""select r.passage_id from results r join fr using(passage_id)
        where r.stage = 'alt_label' and r.pin_hash like '{QWEN_PIN}%' and r.valid_schema""").df()
    fr = con.sql("select * from fr").df()
    df = fr[fr.passage_id.isin(g.passage_id) & ~fr.passage_id.isin(EXCLUDE)]
    df = df.merge(w[["work_id", "author_group", "era", "canonical", "year_used"]], on="work_id")
    df["qwen"] = df.passage_id.isin(q.passage_id)
    return df.sort_values("passage_id").reset_index(drop=True)


def cmd_sample(a):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "in").mkdir(exist_ok=True)
    if (OUT / "sample.parquet").exists() and not a.force:
        sys.exit("sample.parquet exists; pass --force to redraw (this invalidates labels)")
    con = duckdb.connect(str(WORK / "ald.duckdb"), read_only=True)
    df = frame(con)
    rng = np.random.default_rng(a.seed)
    picks, cells = [], []
    for era in ERAS:
        for can in (False, True):
            c = df[(df.era == era) & (df.canonical == can)]
            n_c = min(a.per_cell, len(c))
            cq, cn = c[c.qwen], c[~c.qwen]
            n_q = min(len(cq), n_c // 2)
            n_n = min(len(cn), n_c - n_q)
            n_q = min(len(cq), n_c - n_n)  # if the no-Qwen side is short, top up from Qwen
            for sub, n_h in ((cq, n_q), (cn, n_n)):
                if n_h == 0:
                    continue
                idx = rng.choice(len(sub), size=n_h, replace=False)
                s = sub.iloc[np.sort(idx)].copy()
                s["N_h"], s["n_h"] = len(sub), n_h
                s["pi"] = n_h / len(sub)
                picks.append(s)
            cells.append(dict(era=era, canonical=can, N_cell=len(c), N_qwen=len(cq), n_cell=n_q + n_n,
                              n_qwen=n_q, works=c.work_id.nunique()))
    s = pd.concat(picks, ignore_index=True)
    s["seed"] = a.seed
    # opaque ids and a shuffled order so batches mix cells
    order = rng.permutation(len(s))
    s = s.iloc[order].reset_index(drop=True)
    s["item_id"] = [f"i{v:06x}" for v in rng.choice(16**6, size=len(s), replace=False)]
    assert s.item_id.is_unique
    s["batch"] = np.arange(len(s)) // BATCH
    s.to_parquet(OUT / "sample.parquet", index=False)
    meta = dict(seed=a.seed, per_cell=a.per_cell, gemma_pin=GEMMA_PIN, qwen_pin=QWEN_PIN,
                frame_rows=len(df), n=len(s), cells=cells,
                note="frame = discovery x primary_v2_capv2 x stratum random x valid Gemma v0.9 label; "
                     "era from year_v2 else year")
    (OUT / "sample_meta.json").write_text(json.dumps(meta, indent=1, default=int))
    (OUT / "codebook_v09.txt").write_text(codebook_block())
    # blind packets
    con.register("sp", s[["passage_id"]])
    txt = con.sql("""select p.passage_id, p.text, p.ctx_before, p.ctx_after
        from 'data/work/passages.parquet' p join sp using(passage_id)""").df()
    s = s.merge(txt, on="passage_id")
    for b, g in s.groupby("batch"):
        parts = []
        for r in g.sort_values("item_id").itertuples():
            parts.append(f"##### ITEM {r.item_id}\n"
                         f"CONTEXT BEFORE (orientation only; never quote it):\n{r.ctx_before}\n\n"
                         f"=== PASSAGE START (judge and quote ONLY this) ===\n{r.text}\n=== PASSAGE END ===\n\n"
                         f"CONTEXT AFTER (orientation only; never quote it):\n{r.ctx_after}\n")
        (OUT / "in" / f"batch_{b:02d}.txt").write_text("\n".join(parts))
    print(pd.DataFrame(cells).to_string())
    print(f"n = {len(s)} in {s.batch.nunique()} batches; frame {len(df)}")


# ---------------------------------------------------------------- verify
def load_claude() -> pd.DataFrame:
    rows = []
    for f in sorted(OUT.glob("batch_*.jsonl")):
        for line in f.read_text().splitlines():
            line = line.strip()
            if line:
                d = json.loads(line)
                d["_file"] = f.name
                rows.append(d)
    return pd.DataFrame(rows)


def quote_ok(q: str, text: str) -> str:
    if not isinstance(q, str) or not q.strip():
        return "missing"
    if q in text:
        return "exact"
    ws = lambda x: re.sub(r"\s+", " ", x).strip()
    if ws(q) in ws(text):
        return "whitespace"
    return "fail"


def cmd_verify(a):
    s = pd.read_parquet(OUT / "sample.parquet")
    con = duckdb.connect(str(WORK / "ald.duckdb"), read_only=True)
    con.register("sp", s[["passage_id"]])
    txt = con.sql("select p.passage_id, p.text from 'data/work/passages.parquet' p join sp using(passage_id)").df()
    s = s.merge(txt, on="passage_id")
    c = load_claude()
    if c.empty:
        sys.exit("no labels yet")
    dup = c.item_id.duplicated(keep="last")
    c = c[~dup]
    m = s.merge(c, on="item_id", how="left", indicator=True)
    yes = m.has_obstacle == "yes"
    m["quote_check"] = [quote_ok(q, t) if y else "n/a" for q, t, y in zip(m.evidence_quote, m.text, yes)]
    bad_locus = yes & ~m.locus.isin(LOCI)
    print("labelled:", (m._merge == "both").sum(), "/", len(s), "dups dropped:", int(dup.sum()))
    print(m.groupby("batch")._merge.apply(lambda x: (x == "both").sum()).to_string())
    print(m.quote_check.value_counts().to_string())
    print("bad locus:", int(bad_locus.sum()))
    fails = m[m.quote_check.isin(["fail", "missing"]) | bad_locus]
    for r in fails.itertuples():
        print(f"  batch {r.batch:02d} {r.item_id} {r.quote_check} locus={r.locus} q={str(r.evidence_quote)[:90]!r}")
    if a.write_fails:
        fails[["item_id", "batch", "quote_check"]].to_csv(OUT / "quote_fails.csv", index=False)


# ---------------------------------------------------------------- analysis
def parse_model(con, s: pd.DataFrame, stage: str, pin: str, prefix: str) -> pd.DataFrame:
    con.register("sp", s[["passage_id"]])
    r = con.sql(f"""select r.passage_id, r.output_json from results r join sp using(passage_id)
        where r.stage = '{stage}' and r.pin_hash like '{pin}%' and r.valid_schema""").df()
    out = []
    for pid, js in zip(r.passage_id, r.output_json):
        d = json.loads(js)
        dom = d.get("domains") or []
        out.append({"passage_id": pid, f"{prefix}_has": d.get("has_obstacle"),
                    f"{prefix}_locus": d.get("locus") if d.get("has_obstacle") == "yes" else None,
                    f"{prefix}_dom1": dom[0] if dom else None,
                    f"{prefix}_fc": d.get("failure_cause") if "COMMUNICATION_INFORMATION" in dom else None})
    return pd.DataFrame(out)


def assemble() -> pd.DataFrame:
    s = pd.read_parquet(OUT / "sample.parquet")
    con = duckdb.connect(str(WORK / "ald.duckdb"), read_only=True)
    c = load_claude().drop_duplicates("item_id", keep="last")
    c = c.rename(columns={"has_obstacle": "c_has", "locus": "c_locus", "failure_cause": "c_fc"})
    c["c_dom1"] = c.domains.apply(lambda d: d[0] if isinstance(d, list) and d else None)
    m = s.merge(c[["item_id", "c_has", "c_locus", "c_dom1", "c_fc", "clarity"]
                  if "clarity" in c else ["item_id", "c_has", "c_locus", "c_dom1", "c_fc"]], on="item_id")
    m = m.merge(parse_model(con, s, "label", GEMMA_PIN, "g"), on="passage_id", how="left")
    m = m.merge(parse_model(con, s, "alt_label", QWEN_PIN, "q"), on="passage_id", how="left")
    m.loc[m.c_has != "yes", "c_locus"] = None
    m["w"] = 1.0 / m.pi
    m["h"] = m.era + "|" + m.canonical.astype(str) + "|" + m.qwen.astype(str)
    return m


def boot_idx(m: pd.DataFrame, B: int, seed: int):
    """Author-cluster bootstrap within each design stratum h. Yields row-index arrays."""
    rng = np.random.default_rng(seed)
    groups = []
    for _, g in m.groupby("h"):
        cl = [np.asarray(ix) for ix in g.groupby("author_group").indices.values()]
        cl = [g.index.values[ix] for ix in cl]
        groups.append(cl)
    for _ in range(B):
        parts = []
        for cl in groups:
            pick = rng.integers(len(cl), size=len(cl))
            parts.extend(cl[i] for i in pick)
        yield np.concatenate(parts)


def wmean(x, w):
    x, w = np.asarray(x, float), np.asarray(w, float)
    ok = ~np.isnan(x)
    return np.nan if w[ok].sum() == 0 else float((x[ok] * w[ok]).sum() / w[ok].sum())


def stats_fn(m: pd.DataFrame, pfx: str, pop_era: dict) -> dict:
    """All point statistics for model `pfx` vs Claude on frame m (rows with a model label)."""
    out = {}
    m = m[m[f"{pfx}_has"].notna()]
    cy = (m.c_has == "yes").values
    my = (m[f"{pfx}_has"] == "yes").values
    w = m.w.values

    def block(mask, tag):
        if mask.sum() == 0:
            return
        out[f"{tag}:prev_claude"] = wmean(cy[mask], w[mask])
        out[f"{tag}:prev_model"] = wmean(my[mask], w[mask])
        out[f"{tag}:precision"] = wmean(cy[mask & my], w[mask & my]) if (mask & my).any() else np.nan
        out[f"{tag}:recall"] = wmean(my[mask & cy], w[mask & cy]) if (mask & cy).any() else np.nan
        both = mask & cy & my
        out[f"{tag}:locus_acc"] = wmean((m[f"{pfx}_locus"].values == m.c_locus.values)[both], w[both]) \
            if both.any() else np.nan
        for L in LOCI:
            k = L.split("_")[0]
            out[f"{tag}:{k}_claude"] = wmean((m.c_locus.values == L)[mask & cy], w[mask & cy]) \
                if (mask & cy).any() else np.nan
            out[f"{tag}:{k}_model"] = wmean((m[f"{pfx}_locus"].values == L)[mask & my], w[mask & my]) \
                if (mask & my).any() else np.nan
            # model locus on Claude-true, model-yes obstacles (pure locus error, no prevalence error)
            out[f"{tag}:{k}_model_on_both"] = wmean((m[f"{pfx}_locus"].values == L)[both], w[both]) \
                if both.any() else np.nan
            out[f"{tag}:{k}_claude_on_both"] = wmean((m.c_locus.values == L)[both], w[both]) \
                if both.any() else np.nan

    era, can = m.era.values, m.canonical.values
    block(np.ones(len(m), bool), "all")
    for e in ERAS:
        block(era == e, f"era={e}")
    for cv in (False, True):
        block(can == cv, f"canon={cv}")
        for e in ERAS:
            block((era == e) & (can == cv), f"cell={e}|{cv}")
    # TF gaps: era-standardised to the frame's era mix
    for k in ("material", "social", "internal"):
        for src in ("claude", "model", "model_on_both", "claude_on_both"):
            gaps = {e: out.get(f"cell={e}|True:{k}_{src}", np.nan) - out.get(f"cell={e}|False:{k}_{src}", np.nan)
                    for e in ERAS}
            ok = [e for e in ERAS if not np.isnan(gaps[e])]
            out[f"TF:{k}_{src}"] = (sum(pop_era[e] * gaps[e] for e in ok) / sum(pop_era[e] for e in ok)
                                    if ok else np.nan)
            for e in ERAS:
                out[f"TF|{e}:{k}_{src}"] = gaps[e]
        out[f"TFbias:{k}"] = out[f"TF:{k}_model"] - out[f"TF:{k}_claude"]
        out[f"TFbias_locusonly:{k}"] = out[f"TF:{k}_model_on_both"] - out[f"TF:{k}_claude_on_both"]
        # H1 (L - E) under each reader, pooled over canon at the frame's canon mix within era
        for src in ("claude", "model"):
            out[f"H1:{k}_{src}"] = out.get(f"era=L:{k}_{src}", np.nan) - out.get(f"era=E:{k}_{src}", np.nan)
        out[f"H1bias:{k}"] = out[f"H1:{k}_model"] - out[f"H1:{k}_claude"]
    # differential error: model - claude material share, canonical minus popular
    for cv in (False, True):
        out[f"err_material|canon={cv}"] = out[f"canon={cv}:material_model"] - out[f"canon={cv}:material_claude"]
    return out


def confusion(m: pd.DataFrame, pfx: str, mask=None) -> pd.DataFrame:
    m = m[m[f"{pfx}_has"].notna()]
    if mask is not None:
        m = m[mask(m)]
    lab = lambda has, loc: np.where(has == "yes", pd.Series(loc).fillna("?").str.split("_").str[0], "no-obst")
    cl = lab(m.c_has.values, m.c_locus.values)
    ml = lab(m[f"{pfx}_has"].values, m[f"{pfx}_locus"].values)
    t = pd.crosstab(pd.Series(cl, name="Claude"), pd.Series(ml, name=pfx), values=m.w, aggfunc="sum").fillna(0)
    n = pd.crosstab(pd.Series(cl, name="Claude"), pd.Series(ml, name=pfx))
    return n, t / t.values.sum()


def cmd_analyze(a):
    m = assemble()
    frame_n = pd.DataFrame(json.loads((OUT / "sample_meta.json").read_text())["cells"])
    pe = frame_n.groupby("era").N_cell.sum()
    pop_era = (pe / pe.sum()).to_dict()
    res = {}
    for pfx in ("g", "q"):
        mm = m if pfx == "g" else m[m.qwen]
        est = stats_fn(mm, pfx, pop_era)
        reps = []
        sub = mm.reset_index(drop=True)
        for ix in boot_idx(sub, a.B, a.seed + (pfx == "q")):
            reps.append(stats_fn(sub.loc[ix].reset_index(drop=True), pfx, pop_era))
        R = pd.DataFrame(reps)
        tab = pd.DataFrame({"est": pd.Series(est),
                            "lo": R.quantile(0.025), "hi": R.quantile(0.975)})
        res[pfx] = tab
        tab.to_csv(OUT / f"stats_{pfx}.csv")
    conf = {}
    for pfx in ("g", "q"):
        mm = m if pfx == "g" else m[m.qwen]
        conf[pfx] = {"all": confusion(mm, pfx)}
        for cv in (False, True):
            conf[pfx][f"canonical={cv}"] = confusion(mm, pfx, lambda d, cv=cv: d.canonical == cv)
        for e in ERAS:
            conf[pfx][f"era={e}"] = confusion(mm, pfx, lambda d, e=e: d.era == e)
    pd.to_pickle(dict(res=res, conf=conf, m=m, pop_era=pop_era), OUT / "analysis.pkl")
    for pfx in ("g", "q"):
        print(f"==== {pfx}")
        print(res[pfx].round(3).to_string())


def fmt(tab, key, pct=True):
    if key not in tab.index or pd.isna(tab.loc[key, "est"]):
        return "n/a"
    e, lo, hi = tab.loc[key, ["est", "lo", "hi"]]
    k = 100 if pct else 1
    return f"{k*e:+.1f} [{k*lo:+.1f}, {k*hi:+.1f}]" if key.startswith(("TF", "H1", "err")) \
        else f"{k*e:.1f} [{k*lo:.1f}, {k*hi:.1f}]"


def cmd_tables(a):
    """Markdown tables from analysis.pkl -> data/work/claude_ref/tables.md (pasted into the doc)."""
    z = pd.read_pickle(OUT / "analysis.pkl")
    m, L = z["m"], []
    L.append("### Sample (labelled)\n")
    L.append(m.groupby(["era", "canonical"]).agg(n=("item_id", "size"), works=("work_id", "nunique"),
             authors=("author_group", "nunique"), qwen=("qwen", "sum"),
             claude_yes=("c_has", lambda x: (x == "yes").sum()),
             gemma_yes=("g_has", lambda x: (x == "yes").sum())).to_markdown())
    for pfx, name in (("g", "Gemma v0.9"), ("q", "Qwen 9B (Qwen sub-strata only)")):
        t = z["res"][pfx]
        L.append(f"\n## {name} vs Claude (design-weighted %, 95% author-cluster bootstrap CI)\n")
        rows = [("all", "all")] + [(f"era={e}", f"era {e}") for e in ERAS] + \
               [(f"canon={c}", "canonical" if c else "popular") for c in (True, False)] + \
               [(f"cell={e}|{c}", f"{e} {'canonical' if c else 'popular'}") for e in ERAS for c in (True, False)]
        L.append("| subset | n | Claude obstacle rate | model obstacle rate | precision | recall | locus acc. (both yes) |")
        L.append("|---|---|---|---|---|---|---|")
        mm = m if pfx == "g" else m[m.qwen]
        mm = mm[mm[f"{pfx}_has"].notna()]
        for k, lab in rows:
            if f"{k}:prev_claude" not in t.index:
                continue
            if k == "all":
                n = len(mm)
            elif k.startswith("era="):
                n = (mm.era == k[4:]).sum()
            elif k.startswith("canon="):
                n = (mm.canonical == (k[6:] == "True")).sum()
            else:
                e, c = k[5:].split("|")
                n = ((mm.era == e) & (mm.canonical == (c == "True"))).sum()
            L.append(f"| {lab} | {n} | " + " | ".join(fmt(t, f"{k}:{s}") for s in
                     ("prev_claude", "prev_model", "precision", "recall", "locus_acc")) + " |")
        L.append("\nLocus shares among obstacles (each reader's own obstacle set), %:\n")
        L.append("| subset | material C | material M | social C | social M | internal C | internal M |")
        L.append("|---|---|---|---|---|---|---|")
        for k, lab in rows:
            if f"{k}:material_claude" not in t.index:
                continue
            L.append(f"| {lab} | " + " | ".join(fmt(t, f"{k}:{x}_{s}") for x in ("material", "social", "internal")
                                                for s in ("claude", "model")) + " |")
        L.append("\nTF gap (canonical minus popular, era-standardised to the frame's era mix), pp:\n")
        L.append("| share | Claude labels | model labels | bias (model - Claude) | Claude, both-yes set | model, both-yes set | locus-only bias |")
        L.append("|---|---|---|---|---|---|---|")
        for x in ("material", "social", "internal"):
            L.append(f"| {x} | " + " | ".join(fmt(t, k) for k in (f"TF:{x}_claude", f"TF:{x}_model", f"TFbias:{x}",
                     f"TF:{x}_claude_on_both", f"TF:{x}_model_on_both", f"TFbias_locusonly:{x}")) + " |")
        L.append("\nTF material gap by era, pp:\n")
        L.append("| era | Claude | model |")
        L.append("|---|---|---|")
        for e in ERAS:
            L.append(f"| {e} | {fmt(t, f'TF|{e}:material_claude')} | {fmt(t, f'TF|{e}:material_model')} |")
        L.append("\nH1-style contrast (L minus E, pooled over canon in the sample's design weights), pp:\n")
        L.append("| share | Claude | model | bias |")
        L.append("|---|---|---|---|")
        for x in ("material", "social", "internal"):
            L.append(f"| {x} | {fmt(t, f'H1:{x}_claude')} | {fmt(t, f'H1:{x}_model')} | {fmt(t, f'H1bias:{x}')} |")
        L.append("\nMaterial-share error (model minus Claude), by canon status, pp: "
                 f"canonical {fmt(t, 'err_material|canon=True')}; popular {fmt(t, 'err_material|canon=False')}\n")
        for k, (n, p) in z["conf"][pfx].items():
            L.append(f"\nLocus confusion, {name}, {k} (rows Claude, cols model; raw counts, then weighted %):\n")
            L.append(n.to_markdown())
            L.append("")
            L.append((100 * p).round(1).to_markdown())
    (OUT / "tables.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


def cmd_exemplars(a):
    """Candidate exemplars: Claude 'vivid' obstacles with quote verified, plus work metadata."""
    m = assemble()
    c = load_claude().drop_duplicates("item_id", keep="last")
    m = m.merge(c[["item_id", "evidence_quote", "rationale", "locus_reason", "domains"]], on="item_id")
    w = pd.read_parquet(WORK / "works_v2.parquet", columns=["work_id", "pg_id", "Title", "author_name", "split_v2"])
    m = m.merge(w, on="work_id")
    assert (m.split_v2 == "discovery").all()
    con = duckdb.connect(str(WORK / "ald.duckdb"), read_only=True)
    con.register("sp", m[["passage_id"]])
    txt = con.sql("select p.passage_id, p.text from 'data/work/passages.parquet' p join sp using(passage_id)").df()
    m = m.merge(txt, on="passage_id")
    m = m[(m.c_has == "yes") & (m.clarity == "vivid")]
    m["qok"] = [q in t for q, t in zip(m.evidence_quote, m.text)]
    m = m[m.qok]
    cols = ["item_id", "passage_id", "era", "canonical", "c_locus", "locus_reason", "domains", "g_locus", "Title",
            "author_name", "year_used", "evidence_quote", "rationale"]
    m[cols].to_json(OUT / "exemplar_candidates.jsonl", orient="records", lines=True, force_ascii=False)
    print(m.groupby(["canonical", "era", "c_locus"]).size().to_string())


def write_packet(path: Path, g: pd.DataFrame, id_col: str):
    parts = []
    for r in g.sort_values(id_col).itertuples():
        parts.append(f"##### ITEM {getattr(r, id_col)}\n"
                     f"CONTEXT BEFORE (orientation only; never quote it):\n{r.ctx_before}\n\n"
                     f"=== PASSAGE START (judge and quote ONLY this) ===\n{r.text}\n=== PASSAGE END ===\n\n"
                     f"CONTEXT AFTER (orientation only; never quote it):\n{r.ctx_after}\n")
    path.write_text("\n".join(parts))


def cmd_overlap(a):
    """Reliability subsample: n items relabelled by a different agent under fresh opaque ids."""
    s = pd.read_parquet(OUT / "sample.parquet")
    rng = np.random.default_rng(a.seed)
    o = s.iloc[np.sort(rng.choice(len(s), size=a.n, replace=False))].copy()
    used = set(s.item_id)
    ids = [f"r{v:06x}" for v in rng.choice(16**6, size=a.n, replace=False)]
    assert not used & set(ids)
    o["rel_id"] = ids
    o = o.iloc[rng.permutation(len(o))].reset_index(drop=True)
    o["rel_batch"] = np.arange(len(o)) // BATCH
    o[["item_id", "rel_id", "rel_batch", "passage_id"]].to_parquet(OUT / "overlap.parquet", index=False)
    con = duckdb.connect(str(WORK / "ald.duckdb"), read_only=True)
    con.register("sp", o[["passage_id"]])
    txt = con.sql("""select p.passage_id, p.text, p.ctx_before, p.ctx_after
        from 'data/work/passages.parquet' p join sp using(passage_id)""").df()
    o = o.merge(txt, on="passage_id")
    for b, g in o.groupby("rel_batch"):
        write_packet(OUT / "in" / f"overlap_{b:02d}.txt", g, "rel_id")
    print(o.groupby("rel_batch").size())


def kappa(a, b):
    a, b = np.asarray(a), np.asarray(b)
    cats = sorted(set(a) | set(b))
    po = (a == b).mean()
    pe = sum((a == c).mean() * (b == c).mean() for c in cats)
    return (po - pe) / (1 - pe) if pe < 1 else np.nan


def cmd_reliability(a):
    """Claude-vs-Claude agreement on the overlap items (different agent, fresh ids)."""
    o = pd.read_parquet(OUT / "overlap.parquet")
    rows = []
    for f in sorted(OUT.glob("overlap_*.jsonl")):
        rows += [json.loads(x) for x in f.read_text().splitlines() if x.strip()]
    r = pd.DataFrame(rows).rename(columns={"item_id": "rel_id"})
    c = load_claude().drop_duplicates("item_id", keep="last")
    m = o.merge(r[["rel_id", "has_obstacle", "locus"]], on="rel_id").merge(
        c[["item_id", "has_obstacle", "locus"]], on="item_id", suffixes=("_2", "_1"))
    h1, h2 = (m.has_obstacle_1 == "yes"), (m.has_obstacle_2 == "yes")
    both = h1 & h2
    l1 = np.where(h1, m.locus_1.fillna("?"), "none")
    l2 = np.where(h2, m.locus_2.fillna("?"), "none")
    out = dict(n=len(m), has_agree=float((h1 == h2).mean()), has_kappa=kappa(h1, h2),
               yes_rate_1=float(h1.mean()), yes_rate_2=float(h2.mean()), n_both_yes=int(both.sum()),
               locus_agree_both_yes=float((m.locus_1[both] == m.locus_2[both]).mean()),
               locus_kappa_both_yes=kappa(m.locus_1[both], m.locus_2[both]),
               joint4_kappa=kappa(l1, l2))
    print(json.dumps(out, indent=1))
    print(pd.crosstab(pd.Series(l1, name="first"), pd.Series(l2, name="second")))
    (OUT / "reliability.json").write_text(json.dumps(out, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("sample")
    s.add_argument("--seed", type=int, default=20261104)
    s.add_argument("--per-cell", type=int, default=200)
    s.add_argument("--force", action="store_true")
    v = sp.add_parser("verify")
    v.add_argument("--write-fails", action="store_true")
    z = sp.add_parser("analyze")
    z.add_argument("--B", type=int, default=2000)
    z.add_argument("--seed", type=int, default=7)
    sp.add_parser("tables")
    sp.add_parser("reliability")
    o = sp.add_parser("overlap")
    o.add_argument("--n", type=int, default=100)
    o.add_argument("--seed", type=int, default=99)
    sp.add_parser("exemplars")
    a = ap.parse_args()
    {"sample": cmd_sample, "verify": cmd_verify, "analyze": cmd_analyze, "tables": cmd_tables,
     "exemplars": cmd_exemplars, "overlap": cmd_overlap, "reliability": cmd_reliability}[a.cmd](a)


if __name__ == "__main__":
    main()
