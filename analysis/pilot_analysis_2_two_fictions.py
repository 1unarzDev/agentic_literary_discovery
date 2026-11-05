"""Pilot analysis 2: two fictions (TF), EXPLORATORY, Discovery only, raw model labels (no DSL, no human labels).

Data: view `results` in data/work/ald.duckdb (deduped across sources), stage `label`, pin 41ca3c7d (v0.9, gemma)
and stage `alt_label`, pin ca0c1188 (qwen) for the robustness check. Passages are mapped to works with
pipeline.split_v2_map (split_v2); only split_v2 == discovery, the registered primary set (primary_v2_capv2, which
includes the verified-date exclusions) and the random backbone (stratum == random) are kept. Era = era_v2.
canonical from data/work/canon.parquet.

SEAL: rows are filtered to Discovery by passage id BEFORE output_json is parsed; any non-Discovery row is counted
and dropped unread (the view holds none by construction).

Estimator (the work is the unit, as in prereg §2): per work, p_obs = mean has_obstacle and p_k = mean
(obstacle and locus k) over its labelled random passages; share_k = sum_w p_k / sum_w p_obs (ratio of work means,
works weighted equally); obstacle rate = mean_w p_obs. CIs: work-cluster bootstrap (B = 2000, works resampled
within era x canonical cells); author-group cluster bootstrap for the headline gaps.

  uv run python -I analysis/pilot_analysis_2_two_fictions.py [--fig] [--examples] [--B 2000]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.split_v2_map import SplitV2  # noqa: E402

WORK = ROOT / "data/work"
FIG = ROOT / "analysis/figs/tf_pilot.png"
OUT = ROOT / "analysis/stats/out/tf_pilot"
LOCI = {"material_external": "material", "social_institutional": "social", "internal_psychological": "internal"}
COLORS = {"material": "#b07400", "social": "#2a78d6", "internal": "#d55181"}
ERAS = ["E", "M", "L"]
SEED = 20261104


def load_labels(stage: str, pin: str) -> pd.DataFrame:
    con = duckdb.connect(str(WORK / "ald.duckdb"), read_only=True)
    ids = con.execute("SELECT passage_id FROM results WHERE stage = ? AND pin_hash LIKE ?", [stage, pin + "%"]).df()
    w = pd.read_parquet(WORK / "works_v2.parquet",
                        columns=["pg_id", "work_id", "split", "split_v2", "author_group", "author_name", "Title",
                                 "year_v2", "era_v2", "genre", "primary_v2_capv2"])
    m = SplitV2.from_frame(w).reassign(ids)
    keep = m.loc[m.split_v2.eq("discovery"), ["passage_id", "work_id_v2"]]
    dropped = len(ids) - len(keep)
    con.register("keep_ids", keep[["passage_id"]])
    r = con.execute("SELECT r.passage_id, r.output_json, r.quote_status FROM results r JOIN keep_ids k USING (passage_id) "
                    "WHERE r.stage = ? AND r.pin_hash LIKE ? AND r.valid_schema", [stage, pin + "%"]).df()
    r = r.merge(keep.rename(columns={"work_id_v2": "work_id"}), on="passage_id")
    o = pd.json_normalize(r.output_json.map(json.loads))
    r = pd.concat([r.drop(columns="output_json").reset_index(drop=True),
                   o[["has_obstacle", "locus", "domains", "evidence_quote", "confidence", "obstacle_summary"]]], axis=1)
    p = pd.read_parquet(WORK / "passages.parquet", columns=["passage_id", "stratum"])
    r = r.merge(p, on="passage_id", how="left")
    c = pd.read_parquet(WORK / "canon.parquet", columns=["work_id", "canonical"])
    r = r.merge(w.drop(columns=["pg_id", "split", "split_v2"]), on="work_id").merge(c, on="work_id", how="left")
    r.attrs["dropped_non_discovery"] = int(dropped)
    r.attrs["n_all_discovery"] = len(r)
    r = r[r.primary_v2_capv2.fillna(False).astype(bool) & r.stratum.eq("random") & r.era_v2.isin(ERAS)].copy()
    r["canonical"] = r.canonical.fillna(False).astype(bool)
    r["obs"] = r.has_obstacle.eq("yes").astype(float)
    for k, v in LOCI.items():
        r[v] = (r.obs.astype(bool) & r.locus.eq(k)).astype(float)
    return r


def work_table(r: pd.DataFrame) -> pd.DataFrame:
    return r.groupby("work_id").agg(era=("era_v2", "first"), canonical=("canonical", "first"),
                                    author=("author_group", "first"), genre=("genre", "first"), n=("obs", "size"),
                                    obs=("obs", "mean"), material=("material", "mean"), social=("social", "mean"),
                                    internal=("internal", "mean")).reset_index()


def stats(w: pd.DataFrame) -> dict:
    o = w.obs.sum()
    d = {k: w[k].sum() / o if o > 0 else np.nan for k in COLORS}
    d["obs_rate"] = w.obs.mean()
    return d


def cell_stats(w: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for era in ERAS + ["all"]:
        for can in (True, False, None):
            s = w if era == "all" else w[w.era == era]
            s = s if can is None else s[s.canonical == can]
            rows.append({"era": era, "canonical": can, **stats(s), "n_works": len(s), "n_passages": int(s.n.sum()),
                         "n_obstacles": float((s.obs * s.n).sum()), "n_authors": s.author.nunique()})
    return pd.DataFrame(rows)


def shift_share(w: pd.DataFrame, a: str, b: str, k: str = "material") -> dict:
    """Bennet decomposition of the a -> b change in share_k over the canonical/non-canonical strata:
    total = sum_g sbar_g dtheta_g (within) + sum_g thetabar_g ds_g (composition); s_g = stratum's obstacle mass."""
    out = {}
    th, s = {}, {}
    for era in (a, b):
        e = w[w.era == era]
        O = e.obs.sum()
        for g in (True, False):
            eg = e[e.canonical == g]
            th[era, g] = eg[k].sum() / eg.obs.sum()
            s[era, g] = eg.obs.sum() / O
        out[f"agg_{era}"] = e[k].sum() / O
    within = sum((s[a, g] + s[b, g]) / 2 * (th[b, g] - th[a, g]) for g in (True, False))
    comp = sum((th[a, g] + th[b, g]) / 2 * (s[b, g] - s[a, g]) for g in (True, False))
    out.update(total=out[f"agg_{b}"] - out[f"agg_{a}"], within=within, composition=comp,
               canon_share_a=s[a, True], canon_share_b=s[b, True])
    return out


