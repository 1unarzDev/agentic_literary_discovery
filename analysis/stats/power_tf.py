"""Power of candidate TF primary statistics under the Discovery-calibrated truth (prereg v0.5 §7.8).

Truth: SimConfig.tf_disc(scale): canonical - non-canonical material gap ~E -8 / M -7 / L -4 pp
(pooled works-weighted ~ -4.2), internal gap ~+3 to +6 (pooled ~ +3.0), social ~equal; late gap
carried by juvenile fiction; corrected primary set (Confirmation ~4,050 works; canonical 37/19/9%).
scale 1.0 = Discovery-size raw-label effect, 0.7 = deflated, 0 = null.
Design: registered v0.5 (seal-safe era x genre x canonical draw, ~1,820 audit items, 4 peers ~2,000
labels kappa ~0.6, grad-student expert on a 50% within-cell subsample (~900), expert-anchored DSL).
Statistics (two-sided, alpha = .05): (a) material gap, (b) joint 2-df Wald (material, internal),
(c) inwardness index gap d_internal - d_material, each with (d) works-weighted (registered) or
era-equal weights; plus the registered genre != juvenile sensitivity.

usage: OMP_NUM_THREADS=1 uv run python -m analysis.stats.power_tf [--reps 100] [--procs 7]
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from analysis import select_annotation as sa
from analysis.stats import annotators as ann
from analysis.stats import dsl, models
from analysis.stats.levers import POPULAR, h1_era, model_codes
from analysis.stats.power_v05 import ANN, peer_labels
from analysis.stats.simulate import LLMNoise, SimConfig, simulate

OUT = Path(__file__).resolve().parent / "out"
T = dsl.TARGETS["locus"]
K = 4
STATS = ("mat", "wald", "index")


def one_rep(args) -> list[dict]:
    scale, kappa, seed = args
    rng = np.random.default_rng(seed + 17)
    c = simulate(SimConfig.tf_disc(scale=scale, seed=seed, noise=LLMNoise.perfect()), audit=False)
    lab = c.labels[(c.labels.split == "confirmation") & (c.labels.stratum == "random")].reset_index(drop=True)
    tru = c.truth.set_index("passage_id").loc[lab.passage_id].reset_index()
    y = T.fn(tru)
    yhat = model_codes(y, h1_era(lab.year.values), lab.genre.isin(POPULAR).values, 0.77, 0.85, rng)
    tpos = tru.set_index("passage_id")
    pos = pd.Series(np.arange(len(lab)), index=lab.passage_id)
    folds = dsl._fold_ids(lab.author_key, 5, seed)
    era = h1_era(lab.year.values)
    meta = lab[["passage_id", "work_id", "author_key", "year", "split", "stratum", "genre", "canonical"]]
    aud, frame = sa.draw_audit_metadata(meta, rng, n_target=1820, use_canon=True)
    cell = frame.set_index("passage_id").audit_cell.loc[lab.passage_id].values
    R3 = np.zeros(len(lab), bool)
    R3[pos.loc[aud.passage_id].values] = True
    Rh = np.zeros(len(lab), bool)
    pih = np.ones(len(lab))
    for cl, g in aud.groupby("audit_cell"):
        k = int(round(0.5 * len(g)))
        if k > 0:
            Rh[rng.choice(pos.loc[g.passage_id].values, k, replace=False)] = True
        pih[cell == cl] = max(k, 1) / len(g)
    peers = peer_labels(aud.passage_id.values, tpos, ANN[kappa], rng)
    ex = tpos.loc[lab.passage_id.values[Rh]].reset_index()
    exr = pd.DataFrame({"passage_id": ex.passage_id, "annotator": "expert", "has_obstacle": ex.has_obstacle,
                        "domains": ex.domains.map(lambda d: list(d)[:1]), "locus": ex.locus, "failure_cause": ex.failure_cause})
    excl = ann.exclusions(ann.expert_agreement(pd.concat([peers, exr]), expert="expert"))
    hp = peers[~peers.annotator.isin(excl)]
    sid, S = dsl.human_soft(hp, T)
    ps = np.zeros((len(lab), K)); ps[pos.loc[sid].values] = S
    R3r = np.zeros(len(lab), bool); R3r[pos.loc[sid].values] = True
    N = pd.Series(cell).value_counts()
    pi3 = pd.Series(cell).map(pd.Series(cell[R3r]).value_counts().reindex(N.index, fill_value=0) / N).values
    Yt = dsl.pseudo_outcomes_anchored(yhat, ps, R3r, pi3, y, Rh & R3r, pih, K, folds, era)
    wd = dsl.aggregate_to_works(lab, {"locus": Yt}, "A")
    wo = dsl.aggregate_to_works(lab, {"locus": dsl.onehot(y, K)}, "oracle")
    design = models.Design.from_data(wo)
    ref = models._ref(wo, None)
    rows = []
    for subset in ("all", "nonjuvenile"):
        m = np.ones(len(wd), bool) if subset == "all" else (wd.cov.genre.values != "juvenile")
        mo = np.ones(len(wo), bool) if subset == "all" else (wo.cov.genre.values != "juvenile")
        r = ref if subset == "all" else ref[ref.genre != "juvenile"]
        for wts, inter in (("works", False), ("works", True), ("era_equal", True)):
            if subset == "nonjuvenile" and inter:
                continue
            try:
                e = models.tf_statistics(wd.subset(m), design, r, weights=wts, interact=inter)
                o = models.tf_statistics(wo.subset(mo), design, r, weights=wts, interact=inter)
            except Exception:
                continue
            rows.append({"scale": scale, "kappa": kappa, "seed": seed, "subset": subset,
                         "weights": wts + ("+canon_x_era" if inter else " (main effect)"),
                         **{k: v for k, v in e.items() if k != "link"},
                         **{f"truth_{k}": o[k] for k in ("d_mat", "d_int", "d_index")},
                         "n_canon_works": int(wd.cov.canonical.sum())})
    return rows


def summarise(raw: pd.DataFrame) -> pd.DataFrame:
    z = stats.norm.isf(0.025) + stats.norm.isf(0.2)
    rows = []
    for key, g in raw.groupby(["scale", "kappa", "subset", "weights"]):
        rec = dict(zip(["scale", "kappa", "subset", "weights"], key), reps=len(g))
        for st, pcol, dcol, secol, tcol in (("a_material", "p_mat", "d_mat", "se_mat", "truth_d_mat"),
                                            ("internal", "p_int", "d_int", "se_int", "truth_d_int"),
                                            ("c_index", "p_index", "d_index", "se_index", "truth_d_index")):
            se = float(np.sqrt(np.mean(g[secol] ** 2)))
            rec.update({f"{st}_truth_pp": 100 * g[tcol].mean(), f"{st}_est_pp": 100 * g[dcol].mean(),
                        f"{st}_se_pp": 100 * se, f"{st}_mde_pp": 100 * z * se,
                        f"{st}_power": float((g[pcol] < 0.05).mean()),
                        f"{st}_right_sign_power": float(((g[pcol] < 0.05) & (np.sign(g[dcol]) == np.sign(g[tcol].mean()))).mean())})
        rec["b_wald2_power"] = float((g.p_wald < 0.05).mean())
        rec["corr_mat_int"] = float(g.corr_mat_int.mean())
        rows.append(rec)
    return pd.DataFrame(rows)


def main(reps: int = 100, procs: int = 7) -> pd.DataFrame:
    jobs = [(sc, 0.6, 3000 + r) for sc in (1.0, 0.7, 0.0) for r in range(reps)]
    rows = []
    with mp.get_context("fork").Pool(procs) as pool:
        for i, r in enumerate(pool.imap_unordered(one_rep, jobs)):
            rows.extend(r)
            if i % 50 == 0:
                print(f"{i + 1}/{len(jobs)}", flush=True)
    raw = pd.DataFrame(rows)
    OUT.mkdir(exist_ok=True)
    raw.to_csv(OUT / "power_tf_raw.csv", index=False)
    s = summarise(raw)
    s.to_csv(OUT / "power_tf.csv", index=False)
    return s


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=100)
    ap.add_argument("--procs", type=int, default=7)
    a = ap.parse_args()
    main(a.reps, a.procs)
