"""Power / MDE for the v0.5 registered design (docs/prereg.md §7.7).

Corpus: SimConfig.v05 (calibrated to v0.9 Discovery: prevalence 0.70, locus ~0.21/0.69/0.10,
observed author ICC ~0.10, work ICC ~0.15; Confirmation primary set ~4,000 works with E ~85,
12 passages per work; canonical authors 31% / 22% / 4% by era).
Model labels: QA-level noise (has_obstacle precision 0.77, recall 0.98, locus accuracy 0.85,
late adventure/juvenile errors over-call material), levers.model_codes.
Audit: seal-safe draw_audit_metadata (era x genre x canonical, budget balanced over era x canonical;
or era x genre only), ~1,820 unique items, 4 peers (~2,000 labels incl. 10% overlap), kappa ~0.6 or
~0.75 vs expert. Expert (grad student) = the estimand's construct, labels a stratified 25% subsample
of the audit (~450 items, all also peer-labelled). Peer exclusion: kappa vs expert < 0.40.
Estimators: P = peers only (v0.4), E = expert only, A = expert-anchored 3-level DSL (registered).
Statistics: TF (two fictions, co-primary), H1 E-vs-L (co-primary), H1-ML (descriptive), H1 within
non-canonical works (secondary), composition share of the aggregate E->L material change.

usage: OMP_NUM_THREADS=1 uv run python -m analysis.stats.power_v05 [--reps 60] [--procs 7]
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
from analysis.stats.levers import POPULAR, h1_era, label_audit, model_codes
from analysis.stats.simulate import LLMNoise, SimConfig, annotate_noisy, simulate

OUT = Path(__file__).resolve().parent / "out"
T = dsl.TARGETS["locus"]
K = 4
ANN = {0.6: (0.25, 0.28, 0.31, 0.34), 0.75: (0.15, 0.15, 0.18, 0.18)}
TRUTHS = {"tf_full": dict(gap=-3.0, trend=0.0), "tf_half": dict(gap=-1.2, trend=0.0),
          "null": dict(gap=0.0, trend=0.0), "tf_trend": dict(gap=-3.0, trend=0.5)}


def peer_labels(ids, tpos, ann_err, rng, overlap=0.10):
    ids = np.array(ids, dtype=object)
    rng.shuffle(ids)
    A = len(ann_err)
    n_ov = int(overlap * len(ids))
    assign = {p: ([i % A, (i + 1) % A] if i < n_ov else [i % A]) for i, p in enumerate(ids)}
    rows = []
    for a in range(A):
        mine = [p for p, l in assign.items() if a in l]
        rows.append(annotate_noisy(tpos.loc[mine].reset_index(), ann_err[a], rng).assign(annotator=f"peer{a}"))
    return pd.concat(rows, ignore_index=True)


def stats_for(wd, design, ref):
    out = {}
    try:
        out["TF"] = models.two_fictions(wd, design, ref)
    except Exception:
        out["TF"] = None
    cache = {}
    yE, yM, yL = (models.era_years(wd.cov, e) for e in (models.EARLY, models.MID, models.LATE))
    for k, (ya, yb) in {"H1": (yE, yL), "H1-ML": (yM, yL)}.items():
        try:
            out[k] = models.h1_contrast(wd, design, ref, years_a=ya, years_b=yb, fit_cache=cache, name=k)
        except Exception:
            out[k] = None
    try:
        sub = wd.subset(~wd.cov.canonical.values.astype(bool))
        out["H1-noncanon"] = models.h1_contrast(sub, design, ref, years_a=models.era_years(sub.cov, models.EARLY),
                                                years_b=models.era_years(sub.cov, models.LATE), name="H1-noncanon")
    except Exception:
        out["H1-noncanon"] = None
    try:
        ss = models.shift_share(wd, "locus", [1], [1, 2, 3], models.EARLY, models.LATE, by="canonical", B=1).set_index("part")
        out["_comp"] = (float(ss.estimate["total"]), float(ss.estimate["composition"]))
    except Exception:
        out["_comp"] = (np.nan, np.nan)
    return out


def one_rep(args) -> list[dict]:
    truth, kappa, seed, strata_variants = args[:4]
    efrac = args[4] if len(args) > 4 else 0.25
    rng = np.random.default_rng(seed + 5)
    c = simulate(SimConfig.v05(seed=seed, noise=LLMNoise.perfect(), **TRUTHS[truth]), audit=False)
    lab = c.labels[(c.labels.split == "confirmation") & (c.labels.stratum == "random")].reset_index(drop=True)
    tru = c.truth.set_index("passage_id").loc[lab.passage_id].reset_index()
    y = T.fn(tru)
    era = h1_era(lab.year.values)
    yhat = model_codes(y, era, lab.genre.isin(POPULAR).values, 0.77, 0.85, rng)
    tpos = tru.set_index("passage_id")
    pos = pd.Series(np.arange(len(lab)), index=lab.passage_id)
    folds = dsl._fold_ids(lab.author_key, 5, seed)
    wo = dsl.aggregate_to_works(lab, {"locus": dsl.onehot(y, K)}, "oracle")
    design = models.Design.from_data(wo)
    ref = models._ref(wo, None).assign(canon_num=0.0)
    so = stats_for(wo, design, ref)
    base = {"efrac": efrac, "truth": truth, "kappa": kappa, "seed": seed, "n_works": len(wo),
            "early_works": int((wo.cov.year < 1850).sum()), "canon_share_L": float(wo.cov[wo.cov.year >= 1885].canonical.mean())}
    rows = []
    meta = lab[["passage_id", "work_id", "author_key", "year", "split", "stratum", "genre", "canonical"]]
    for strata in strata_variants:
        aud, frame = sa.draw_audit_metadata(meta, rng, n_target=1820, use_canon=(strata == "era_genre_canon"))
        cell = frame.set_index("passage_id").audit_cell.loc[lab.passage_id].values
        pi3 = frame.set_index("passage_id").pi_audit.loc[lab.passage_id].values
        R3 = np.zeros(len(lab), bool)
        R3[pos.loc[aud.passage_id].values] = True
        # expert: stratified 25% subsample of the audit within audit cells
        Rh = np.zeros(len(lab), bool)
        pih = np.ones(len(lab))
        for cl, g in aud.groupby("audit_cell"):
            k = int(round(efrac * len(g)))
            idx = pos.loc[g.passage_id].values
            if k > 0:
                Rh[rng.choice(idx, k, replace=False)] = True
            pih[cell == cl] = max(k, 1) / len(g)
        peers = peer_labels(aud.passage_id.values, tpos, ANN[kappa], rng)
        ex = tpos.loc[lab.passage_id.values[Rh]].reset_index()
        ex_rows = pd.DataFrame({"passage_id": ex.passage_id, "annotator": "expert", "has_obstacle": ex.has_obstacle,
                                "domains": ex.domains.map(lambda d: list(d)[:1]), "locus": ex.locus,
                                "failure_cause": ex.failure_cause})
        human = pd.concat([peers, ex_rows], ignore_index=True)
        rep_k = ann.expert_agreement(human, expert="expert")
        excl = ann.exclusions(rep_k)
        hp = peers[~peers.annotator.isin(excl)]
        sid, S = dsl.human_soft(hp, T)
        peer_soft = np.zeros((len(lab), K))
        peer_soft[pos.loc[sid].values] = S
        R3r = np.zeros(len(lab), bool)
        R3r[pos.loc[sid].values] = True
        N = pd.Series(cell).value_counts()
        pi3r = pd.Series(cell).map(pd.Series(cell[R3r]).value_counts().reindex(N.index, fill_value=0) / N).values
        Rh = Rh & R3r
        Yt = {
            "P_peers": dsl.pseudo_outcomes(yhat, peer_soft, R3r, pi3r, K, method="calib", folds=folds, strata=era),
            "E_expert": dsl.pseudo_outcomes(yhat, y, Rh, pi3r * pih, K, method="calib", folds=folds, strata=era),
            "A_anchored": dsl.pseudo_outcomes_anchored(yhat, peer_soft, R3r, pi3r, y, Rh, pih, K, folds, era),
        }
        for est, Y in Yt.items():
            wd = dsl.aggregate_to_works(lab, {"locus": Y}, est)
            st = stats_for(wd, design, ref)
            for k in ("TF", "H1", "H1-ML", "H1-noncanon"):
                e, o = st[k], so[k]
                if e is None or o is None:
                    continue
                rows.append({**base, "strata": strata, "estimator": est, "stat": k,
                             "n_audit": int(R3r.sum()), "n_expert": int(Rh.sum()), "n_peer_labels": len(hp),
                             "n_excluded": len(excl), "kappa_meas": float(rep_k.kappa_locus.mean()),
                             "est_mat": e.components[0].estimate, "se_mat": e.components[0].se,
                             "est_int": e.components[1].estimate, "se_int": e.components[1].se,
                             "p": e.extra["p_test"], "cls": e.extra["classification"],
                             "truth_mat": o.components[0].estimate, "truth_int": o.components[1].estimate,
                             "truth_cls": o.extra["classification"],
                             "comp_total": st["_comp"][0], "comp_part": st["_comp"][1],
                             "truth_comp_total": so["_comp"][0], "truth_comp_part": so["_comp"][1]})
    return rows


def summarise(raw: pd.DataFrame) -> pd.DataFrame:
    z05 = stats.norm.isf(0.025) + stats.norm.isf(0.2)
    z025 = stats.norm.isf(0.0125) + stats.norm.isf(0.2)
    raw = raw.assign(rej025=(raw.p < 0.025).astype(float), rej05=(raw.p < 0.05).astype(float),
                     right_cls=(raw.cls == raw.truth_cls).astype(float),
                     wrong_dir=(((raw.cls == "inward") & (raw.truth_cls == "outward")) |
                                ((raw.cls == "outward") & (raw.truth_cls == "inward"))).astype(float),
                     cover=((raw.est_mat - 1.96 * raw.se_mat <= raw.truth_mat) &
                            (raw.truth_mat <= raw.est_mat + 1.96 * raw.se_mat)).astype(float))
    if "efrac" not in raw:
        raw["efrac"] = 0.25
    k = ["efrac", "truth", "kappa", "strata", "estimator", "stat"]
    s = raw.groupby(k).agg(reps=("p", "size"), power_025=("rej025", "mean"), power_05=("rej05", "mean"),
                           cls_correct=("right_cls", "mean"), wrong_direction=("wrong_dir", "mean"),
                           truth_mat=("truth_mat", "mean"), est_mat=("est_mat", "mean"), sd_mat=("est_mat", "std"),
                           se_mat=("se_mat", lambda x: float(np.sqrt(np.mean(np.asarray(x) ** 2)))),
                           se_int=("se_int", lambda x: float(np.sqrt(np.mean(np.asarray(x) ** 2)))),
                           cover=("cover", "mean"), n_audit=("n_audit", "median"), n_expert=("n_expert", "median"),
                           kappa_meas=("kappa_meas", "mean"), excluded=("n_excluded", "mean"),
                           comp_total=("comp_total", "mean"), comp_part=("comp_part", "mean"),
                           truth_comp_total=("truth_comp_total", "mean"), truth_comp_part=("truth_comp_part", "mean"),
                           early_works=("early_works", "mean")).reset_index()
    s["mde_mat_pp_a025"] = 100 * z025 * s.se_mat
    s["mde_int_pp_a025"] = 100 * z025 * s.se_int
    s["mde_mat_pp_a05"] = 100 * z05 * s.se_mat
    return s


def jobs(reps: int) -> list:
    out = []
    for truth in TRUTHS:
        for kappa in (0.6, 0.75):
            n = reps * 2 if (truth == "tf_full" and kappa == 0.6) else reps
            for r in range(n):
                out.append((truth, kappa, 1000 + r, ("era_genre_canon", "era_genre")))
    return out


def main(reps: int = 60, procs: int = 7, expert_extra: bool = False) -> pd.DataFrame:
    js = jobs(reps)
    tag = ""
    if expert_extra:   # expert budget lever: ~900 expert labels (50% of the audit) and ~225 (12.5%)
        js = [(t, 0.6, 1000 + r, ("era_genre_canon",), f) for t in ("tf_full", "null") for f in (0.5, 0.125)
              for r in range(reps)]
        tag = "_expert"
    OUT.mkdir(exist_ok=True)
    rows = []
    with mp.get_context("fork").Pool(procs) as pool:
        for i, r in enumerate(pool.imap_unordered(one_rep, js)):
            rows.extend(r)
            if i % 40 == 0:
                print(f"{i + 1}/{len(js)}", flush=True)
                pd.DataFrame(rows).to_csv(OUT / f"power_v05{tag}_raw.partial.csv", index=False)
    raw = pd.DataFrame(rows)
    raw.to_csv(OUT / f"power_v05{tag}_raw.csv", index=False)
    s = summarise(raw)
    s.to_csv(OUT / f"power_v05{tag}.csv", index=False)
    return s


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=60)
    ap.add_argument("--procs", type=int, default=7)
    ap.add_argument("--expert-extra", action="store_true")
    a = ap.parse_args()
    main(a.reps, a.procs, a.expert_extra)
