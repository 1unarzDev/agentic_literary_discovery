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


def draw_audit(lab: pd.DataFrame, teaching_authors: set, rng: np.random.Generator,
               n_target: int = 200, group_col: str = "group") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Probability sample for DSL/PPI. `lab` needs era, <group_col>, split, stratum, author_key, passage_id.

    group_col: "group" (locus groups, the original design) or e.g. "dgroup" = domain_group() strata
    (the registered final design: Confirmation only, era x predicted-domain group, n_target ~1800).
    Restrict `lab` to the Confirmation split before calling to draw a Confirmation-only audit.

    Returns (audit, frame). `frame` lists EVERY pool passage with its audit cell and first-order
    inclusion probability pi_audit = n_cell / N_cell (0 for passages outside the pool); DSL needs
    pi for unaudited passages too, so the frame must be persisted (analysis/stats/README.md).
    """
    pool = lab[~lab.author_key.isin(teaching_authors) & (lab.stratum == "random")]
    cells = pool.groupby(["era", group_col, "split"])
    n_cells = cells.ngroups
    per = max(2, int(np.ceil(n_target / n_cells)))
    rows, frame = [], []
    for key, g in cells:
        k = min(per, len(g))
        s = g.sample(n=k, random_state=int(rng.integers(1e9)))
        s = s.assign(audit_cell="|".join(key), cell_N=len(g), cell_n=k, weight=len(g) / k)
        rows.append(s)
        frame.append(pd.DataFrame({"passage_id": g.passage_id.values, "audit_cell": "|".join(key),
                                   "pi_audit": k / len(g)}))
    audit = pd.concat(rows)
    audit = audit.sample(frac=1, random_state=SEED)
    return audit, pd.concat(frame, ignore_index=True)


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
