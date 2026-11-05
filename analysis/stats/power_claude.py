"""Power under the Claude-reference construct (prereg v0.5 §7.9; docs/claude_reference_analysis.md).

Truth (the "expert construct" stand-in) per era x canonical cell, from Claude's blind labels
(design-weighted, Discovery): obstacle rate and locus shares among obstacles
    E canon .471 (mat .150 soc .737 int .113)   E pop .485 (.159 .794 .047)
    M canon .573 (.225 .669 .106)               M pop .421 (.258 .667 .075)
    L canon .444 (.295 .568 .137)               L pop .466 (.337 .615 .048)
i.e. TF material gap ~-4, internal gap ~+8 pp; H1 material L-E ~+17 pp within both strata.
Author / work random effects on the logits (observed ICC ~0.10 / 0.15 as in v05).
Model labels: Gemma-vs-Claude confusion by cell - recall, false-yes rate matched to Gemma's cell
obstacle rate, false-yes locus mix (canonical leans social/internal, popular leans material), locus
confusion pattern from the pooled Claude x Gemma table with the cell's locus accuracy.
Humans: 4 peers with code-level noise (kappa ~0.6 vs expert), 10% overlap; expert = truth on a 50%
within-cell subsample (~900); seal-safe era x genre x canonical draw (~1,820); expert-anchored DSL.
Works / years / genres / canonical flags / authors: SimConfig.tf_disc structure (corrected primary set).

Statistics (two-sided, alpha .05): TF (a) material, (b) 2-df Wald, (c) inwardness index
d_int - d_mat; H1 (E vs L) (a) material, (b) 2-df Wald, (c) index; and the gatekeeping options.

usage: OMP_NUM_THREADS=1 uv run python -m analysis.stats.power_claude [--reps 100] [--procs 7]
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from analysis import select_annotation as sa
from analysis.stats import dsl, models
from analysis.stats.annotators import cohen_kappa
from analysis.stats.simulate import LLMNoise, SimConfig, simulate

OUT = Path(__file__).resolve().parent / "out"
K = 4
ERAS = ("E", "M", "L")
# Claude reference cells: (obstacle rate, material, social, internal)
CLAUDE = {("E", True): (0.471, 0.150, 0.737, 0.113), ("E", False): (0.485, 0.159, 0.794, 0.047),
          ("M", True): (0.573, 0.225, 0.669, 0.106), ("M", False): (0.421, 0.258, 0.667, 0.075),
          ("L", True): (0.444, 0.295, 0.568, 0.137), ("L", False): (0.466, 0.337, 0.615, 0.048)}
# Gemma vs Claude by cell: (Gemma obstacle rate, recall, locus accuracy on both-yes)
GEMMA = {("E", True): (0.727, 0.956, 0.832), ("E", False): (0.649, 0.940, 0.835),
         ("M", True): (0.703, 0.889, 0.849), ("M", False): (0.612, 0.971, 0.935),
         ("L", True): (0.656, 0.912, 0.673), ("L", False): (0.573, 0.896, 0.801)}
FP_MIX = {True: np.array([16, 99, 27], float), False: np.array([31, 73, 23], float)}   # (mat, soc, int)
CONF = np.array([[83, 30, 7], [22, 322, 30], [5, 17, 37]], float)   # rows Claude mat/soc/int -> Gemma
PEER_ERR = (0.32, 0.36, 0.40, 0.44)          # code-level replacement rate -> kappa ~ 1 - e ~ 0.6
SD = {"obs_a": 0.45, "obs_w": 0.35, "loc_a": 0.75, "loc_w": 0.6}


def h1_era(y):
    return np.where(y < 1850, "E", np.where(y < 1885, "M", "L"))


def true_codes(lab: pd.DataFrame, rng, scale_tf: float = 1.0, scale_h1: float = 1.0) -> np.ndarray:
    """scale_tf / scale_h1 shrink the canon gap / the era trend toward the pooled cell values."""
    era = h1_era(lab.year.values)
    can = lab.canonical.values.astype(bool)
    authors, ai = np.unique(lab.author_key.values, return_inverse=True)
    works, wi = np.unique(lab.work_id.values, return_inverse=True)
    ua = rng.normal(0, 1, (len(authors), 3))
    uw = rng.normal(0, 1, (len(works), 3))
    tab = pd.DataFrame(CLAUDE, index=["rate", "mat", "soc", "int"]).T
    era_mean = tab.groupby(level=0).mean()
    canon_mean = tab.groupby(level=1).mean()
    grand = tab.mean()
    n = len(lab)
    out = np.zeros(n, int)
    rate = np.zeros(n)
    probs = np.zeros((n, 3))
    for (e, c), row in tab.iterrows():
        m = (era == e) & (can == c)
        # shrink: cell = grand + scale_h1*(era effect) + scale_tf*(canon effect) + interaction*min
        eff = grand + scale_h1 * (era_mean.loc[e] - grand) + scale_tf * (canon_mean.loc[c] - grand) \
            + min(scale_tf, scale_h1) * (row - era_mean.loc[e] - canon_mean.loc[c] + grand)
        rate[m] = eff["rate"]
        probs[m] = np.clip([eff["mat"], eff["soc"], eff["int"]], 0.005, None)
    lo = np.log(rate / (1 - rate)) + SD["obs_a"] * ua[ai, 0] + SD["obs_w"] * uw[wi, 0]
    obs = rng.random(n) < 1 / (1 + np.exp(-lo))
    lg = np.log(probs / probs[:, [1]])           # social reference
    lg[:, 0] += SD["loc_a"] * ua[ai, 1] + SD["loc_w"] * uw[wi, 1]
    lg[:, 2] += SD["loc_a"] * ua[ai, 2] + SD["loc_w"] * uw[wi, 2]
    p = np.exp(lg - lg.max(1, keepdims=True))
    p /= p.sum(1, keepdims=True)
    loc = (p.cumsum(1) < rng.random(n)[:, None]).sum(1)          # 0 mat, 1 soc, 2 int
    code = np.array([1, 2, 3])[loc]                              # locus target codes
    out[obs] = code[obs]
    return out


def gemma_codes(y: np.ndarray, lab: pd.DataFrame, rng) -> np.ndarray:
    era = h1_era(lab.year.values)
    can = lab.canonical.values.astype(bool)
    n = len(y)
    out = np.zeros(n, int)
    for (e, c), (g_rate, rec, acc) in GEMMA.items():
        m = (era == e) & (can == c)
        if not m.any():
            continue
        c_rate = (y[m] > 0).mean()
        fp = np.clip((g_rate - rec * c_rate) / max(1 - c_rate, 1e-6), 0, 1)
        idx = np.where(m)[0]
        yo = y[idx] > 0
        pred_obs = np.where(yo, rng.random(len(idx)) < rec, rng.random(len(idx)) < fp)
        fpm = pred_obs & ~yo
        out[idx[fpm]] = 1 + rng.choice(3, fpm.sum(), p=FP_MIX[c] / FP_MIX[c].sum())
        tp = pred_obs & yo
        # locus confusion: off-diagonal pattern from CONF, diagonal scaled to the cell accuracy
        off = CONF.copy()
        np.fill_diagonal(off, 0)
        off = off / off.sum(1, keepdims=True)
        tl = y[idx[tp]] - 1
        keep = rng.random(tp.sum()) < acc
        alt = np.array([rng.choice(3, p=off[k]) for k in tl]) if tp.sum() else np.array([], int)
        out[idx[tp]] = 1 + np.where(keep, tl, alt)
    return out


def peer_codes(y: np.ndarray, err: float, marg: np.ndarray, rng) -> np.ndarray:
    rep = rng.random(len(y)) < err
    return np.where(rep, rng.choice(K, len(y), p=marg), y)


def h1_index(e) -> tuple[float, float, float]:
    V = e.extra["era_shares"]["_cov"]
    d = e.components[1].estimate - e.components[0].estimate
    se = float(np.sqrt(max(V[0, 0] + V[1, 1] - 2 * V[0, 1], 0)))
    return d, se, float(2 * stats.norm.sf(abs(d) / se))


def one_rep(args) -> list[dict]:
    scale_tf, scale_h1, seed = args
    rng = np.random.default_rng(seed + 29)
    c = simulate(SimConfig.tf_disc(seed=seed, noise=LLMNoise.perfect()), audit=False)
    lab = c.labels[(c.labels.split == "confirmation") & (c.labels.stratum == "random")].reset_index(drop=True)
    y = true_codes(lab, rng, scale_tf, scale_h1)
    yhat = gemma_codes(y, lab, rng)
    era = h1_era(lab.year.values)
    pos = pd.Series(np.arange(len(lab)), index=lab.passage_id)
    folds = dsl._fold_ids(lab.author_key, 5, seed)
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
    # peers: 4 annotators, random assignment, 10% overlap
    ids = np.where(R3)[0]
    rng.shuffle(ids)
    marg = np.bincount(y, minlength=K) / len(y)
    S = np.zeros((len(lab), K))
    cnt = np.zeros(len(lab))
    n_ov = int(0.1 * len(ids))
    kap = []
    for a, e in enumerate(PEER_ERR):
        mine = np.concatenate([ids[a::4], ids[:n_ov][(np.arange(n_ov) % 4) == (a - 1) % 4]])
        pc = peer_codes(y[mine], e, marg, rng)
        S[mine, pc] += 1
        cnt[mine] += 1
        ex = Rh[mine]
        kap.append(cohen_kappa(pc[ex], y[mine][ex]))
    keep_peer = [k >= 0.40 for k in kap]          # registered exclusion (here none expected)
    S = np.where(cnt[:, None] > 0, S / np.maximum(cnt, 1)[:, None], 0)
    Yt = dsl.pseudo_outcomes_anchored(yhat, S, R3, frame.set_index("passage_id").pi_audit.loc[lab.passage_id].values,
                                      y, Rh, pih, K, folds, era)
    wd = dsl.aggregate_to_works(lab, {"locus": Yt}, "A")
    wo = dsl.aggregate_to_works(lab, {"locus": dsl.onehot(y, K)}, "oracle")
    design = models.Design.from_data(wo)
    ref = models._ref(wo, None)
    row = {"scale_tf": scale_tf, "scale_h1": scale_h1, "seed": seed, "kappa_peers": float(np.mean(kap)),
           "n_excluded": int(sum(not k for k in keep_peer))}
    for wts, inter in (("works", False), ("era_equal", True)):
        tag = "TF" if wts == "works" else "TFeq"
        e = models.tf_statistics(wd, design, ref, weights=wts, interact=inter)
        o = models.tf_statistics(wo, design, ref, weights=wts, interact=inter)
        row.update({f"{tag}_p_mat": e["p_mat"], f"{tag}_p_wald": e["p_wald"], f"{tag}_p_index": e["p_index"],
                    f"{tag}_d_mat": e["d_mat"], f"{tag}_se_mat": e["se_mat"], f"{tag}_d_int": e["d_int"],
                    f"{tag}_se_int": e["se_int"], f"{tag}_d_index": e["d_index"], f"{tag}_se_index": e["se_index"],
                    f"{tag}_truth_mat": o["d_mat"], f"{tag}_truth_int": o["d_int"], f"{tag}_truth_index": o["d_index"]})
    eh, oh = models.h1(wd, design, ref, alpha=0.05), models.h1(wo, design, ref, alpha=0.05)
    dI, seI, pI = h1_index(eh)
    row.update({"H1_p_mat": eh.components[0].p_two, "H1_p_wald": eh.p, "H1_p_index": pI,
                "H1_d_mat": eh.components[0].estimate, "H1_se_mat": eh.components[0].se,
                "H1_d_int": eh.components[1].estimate, "H1_se_int": eh.components[1].se,
                "H1_d_index": dI, "H1_se_index": seI, "H1_cls": eh.extra["classification"],
                "H1_truth_mat": oh.components[0].estimate, "H1_truth_int": oh.components[1].estimate,
                "H1_truth_index": h1_index(oh)[0]})
    return [row]


def summarise(raw: pd.DataFrame) -> pd.DataFrame:
    z = stats.norm.isf(0.025) + stats.norm.isf(0.2)
    out = []
    for key, g in raw.groupby(["scale_tf", "scale_h1"]):
        r = {"scale_tf": key[0], "scale_h1": key[1], "reps": len(g), "kappa_peers": g.kappa_peers.mean()}
        for t in ("TF", "TFeq", "H1"):
            for stt, pcol, se, tr in (("a_mat", "p_mat", "se_mat", "truth_mat"), ("b_wald", "p_wald", None, None),
                                      ("c_index", "p_index", "se_index", "truth_index")):
                r[f"{t}_{stt}_power"] = float((g[f"{t}_{pcol}"] < 0.05).mean())
                if se:
                    r[f"{t}_{stt}_truth_pp"] = 100 * g[f"{t}_{tr}"].mean()
                    r[f"{t}_{stt}_mde_pp"] = 100 * z * float(np.sqrt(np.mean(g[f"{t}_{se}"] ** 2)))
            r[f"{t}_int_truth_pp"] = 100 * g[f"{t}_truth_int"].mean()
        # multiplicity designs for TF (index) + H1 (Wald), alpha .05 family-wise
        tf_p, h1_p = g.TF_p_index, g.H1_p_wald
        r["gate_TF_then_H1__P(TF)"] = float((tf_p < 0.05).mean())
        r["gate_TF_then_H1__P(H1 & TF)"] = float(((tf_p < 0.05) & (h1_p < 0.05)).mean())
        r["split_025__P(TF)"] = float((tf_p < 0.025).mean())
        r["split_025__P(H1)"] = float((h1_p < 0.025).mean())
        r["H1_secondary_holm__P(H1)"] = float((h1_p < 0.05 / 3).mean())   # worst-case Holm step among 3
        out.append(r)
    return pd.DataFrame(out)


def main(reps: int = 100, procs: int = 7) -> pd.DataFrame:
    jobs = [(st, sh, 5000 + r) for st, sh in ((1.0, 1.0), (0.7, 0.7), (0.0, 0.0), (1.0, 0.0), (0.0, 1.0))
            for r in range(reps)]
    rows = []
    with mp.get_context("fork").Pool(procs) as pool:
        for i, r in enumerate(pool.imap_unordered(one_rep, jobs)):
            rows.extend(r)
            if i % 50 == 0:
                print(f"{i + 1}/{len(jobs)}", flush=True)
    raw = pd.DataFrame(rows)
    OUT.mkdir(exist_ok=True)
    raw.to_csv(OUT / "power_claude_raw.csv", index=False)
    s = summarise(raw)
    s.to_csv(OUT / "power_claude.csv", index=False)
    return s


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=100)
    ap.add_argument("--procs", type=int, default=7)
    a = ap.parse_args()
    main(a.reps, a.procs)