def boot_index(w: pd.DataFrame, B: int, seed: int, cluster: str = "work") -> list[np.ndarray]:
    """Row-index resamples: works within era x canonical cells (cluster='work') or author groups (cluster='author')."""
    rng = np.random.default_rng(seed)
    if cluster == "work":
        groups = [np.flatnonzero(m) for _, m in w.groupby(["era", "canonical"]).groups.items() for m in
                  [w.index.isin(m)]]
        return [np.concatenate([rng.choice(g, len(g)) for g in groups]) for _ in range(B)]
    codes, uniq = pd.factorize(w.author)
    members = [np.flatnonzero(codes == i) for i in range(len(uniq))]
    return [np.concatenate([members[i] for i in rng.integers(0, len(uniq), len(uniq))]) for _ in range(B)]


def ci(x) -> tuple[float, float]:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return float(np.quantile(x, 0.025)), float(np.quantile(x, 0.975))


def summarize(w: pd.DataFrame, B: int, seed: int = SEED) -> dict:
    w = w.reset_index(drop=True)
    est = cell_stats(w)
    gaps = gap_table(w)
    ss = {f"{a}->{b}": shift_share(w, a, b) for a, b in (("E", "L"), ("M", "L"), ("E", "M"))}
    ss_int = {f"{a}->{b}": shift_share(w, a, b, "internal") for a, b in (("E", "L"), ("M", "L"))}
    res = {"cells": est, "gaps": gaps, "ss": ss, "ss_int": ss_int}
    for cl in ("work", "author"):
        bs_cells, bs_gaps, bs_ss, bs_ssi = [], [], [], []
        for idx in boot_index(w, B, seed, cl):
            bw = w.iloc[idx]
            if cl == "work":
                bs_cells.append(cell_stats(bw)[list(COLORS) + ["obs_rate"]].to_numpy())
            bs_gaps.append(gap_table(bw)[["gap_material", "gap_social", "gap_internal", "gap_obs"]].to_numpy())
            try:
                bs_ss.append([[v[k] for k in ("total", "within", "composition")] for v in
                              (shift_share(bw, *p.split("->")) for p in ss)])
                bs_ssi.append([[v[k] for k in ("total", "within", "composition")] for v in
                               (shift_share(bw, *p.split("->"), "internal") for p in ss_int)])
            except ZeroDivisionError:
                pass
        res[f"boot_{cl}"] = {"cells": np.array(bs_cells) if bs_cells else None, "gaps": np.array(bs_gaps),
                             "ss": np.array(bs_ss), "ss_int": np.array(bs_ssi)}
    return res


