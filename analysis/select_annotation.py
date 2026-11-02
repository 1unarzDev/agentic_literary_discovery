"""Select the two human-annotation sets from model labels (run Thu Nov 5).

TEACHING (~100, Discovery only, authors then excluded from evaluation):
  - prototypes: per domain, the highest-confidence label+alt_label agreements with verified quotes (4/domain)
  - boundary: label vs alt_label disagreements on has_obstacle or locus, or confidence in [0.4, 0.7] (30)
  - cross-era pairs: per domain, one pre-1850 + one post-1885 prototype with matching domain (2/domain)
AUDIT (~200, both splits, probability sample with recorded inclusion weights):
  stratified by era (3) x predicted label group (obstacle-material / social / internal / no-obstacle) x split,
  equal allocation per cell, simple random within cell -> weight = N_cell / n_cell.
40 audit items are double-coded (both annotators); the rest are split between annotators.

usage: uv run python -I analysis/select_annotation.py labels.parquet [alt_labels.parquet]
writes data/work/annotation/{teaching,audit}.parquet and an items JSON for /v1/admin/ann_items
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/work/annotation"
SEED = 20261105
ANNOTATORS = ["student", "teacher"]
DOMAINS = ["DISTANCE_TRAVEL", "COMMUNICATION_INFORMATION", "DARKNESS_VISIBILITY", "ILLNESS_BODY_DEATH",
           "MONEY_PROPERTY_LAW", "SOCIAL_RANK_CONVENTION", "INTERPERSONAL_CONFLICT", "INNER_STATE", "NATURE_WEATHER"]


def era(decade: int) -> str:
    return "early_1800_1849" if decade < 1850 else ("mid_1850_1884" if decade < 1885 else "late_1885_1920")


def group(r) -> str:
    if r.has_obstacle != "yes":
        return "no_obstacle"
    return {"material_external": "material", "social_institutional": "social",
            "internal_psychological": "internal"}.get(r.locus, "other")


# H2 audit strata (prereg R3): predicted primary domain, merged to 8 groups that also nest the
# locus groups (material = DIST/DARK/ILLNESS/NATURE split three ways; social; internal)
DOMAIN_GROUP = {"COMMUNICATION_INFORMATION": "comm", "DISTANCE_TRAVEL": "distance", "DARKNESS_VISIBILITY": "darkness",
                "ILLNESS_BODY_DEATH": "material_other", "NATURE_WEATHER": "material_other",
                "MONEY_PROPERTY_LAW": "social", "SOCIAL_RANK_CONVENTION": "social", "INTERPERSONAL_CONFLICT": "social",
                "INNER_STATE": "internal", "OTHER": "other"}


def domain_group(r) -> str:
    """Audit stratum by predicted primary (first-listed) domain; 'no_obstacle' if no obstacle."""
    if r.has_obstacle != "yes":
        return "no_obstacle"
    d = list(r.domains) if r.domains is not None else []
    return DOMAIN_GROUP.get(d[0], "other") if d else "other"


def item_id(pid: str) -> str:
    # opaque id: never reveals pg number to annotators
    return "it_" + hashlib.sha256(f"{SEED}:{pid}".encode()).hexdigest()[:12]


LABEL_DERIVED = {"group", "dgroup", "has_obstacle", "locus", "domains"}   # never strata under the seal (prereg v0.5)


def era_by_year(year) -> np.ndarray:
    """Estimand eras on YEAR cuts (prereg v0.5): E 1800-1849, M 1850-1884, L 1885-1929."""
    y = np.asarray(year)
    return np.where(y < 1850, "E_1800_1849", np.where(y < 1885, "M_1850_1884", "L_1885_1929"))


def draw_audit(lab: pd.DataFrame, teaching_authors: set, rng: np.random.Generator,
               n_target: int = 200, group_col: str | list = "group", balance_on: list | None = None,
               metadata_only: bool = False, n_min: int = 2) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Probability sample for DSL/PPI. `lab` needs era, <group_col(s)>, split, stratum, author_key, passage_id.

    Strata = era x group_col(s) x split. Allocation:
      balance_on=None  : equal n per stratum (legacy designs, n_cell = min(per, N_cell));
      balance_on=[...] : n_target split equally over the cells of `balance_on` (x split), then within
                         each such cell proportional to N_cell (at least n_min, at most N_cell).
    metadata_only=True refuses label-derived strata (LABEL_DERIVED): the registered v0.5 seal fix,
    because N_cell of predicted-label strata reveals the naive Confirmation answer.

    Registered v0.5 call (Confirmation, before registration):
      draw_audit_metadata(meta_conf, rng, n_target) == draw_audit(meta_conf, set(), rng, n_target,
          group_col=["genre", "canonical"], balance_on=["era", "canonical"], metadata_only=True)
    with meta_conf.era = era_by_year(year). If `canonical` is not yet available, use
    group_col=["genre"], balance_on=["era"].

    Returns (audit, frame). `frame` lists EVERY pool passage with its audit cell and first-order
    inclusion probability pi_audit = n_cell / N_cell; DSL needs pi for unaudited passages too, so the
    frame must be persisted. Do not print or publish N_cell before registration; deposit
    cell_table_hash(frame) instead.
    """
    gcols = [group_col] if isinstance(group_col, str) else list(group_col)
    if metadata_only and (set(gcols) | set(balance_on or [])) & LABEL_DERIVED:
        raise ValueError(f"label-derived strata {set(gcols) & LABEL_DERIVED} break the Confirmation seal")
    pool = lab[~lab.author_key.isin(teaching_authors) & (lab.stratum == "random")]
    keys = ["era"] + [c for c in gcols if c != "era"] + ["split"]
    cells = pool.groupby(keys)
    if balance_on is None:
        per = max(n_min, int(np.ceil(n_target / cells.ngroups)))
        alloc = {k: min(per, len(g)) for k, g in cells}
    else:
        bkeys = list(dict.fromkeys(list(balance_on) + ["split"]))
        Ncell = cells.size()
        bal = Ncell.groupby(level=[keys.index(b) for b in bkeys])
        budget = n_target / bal.ngroups
        alloc = {}
        for _, sub in bal:
            share = budget * sub / sub.sum()
            for k, N in sub.items():
                alloc[k] = int(min(N, max(n_min, round(share[k]))))
    rows, frame = [], []
    for key, g in cells:
        key = key if isinstance(key, tuple) else (key,)
        k = alloc[key]
        cell = "|".join(map(str, key))
        s = g.sample(n=k, random_state=int(rng.integers(1e9)))
        s = s.assign(audit_cell=cell, cell_N=len(g), cell_n=k, weight=len(g) / k)
        rows.append(s)
        frame.append(pd.DataFrame({"passage_id": g.passage_id.values, "audit_cell": cell, "pi_audit": k / len(g)}))
    audit = pd.concat(rows)
    audit = audit.sample(frac=1, random_state=SEED)
    return audit, pd.concat(frame, ignore_index=True)


