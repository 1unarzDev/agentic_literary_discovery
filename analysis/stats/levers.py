"""Design levers for H1 power before the freeze (prereg v0.5 §7.6).

One replicate = one pilot-like corpus (SimConfig.pilot_step: material +~8 pp step in 1883, internal
flat) or a null corpus, Confirmation half, random backbone. On it we vary:
  L1 model accuracy  - model labels for the locus target generated directly from the truth with
                       has_obstacle precision P, recall 0.98 and locus accuracy A (QA-like heterogeneity:
                       early x0.7 error, late adventure/juvenile x2 error with material over-calls)
  L2 allocation      - equal over era x predicted-locus (draw_audit "group" design) vs residual-variance
                       (Neyman) allocation over era x predicted-locus x popular-genre, with S_h
                       estimated from a 600-passage Discovery pilot sample (noisy humans)
  L3 contrast        - EL (1800-49 vs 1885-1929), ML (1850-84 vs 1885-1929), LIN (linear in year,
                       1840-1929), STEP (pre/post 1880, 1840-1929); all two-sided 2-df Wald + classes
  L4 annotator noise - none | pooled confusion from the 30 expert items | per-annotator confusion |
                       oracle (true) confusion; unbiased correction o @ M^-1
  L5 label count     - ~2,050 labels (1,760 unique items) vs ~3,050 (2,670 unique)
Human process as registered: 4 annotators (kappa ~0.6 or ~0.75 vs expert), 10% overlap, 30 expert
items, kappa < 0.40 exclusion, annotator-mean soft labels, cross-fitted calibrated DSL, logit with
identity fallback, author-clustered sandwich.

usage: OMP_NUM_THREADS=1 uv run python -m analysis.stats.levers [--reps 20] [--procs 7]
writes analysis/stats/out/levers_raw.csv, levers.csv
"""
from __future__ import annotations

import argparse
import itertools
import multiprocessing as mp
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from analysis.stats import annotators as ann
from analysis.stats import dsl, models
from analysis.stats.simulate import LLMNoise, SimConfig, annotate_noisy, simulate

OUT = Path(__file__).resolve().parent / "out"
T = dsl.TARGETS["locus"]
K = 4
ANN = {0.6: (0.25, 0.28, 0.31, 0.34), 0.75: (0.15, 0.15, 0.18, 0.18)}
POPULAR = {"adventure", "juvenile"}
FP_LOCUS = np.array([0.30, 0.55, 0.15])        # locus mix of false-positive obstacles (pilot QA)
CONTRASTS = ("EL", "ML", "LIN", "STEP")


def h1_era(year: np.ndarray) -> np.ndarray:
    return np.where(year < 1850, "E", np.where(year < 1885, "M", "L"))


# ------------------------------------------------------------------ L1: model labels

def model_codes(y: np.ndarray, era: np.ndarray, popular: np.ndarray, precision: float, locus_acc: float,
                rng: np.random.Generator, recall: float = 0.98) -> np.ndarray:
    """Model locus-target codes from true codes. Precision is defined at the corpus prevalence."""
    n = len(y)
    obs = y > 0
    pi = obs.mean()
    fp = min(1.0, recall * pi * (1 - precision) / (precision * (1 - pi)))
    out = np.zeros(n, int)
    pred_obs = np.where(obs, rng.random(n) < recall, rng.random(n) < fp)
    # false positives: locus from the pilot false-yes mix
    fpm = pred_obs & ~obs
    out[fpm] = 1 + rng.choice(3, fpm.sum(), p=FP_LOCUS)
    # true positives: era / genre-heterogeneous locus error, mean error = 1 - locus_acc
    tp = pred_obs & obs
    mult = np.where(era == "E", 0.7, 1.0) * np.where((era == "L") & popular, 2.0, 1.0)
    e = (1 - locus_acc) * mult / mult[tp].mean()
    e = np.clip(e, 0, 0.95)
    err = tp & (rng.random(n) < e)
    out[tp & ~err] = y[tp & ~err]
    # errors: late popular -> material over-call (70%) when true is not material; else uniform other
    idx = np.where(err)[0]
    for i in idx:
        others = [k for k in (1, 2, 3) if k != y[i]]
        if era[i] == "L" and popular[i] and y[i] != 1 and rng.random() < 0.7:
            out[i] = 1
        else:
            out[i] = others[rng.integers(2)]
    return out


