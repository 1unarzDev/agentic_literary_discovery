"""Power / minimum detectable effect (MDE) for the H1 era contrast (material share of obstacles,
1800-39 vs 1885-1920, standardised identity-link DSL model), by simulation.

For each grid point (works per split x passages per work x author ICC x obstacle prevalence) a
corpus is simulated; on the Confirmation split we compute the cluster-robust SE of the contrast for
  oracle      true labels on every passage (the floor: infinite, perfect audit)
  dsl_raw / dsl_calib   single-phase DSL with the select_annotation audit at several sizes
  two_phase   Tier-3 model on a stratified probability sample of n3 passages, humans nested in it
MDE = (z_{1-a/2} + z_{0.80}) * SE, reported in percentage points for a = 0.05 and a = 0.01
(the first Holm step for 5 tests). The cluster-robust SE is validated as an estimate of the
sampling SD in validate.py, so SE-based MDEs are used here.

usage: uv run python -m analysis.stats.power [--reps 2] [--procs 16] [--quick]
writes analysis/stats/out/power_raw.csv and power_mde.csv
"""
from __future__ import annotations

import argparse
import itertools
import multiprocessing as mp
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from analysis.select_annotation import draw_audit
from analysis.stats import dsl, models
from analysis.stats.simulate import ERAS3, LLMNoise, SimConfig, group_vec, simulate

OUT = Path(__file__).resolve().parent / "out"
Z = {0.05: stats.norm.isf(0.025) + stats.norm.isf(0.2), 0.01: stats.norm.isf(0.005) + stats.norm.isf(0.2)}
AUDITS = (100, 250, 500, 1000, 2000, 4000)              # human labels per split (single phase)
TWO_PHASE = ((5000, 250), (5000, 500), (10000, 500), (10000, 1000))   # (Tier-3 n, human n) per split
TIER3_ACC = (0.86, 0.89, 0.92)                          # Tier-3 locus-category accuracy by era
NOISE = {"base": LLMNoise(),
         "good": LLMNoise(sens=(0.88, 0.91, 0.94), spec=(0.90, 0.92, 0.94), dom_acc=(0.78, 0.83, 0.88),
                          cause_acc=(0.7, 0.75, 0.8))}


H1_ALLOC = {"early": 0.45, "mid": 0.10, "late": 0.45}   # recommended allocation over H1 windows


