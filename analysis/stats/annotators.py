"""Annotator reliability and the pre-registered exclusion rule (docs/prereg.md §3.4).

- kappa of each non-expert annotator vs the expert reference (teacher) on the 30 expert items, on
  the H1 construct `locus` (4 categories: none / material / social / internal) and on has_obstacle;
- pairwise kappa on the ~10% overlap pairs, overall and by era (era-differential reliability check);
- exclusion: an annotator whose locus kappa vs expert is < 0.40 (on >= 20 jointly labelled expert
  items) is excluded; all of their rows are dropped before DSL and pi is recomputed per cell from
  the retained labels (dsl.audit_design), valid because items were randomly assigned to annotators.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from analysis.stats.dsl import TARGETS, _era

KAPPA_MIN = 0.40
MIN_EXPERT_ITEMS = 20


def cohen_kappa(a: np.ndarray, b: np.ndarray) -> float:
    a, b = np.asarray(a), np.asarray(b)
    if len(a) == 0:
        return float("nan")
    cats = np.union1d(a, b)
    po = np.mean(a == b)
    pe = sum(np.mean(a == c) * np.mean(b == c) for c in cats)
    return float((po - pe) / (1 - pe)) if pe < 1 else 1.0


def _codes(h: pd.DataFrame, target: str) -> pd.Series:
    return pd.Series(TARGETS[target].fn(h), index=h.index)


def expert_agreement(human: pd.DataFrame, expert: str = "teacher", targets=("locus", "obstacle")) -> pd.DataFrame:
    """kappa of each annotator vs the expert on items both labelled."""
    ex = human[human.annotator == expert].set_index("passage_id")
    rows = []
    for a, g in human[human.annotator != expert].groupby("annotator"):
        g = g[g.passage_id.isin(ex.index)].set_index("passage_id")
        r = {"annotator": a, "n_expert_items": len(g)}
        for t in targets:
            r[f"kappa_{t}"] = cohen_kappa(TARGETS[t].fn(g.reset_index()), TARGETS[t].fn(ex.loc[g.index].reset_index()))
        rows.append(r)
    return pd.DataFrame(rows)


def exclusions(report: pd.DataFrame, kappa_min: float = KAPPA_MIN, min_items: int = MIN_EXPERT_ITEMS) -> set:
    """Registered rule: exclude annotators with locus kappa vs expert < kappa_min. Annotators with
    fewer than min_items expert items are excluded too (cannot be certified)."""
    bad = report[(report.kappa_locus < kappa_min) | (report.n_expert_items < min_items)]
    return set(bad.annotator)


def overlap_agreement(human: pd.DataFrame, labels: pd.DataFrame | None = None, expert: str = "teacher",
                      expert_items: set | None = None, target: str = "locus") -> pd.DataFrame:
    """Pairwise kappa on overlap items (expert items excluded), overall and by era if `labels`
    (with passage_id, decade) is given."""
    h = human[(human.annotator != expert)]
    if expert_items:
        h = h[~h.passage_id.isin(expert_items)]
    multi = h.groupby("passage_id").annotator.nunique()
    h = h[h.passage_id.isin(multi[multi >= 2].index)]
    h = h.assign(code=TARGETS[target].fn(h))
    if labels is not None:
        h = h.merge(labels[["passage_id", "decade"]], on="passage_id", how="left")
        h["era"] = _era(h.decade.fillna(1900).astype(int).values)
    out = []
    groups = [("all", h)] + (list(h.groupby("era")) if labels is not None else [])
    for name, g in groups:
        w = g.pivot_table(index="passage_id", columns="annotator", values="code", aggfunc="first")
        a_all, b_all = [], []
        for x, y in itertools.combinations(w.columns, 2):
            m = w[x].notna() & w[y].notna()
            a_all += list(w.loc[m, x])
            b_all += list(w.loc[m, y])
        out.append({"subset": name, "n_pairs": len(a_all), f"kappa_{target}": cohen_kappa(a_all, b_all)})
    return pd.DataFrame(out)
