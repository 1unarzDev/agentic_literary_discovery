"""EXPLORATORY (not pre-registered): "Who stands in the way?" (A) and "How are obstacles overcome?" (B).

Literary review R2 and R3 (docs/review/literary_review.md). DISCOVERY HALF ONLY: works_v2.split_v2 == 'discovery'.
Never touches Confirmation or sealed data. All codings are raw LLM (sub-agent) codings, uncorrected.

Subcommands
  prepare   draw the stratified samples (era_v2 x canonical) and write blinded batch files
            data/work/explore_who/batches/{a,b}_NNN.jsonl  (opaque id + text only) and the private key
            data/work/explore_who/key_{a,b}.parquet (id -> passage_id, work, strata, weights).
  check     validate coder outputs data/work/explore_who/out/{a,b}_NNN.jsonl against the batches.
  analyze   merge, work-clustered bootstrap, figures (analysis/figs/explore_{who,resolution}.png),
            and print markdown tables + exemplar candidates (quotes verified verbatim against the text).

usage: uv run --with pandas,duckdb,pyarrow,matplotlib python -I analysis/explore_who_resolution.py <cmd>
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
W = ROOT / "data/work"
OUT = W / "explore_who"
FIGS = ROOT / "analysis/figs"
PIN = "41ca3c7d"
SEED = 20261104
ERAS = ["E", "M", "L"]
ERA_LABEL = {"E": "1800–49", "M": "1850–84", "L": "1885–1929"}
A_DOMAINS = {"INTERPERSONAL_CONFLICT", "SOCIAL_RANK_CONVENTION", "MONEY_PROPERTY_LAW", "COMMUNICATION_INFORMATION"}
A_PER_CELL, B_PER_CELL = 250, 134
A_BATCH, B_BATCH = 50, 40
MAX_PER_WORK = 3
B = int(__import__("os").environ.get("BOOT", 2000))

# Okabe-Ito (colorblind-safe)
OI = {"orange": "#E69F00", "sky": "#56B4E9", "green": "#009E73", "yellow": "#F0E442", "blue": "#0072B2",
      "verm": "#D55E00", "purple": "#CC79A7", "grey": "#999999", "black": "#000000"}


# ------------------------------------------------------------------ population
def population() -> pd.DataFrame:
    import duckdb
    con = duckdb.connect(str(W / "ald.duckdb"), read_only=True)
    r = con.sql(f"""select passage_id, job_id, output_json from results
                    where stage='label' and pin_hash like '{PIN}%' and valid_schema
                      and job_id like '%disc%' and job_id not like '%_dup'""").df()
    r = r.drop_duplicates("passage_id")
    o = pd.json_normalize(r.output_json.map(json.loads))
    r = pd.concat([r.drop(columns="output_json").reset_index(drop=True), o], axis=1)
    r = r[r.has_obstacle == "yes"]
    p = pd.read_parquet(W / "passages.parquet",
                        columns=["passage_id", "work_id", "pg_id", "split", "stratum", "char_start", "char_end"],
                        filters=[("split", "==", "discovery")])
    r = r.merge(p, on="passage_id", how="inner")
    w = pd.read_parquet(W / "works_v2.parquet", columns=[
        "work_id", "split_v2", "era_v2", "year_v2", "date_exclusion", "primary_v2_capv2", "historical_setting",
        "juvenile", "author_group", "author_name", "Title"])
    c = pd.read_parquet(W / "canon.parquet", columns=["work_id", "canonical"])
    g = pd.read_parquet(W / "genre.parquet", columns=["work_id", "genre"])
    d = r.merge(w, on="work_id").merge(c, on="work_id").merge(g, on="work_id")
    d = d[(d.split_v2 == "discovery") & d.era_v2.notna() & d.date_exclusion.isna()].copy()
    assert (d.split_v2 == "discovery").all() and (d.split == "discovery").all()
    d["canonical"] = d.canonical.fillna(False).astype(bool)
    d["cell"] = d.era_v2 + "_" + np.where(d.canonical, "canon", "pop")
    d["inA"] = d.domains.map(lambda x: bool(set(x) & A_DOMAINS))
    return d


def draw(pop: pd.DataFrame, per_cell: int, rng: np.random.Generator) -> pd.DataFrame:
    """Within each era x canonical cell: shuffle, keep <= MAX_PER_WORK per work, take per_cell."""
    out = []
    for cell, g in pop.groupby("cell"):
        g = g.sample(frac=1, random_state=rng.integers(1 << 31))
        g = g[g.groupby("work_id").cumcount() < MAX_PER_WORK].head(per_cell).copy()
        g["N_cell"] = (pop.cell == cell).sum()
        g["n_cell"] = len(g)
        g["w"] = g.N_cell / g.n_cell
        out.append(g)
    return pd.concat(out)


def opaque(prefix: str, pid: str) -> str:
    return prefix + hashlib.sha256(f"{SEED}:{prefix}:{pid}".encode()).hexdigest()[:10]


def following_text(pg_id: int, char_start: int, char_end: int) -> str:
    """ctx_after + the next two passage-length windows of the same work (clean text, char offsets)."""
    t = (W / "clean" / f"{pg_id}.txt").read_text(encoding="utf-8")
    end = min(len(t), char_end + 2 * (char_end - char_start) + 600)
    m = re.search(r"\s", t[end:end + 200])
    if m:
        end += m.start()
    return t[char_end:end].strip()


def prepare() -> None:
    rng = np.random.default_rng(SEED)
    pop = population()
    (OUT / "batches").mkdir(parents=True, exist_ok=True)
    (OUT / "out").mkdir(parents=True, exist_ok=True)
    text = pd.read_parquet(W / "passages.parquet", columns=["passage_id", "text"], filters=[("split", "==", "discovery")])
    manifest = {"pin": PIN, "seed": SEED, "n_obstacles": int(len(pop)), "n_A_frame": int(pop.inA.sum()),
                "cells": pop.groupby("cell").agg(n=("passage_id", "size"), nA=("inA", "sum")).astype(int).to_dict()}
    for tag, frame, per, bs in [("a", pop[pop.inA], A_PER_CELL, A_BATCH), ("b", pop, B_PER_CELL, B_BATCH)]:
        s = draw(frame, per, rng).merge(text, on="passage_id")
        s["oid"] = [opaque(tag, x) for x in s.passage_id]
        if tag == "b":
            s["following"] = [following_text(r.pg_id, r.char_start, r.char_end) for r in s.itertuples()]
        s = s.sample(frac=1, random_state=SEED).reset_index(drop=True)  # mix strata within batches
        s["batch"] = s.index // bs
        keep = ["oid", "passage_id", "work_id", "author_group", "author_name", "Title", "year_v2", "era_v2",
                "canonical", "cell", "genre", "juvenile", "historical_setting", "primary_v2_capv2", "N_cell",
                "n_cell", "w", "batch", "domains", "locus", "obstacle_summary", "evidence_quote"]
        s[keep].to_parquet(OUT / f"key_{tag}.parquet")
        for b, g in s.groupby("batch"):
            with open(OUT / "batches" / f"{tag}_{b:03d}.jsonl", "w", encoding="utf-8") as f:
                for r in g.itertuples():
                    rec = {"id": r.oid, "passage": r.text}
                    if tag == "b":
                        rec["obstacle"] = r.obstacle_summary
                        rec["following_text"] = r.following
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        manifest[f"sample_{tag}"] = {"n": int(len(s)), "batches": int(s.batch.max() + 1),
                                     "per_cell": s.cell.value_counts().to_dict(), "works": int(s.work_id.nunique())}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(json.dumps(manifest, indent=1))


def reliability() -> None:
    """Independent re-coding subsample: 100 A ids (2 batches) + 40 B ids (1 batch), re-shuffled, new batch files
    {a,b}_rel_NNN.jsonl with the same opaque ids. Coded by fresh sub-agents that never saw the first pass."""
    rng = np.random.default_rng(SEED + 1)
    for tag, n, bs in [("a", 100, A_BATCH), ("b", 40, B_BATCH)]:
        src = {}
        for f in sorted((OUT / "batches").glob(f"{tag}_[0-9]*.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                j = json.loads(line)
                src[j["id"]] = line
        ids = rng.choice(sorted(src), n, replace=False)
        for b in range(n // bs):
            (OUT / "batches" / f"{tag}_rel_{b:03d}.jsonl").write_text(
                "\n".join(src[i] for i in ids[b * bs:(b + 1) * bs]) + "\n", encoding="utf-8")
    print("reliability batches written")


def kappa(x: pd.Series, y: pd.Series) -> float:
    cats = sorted(set(x) | set(y))
    po = float((x.values == y.values).mean())
    pe = sum(float((x == c).mean()) * float((y == c).mean()) for c in cats)
    return (po - pe) / (1 - pe) if pe < 1 else np.nan


def agreement(lines: list[str]) -> None:
    for tag, cols in [("a", list(A_ENUM)), ("b", list(B_ENUM))]:
        rel = []
        for f in sorted((OUT / "out").glob(f"{tag}_rel_*.jsonl")):
            rel += [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        if not rel:
            continue
        r = pd.DataFrame(rel)
        main = load_out(tag)
        m = r.merge(main, on="id", suffixes=("_2", "_1"))
        out = [f"| {c} | {100*(m[c+'_1']==m[c+'_2']).mean():.0f}% | {kappa(m[c+'_1'], m[c+'_2']):.2f} |" for c in cols]
        if tag == "a":
            for nm, f in [("guardian enforcing convention", lambda t, s: (t["role" + s].isin(["parent", "aunt_guardian"])
                                                                          & (t["acts_for" + s] == "enforcing_rule_convention"))),
                          ("institution/collective", lambda t, s: t["opponent_type" + s].isin(["institution", "collective"]))]:
                a1, a2 = f(m, "_1"), f(m, "_2")
                out.append(f"| {nm} (derived) | {100*(a1==a2).mean():.0f}% | {kappa(a1, a2):.2f} |")
        else:
            for nm, f in [("chance or providence (derived)", lambda t, s: t["means" + s].isin(["chance_coincidence", "providence_fate"]))]:
                a1, a2 = f(m, "_1"), f(m, "_2")
                out.append(f"| {nm} | {100*(a1==a2).mean():.0f}% | {kappa(a1, a2):.2f} |")
        lines += [f"Independent re-coding agreement, {tag.upper()} (n={len(m)}):", "", "| field | agreement | Cohen's κ |",
                  "|---|---|---|", *out, ""]


# ------------------------------------------------------------------ schemes
A_ENUM = {
    "opponent_type": {"person", "family_member", "institution", "collective", "none"},
    "role": {"parent", "aunt_guardian", "suitor_rival", "spouse", "employer_master", "servant", "official_police_lawyer",
             "clergy", "villain_criminal", "friend", "stranger", "other", "none"},
    "opponent_gender": {"male", "female", "mixed", "unknown"},
    "acts_for": {"self_interest", "enforcing_rule_convention", "institution", "unclear"},
    "protagonist_gender": {"female", "male", "unknown"},
}
B_ENUM = {
    "resolved_in_view": {"yes", "no", "unclear"},
    "means": {"chance_coincidence", "providence_fate", "another_person", "own_action", "institution", "technology",
              "time_delay", "not_resolved"},
}


def load_out(tag: str) -> pd.DataFrame:
    rows = []
    for f in sorted((OUT / "out").glob(f"{tag}_[0-9]*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    print("bad json", f.name, line[:80], file=sys.stderr)
    return pd.DataFrame(rows).drop_duplicates("id", keep="last") if rows else pd.DataFrame(columns=["id"])


def check() -> None:
    for tag, enum in [("a", A_ENUM), ("b", B_ENUM)]:
        key = pd.read_parquet(OUT / f"key_{tag}.parquet")
        o = load_out(tag)
        missing = key[~key.oid.isin(o.id)]
        bad = {k: int((~o[k].isin(v)).sum()) for k, v in enum.items() if k in o}
        print(tag, "coded", o.id.isin(key.oid).sum(), "/", len(key), "missing batches",
              sorted(missing.batch.unique().tolist()), "invalid", bad)


# ------------------------------------------------------------------ analysis helpers
def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("’", "'").replace("‘", "'").replace("“", '"')
                  .replace("”", '"')).strip()


def verified(quote, text: str) -> bool:
    return isinstance(quote, str) and len(quote.split()) >= 4 and norm(quote) in norm(text)


def wmean(df: pd.DataFrame, col: str) -> float:
    return float(np.average(df[col], weights=df.w)) if len(df) else np.nan


def boot(df: pd.DataFrame, col: str, by: str, levels, n: int = B, seed: int = SEED, diff=None):
    """Work-clustered bootstrap (resample works within each sampling cell); stratum-weighted means.
    Returns {level: (est, lo, hi)} and optionally the diff (levels[diff[0]] - levels[diff[1]])."""
    rng = np.random.default_rng(seed)
    est = {l: wmean(df[df[by] == l], col) for l in levels}
    works = {c: g.work_id.unique() for c, g in df.groupby("cell")}
    idx = {wk: g.index.values for wk, g in df.groupby("work_id")}
    draws = {l: [] for l in levels}
    dd = []
    for _ in range(n):
        ii = np.concatenate([np.concatenate([idx[x] for x in rng.choice(ws, len(ws))]) for ws in works.values()])
        s = df.loc[ii]
        v = {l: wmean(s[s[by] == l], col) for l in levels}
        for l in levels:
            draws[l].append(v[l])
        if diff:
            dd.append(v[diff[0]] - v[diff[1]])
    res = {l: (est[l], np.nanpercentile(draws[l], 2.5), np.nanpercentile(draws[l], 97.5)) for l in levels}
    if diff:
        res["diff"] = (est[diff[0]] - est[diff[1]], np.nanpercentile(dd, 2.5), np.nanpercentile(dd, 97.5))
    return res


def fmt(t, pct=True):
    e, lo, hi = t
    if np.isnan(e):
        return "–"
    return f"{100*e:.0f}% [{100*lo:.0f}, {100*hi:.0f}]" if pct else f"{e:.2f} [{lo:.2f}, {hi:.2f}]"


def fmt_pp(t):
    e, lo, hi = t
    return f"{100*e:+.0f} pp [{100*lo:+.0f}, {100*hi:+.0f}]"


def merged(tag: str) -> pd.DataFrame:
    key = pd.read_parquet(OUT / f"key_{tag}.parquet")
    o = load_out(tag)
    d = key.merge(o, left_on="oid", right_on="id", how="inner")
    text = pd.read_parquet(W / "passages.parquet", columns=["passage_id", "text"], filters=[("split", "==", "discovery")])
    d = d.merge(text, on="passage_id")
    for k, v in (A_ENUM if tag == "a" else B_ENUM).items():
        d = d[d[k].isin(v)]
    d["era_canon"] = d.era_v2 + "_" + np.where(d.canonical, "canon", "pop")
    return d.reset_index(drop=True)


def cell_table(d: pd.DataFrame, col: str, label: str) -> list[str]:
    """Rows: era; columns: popular / canonical / all (weighted), with work-clustered bootstrap CIs."""
    rows = []
    for era in ERAS:
        e = d[d.era_v2 == era]
        r = boot(e, col, "canonical", [False, True], n=B // 2)
        a = boot(e.assign(_all=1), col, "_all", [1], n=B // 2)
        rows.append(f"| {ERA_LABEL[era]} | {fmt(r[False])} (n={int((~e.canonical).sum())}) | "
                    f"{fmt(r[True])} (n={int(e.canonical.sum())}) | {fmt(a[1])} |")
    return [f"**{label}**", "", "| Era | Popular | Canonical | All (cell-weighted) |", "|---|---|---|---|", *rows, ""]


def trend(d: pd.DataFrame, col: str, group=None) -> tuple:
    """L minus E difference (weighted), work-clustered bootstrap; optionally within a canonical group."""
    s = d if group is None else d[d.canonical == group]
    return boot(s, col, "era_v2", ["E", "L"], diff=("L", "E"))["diff"]


def did(d: pd.DataFrame, col: str) -> tuple:
    """(L-E | canonical) - (L-E | popular)."""
    rng = np.random.default_rng(SEED + 7)
    def stat(s):
        m = {(e, c): wmean(s[(s.era_v2 == e) & (s.canonical == c)], col) for e in "EL" for c in (True, False)}
        return (m["L", True] - m["E", True]) - (m["L", False] - m["E", False])
    est = stat(d)
    works = {c: g.work_id.unique() for c, g in d.groupby("cell")}
    idx = {wk: g.index.values for wk, g in d.groupby("work_id")}
    v = []
    for _ in range(B):
        ii = np.concatenate([np.concatenate([idx[x] for x in rng.choice(ws, len(ws))]) for ws in works.values()])
        v.append(stat(d.loc[ii]))
    return est, np.nanpercentile(v, 2.5), np.nanpercentile(v, 97.5)


# ------------------------------------------------------------------ analyze
def analyze_a(lines: list[str]) -> pd.DataFrame:
    d = merged("a")
    d["inst"] = (d.opponent_type == "institution").astype(int)
    d["impersonal"] = d.opponent_type.isin(["institution", "collective"]).astype(int)
    d["family"] = (d.opponent_type == "family_member").astype(int)
    d["female_opp"] = (d.opponent_gender == "female").astype(int)
    d["convention"] = (d.acts_for == "enforcing_rule_convention").astype(int)
    d["guardian_conv"] = (d.role.isin(["parent", "aunt_guardian"]) & (d.acts_for == "enforcing_rule_convention")).astype(int)
    d["fem_guardian_conv"] = (d.guardian_conv.astype(bool) & (d.opponent_gender == "female")).astype(int)
    d["aunt_guard"] = (d.role == "aunt_guardian").astype(int)
    d["parent"] = (d.role == "parent").astype(int)
    d["official"] = (d.role == "official_police_lawyer").astype(int)
    d["villain"] = (d.role == "villain_criminal").astype(int)
    d["female_prot"] = (d.protagonist_gender == "female").astype(int)
    pers = d[d.opponent_type.isin(["person", "family_member"])].copy()
    lines += [f"A coded: {len(d)} passages from {d.work_id.nunique()} works.", ""]
    lines += ["Opponent type (weighted shares, all eras):", ""]
    tab = d.groupby("opponent_type").w.sum() / d.w.sum()
    lines += ["| opponent_type | share |", "|---|---|", *[f"| {k} | {100*v:.0f}% |" for k, v in tab.sort_values(ascending=False).items()], ""]
    tab = d.groupby("role").w.sum() / d.w.sum()
    lines += ["| role | share |", "|---|---|", *[f"| {k} | {100*v:.1f}% |" for k, v in tab.sort_values(ascending=False).items()], ""]
    for col, lab in [("impersonal", "Opponent is an institution or collective (share of coded passages)"),
                     ("inst", "Opponent is an institution"),
                     ("family", "Opponent is a family member"),
                     ("guardian_conv", "Parent / aunt / guardian enforcing a rule or convention"),
                     ("fem_guardian_conv", "...and female"),
                     ("convention", "Opponent acts to enforce a rule or convention"),
                     ("female_prot", "Blocked protagonist is female"),
                     ("villain", "Opponent is a villain / criminal"),
                     ("official", "Opponent is an official / police / lawyer")]:
        lines += cell_table(d, col, lab)
    lines += cell_table(pers, "female_opp", "Female opponent, among person/family opponents")
    lines += ["L − E trends (weighted, work-clustered 95% CI):", "", "| measure | all | popular | canonical | DiD canon − pop |",
              "|---|---|---|---|---|"]
    for col in ["impersonal", "inst", "guardian_conv", "fem_guardian_conv", "convention", "villain", "female_prot"]:
        lines.append(f"| {col} | {fmt_pp(trend(d, col))} | {fmt_pp(trend(d, col, False))} | "
                     f"{fmt_pp(trend(d, col, True))} | {fmt_pp(did(d, col))} |")
    lines.append(f"| female_opp (persons) | {fmt_pp(trend(pers, 'female_opp'))} | {fmt_pp(trend(pers, 'female_opp', False))} | "
                 f"{fmt_pp(trend(pers, 'female_opp', True))} | {fmt_pp(did(pers, 'female_opp'))} |")
    lines.append("")
    # gender pairing: who blocks women?
    x = pers[pers.protagonist_gender.isin(["female", "male"]) & pers.opponent_gender.isin(["female", "male"])]
    ct = x.groupby(["protagonist_gender", "opponent_gender"]).w.sum().unstack()
    ct = ct.div(ct.sum(axis=1), axis=0)
    lines += ["Opponent gender by protagonist gender (person/family opponents, weighted row shares):", "",
              "| protagonist | female opp | male opp |", "|---|---|---|",
              *[f"| {i} | {100*r['female']:.0f}% | {100*r['male']:.0f}% |" for i, r in ct.iterrows()], ""]
    fp = x[x.protagonist_gender == "female"].assign(fo=lambda t: (t.opponent_gender == "female").astype(int))
    mp = x[x.protagonist_gender == "male"].assign(fo=lambda t: (t.opponent_gender == "female").astype(int))
    lines += [f"Female-opponent share when the protagonist is female: {fmt(boot(fp.assign(_a=1), 'fo', '_a', [1])[1])}; "
              f"male protagonist: {fmt(boot(mp.assign(_a=1), 'fo', '_a', [1])[1])}.", ""]
    # who enforces convention: gender among guardians
    gc = d[d.guardian_conv == 1]
    lines += [f"Guardian-enforcing-convention rows: {len(gc)}; female {100*(gc.opponent_gender=='female').mean():.0f}%, "
              f"male {100*(gc.opponent_gender=='male').mean():.0f}% (unweighted).", ""]
    rc = d.groupby("role").apply(lambda g: (g.opponent_gender == "female").mean()).sort_values(ascending=False)
    lines += ["Female share by role (unweighted): " + ", ".join(f"{k} {100*v:.0f}% (n={int((d.role==k).sum())})" for k, v in rc.items()), ""]
    # agreement with the label's domain: RANK vs INTERPERSONAL against acts_for
    d["rank"] = d.domains.map(lambda z: "SOCIAL_RANK_CONVENTION" in list(z))
    ct = pd.crosstab(d["rank"], d.acts_for, normalize="index")
    lines += ["v0.9 label SOCIAL_RANK_CONVENTION (rows) vs coded acts_for (cols), row shares:", "",
              ct.round(2).to_markdown(), ""]
    # sensitivity: primary set only
    pr = d[d.primary_v2_capv2.fillna(False).astype(bool)]
    lines += [f"Sensitivity, registered-primary works only (n={len(pr)}): impersonal L−E {fmt_pp(trend(pr, 'impersonal'))}; "
              f"guardian_conv L−E {fmt_pp(trend(pr, 'guardian_conv'))}; canonical L−E {fmt_pp(trend(pr, 'guardian_conv', True))}.", ""]
    fig_a(d)
    return d


def analyze_b(lines: list[str]) -> pd.DataFrame:
    d = merged("b")
    d["resolved"] = (d.resolved_in_view == "yes").astype(int)
    d["chance_prov"] = (d.resolved.astype(bool) & d.means.isin(["chance_coincidence", "providence_fate"])).astype(int)
    lines += [f"B coded: {len(d)} passages from {d.work_id.nunique()} works.", ""]
    lines += cell_table(d, "resolved", "Obstacle resolved within the passage + following ~700 words")
    r = d[d.resolved == 1].copy()
    for m in B_ENUM["means"] - {"not_resolved"}:
        r[m] = (r.means == m).astype(int)
    r["chance_prov"] = r.means.isin(["chance_coincidence", "providence_fate"]).astype(int)
    r["agency"] = (r.means == "own_action").astype(int)
    tab = r.groupby("means").w.sum() / r.w.sum()
    lines += [f"Means of resolution, among resolved (n={len(r)}), weighted:", "", "| means | share |", "|---|---|",
              *[f"| {k} | {100*v:.1f}% |" for k, v in tab.sort_values(ascending=False).items()], ""]
    for col, lab in [("chance_prov", "Chance or providence, share of resolved obstacles"),
                     ("own_action", "Character's own action, share of resolved"),
                     ("another_person", "Another person's help, share of resolved"),
                     ("institution", "Institution (law/police), share of resolved"),
                     ("technology", "Technology, share of resolved")]:
        lines += cell_table(r, col, lab)
    lines += cell_table(d, "chance_prov", "Resolved by chance or providence, share of ALL sampled obstacles")
    lines += ["L − E trends, among resolved (weighted, work-clustered 95% CI):", "",
              "| measure | all | popular | canonical | DiD canon − pop |", "|---|---|---|---|---|"]
    for col in ["chance_prov", "chance_coincidence", "providence_fate", "own_action", "another_person", "technology"]:
        lines.append(f"| {col} | {fmt_pp(trend(r, col))} | {fmt_pp(trend(r, col, False))} | "
                     f"{fmt_pp(trend(r, col, True))} | {fmt_pp(did(r, col))} |")
    lines.append(f"| resolved (all obstacles) | {fmt_pp(trend(d, 'resolved'))} | {fmt_pp(trend(d, 'resolved', False))} | "
                 f"{fmt_pp(trend(d, 'resolved', True))} | {fmt_pp(did(d, 'resolved'))} |")
    lines.append("")
    # raw counts of chance/providence by cell
    ct = r.groupby(["era_v2", "canonical"]).agg(n=("chance_prov", "size"), cp=("chance_prov", "sum"),
                                               prov=("providence_fate", "sum"), ch=("chance_coincidence", "sum"))
    lines += ["Raw counts among resolved (cell × chance/providence):", "", ct.to_markdown(), ""]
    pr = r[r.primary_v2_capv2.fillna(False).astype(bool)]
    lines += [f"Sensitivity, registered-primary works only (resolved n={len(pr)}): chance/providence L−E "
              f"{fmt_pp(trend(pr, 'chance_prov'))}; own action L−E {fmt_pp(trend(pr, 'own_action'))}.", ""]
    nh = r[~r.historical_setting.fillna(False).astype(bool) & ~r.juvenile.fillna(False).astype(bool)]
    lines += [f"Sensitivity, excluding historical-setting and juvenile works (resolved n={len(nh)}): chance/providence L−E "
              f"{fmt_pp(trend(nh, 'chance_prov'))}; own action L−E {fmt_pp(trend(nh, 'own_action'))}.", ""]
    fig_b(d, r)
    return d


def _bars(ax, d, cols, labels, colors, title):
    x = np.arange(3)
    k = len(cols)
    width = 0.8 / (2 * k)
    for gi, canon in enumerate([False, True]):
        for ci, col in enumerate(cols):
            ests = [boot(d[(d.era_v2 == e) & (d.canonical == canon)].assign(_a=1), col, "_a", [1], n=400)[1] for e in ERAS]
            m = np.array([t[0] for t in ests]) * 100
            lo = m - np.array([t[1] for t in ests]) * 100
            hi = np.array([t[2] for t in ests]) * 100 - m
            pos = x + (gi * k + ci - (2 * k - 1) / 2) * width
            ax.bar(pos, m, width * 0.92, color=colors[ci], alpha=1.0 if canon else 0.55,
                   hatch=None if canon else "//", edgecolor="white" if canon else colors[ci], linewidth=0.6,
                   label=f"{labels[ci]}, {'canonical' if canon else 'popular'}")
            ax.errorbar(pos, m, yerr=[lo, hi], fmt="none", ecolor="#333333", elinewidth=0.8, capsize=2)
    ax.set_ylim(0, ax.get_ylim()[1] * 1.35)  # headroom for the legend
    ax.set_xticks(x, [ERA_LABEL[e] for e in ERAS])
    ax.set_ylabel("% of coded passages")
    ax.set_title(title, fontsize=10, loc="left")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#dddddd", linewidth=0.6)
    ax.set_axisbelow(True)


def fig_a(d: pd.DataFrame) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    _bars(axes[0], d, ["impersonal", "family"], ["institution/collective", "family member"],
          [OI["blue"], OI["orange"]], "A. Who opposes? Opponent type")
    _bars(axes[1], d, ["guardian_conv", "fem_guardian_conv"], ["guardian enforcing convention", "…and female"],
          [OI["green"], OI["purple"]], "B. The guardian enforcing convention")
    for ax in axes:
        ax.legend(fontsize=7, frameon=False, loc="upper right")
    fig.suptitle("EXPLORATORY · Discovery half · raw LLM codings · bars = cell estimates, whiskers = work-clustered 95% CI",
                 fontsize=8, color="#555555", y=0.995)
    fig.tight_layout()
    FIGS.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGS / "explore_who.png", dpi=200)


def fig_b(d: pd.DataFrame, r: pd.DataFrame) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    _bars(axes[0], d, ["resolved"], ["resolved in view"], [OI["grey"]], "A. Obstacles resolved within ~1,000 words")
    _bars(axes[1], r, ["chance_prov", "own_action"], ["chance/providence", "own action"],
          [OI["verm"], OI["blue"]], "B. How resolved obstacles are overcome (% of resolved)")
    for ax in axes:
        ax.legend(fontsize=7, frameon=False, loc="upper right")
    fig.suptitle("EXPLORATORY · Discovery half · raw LLM codings · bars = cell estimates, whiskers = work-clustered 95% CI",
                 fontsize=8, color="#555555", y=0.995)
    fig.tight_layout()
    fig.savefig(FIGS / "explore_resolution.png", dpi=200)


def exemplars(a: pd.DataFrame, b: pd.DataFrame) -> list[str]:
    out = ["## Exemplar candidates (quote verified verbatim against the passage or following text)", ""]
    a = a[[verified(q, t) for q, t in zip(a.get("quote", pd.Series([None] * len(a))), a.text)]]
    picks = [("guardian_conv", 1), ("inst", 1), ("fem_guardian_conv", 1), ("villain", 1)]
    for col, v in picks:
        s = a[a[col] == v].sample(min(6, (a[col] == v).sum()), random_state=SEED)
        for r in s.itertuples():
            out.append(f"- A/{col} | {r.Title[:60]} ({r.author_name}, {int(r.year_v2)}; {r.cell}) | {r.opponent_type}/{r.role}/"
                       f"{r.opponent_gender}/{r.acts_for} | \"{r.quote}\" | {r.passage_id}")
    ft = {}
    key = pd.read_parquet(OUT / "key_b.parquet")
    for f in sorted((OUT / "batches").glob("b_[0-9]*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            j = json.loads(line)
            ft[j["id"]] = j["passage"] + " " + j["following_text"]
    b = b[[verified(q, ft.get(i, "")) for q, i in zip(b.get("quote", pd.Series([None] * len(b))), b.oid)]]
    for m in ["chance_coincidence", "providence_fate", "technology", "institution", "own_action"]:
        s = b[(b.means == m) & (b.resolved_in_view == "yes")]
        s = s.sample(min(6, len(s)), random_state=SEED)
        for r in s.itertuples():
            out.append(f"- B/{m} | {r.Title[:60]} ({r.author_name}, {int(r.year_v2)}; {r.cell}) | obstacle: {r.obstacle_summary} | "
                       f"\"{r.quote}\" | {r.passage_id}")
    return out


def analyze() -> None:
    lines: list[str] = ["# explore_who_and_resolution: raw output (EXPLORATORY, Discovery only)", ""]
    a = analyze_a(lines)
    b = analyze_b(lines)
    agreement(lines)
    lines += exemplars(a, b)
    (OUT / "analysis_out.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    {"prepare": prepare, "check": check, "analyze": analyze, "reliability": reliability}[sys.argv[1]]()