def draw_h1_aligned(lab: pd.DataFrame, n: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Recommended audit: strata = H1 window (1800-39 / 1840-84 / 1885-1920+) x predicted group,
    era allocation H1_ALLOC, equal across groups within era, SRS within cell. Returns (R, pi)."""
    yr = lab.year.values
    win = np.where(yr < 1840, "early", np.where(yr < 1885, "mid", "late"))
    cell = pd.Series(win).astype(str) + "|" + pd.Series(group_vec(lab))
    R = np.zeros(len(lab), bool)
    pi = np.zeros(len(lab))
    for key, idx in cell.groupby(cell).groups.items():
        idx = np.asarray(idx)
        e = key.split("|")[0]
        k = min(len(idx), int(np.ceil(n * H1_ALLOC[e] / 4)))
        R[rng.choice(idx, k, replace=False)] = True
        pi[idx] = k / len(idx)
    return R, pi


def _se_h1(lab: pd.DataFrame, Yt: np.ndarray, design, method: str) -> float:
    wd = dsl.aggregate_to_works(lab, {"locus": Yt}, method)
    models.LINK["default"] = "identity"
    e = models.h1(wd, design)
    return e.components[0].se, e.components[0].estimate


def one_point(args) -> list[dict]:
    (W, m, icc, prev, noise, seed), audits, two_phase = args
    cfg = SimConfig(n_works=2 * W, passages_per_work=m, icc_author=icc, prevalence=prev,
                    noise=NOISE[noise], seed=seed)
    c = simulate(cfg, audit=False)
    lab = c.labels[c.labels.split == "confirmation"].reset_index(drop=True)
    tru = c.truth.set_index("passage_id").loc[lab.passage_id].reset_index()
    T = dsl.TARGETS["locus"]
    yhat, y = T.fn(lab), T.fn(tru)
    K = T.K
    base = {"works_per_split": W, "passages_per_work": m, "icc": icc, "prevalence": prev, "noise": noise,
            "seed": seed, "early_works": int((lab.drop_duplicates("work_id").year < 1840).sum())}
    wd0 = dsl.aggregate_to_works(lab, {"locus": dsl.onehot(y, K)}, "oracle")
    design = models.Design.from_data(wd0)
    rows = []
    se, est = _se_h1(lab, dsl.onehot(y, K), design, "oracle")
    rows.append({**base, "estimator": "oracle", "n_human": np.inf, "n_tier3": 0, "se": se, "est": est,
                 "n_human_nominal": -1, "n_tier3_nominal": 0})
    se, est = _se_h1(lab, dsl.onehot(yhat, K), design, "naive")
    rows.append({**base, "estimator": "naive", "n_human": 0, "n_tier3": 0, "se": se, "est": est,
                 "n_human_nominal": 0, "n_tier3_nominal": 0})
    sel = lab.assign(era=np.array(ERAS3, dtype=object)[np.searchsorted([1850, 1885], lab.decade.values, side="right")],
                     group=group_vec(lab))
    rng = np.random.default_rng(seed + 7)
    pos = pd.Series(np.arange(len(lab)), index=lab.passage_id)
    folds = dsl._fold_ids(lab.author_key, 5, seed)
    for n in audits:
        aud, frame = draw_audit(sel, set(), rng, n_target=n)
        pi = frame.set_index("passage_id").pi_audit.loc[lab.passage_id].values
        R = np.zeros(len(lab), bool)
        R[pos.loc[aud.passage_id].values] = True
        for g in ("raw", "calib"):
            Yt = dsl.pseudo_outcomes(yhat, y, R, pi, K, method=g, folds=folds)
            se, est = _se_h1(lab, Yt, design, f"dsl_{g}")
            rows.append({**base, "estimator": f"dsl_{g}", "n_human": int(R.sum()), "n_tier3": 0, "se": se, "est": est,
                         "n_human_nominal": n, "n_tier3_nominal": 0})
        R, pi = draw_h1_aligned(lab, n, rng)
        Yt = dsl.pseudo_outcomes(yhat, y, R, pi, K, method="calib", folds=folds)
        se, est = _se_h1(lab, Yt, design, "dsl_calib_h1alloc")
        rows.append({**base, "estimator": "dsl_calib_h1alloc", "n_human": int(R.sum()), "n_tier3": 0, "se": se,
                     "est": est, "n_human_nominal": n, "n_tier3_nominal": 0})
    # two-phase: Tier-3 labels = truth with era-varying accuracy, errors uniform over other categories
    era_i = np.searchsorted([1850, 1885], lab.decade.values, side="right")
    acc = np.asarray(TIER3_ACC)[era_i]
    wrong = rng.random(len(lab)) > acc
    y3 = np.where(wrong, (y + rng.integers(1, K, len(lab))) % K, y)
    for n3, nh in two_phase:
        aud3, frame3 = draw_audit(sel, set(), rng, n_target=n3)
        pi3 = frame3.set_index("passage_id").pi_audit.loc[lab.passage_id].values
        R3 = np.zeros(len(lab), bool)
        R3[pos.loc[aud3.passage_id].values] = True
        # humans: stratified SRS within the phase-3 sample, same cells, equal allocation
        cells = aud3.groupby("audit_cell")
        per = int(np.ceil(nh / cells.ngroups))
        Rh = np.zeros(len(lab), bool)
        pih = np.ones(len(lab))
        for _, gdf in cells:
            k = min(per, len(gdf))
            pick = gdf.sample(n=k, random_state=int(rng.integers(1 << 30)))
            idx = pos.loc[gdf.passage_id].values
            pih[idx] = k / len(gdf)
            Rh[pos.loc[pick.passage_id].values] = True
        Yt = dsl.pseudo_outcomes_two_phase(yhat, y3, y, R3, pi3, Rh, pih, K)
        se, est = _se_h1(lab, Yt, design, "two_phase")
        rows.append({**base, "estimator": "two_phase", "n_human": int(Rh.sum()), "n_tier3": int(R3.sum()),
                     "se": se, "est": est, "n_human_nominal": nh, "n_tier3_nominal": n3})
    return rows


def grid(quick: bool = False, reps: int = 2, curve: bool = False):
    if quick:
        pts = [(6000, 24, 0.05, 0.45, "base")]
    elif curve:   # audit-size curve at the base point, more replicates
        pts = [(6000, 24, 0.05, 0.45, "base"), (6000, 24, 0.05, 0.45, "good")]
    else:
        pts = list(itertools.product((5000, 6000, 7000), (12, 18, 24), (0.02, 0.05, 0.10, 0.20),
                                     (0.30, 0.45, 0.60), ("base",)))
        pts += list(itertools.product((6000,), (12, 24), (0.05, 0.10), (0.45,), ("good",)))
    return [p + (100 + r,) for p in pts for r in range(reps)]


def summarise(raw: pd.DataFrame) -> pd.DataFrame:
    keys = ["works_per_split", "passages_per_work", "icc", "prevalence", "noise", "estimator",
            "n_tier3_nominal", "n_human_nominal"]
    s = raw.groupby(keys).agg(n_human=("n_human", "median"), n_tier3=("n_tier3", "median"),
                              se=("se", lambda x: np.sqrt(np.mean(x ** 2))), se_sd=("se", "std"),
                              est=("est", "mean"), early_works=("early_works", "mean"), reps=("se", "size")).reset_index()
    for a, z in Z.items():
        s[f"mde_pp_a{str(a)[2:]}"] = 100 * z * s.se     # mde_pp_a05, mde_pp_a01
    return s


def main(reps=2, procs=16, quick=False, curve=False):
    jobs = [(p, AUDITS, TWO_PHASE) for p in grid(quick, reps, curve)]
    with mp.get_context("fork").Pool(procs) as pool:
        raw = pd.DataFrame([r for rows in pool.imap_unordered(one_point, jobs) for r in rows])
    OUT.mkdir(exist_ok=True)
    tag = "_curve" if curve else ("_quick" if quick else "")
    raw.to_csv(OUT / f"power_raw{tag}.csv", index=False)
    s = summarise(raw)
    s.to_csv(OUT / f"power_mde{tag}.csv", index=False)
    return s


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--procs", type=int, default=16)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--curve", action="store_true", help="audit-size curve at the base point (use --reps 12)")
    a = ap.parse_args()
    s = main(a.reps, a.procs, a.quick, a.curve)
    pd.set_option("display.width", 220)
    print(s.round(4).to_string())
