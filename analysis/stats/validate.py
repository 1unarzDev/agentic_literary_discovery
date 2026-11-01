"""Coverage validation: DSL 95% CIs under era-varying LLM label noise, vs naive model-label CIs.

Truth = the same estimator applied to TRUE labels on a very large corpus from the same generating
process (150k works), so it is the superpopulation estimand (model-free for era shares; the
pseudo-true g-computation contrast for the H1 regressions, computed per link with fixed knots and a
fixed reference covariate table).

usage: uv run python -m analysis.stats.validate [--reps 300] [--audit 200,1000,4000] [--procs 16]
writes analysis/stats/out/coverage_raw.csv, coverage.csv and figs/dsl_coverage.png
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
from pathlib import Path

import numpy as np
import pandas as pd

from analysis.stats import dsl, models
from analysis.stats.simulate import SimConfig, simulate

HERE = Path(__file__).resolve().parent
OUT, FIGS = HERE / "out", HERE / "figs"
H1_ERAS = {"early": (1800, 1849), "mid": (1850, 1884), "late": (1885, 1929)}   # G0 eras
TARGET_SHARES = [("locus", "material", [1], [1, 2, 3]), ("locus", "internal", [3], [1, 2, 3]),
                 ("obstacle", "prevalence", [1], None), ("darkness", "darkness", [1], None)]
ESTIMATORS = [("naive", "raw"), ("dsl", "raw"), ("dsl", "calib"), ("dsl", "calib_s")]


def era_of(year: np.ndarray) -> np.ndarray:
    out = np.full(len(year), None, dtype=object)
    for k, (a, b) in H1_ERAS.items():
        out[(year >= a) & (year <= b)] = k
    return out


def estimates(wd: dsl.WorkData, design: models.Design, ref: pd.DataFrame, links=("identity",)) -> list[dict]:
    rows = []
    era = era_of(wd.cov.year.values)
    for tgt, lab, num, den in TARGET_SHARES:
        r = dsl.ratio_shares(wd, tgt, num, den, by=era)
        for _, x in r.table.iterrows():
            rows.append({"quantity": f"{lab} share [{x['group']}]", "est": x.estimate, "se": x.se})
        d, s = r.contrast("early", "late", num[0])
        rows.append({"quantity": f"{lab} raw contrast late-early", "est": d, "se": s})
    for link in links:
        models.LINK["default"] = link
        e = models.h1(wd, design, ref_cov=ref)
        for c in e.components[:2]:
            rows.append({"quantity": f"H1 {c.label} contrast [{link}]", "est": c.estimate, "se": c.se,
                         "fallback": e.extra["fit"].fit.n_iter == -1})
    models.LINK["default"] = "logit"
    return rows


def truth_table(seed: int = 999, n_works: int = 150_000) -> tuple[pd.DataFrame, models.Design, pd.DataFrame]:
    c = simulate(SimConfig(n_works=n_works, passages_per_work=4, seed=seed, wpa_max=20), audit=False)
    wd = dsl.prepare(c.labels, method="oracle", truth=c.truth, split=None,
                     targets=("locus", "obstacle", "darkness"))
    design = models.Design.from_data(wd)
    ref = wd.cov.sample(n=3000, random_state=1).reset_index(drop=True)
    t = pd.DataFrame(estimates(wd, design, ref, links=("identity", "logit")))[["quantity", "est"]]
    return t.rename(columns={"est": "truth"}), design, ref


def one_rep(args) -> list[dict]:
    seed, audit_n, design, ref = args
    c = simulate(SimConfig(seed=seed, audit_n=audit_n))
    rows = []
    for meth, g in ESTIMATORS:
        wd = dsl.prepare(c.labels, c.human, c.frame, method=meth, g=g, targets=("locus", "obstacle", "darkness"),
                         seed=seed)
        links = ("identity", "logit") if (meth, g) in (("dsl", "calib"), ("naive", "raw")) else ("identity",)
        name = "naive" if meth == "naive" else f"dsl_{g}"
        for r in estimates(wd, design, ref, links):
            rows.append({**r, "estimator": name, "seed": seed, "audit_n": audit_n,
                         "n_labelled": wd.info.get("n_labelled", 0)})
    # PPI cross-check: passage-level obstacle prevalence per H1 era, stratified by audit cell
    lab = c.labels[(c.labels.split == "confirmation") & (c.labels.stratum == "random")].reset_index(drop=True)
    fr = lab[["passage_id"]].merge(c.frame, on="passage_id", how="left")
    h = dsl.resolve_human(c.human).set_index("passage_id")
    era = era_of(lab.year.values)
    yhat = (lab.has_obstacle.values == "yes").astype(float)
    for e in H1_ERAS:
        m = era == e
        ids = lab.passage_id[m]
        labd = ids[ids.isin(h.index)]
        if len(labd) < 4:
            continue
        y = (h.loc[labd, "has_obstacle"].values == "yes").astype(float)
        yh = (lab.set_index("passage_id").loc[labd, "has_obstacle"].values == "yes").astype(float)
        res = dsl.ppi_mean(yhat[m], y, yh, strata_all=fr.audit_cell.values[m], strata_lab=h.loc[labd, "audit_cell"].values)
        rows.append({"quantity": f"prevalence share [{e}]", "est": res.estimate, "se": res.se, "estimator": "ppi_strat",
                     "seed": seed, "audit_n": audit_n, "n_labelled": len(labd)})
    return rows


def summarise(raw: pd.DataFrame, truth: pd.DataFrame) -> pd.DataFrame:
    d = raw.merge(truth, on="quantity")
    d["cover"] = (d.est - 1.96 * d.se <= d.truth) & (d.truth <= d.est + 1.96 * d.se)
    d["err"] = d.est - d.truth
    g = d.groupby(["audit_n", "estimator", "quantity"])
    s = g.agg(n_lab=("n_labelled", "median"), truth=("truth", "first"), mean_est=("est", "mean"),
              bias=("err", "mean"), emp_sd=("est", "std"), mean_se=("se", "median"), coverage=("cover", "mean"),
              reps=("cover", "size")).reset_index()
    if "fallback" in d:
        s = s.merge(g.fallback.apply(lambda x: float(np.nanmean(x.astype(float))) if x.notna().any() else np.nan)
                    .rename("fallback_rate").reset_index(), on=["audit_n", "estimator", "quantity"])
    s["mc_se_cov"] = np.sqrt(s.coverage * (1 - s.coverage) / s.reps)
    return s


def figure(summ: pd.DataFrame, raw: pd.DataFrame, truth: pd.DataFrame, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ink, ink2, grid = "#0b0b0b", "#52514e", "#e4e3df"
    col = {"naive": "#eb6834", "dsl_calib": "#2a78d6", "truth": "#52514e"}
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": ink2, "axes.labelcolor": ink, "xtick.color": ink2,
                         "ytick.color": ink2, "axes.spines.top": False, "axes.spines.right": False})
    fig, (a, b) = plt.subplots(1, 2, figsize=(9, 4.2), gridspec_kw={"width_ratios": [1.1, 1]})
    an = int(sorted(raw.audit_n.unique())[-1])
    eras = list(H1_ERAS)
    for k, est in enumerate(["naive", "dsl_calib"]):
        d = raw[(raw.estimator == est) & (raw.audit_n == an) & raw.quantity.str.startswith("material share [")]
        for i, e in enumerate(eras):
            v = d[d.quantity == f"material share [{e}]"].est.values
            x = i + (k - 0.5) * 0.28
            lo, q1, md, q3, hi = np.quantile(v, [0.025, 0.25, 0.5, 0.75, 0.975])
            a.plot([x, x], [lo, hi], color=col[est], lw=1.2, solid_capstyle="round")
            a.plot([x, x], [q1, q3], color=col[est], lw=5, solid_capstyle="round")
            a.plot([x], [md], "o", color="white", ms=3, zorder=3)
    tv = [truth.set_index("quantity").truth[f"material share [{e}]"] for e in eras]
    for i, t in enumerate(tv):
        a.plot([i - 0.4, i + 0.4], [t, t], color=col["truth"], lw=1.5, ls=(0, (3, 2)))
    a.set_xticks(range(3), ["1800–49", "1850–84", "1885–1929"])
    a.set_ylabel("material share of obstacles")
    a.set_title(f"A. Sampling distribution over {raw.seed.nunique()} corpora", loc="left", color=ink, fontsize=9.5)
    a.grid(axis="y", color=grid, lw=0.6)
    a.text(2.42, tv[2], "truth", color=ink2, va="center", fontsize=8)
    a.legend(handles=[plt.Line2D([], [], color=col["naive"], lw=5, label="naive model labels"),
                      plt.Line2D([], [], color=col["dsl_calib"], lw=5, label=f"DSL ({int(raw[(raw.audit_n == an) & (raw.estimator == 'dsl_calib')].n_labelled.median())} human labels)")],
             frameon=False, loc="upper right", fontsize=8)
    # B: coverage by audit size for the key quantities
    qs = ["material share [early]", "material share [late]", "material raw contrast late-early",
          "H1 material share contrast [identity]"]
    labels = ["material 1800–49", "material 1885–1929", "contrast (raw)", "H1 contrast (model)"]
    s = summ[summ.quantity.isin(qs)]
    ans = sorted(s.audit_n.unique())
    w = 0.8 / (len(ans) + 1)
    nl = summ[summ.estimator == "dsl_calib"].groupby("audit_n").n_lab.median()
    for j, (est, nm) in enumerate([("naive", "naive model labels")] +
                                  [("dsl_calib", f"DSL, {int(nl.get(x, x))} human labels") for x in ans]):
        sub = s[s.estimator == est] if est == "naive" else s[(s.estimator == est) & (s.audit_n == ans[j - 1])]
        if est == "naive":
            sub = sub[sub.audit_n == ans[-1]]
        vals = [sub.set_index("quantity").coverage.get(q, np.nan) for q in qs]
        shade = col["naive"] if est == "naive" else ["#9ec5f0", "#5e9fe6", "#2a78d6", "#1a4f91"][min(j - 1, 3)]
        xs = np.arange(len(qs)) + (j - len(ans) / 2) * w
        b.bar(xs, vals, width=w * 0.9, color=shade, label=nm)
        if est == "naive":
            for x, v in zip(xs, vals):
                b.text(x, max(v, 0) + 0.02, f"{v:.2f}", ha="center", va="bottom", fontsize=7, color=ink2)
    b.axhline(0.95, color=ink2, lw=1, ls=(0, (3, 2)))
    b.text(len(qs) - 0.45, 0.955, "0.95", color=ink2, fontsize=8, va="bottom", ha="right")
    b.set_xticks(range(len(qs)), labels, rotation=15, ha="right")
    b.set_ylim(0, 1.05)
    b.set_ylabel("95% CI coverage")
    b.set_title("B. Coverage under era-varying label noise", loc="left", color=ink, fontsize=9.5)
    b.grid(axis="y", color=grid, lw=0.6)
    b.legend(frameon=False, fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.32), ncol=2)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, facecolor="white")
    plt.close(fig)


def main(reps: int = 300, audits=(200, 1000, 4000), procs: int = 8) -> pd.DataFrame:
    truth, design, ref = truth_table()
    jobs = [(10_000 + i, a, design, ref) for a in audits for i in range(reps)]
    with mp.get_context("fork").Pool(procs) as pool:
        raw = pd.DataFrame([r for rows in pool.imap_unordered(one_rep, jobs, chunksize=2) for r in rows])
    OUT.mkdir(exist_ok=True)
    raw.to_csv(OUT / "coverage_raw.csv", index=False)
    truth.to_csv(OUT / "coverage_truth.csv", index=False)
    summ = summarise(raw, truth)
    summ.to_csv(OUT / "coverage.csv", index=False)
    figure(summ, raw, truth, FIGS / "dsl_coverage.png")
    return summ


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=300)
    ap.add_argument("--audit", default="200,1000,4000")
    ap.add_argument("--procs", type=int, default=8)
    ap.add_argument("--figure-only", action="store_true", help="redraw from out/*.csv")
    a = ap.parse_args()
    if a.figure_only:
        raw, truth = pd.read_csv(OUT / "coverage_raw.csv"), pd.read_csv(OUT / "coverage_truth.csv")
        figure(pd.read_csv(OUT / "coverage.csv"), raw, truth, FIGS / "dsl_coverage.png")
        raise SystemExit
    s = main(a.reps, tuple(int(x) for x in a.audit.split(",")), a.procs)
    pd.set_option("display.width", 220)
    print(s[s.quantity.str.contains("material|H1|prevalence")].round(3).to_string())
