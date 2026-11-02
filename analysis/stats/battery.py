"""C-lite robustness battery (plan §4.7) and the pre-registered verdict rule.

Checks (each returns pass / fail / n.a.; a check that cannot run for missing data FAILS):
  1 leave-one-author-out   one-step influence jackknife over authors (exact refits via a grouped
                           jackknife when the effect has no influence matrix, i.e. H3)
  2 leave-one-decade-out   refit without each decade
  3 drop each major genre  refit without each genre holding >= 5% of works
  4 high-confidence dates  refit on date_confidence == "high"
  5 drop top-decile memorised works (memorization score)
  6 alternate model labels (naive alt-family labels vs naive primary labels on the same works)
  7 segmentation variants  (naive labels from 250/500-word segmentations vs primary naive; stub
                           taking alternate label tables)
  8 date permutation       null distribution; default permutes AUTHOR-LEVEL date profiles among
                           authors within genre (see prereg: permuting within author x genre
                           blocks leaves between-author chronology intact and is not a null)
  9 replication sample     same sign in ELTeC / Chicago / other frame
Pass rule for re-estimates (1-7): every directional component keeps the declared sign and at
least 50% of the primary magnitude. Permutation: one-sided permutation p < 0.05 for every
directional component. Replication: declared sign for every directional component.
Verdict: supported = Holm-significant AND passes >= ceil(7/9 * applicable) AND replication same sign;
unstable = Holm-significant but not the rest; null = not Holm-significant.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from analysis.stats.dsl import WorkData
from analysis.stats.models import Effect

HypFn = Callable[[WorkData], Effect]
CHECKS = ["leave_one_author_out", "leave_one_decade_out", "drop_genre", "high_conf_dates", "drop_memorized",
          "alt_model_labels", "segmentation", "date_permutation", "replication"]


@dataclass
class Check:
    name: str
    passed: bool | None          # None = not applicable
    detail: dict = field(default_factory=dict)


@dataclass
class BatteryResult:
    hypothesis: str
    checks: list[Check]
    holm_reject: bool
    verdict: str
    n_pass: int
    n_applicable: int
    need: int

    def table(self) -> pd.DataFrame:
        return pd.DataFrame([{"hypothesis": self.hypothesis, "check": c.name,
                              "result": "n/a" if c.passed is None else ("pass" if c.passed else "fail"),
                              **{k: v for k, v in c.detail.items() if np.isscalar(v) or isinstance(v, str)}}
                             for c in self.checks])


def _ref(primary: Effect) -> tuple[list[int], np.ndarray]:
    """Components a re-estimate must reproduce, and their reference signs.
    Directional tests: the tested components with their declared signs.
    Two-sided H1 (prereg v0.4): the tested components whose 95% CI excludes 0 in the primary fit,
    with their OBSERVED signs (e.g. 'outward' -> material up; 'inward' -> both); if none excludes 0,
    all tested components with observed signs (the battery is then moot: the verdict is null)."""
    idx = primary.tested_idx
    if primary.extra.get("two_sided"):
        sig = [i for i in idx if not (primary.components[i].ci()[0] <= 0 <= primary.components[i].ci()[1])]
        idx = sig or idx
        return idx, np.sign([primary.components[i].estimate for i in idx])
    return idx, np.array([primary.components[i].expected_sign for i in idx])


def _ests(e: Effect, idx: list[int] | None = None) -> np.ndarray:
    idx = e.tested_idx if idx is None else idx
    return np.array([e.components[i].estimate for i in idx])


def _signs(e: Effect) -> np.ndarray:
    return _ref(e)[1]


def holds(primary: Effect, variant: Effect | np.ndarray | None, frac: float = 0.5, ref: Effect | None = None) -> bool:
    """Every reference component keeps its reference sign and >= frac of the reference magnitude."""
    if variant is None:
        return False
    idx, s = _ref(primary)
    v = _ests(variant, idx) if isinstance(variant, Effect) else np.asarray(variant, float)
    r = _ests(ref or primary, idx)
    if np.any(~np.isfinite(v)):
        return False
    return bool(np.all(np.sign(v) == s) and np.all(np.abs(v) >= frac * np.abs(r)))


def _safe(fn: HypFn, wd: WorkData) -> Effect | None:
    try:
        return fn(wd)
    except Exception:            # an empty era / singular design counts as a failed re-estimate
        return None


# ------------------------------------------------------------------ individual checks

def leave_one_author_out(fn: HypFn, wd: WorkData, primary: Effect, n_groups: int = 20, seed: int = 0) -> Check:
    idx, s = _ref(primary)
    est = _ests(primary, idx)
    if primary.infl is not None:
        loo = est[None, :] - primary.infl[:, idx]
        G = len(loo)
        jk_se = np.sqrt((G - 1) / G * ((loo - loo.mean(0)) ** 2).sum(0))
        ok = np.all(np.sign(loo) == s, axis=1) & np.all(np.abs(loo) >= 0.5 * np.abs(est), axis=1)
        worst = int(np.argmin(np.min(s * loo / np.abs(est), axis=1)))
        authors = pd.factorize(wd.cov.author_key)[1]
        return Check("leave_one_author_out", bool(ok.all()),
                     {"method": "influence", "n_authors": G, "n_fail": int((~ok).sum()),
                      "worst_author": str(authors[worst]), "worst_estimate": float(loo[worst][0]),
                      "jackknife_se": float(jk_se[0])})
    codes, uniq = pd.factorize(wd.cov.author_key)
    grp = np.random.default_rng(seed).permutation(len(uniq)) % n_groups
    outs = []
    for gi in range(n_groups):
        e = _safe(fn, wd.subset(grp[codes] != gi))
        outs.append(holds(primary, e))
    return Check("leave_one_author_out", all(outs), {"method": f"grouped_jackknife_{n_groups}",
                                                     "n_fail": int(len(outs) - sum(outs))})


def leave_one_decade_out(fn: HypFn, wd: WorkData, primary: Effect) -> Check:
    res = {}
    for d in sorted(wd.cov.decade.unique()):
        res[int(d)] = holds(primary, _safe(fn, wd.subset(wd.cov.decade.values != d)))
    fails = [d for d, ok in res.items() if not ok]
    return Check("leave_one_decade_out", not fails, {"failed_decades": ",".join(map(str, fails)) or "-"})


def drop_genre(fn: HypFn, wd: WorkData, primary: Effect, min_share: float = 0.05) -> Check:
    vc = wd.cov.genre.value_counts(normalize=True)
    res = {g: holds(primary, _safe(fn, wd.subset(wd.cov.genre.values != g))) for g in vc[vc >= min_share].index}
    fails = [g for g, ok in res.items() if not ok]
    return Check("drop_genre", not fails, {"failed_genres": ",".join(fails) or "-", "n_genres": len(res)})


def subset_check(name: str, fn: HypFn, wd: WorkData, primary: Effect, col: str,
                 mask_fn: Callable[[pd.Series], np.ndarray]) -> Check:
    if col not in wd.cov:
        return Check(name, False, {"note": f"not run: column {col} missing"})
    m = mask_fn(wd.cov[col])
    e = _safe(fn, wd.subset(m))
    return Check(name, holds(primary, e), {"n_works": int(m.sum()),
                                           "estimate": float(_ests(e, _ref(primary)[0])[0]) if e else float("nan")})


def label_variant_check(name: str, fn: HypFn, primary: Effect, variants: list[tuple[WorkData, WorkData]] | None) -> Check:
    """variants: (variant-label WorkData, primary-label WorkData on the same works), both naive."""
    if not variants:
        return Check(name, False, {"note": "not run: no variant label table supplied"})
    oks, ests = [], []
    for var_wd, prim_wd in variants:
        ev, ep = _safe(fn, var_wd), _safe(fn, prim_wd)
        oks.append(ev is not None and ep is not None and holds(primary, ev, ref=ep))
        ests.append(float(_ests(ev, _ref(primary)[0])[0]) if ev else float("nan"))
    return Check(name, all(oks), {"n_variants": len(variants), "first_estimate": ests[0]})


def permute_years(cov: pd.DataFrame, rng: np.random.Generator, mode: str = "author_profile") -> np.ndarray:
    """mode="author_profile": within each genre, permute authors' mean years among authors and shift
    each work by (new mean - old mean); keeps within-author spread and the genre's date mix.
    mode="literal": permute years among works within author x genre blocks (plan wording)."""
    y = cov.year.values.astype(float).copy()
    if mode == "literal":
        for _, idx in cov.groupby(["author_key", "genre"]).indices.items():
            y[idx] = y[rng.permutation(idx)]
        return y
    for _, gi in cov.groupby("genre").indices.items():
        sub = cov.iloc[gi]
        am = sub.groupby("author_key").year.mean()
        newm = pd.Series(rng.permutation(am.values), index=am.index)
        shift = (newm - am).loc[sub.author_key].values
        y[gi] = y[gi] + shift
    return np.clip(np.round(y), cov.year.min(), cov.year.max())


def date_permutation(fn: HypFn, wd: WorkData, primary: Effect, n_perm: int = 200, seed: int = 0,
                     mode: str = "author_profile") -> Check:
    rng = np.random.default_rng(seed)
    idx, s = _ref(primary)
    est = _ests(primary, idx)
    null = []
    for _ in range(n_perm):
        e = _safe(fn, wd.with_years(permute_years(wd.cov, rng, mode)))
        null.append(_ests(e, idx) if e else np.full(len(est), np.nan))
    null = np.array(null)
    p = (1 + np.nansum(s * null >= s * est, axis=0)) / (1 + np.isfinite(null).sum(0))
    return Check("date_permutation", bool(np.all(p < 0.05)),
                 {"mode": mode, "n_perm": n_perm, "p_perm": float(p.max()),
                  "null_mean": float(np.nanmean(null[:, 0])), "null_sd": float(np.nanstd(null[:, 0]))})


def permute_canon(cov: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    """TF null (prereg v0.5): permute AUTHOR-level canonical flags among authors within era blocks
    (era of the author's mean year), keeping the canonical share per era and authors intact."""
    a = cov.groupby("author_key").agg(year=("year", "mean"), canonical=("canonical", "first"))
    a["era"] = np.where(a.year < 1850, "E", np.where(a.year < 1885, "M", "L"))
    newc = a.canonical.copy()
    for _, idx in a.groupby("era").groups.items():
        newc.loc[idx] = rng.permutation(a.canonical.loc[idx].values)
    return newc.loc[cov.author_key].values


def canon_permutation(fn: HypFn, wd: WorkData, primary: Effect, n_perm: int = 200, seed: int = 0) -> Check:
    rng = np.random.default_rng(seed)
    idx, s = _ref(primary)
    est = _ests(primary, idx)
    null = []
    for _ in range(n_perm):
        cov = wd.cov.assign(canonical=permute_canon(wd.cov, rng))
        e = _safe(fn, WorkData(cov, wd.Y, wd.method, wd.info))
        null.append(_ests(e, idx) if e else np.full(len(est), np.nan))
    null = np.array(null)
    p = (1 + np.nansum(s * null >= s * est, axis=0)) / (1 + np.isfinite(null).sum(0))
    return Check("date_permutation", bool(np.all(p < 0.05)),
                 {"mode": "canon_author_within_era", "n_perm": n_perm, "p_perm": float(p.max())})


def replication(fn: HypFn, primary: Effect, rep: WorkData | None, rep_fn: HypFn | None = None) -> Check:
    """rep_fn lets the replication use another era window (e.g. ELTeC starts 1841)."""
    if rep is None:          # prereg v0.5 (review P9.5): replication is reported when available, never a gate
        return Check("replication", None, {"note": "not run: no replication sample (optional)"})
    e = _safe(rep_fn or fn, rep)
    idx, s = _ref(primary)
    ok = e is not None and bool(np.all(np.sign(_ests(e, idx)) == s))
    return Check("replication", ok, {"estimate": float(_ests(e, idx)[0]) if e else float("nan"),
                                     "se": float(e.components[idx[0]].se) if e else float("nan")})


# ------------------------------------------------------------------ battery + verdict

def verdict(holm_reject: bool, checks: list[Check]) -> tuple[str, int, int, int]:
    app = [c for c in checks if c.passed is not None]
    n_pass = sum(bool(c.passed) for c in app)
    need = math.ceil(7 / 9 * len(app))
    rep = next((c for c in checks if c.name == "replication"), None)
    rep_ok = rep is None or rep.passed is None or bool(rep.passed)   # optional since v0.5
    if not holm_reject:
        return "null", n_pass, len(app), need
    if n_pass >= need and rep_ok:
        return "supported", n_pass, len(app), need
    return "unstable", n_pass, len(app), need


def run_battery(name: str, fn: HypFn, wd: WorkData, holm_reject: bool, primary: Effect | None = None, *,
                alt: list[tuple[WorkData, WorkData]] | None = None,
                segmentation: list[tuple[WorkData, WorkData]] | None = None,
                replication_wd: WorkData | None = None, replication_fn: HypFn | None = None,
                n_perm: int = 200, seed: int = 0, not_applicable: tuple = (),
                perm_mode: str = "author_profile") -> BatteryResult:
    """perm_mode="canon" uses canon_permutation (TF); otherwise date permutation."""
    primary = primary or fn(wd)
    checks = [
        leave_one_author_out(fn, wd, primary, seed=seed),
        leave_one_decade_out(fn, wd, primary),
        drop_genre(fn, wd, primary),
        subset_check("high_conf_dates", fn, wd, primary, "date_confidence", lambda s: (s == "high").values),
        subset_check("drop_memorized", fn, wd, primary, "memorization", lambda s: (s < s.quantile(0.9)).values),
        label_variant_check("alt_model_labels", fn, primary, alt),
        label_variant_check("segmentation", fn, primary, segmentation),
        (canon_permutation(fn, wd, primary, n_perm, seed) if perm_mode == "canon"
         else date_permutation(fn, wd, primary, n_perm, seed, perm_mode)) if "date_permutation" not in not_applicable
        else Check("date_permutation", None, {"note": "n/a for this hypothesis"}),
        replication(fn, primary, replication_wd, replication_fn),
    ]
    for c in checks:
        if c.name in not_applicable:
            c.passed = None
    v, n_pass, n_app, need = verdict(holm_reject, checks)
    cls = primary.extra.get("classification")
    if cls and v != "null":
        v = f"{v}: {cls}"          # e.g. "supported: outward" (two-sided H1, prereg v0.4)
    return BatteryResult(name, checks, holm_reject, v, n_pass, n_app, need)


# ------------------------------------------------------------------ CLI (real data)

def _naive_pair(variant_labels: pd.DataFrame, labels: pd.DataFrame, split: str) -> tuple[WorkData, WorkData]:
    """(variant naive, primary naive) on the works covered by the variant table."""
    from analysis.stats.dsl import prepare
    v = prepare(variant_labels, method="naive", split=split, strata=None)
    p = prepare(labels[labels.work_id.isin(set(v.cov.work_id))], method="naive", split=split)
    return v, p


def run_all(labels_path: str, human_path: str, frame_path: str, keywords_path: str | None = None,
            alt_path: str | None = None, seg_paths: tuple = (), rep_labels: str | None = None,
            rep_human: str | None = None, rep_frame: str | None = None, split: str = "confirmation",
            n_perm: int = 200, out_dir: str = "analysis/stats/out/confirmatory",
            expert: str = "grad", teacher: str = "teacher", genre_path: str | None = None,
            works_path: str | None = None, canon_path: str | None = None) -> pd.DataFrame:
    """Registered v0.5 pipeline: attach genre + canon, annotator rules, expert-anchored DSL,
    confirmatory family (TF + H1 co-primary at 0.025), battery on the co-primaries, verdicts."""
    import functools
    from pathlib import Path

    from analysis.stats import annotators as ann
    from analysis.stats import models
    from analysis.stats.dsl import prepare_anchored
    labels, human = pd.read_parquet(labels_path), pd.read_parquet(human_path)
    genre = pd.read_parquet(genre_path) if genre_path else None
    if genre is not None:
        labels = models.attach_genre(labels, genre)
    if canon_path:
        labels = models.attach_canon(labels, pd.read_parquet(canon_path))
    ref_cov = None
    if works_path:
        w = pd.read_parquet(works_path)
        if "in_primary_cap" in w:
            w = w[w.in_primary_cap & w.date_confidence.isin(["high", "medium"])]
        if "origin" not in w and "origin_locc" in w:
            w = w.assign(origin=w.origin_locc)
        ref_cov = models.reference_covariates(w, genre)
        if canon_path:
            ref_cov = ref_cov.merge(pd.read_parquet(canon_path)[["work_id", "canonical"]], on="work_id", how="left")
            ref_cov["canonical"] = ref_cov.canonical.fillna(False).astype(bool)
    frame = pd.read_parquet(frame_path)
    kw = pd.read_csv(keywords_path) if keywords_path else None
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    # annotator rules (prereg v0.5 §5.1): peers vs the grad-student anchor; teacher items descriptive
    rep_k = ann.expert_agreement(human[human.annotator != teacher], expert=expert)
    excl = ann.exclusions(rep_k)
    rep_k.assign(excluded=rep_k.annotator.isin(excl)).to_csv(out / "annotator_agreement.csv", index=False)
    ann.overlap_agreement(human[~human.annotator.isin({expert, teacher})], labels, expert=expert).to_csv(
        out / "overlap_agreement.csv", index=False)
    if teacher in set(human.annotator):
        ann.expert_agreement(human[human.annotator.isin({teacher, expert})], expert=teacher).to_csv(
            out / "teacher_vs_grad_descriptive.csv", index=False)
    wd = prepare_anchored(labels, human, frame, expert=expert, exclude_annotators={teacher} | excl, split=split)
    design = models.Design.from_data(wd)
    tab, effs = models.confirmatory(wd, kw, design=design, ref_cov=ref_cov)
    rej = tab.groupby("test").reject.first().to_dict()
    alt = [_naive_pair(pd.read_parquet(alt_path), labels, split)] if alt_path else None
    seg = [_naive_pair(pd.read_parquet(p), labels, split) for p in seg_paths] or None
    fns = {"H1": functools.partial(models.h1, design=design, ref_cov=ref_cov)}
    if "TF" in effs:
        fns["TF"] = functools.partial(models.two_fictions, design=design, ref_cov=ref_cov)
    tabs = []
    for k, fn in fns.items():
        r = run_battery(k, fn, wd, bool(rej[k]), effs[k], alt=alt, segmentation=seg, replication_wd=None,
                        n_perm=n_perm, perm_mode="canon" if k == "TF" else "author_profile")
        tabs.append(r.table().assign(verdict=r.verdict, n_pass=r.n_pass, need=r.need))
    bt = pd.concat(tabs)
    tab.to_csv(out / "confirmatory.csv", index=False)
    bt.to_csv(out / "battery.csv", index=False)
    return bt


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="confirmatory tests + battery + verdicts on real data")
    ap.add_argument("labels"); ap.add_argument("human"); ap.add_argument("frame")
    ap.add_argument("--keywords"); ap.add_argument("--alt"); ap.add_argument("--seg", action="append", default=[])
    ap.add_argument("--rep-labels"); ap.add_argument("--rep-human"); ap.add_argument("--rep-frame")
    ap.add_argument("--split", default="confirmation"); ap.add_argument("--n-perm", type=int, default=200)
    ap.add_argument("--genre", default="data/work/genre.parquet", help="registered genre variable")
    ap.add_argument("--works", default="data/work/works_v2.parquet", help="metadata for the pooled standard")
    ap.add_argument("--canon", default="data/work/canon.parquet", help="registered canonicity flag")
    ap.add_argument("--expert", default="grad"); ap.add_argument("--teacher", default="teacher")
    a = ap.parse_args()
    import os
    ex = lambda p: p if p and os.path.exists(p) else None
    bt = run_all(a.labels, a.human, a.frame, a.keywords, a.alt, tuple(a.seg), a.rep_labels, a.rep_human,
                 a.rep_frame, a.split, a.n_perm, expert=a.expert, teacher=a.teacher, genre_path=ex(a.genre),
                 works_path=ex(a.works), canon_path=ex(a.canon))
    print(bt.groupby("hypothesis")[["verdict", "n_pass", "need"]].first())