def draw_audit_metadata(meta: pd.DataFrame, rng: np.random.Generator, n_target: int = 1800,
                        use_canon: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Registered v0.5 audit draw (seal-safe): strata era(year) x genre x canonical, budget balanced
    over era x canonical, proportional to N within. `meta` = Confirmation passages with passage_id,
    work_id, author_key, year, split, stratum, genre (+ canonical). No label columns are read."""
    m = meta.assign(era=era_by_year(meta.year.values))
    if use_canon and "canonical" in m:
        m = m.assign(canonical=m.canonical.astype(bool).map({True: "canon", False: "noncanon"}))
        return draw_audit(m, set(), rng, n_target, group_col=["genre", "canonical"],
                          balance_on=["era", "canonical"], metadata_only=True)
    return draw_audit(m, set(), rng, n_target, group_col=["genre"], balance_on=["era"], metadata_only=True)


def cell_table_hash(frame: pd.DataFrame) -> str:
    """SHA-256 of the (cell, N_cell, pi) table: deposit this, not the counts, before registration."""
    t = frame.groupby("audit_cell").agg(N=("passage_id", "size"), pi=("pi_audit", "first")).reset_index()
    txt = t.sort_values("audit_cell").to_csv(index=False)
    return hashlib.sha256(txt.encode()).hexdigest()


def main(lab_path: str, alt_path: str | None = None) -> None:
    rng = np.random.default_rng(SEED)
    lab = pd.read_parquet(lab_path)  # columns: passage_id, work_id, author_key, decade, split, stratum, text, ctx_*, has_obstacle, domains, locus, confidence, quote_status
    lab["era"] = lab.decade.map(era)
    lab["group"] = lab.apply(group, axis=1)
    if alt_path:
        alt = pd.read_parquet(alt_path)[["passage_id", "has_obstacle", "locus", "domains"]].add_prefix("alt_")
        lab = lab.merge(alt, left_on="passage_id", right_on="alt_passage_id", how="left")
    lab = lab[lab.stratum.isin(["random", "enrich_comm", "enrich_mob", "enrich_dark"])]

    # ---------------- teaching (Discovery only)
    d = lab[lab.split == "discovery"]
    proto = []
    for dom in DOMAINS:
        c = d[(d.has_obstacle == "yes") & d.domains.map(lambda x: dom in list(x)) & (d.quote_status.isin(["exact", "normalized"]))]
        if "alt_has_obstacle" in c:
            c = c[(c.alt_has_obstacle == "yes") & c.alt_domains.map(lambda x: x is not None and dom in list(x))]
        c = c.sort_values("confidence", ascending=False)
        for e in ("early_1800_1849", "late_1885_1920"):
            proto.append(c[c.era == e].head(1).assign(t_reason=f"crossera_{dom}"))
        proto.append(c.head(12).sample(n=min(4, len(c.head(12))), random_state=SEED).assign(t_reason=f"proto_{dom}"))
    proto = pd.concat(proto).drop_duplicates("passage_id")
    if "alt_has_obstacle" in d:
        bnd = d[(d.alt_has_obstacle.notna()) & ((d.has_obstacle != d.alt_has_obstacle) | (d.locus != d.alt_locus))]
    else:
        bnd = d.iloc[0:0]
    bnd = pd.concat([bnd, d[d.confidence.between(0.4, 0.7)]]).drop_duplicates("passage_id")
    bnd = bnd[~bnd.passage_id.isin(proto.passage_id)].sample(n=min(30, len(bnd)), random_state=SEED).assign(t_reason="boundary")
    teaching = pd.concat([proto, bnd])
    teaching_authors = set(teaching.author_key)

    # ---------------- audit (probability sample; exclude teaching authors)
    audit, frame = draw_audit(lab, teaching_authors, rng)
    n_cells = frame.audit_cell.nunique()
    dbl = set(audit.passage_id.iloc[:40])
    rest = list(audit.passage_id.iloc[40:])

    OUT.mkdir(parents=True, exist_ok=True)
    teaching.to_parquet(OUT / "teaching.parquet", index=False)
    audit.to_parquet(OUT / "audit.parquet", index=False)
    frame.to_parquet(OUT / "audit_frame.parquet", index=False)  # pi_audit for every pool passage (DSL)

    items = []
    for _, r in teaching.iterrows():
        items.append({"item_id": item_id(r.passage_id), "passage_id": r.passage_id, "text": r.text,
                      "ctx_before": r.ctx_before, "ctx_after": r.ctx_after, "set": "teaching", "assign": ANNOTATORS})
    for i, (_, r) in enumerate(audit.iterrows()):
        assign = ANNOTATORS if r.passage_id in dbl else [ANNOTATORS[rest.index(r.passage_id) % 2]]
        items.append({"item_id": item_id(r.passage_id), "passage_id": r.passage_id, "text": r.text,
                      "ctx_before": r.ctx_before, "ctx_after": r.ctx_after, "set": "audit", "assign": assign})
    (OUT / "ann_items.json").write_text(json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8")
    per_ann = {a: sum(a in it["assign"] for it in items) for a in ANNOTATORS}
    print(f"teaching={len(teaching)} audit={len(audit)} cells={n_cells} per-annotator={per_ann}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