def gap_table(w: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for era in ERAS + ["all"]:
        s = w if era == "all" else w[w.era == era]
        c, n = stats(s[s.canonical]), stats(s[~s.canonical])
        rows.append({"era": era, **{f"gap_{k}": c[k] - n[k] for k in COLORS}, "gap_obs": c["obs_rate"] - n["obs_rate"]})
    # era-standardised pooled gap: era gaps weighted by each era's share of all works
    wt = w.era.value_counts(normalize=True)
    g = pd.DataFrame(rows[:3]).set_index("era")
    rows.append({"era": "std", **{c: float((g[c] * wt.reindex(g.index)).sum()) for c in g.columns}})
    return pd.DataFrame(rows)


def fmt(x, lo, hi, pp=True) -> str:
    f = 100 if pp else 1
    return f"{x * f:+.1f} [{lo * f:+.1f}, {hi * f:+.1f}]" if pp else f"{x:.3f} [{lo:.3f}, {hi:.3f}]"


def share_fmt(x, lo, hi) -> str:
    return f"{x:.3f} [{lo:.3f}, {hi:.3f}]"


def report(res: dict, label: str) -> str:
    L = [f"### {label}"]
    cells, bc = res["cells"], res["boot_work"]["cells"]
    L.append("| Era | Stratum | Works | Authors | Passages | Obstacle rate | Material | Social | Internal |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for i, r in cells.iterrows():
        st = {True: "canonical", False: "non-canonical", None: "all"}[r.canonical]
        q = [share_fmt(r[k], *ci(bc[:, i, j])) for j, k in enumerate(list(COLORS) + ["obs_rate"])]
        L.append(f"| {r.era} | {st} | {r.n_works:,} | {r.n_authors:,} | {r.n_passages:,} | {q[3]} | {q[0]} | {q[1]} | {q[2]} |")
    L.append("")
    L.append("**Canonical − non-canonical gap (pp), work-bootstrap CI / author-bootstrap CI:**")
    L.append("")
    L.append("| Era | Material | Social | Internal | Obstacle rate |")
    L.append("|---|---|---|---|---|")
    g, bw, ba = res["gaps"], res["boot_work"]["gaps"], res["boot_author"]["gaps"]
    for i, r in g.iterrows():
        cells_ = []
        for j, k in enumerate(["gap_material", "gap_social", "gap_internal", "gap_obs"]):
            lo, hi = ci(bw[:, i, j])
            alo, ahi = ci(ba[:, i, j])
            cells_.append(f"{r[k] * 100:+.1f} [{lo * 100:+.1f}, {hi * 100:+.1f}] / [{alo * 100:+.1f}, {ahi * 100:+.1f}]")
        name = {"std": "pooled, era-standardised", "all": "pooled, raw"}.get(r.era, r.era)
        L.append(f"| {name} | " + " | ".join(cells_) + " |")
    L.append("")
    for key, nm in (("ss", "material"), ("ss_int", "internal")):
        L.append(f"**Composition decomposition of the aggregate {nm} share (pp), canonical/non-canonical strata, "
                 "work-bootstrap CI / author-bootstrap CI:**")
        L.append("")
        L.append("| Contrast | Aggregate shares | Canonical share of obstacles | Total Δ | Within-stratum | Composition |")
        L.append("|---|---|---|---|---|---|")
        for i, (p, v) in enumerate(res[key].items()):
            a, b = p.split("->")
            bw_, ba_ = res["boot_work"][key], res["boot_author"][key]
            c3 = []
            for j, k in enumerate(("total", "within", "composition")):
                lo, hi = ci(bw_[:, i, j]); alo, ahi = ci(ba_[:, i, j])
                c3.append(f"{v[k] * 100:+.1f} [{lo * 100:+.1f}, {hi * 100:+.1f}] / [{alo * 100:+.1f}, {ahi * 100:+.1f}]")
            L.append(f"| {a} → {b} | {v['agg_' + a]:.3f} → {v['agg_' + b]:.3f} | {v['canon_share_a']:.0%} → "
                     f"{v['canon_share_b']:.0%} | " + " | ".join(c3) + " |")
        L.append("")
    return "\n".join(L)


def figure(res: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cells, bc = res["cells"], res["boot_work"]["cells"]
    fig, axes = plt.subplots(1, 3, figsize=(11, 4.1), sharey=False)
    x = np.arange(3) * 1.0
    for ax, (j, k) in zip(axes, enumerate(COLORS)):
        for can, dx, mk, fill in ((True, -0.13, "o", True), (False, 0.13, "s", False)):
            ii = [cells.index[(cells.era == e) & (cells.canonical == can)][0] for e in ERAS]
            y = cells.loc[ii, k].to_numpy()
            lo = np.array([ci(bc[:, i, j])[0] for i in ii]); hi = np.array([ci(bc[:, i, j])[1] for i in ii])
            ax.errorbar(x + dx, y, yerr=[y - lo, hi - y], fmt=mk, ms=7, color=COLORS[k], capsize=3, lw=1.4,
                        mfc=COLORS[k] if fill else "white", mew=1.6, ls="-" if can else "--",
                        label="canonical" if can else "non-canonical")
            for xi, loi, i in zip(x + dx, lo, ii):
                ax.annotate(f"{cells.loc[i, 'n_works']:,}", (xi, loi), textcoords="offset points", xytext=(0, -10),
                            ha="center", fontsize=7, color="#555555")
        ax.set_xticks(x, ["1800–49", "1850–84", "1885–1929"])
        ax.set_title(f"{k} share of obstacles", fontsize=11, color="#222222", loc="left")
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", color="#e6e6e6", lw=0.8)
        ax.set_axisbelow(True)
        ax.set_xlim(-0.4, 2.4)
        lo_, hi_ = ax.get_ylim()
        ax.set_ylim(max(0, lo_ - 0.02), hi_ + 0.01)
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], color="#444444", marker="o", ms=7, ls="-", label="canonical (filled, solid)"),
               Line2D([], [], color="#444444", marker="s", ms=7, mfc="white", mew=1.6, ls="--",
                      label="non-canonical (open, dashed)")]
    fig.legend(handles=handles, frameon=False, fontsize=8.5, ncol=2, loc="upper left", bbox_to_anchor=(0.01, 0.93))
    fig.suptitle("Two fictions (exploratory; Discovery half; raw model labels): where obstacles come from, "
                 "canonical vs non-canonical works", fontsize=10.5, x=0.01, ha="left")
    fig.text(0.01, 0.005, "Points: ratio of work means; bars: 95% work-cluster bootstrap CI; numbers: works per cell. "
             "No human correction (DSL) applied.", fontsize=7.5, color="#555555")
    fig.tight_layout(rect=(0, 0.03, 1, 0.88))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200)