# ------------------------------------------------------------------ L2: allocation

def draw_cells(cells: np.ndarray, n_by_cell: dict, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Stratified SRS: returns (R, pi) for the given per-cell sample sizes."""
    R = np.zeros(len(cells), bool)
    pi = np.zeros(len(cells))
    s = pd.Series(np.arange(len(cells)), index=cells)
    for c, idx in s.groupby(level=0):
        idx = idx.values
        k = int(min(len(idx), n_by_cell.get(c, 0)))
        if k > 0:
            R[rng.choice(idx, k, replace=False)] = True
        pi[idx] = k / len(idx)
    return R, pi


def equal_alloc(cells: np.ndarray, n: int) -> dict:
    vc = pd.Series(cells).value_counts()
    per = int(np.ceil(n / len(vc)))
    return {c: min(per, N) for c, N in vc.items()}


def neyman_alloc(cells: np.ndarray, S: dict, n: int, n_min: int = 8) -> dict:
    """n_h proportional to N_h * S_h, at least n_min, at most N_h (iterative capping)."""
    vc = pd.Series(cells).value_counts()
    w = pd.Series({c: vc[c] * S.get(c, np.mean(list(S.values()))) for c in vc.index})
    alloc = pd.Series(0.0, index=vc.index)
    fixed = pd.Series(False, index=vc.index)
    remaining = n
    for _ in range(20):
        free = ~fixed
        a = remaining * w[free] / w[free].sum()
        lo = a < n_min
        hi = a > vc[free]
        if not (lo.any() or hi.any()):
            alloc[free] = a
            break
        for c in a[lo].index:
            alloc[c] = min(n_min, vc[c]); fixed[c] = True
        for c in a[hi].index:
            alloc[c] = vc[c]; fixed[c] = True
        remaining = n - alloc[fixed].sum()
    return {c: int(round(v)) for c, v in alloc.items()}


def residual_sd_from_pilot(cells: np.ndarray, y: np.ndarray, yhat: np.ndarray, rng: np.random.Generator,
                           n_pilot: int = 600, ann_err: float = 0.3, truth_rows: pd.DataFrame | None = None,
                           prior: float = 5.0) -> dict:
    """S_h = sqrt(shrunk disagreement rate) from a random pilot sample (Discovery split) labelled by one
    noisy annotator: what the team can actually know before allocating."""
    idx = rng.choice(len(y), min(n_pilot, len(y)), replace=False)
    yh = T.fn(annotate_noisy(truth_rows.iloc[idx], ann_err, rng)) if truth_rows is not None else y[idx]
    d = (yh != yhat[idx]).astype(float)
    dbar = d.mean()
    out = {}
    for c in np.unique(cells):
        m = cells[idx] == c
        out[c] = float(np.sqrt(max((d[m].sum() + prior * dbar) / (m.sum() + prior), 1e-3)))
    return out


# ------------------------------------------------------------------ human labelling (registered process)

def label_audit(ids: np.ndarray, tpos: pd.DataFrame, era_of: pd.Series, ann_err: tuple,
                rng: np.random.Generator, overlap: float = 0.10, n_expert_per_era: int = 10) -> tuple[pd.DataFrame, np.ndarray]:
    ids = np.array(ids, dtype=object)
    rng.shuffle(ids)
    A = len(ann_err)
    expert = np.concatenate([rng.choice(ids[era_of.loc[ids].values == e], min(n_expert_per_era, (era_of.loc[ids].values == e).sum()),
                                        replace=False) for e in ("E", "M", "L")])
    rest = ids[~np.isin(ids, expert)]
    n_ov = int(overlap * len(rest))
    assign = {p: ([i % A, (i + 1) % A] if i < n_ov else [i % A]) for i, p in enumerate(rest)}
    for p in expert:
        assign[p] = list(range(A))
    rows = []
    for a in range(A):
        mine = [p for p, lst in assign.items() if a in lst]
        rows.append(annotate_noisy(tpos.loc[mine].reset_index(), ann_err[a], rng).assign(annotator=f"ann{a}"))
    ex = tpos.loc[expert].reset_index()
    rows.append(pd.DataFrame({"passage_id": ex.passage_id, "annotator": "teacher", "has_obstacle": ex.has_obstacle,
                              "domains": ex.domains.map(lambda d: list(d)[:1]), "locus": ex.locus,
                              "failure_cause": ex.failure_cause}))
    return pd.concat(rows, ignore_index=True), expert


# ------------------------------------------------------------------ L4: annotator confusion correction

def confusion(obs: np.ndarray, true: np.ndarray, prior: np.ndarray) -> np.ndarray:
    C = prior.astype(float).copy()
    np.add.at(C, (true, obs), 1.0)
    return C / C.sum(1, keepdims=True)


def corrected_soft(human: pd.DataFrame, mode: str, excl: set, oracle_M: dict | None = None,
                   expert: str = "teacher") -> tuple[np.ndarray, np.ndarray, int]:
    """Annotator-mean soft labels after the unbiased misclassification correction o @ M_a^-1
    (E[onehot(obs) | true k] = M[k] => E[onehot(obs) M^-1] = e_k). M rows = true (expert), cols = obs.
    mode: "none" | "pooled" (one M from all annotators' expert items) | "per" (per-annotator M, prior 2 x
    pooled) | "oracle" (true M). Returns (ids, Y, n_fallback): ill-conditioned M (cond > 50) -> pooled."""
    h = human[~human.annotator.isin(excl | {expert})]
    codes = T.fn(h)
    ex = human[human.annotator == expert].set_index("passage_id")
    ex_code = pd.Series(T.fn(ex.reset_index()), index=ex.index)
    on_ex = h.passage_id.isin(ex.index).values
    pooled = confusion(codes[on_ex], ex_code.loc[h.passage_id[on_ex]].values, np.eye(K))
    Ms, nfb = {}, 0
    for a in h.annotator.unique():
        if mode == "none":
            M = np.eye(K)
        elif mode == "pooled":
            M = pooled
        elif mode == "oracle":
            M = oracle_M[a]
        else:
            m = (h.annotator.values == a) & on_ex
            M = confusion(codes[m], ex_code.loc[h.passage_id[m]].values, 2 * pooled)
        if np.linalg.cond(M) > 50:
            M, nfb = pooled, nfb + 1
        Ms[a] = np.linalg.inv(M)
    V = np.zeros((len(h), K))
    for a, Minv in Ms.items():
        m = h.annotator.values == a
        V[m] = dsl.onehot(codes[m], K) @ Minv
    pid, inv = np.unique(h.passage_id.values, return_inverse=True)
    S = np.zeros((len(pid), K))
    np.add.at(S, inv, V)
    return pid, S / np.bincount(inv)[:, None], nfb


# ------------------------------------------------------------------ one replicate

def contrasts(wd: dsl.WorkData, design, ref) -> dict:
    cache: dict = {}
    yE = models.era_years(wd.cov, models.EARLY)
    yM = models.era_years(wd.cov, models.MID)
    yL = models.era_years(wd.cov, models.LATE)
    spec = {"EL": dict(time="spline", years_a=yE, years_b=yL),
            "ML": dict(time="spline", years_a=yM, years_b=yL),
            "LIN": dict(time="linear", window=(1840, 1929), years_a=[1840], years_b=[1929]),
            "STEP": dict(time="step", window=(1840, 1929), cut=1880, years_a=[1879], years_b=[1880])}
    out = {}
    for k, kw in spec.items():
        try:
            out[k] = models.h1_contrast(wd, design, ref, fit_cache=cache, name=k, **kw)
        except Exception:
            out[k] = None
    return out


def one_rep(args) -> list[dict]:
    truth_kind, precision, locus_acc, kappa, seed, variants = args
    rng = np.random.default_rng(seed + 101)
    cfg = (SimConfig.pilot_step(n_works=15500, seed=seed, noise=LLMNoise.perfect(), prevalence=0.70)
           if truth_kind == "pilot" else
           SimConfig(n_works=15500, seed=seed, noise=LLMNoise.perfect(), prevalence=0.70, effect=0.0))
    c = simulate(cfg, audit=False)
    lab_all = c.labels[c.labels.stratum == "random"].reset_index(drop=True)
    tru_all = c.truth.set_index("passage_id").loc[lab_all.passage_id].reset_index()
    conf = (lab_all.split == "confirmation").values
    lab, tru = lab_all[conf].reset_index(drop=True), tru_all[conf].reset_index(drop=True)
    disc_lab, disc_tru = lab_all[~conf].reset_index(drop=True), tru_all[~conf].reset_index(drop=True)
    y = T.fn(tru)
    era = h1_era(lab.year.values)
    pop = lab.genre.isin(POPULAR).values
    yhat = model_codes(y, era, pop, precision, locus_acc, rng)
    # pilot (Discovery) for Neyman S_h
    yd = T.fn(disc_tru)
    erad, popd = h1_era(disc_lab.year.values), disc_lab.genre.isin(POPULAR).values
    yhatd = model_codes(yd, erad, popd, precision, locus_acc, rng)
    cell_n = pd.Series(era).astype(str) + "|" + pd.Series(yhat).astype(str) + "|" + pd.Series(np.where(pop, "pop", "oth"))
    cell_nd = pd.Series(erad).astype(str) + "|" + pd.Series(yhatd).astype(str) + "|" + pd.Series(np.where(popd, "pop", "oth"))
    cell_eq = pd.Series(era).astype(str) + "|" + pd.Series(yhat).astype(str)
    S = residual_sd_from_pilot(cell_nd.values, yd, yhatd, rng, truth_rows=disc_tru)
    tpos = tru.set_index("passage_id")
    era_of = pd.Series(era, index=lab.passage_id)
    pos = pd.Series(np.arange(len(lab)), index=lab.passage_id)
    folds = dsl._fold_ids(lab.author_key, 5, seed)
    # oracle effects (expert construct, human schema)
    wo = dsl.aggregate_to_works(lab, {"locus": dsl.onehot(y, K)}, "oracle")
    design = models.Design.from_data(wo)
    ref = models._ref(wo, None)
    models.LINK["default"] = "logit"
    oc = contrasts(wo, design, ref)
    # oracle confusion per annotator (true M) from a large sample
    big = tru.sample(min(20000, len(tru)), random_state=seed)
    ybig = T.fn(big)
    base = {"truth_kind": truth_kind, "precision": precision, "locus_acc": locus_acc, "kappa": kappa, "seed": seed,
            "model_locus_acc_real": float(((yhat == y) & (y > 0)).sum() / max(((yhat > 0) & (y > 0)).sum(), 1)),
            "model_precision_real": float(((yhat > 0) & (y > 0)).sum() / max((yhat > 0).sum(), 1))}
    rows = []
    ann_err = ANN[kappa]
    oracle_M = {f"ann{a}": confusion(T.fn(annotate_noisy(big, e, rng)), ybig, np.zeros((K, K)) + 1e-9)
                for a, e in enumerate(ann_err)}
    for alloc, n_unique, corrections in variants:
        nb = neyman_alloc(cell_n.values, S, n_unique) if alloc == "neyman" else equal_alloc(cell_eq.values, n_unique)
        R, pi = draw_cells((cell_n if alloc == "neyman" else cell_eq).values, nb, rng)
        ids = lab.passage_id.values[R]
        human, expert = label_audit(ids, tpos, era_of, ann_err, rng)
        rep_k = ann.expert_agreement(human)
        excl = ann.exclusions(rep_k)
        for corr in corrections:
            sid, Ysoft, nfb = corrected_soft(human, corr, excl, oracle_M)
            Rl = np.zeros(len(lab), bool)
            Rl[pos.loc[sid].values] = True
            Yl = np.zeros((len(lab), K))
            Yl[pos.loc[sid].values] = Ysoft
            # pi recomputed on retained labels per cell
            cells = (cell_n if alloc == "neyman" else cell_eq).values
            Ncell = pd.Series(cells).value_counts()
            ncell = pd.Series(cells[Rl]).value_counts().reindex(Ncell.index, fill_value=0)
            pi_r = pd.Series(cells).map(ncell / Ncell).values
            Yt = dsl.pseudo_outcomes(yhat, Yl, Rl, pi_r, K, method="calib", folds=folds,
                                     strata=era)
            wd = dsl.aggregate_to_works(lab, {"locus": Yt}, "dsl")
            ec = contrasts(wd, design, ref)
            for k in CONTRASTS:
                e, o = ec[k], oc[k]
                if e is None or o is None:
                    continue
                rows.append({**base, "alloc": alloc, "n_unique": int(Rl.sum()), "n_labels": int((~human.annotator.isin(excl | {"teacher"})).sum()),
                             "correction": corr, "contrast": k, "n_excluded": len(excl), "corr_fallbacks": nfb,
                             "est_mat": e.components[0].estimate, "se_mat": e.components[0].se,
                             "est_int": e.components[1].estimate, "se_int": e.components[1].se,
                             "p": e.extra["p_test"], "cls": e.extra["classification"],
                             "truth_mat": o.components[0].estimate, "truth_int": o.components[1].estimate,
                             "link": e.extra["link"]})
    return rows


VARIANTS = [("equal", 1760, ("none", "pooled", "per", "oracle")),
            ("neyman", 1760, ("none", "pooled")),
            ("equal", 2670, ("none",)),
            ("neyman", 2670, ("none",))]


def summarise(raw: pd.DataFrame) -> pd.DataFrame:
    k = ["truth_kind", "precision", "locus_acc", "kappa", "alloc", "n_labels_nom", "correction", "contrast"]
    raw = raw.assign(n_labels_nom=np.where(raw.n_unique > 2200, "~3050", "~2050"),
                     cls_outward=(raw.cls == "outward").astype(float), cls_inward=(raw.cls == "inward").astype(float),
                     cls_mixed=(raw.cls == "mixed").astype(float), reject=(raw.p < 0.05).astype(float),
                     cover_mat=((raw.est_mat - 1.96 * raw.se_mat <= raw.truth_mat) &
                                (raw.truth_mat <= raw.est_mat + 1.96 * raw.se_mat)).astype(float))
    z = stats.norm.isf(0.025) + stats.norm.isf(0.2)
    s = raw.groupby(k).agg(reps=("p", "size"), power=("reject", "mean"), outward=("cls_outward", "mean"),
                           inward=("cls_inward", "mean"), mixed=("cls_mixed", "mean"),
                           truth_mat=("truth_mat", "mean"), est_mat=("est_mat", "mean"), sd_mat=("est_mat", "std"),
                           se_mat=("se_mat", lambda x: float(np.sqrt(np.mean(np.asarray(x) ** 2)))),
                           se_int=("se_int", lambda x: float(np.sqrt(np.mean(np.asarray(x) ** 2)))),
                           cover_mat=("cover_mat", "mean"), n_unique=("n_unique", "median"),
                           prec_real=("model_precision_real", "mean"), acc_real=("model_locus_acc_real", "mean")).reset_index()
    s["mde_mat_pp"] = 100 * z * s.se_mat
    s["mde_int_pp"] = 100 * z * s.se_int
    s["attenuation"] = s.est_mat / s.truth_mat
    return s


def grid(reps: int) -> list:
    jobs = []
    for prec, acc in itertools.product((0.77, 0.88, 0.95), (0.85, 0.90, 0.95)):
        for kappa in (0.6, 0.75):
            for r in range(reps):
                jobs.append(("pilot", prec, acc, kappa, 700 + r, VARIANTS))
    for prec, acc in ((0.77, 0.90), (0.95, 0.95)):          # size checks
        for r in range(reps):
            jobs.append(("null", prec, acc, 0.6, 900 + r, [("equal", 1760, ("none", "pooled")), ("neyman", 1760, ("none",))]))
    return jobs


def main(reps: int = 20, procs: int = 7) -> pd.DataFrame:
    jobs = grid(reps)
    OUT.mkdir(exist_ok=True)
    rows = []
    with mp.get_context("fork").Pool(procs) as pool:
        for i, r in enumerate(pool.imap_unordered(one_rep, jobs)):
            rows.extend(r)
            if i % 25 == 0:
                pd.DataFrame(rows).to_csv(OUT / "levers_raw.partial.csv", index=False)
                print(f"{i + 1}/{len(jobs)}", flush=True)
    raw = pd.DataFrame(rows)
    raw.to_csv(OUT / "levers_raw.csv", index=False)
    s = summarise(raw)
    s.to_csv(OUT / "levers.csv", index=False)
    return s


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--procs", type=int, default=7)
    a = ap.parse_args()
    main(a.reps, a.procs)