def alt_compare(r: pd.DataFrame, alt: pd.DataFrame, B: int) -> tuple[str, dict]:
    ov = r.merge(alt[["passage_id", "obs", "material", "social", "internal", "locus", "has_obstacle"]],
                 on="passage_id", suffixes=("", "_alt"))
    lines = [f"Overlap: {len(ov):,} passages from {ov.work_id.nunique():,} works "
             f"({ov[ov.canonical].work_id.nunique():,} canonical)."]
    both = ov[ov.obs.astype(bool) & ov.obs_alt.astype(bool)]
    agree_obs = (ov.has_obstacle == ov.has_obstacle_alt).mean()
    agree_loc = (both.locus == both.locus_alt).mean()
    lines.append(f"Obstacle rate on the overlap: gemma {ov.obs.mean():.3f}, qwen {ov.obs_alt.mean():.3f}. "
                 f"has_obstacle agreement {agree_obs:.3f}; locus agreement where both say obstacle {agree_loc:.3f} "
                 f"(n = {len(both):,}).")
    out = {}
    for tag, suf in (("gemma (v0.9 label)", ""), ("qwen (alt_label)", "_alt")):
        t = ov.assign(obs=ov["obs" + suf], material=ov["material" + suf], social=ov["social" + suf],
                      internal=ov["internal" + suf])
        w = work_table(t).reset_index(drop=True)
        g = gap_table(w)
        bs = np.array([gap_table(w.iloc[i])[["gap_material", "gap_social", "gap_internal", "gap_obs"]].to_numpy()
                       for i in boot_index(w, B, SEED, "work")])
        out[tag] = (g, bs, cell_stats(w))
    lines.append("")
    lines.append("| Model | Era | Material gap | Social gap | Internal gap | Material share canon / non-canon |")
    lines.append("|---|---|---|---|---|---|")
    for tag, (g, bs, cs) in out.items():
        for i, r_ in g.iterrows():
            if r_.era == "all":
                continue
            c = [f"{r_[k] * 100:+.1f} [{ci(bs[:, i, j])[0] * 100:+.1f}, {ci(bs[:, i, j])[1] * 100:+.1f}]"
                 for j, k in enumerate(["gap_material", "gap_social", "gap_internal"])]
            if r_.era == "std":
                sh = "—"
            else:
                a_ = cs[(cs.era == r_.era) & (cs.canonical == True)].iloc[0]  # noqa: E712
                b_ = cs[(cs.era == r_.era) & (cs.canonical == False)].iloc[0]  # noqa: E712
                sh = f"{a_.material:.3f} / {b_.material:.3f} (works {a_.n_works} / {b_.n_works})"
            nm = "pooled, era-std" if r_.era == "std" else r_.era
            lines.append(f"| {tag} | {nm} | " + " | ".join(c) + f" | {sh} |")
    return "\n".join(lines), out


def examples(r: pd.DataFrame, n: int = 12, seed: int = SEED) -> pd.DataFrame:
    """Candidate quotes per locus x stratum, verified verbatim against passages.parquet text."""
    c = r[r.obs.astype(bool) & r.locus.isin(LOCI) & r.confidence.astype(float).ge(0.8)].copy()
    c = c[c.evidence_quote.str.len().between(40, 170)]
    txt = pd.read_parquet(WORK / "passages.parquet", columns=["passage_id", "text"],
                          filters=[("passage_id", "in", c.passage_id.tolist())])
    c = c.merge(txt, on="passage_id")
    c["verbatim"] = [q in t for q, t in zip(c.evidence_quote, c.text)]
    c = c[c.verbatim]
    out = []
    for loc in LOCI:
        for can in (True, False):
            s = c[(c.locus == loc) & (c.canonical == can)]
            out.append(s.sample(min(n, len(s)), random_state=seed))
    return pd.concat(out)[["passage_id", "locus", "canonical", "author_name", "Title", "year_v2", "era_v2", "genre",
                           "evidence_quote", "obstacle_summary", "quote_status"]]


def fig_only(B: int = 2000) -> None:
    r = load_labels("label", "41ca3c7d")
    w = work_table(r).reset_index(drop=True)
    res = {"cells": cell_stats(w), "boot_work": {"cells": np.array(
        [cell_stats(w.iloc[i])[list(COLORS) + ["obs_rate"]].to_numpy() for i in boot_index(w, B, SEED, "work")])}}
    figure(res, FIG)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--B", type=int, default=2000)
    ap.add_argument("--fig", action="store_true")
    ap.add_argument("--examples", action="store_true")
    ap.add_argument("--fig-only", action="store_true")
    a = ap.parse_args(argv)
    if a.fig_only:
        fig_only(a.B)
        return
    OUT.mkdir(parents=True, exist_ok=True)
    r = load_labels("label", "41ca3c7d")
    print(f"label rows: dropped non-Discovery {r.attrs['dropped_non_discovery']}, Discovery rows {r.attrs['n_all_discovery']}, "
          f"analysed (primary, random, in window) {len(r)}; quote_status {r.quote_status.value_counts().to_dict()}")
    w = work_table(r)
    res = summarize(w, a.B)
    md = [report(res, "v0.9 label model (gemma4 12B, pin 41ca3c7d)")]
    res["cells"].to_csv(OUT / "cells.csv", index=False)
    res["gaps"].to_csv(OUT / "gaps.csv", index=False)
    # sensitivity: drop juvenile; drop quote-hallucinated rows
    for nm, mask in (("without LCSH-juvenile works", w.genre.ne("juvenile")),):
        rs = summarize(w[mask], max(500, a.B // 4))
        md.append(report(rs, f"Sensitivity: {nm}"))
    rq = r[~r.quote_status.eq("hallucinated")]
    md.append(report(summarize(work_table(rq), max(500, a.B // 4)), "Sensitivity: quote-hallucinated rows dropped"))
    alt = load_labels("alt_label", "ca0c1188")
    print(f"alt rows: dropped non-Discovery {alt.attrs['dropped_non_discovery']}, analysed {len(alt)}")
    txt, _ = alt_compare(r, alt, max(500, a.B // 4))
    md.append("### Robustness: second model (qwen, alt_label, pin ca0c1188) on the overlapping passages\n\n" + txt)
    (OUT / "report.md").write_text("\n\n".join(md) + "\n", encoding="utf-8")
    print("\n\n".join(md))
    if a.fig:
        figure(res, FIG)
        print("wrote", FIG)
    if a.examples:
        ex = examples(r)
        ex.to_csv(OUT / "example_candidates.csv", index=False)
        print("wrote", OUT / "example_candidates.csv", len(ex))


if __name__ == "__main__":
    main()
