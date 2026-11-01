"""Pilot analysis 1: is the Discovery-wave material-locus rise within-genre or composition?

Discovery data only (labels: results view, stage='label'; metadata: works + genre).
Raw Tier-2 model labels with no human correction: biased, read for direction and robustness only.

usage: uv run --with pandas,duckdb,pyarrow,statsmodels,scipy,matplotlib python -I analysis/pilot_analysis_1.py [--fig]
"""
from __future__ import annotations

import json
import re
import sys
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
W = ROOT / "data/work"
FIG = ROOT / "analysis/figs/pilot_locus.png"
B = 1000
RNG = np.random.default_rng(20261101)
ERAS = ["E", "M", "L"]
LOCI = ["material_external", "social_institutional", "internal_psychological"]
SHORT = {"material_external": "material", "social_institutional": "social", "internal_psychological": "internal"}
POPULAR = {"adventure", "juvenile", "sensation_mystery", "romance"}

DEFAULT_LOCUS = {
    "DISTANCE_TRAVEL": "material_external", "DARKNESS_VISIBILITY": "material_external",
    "NATURE_WEATHER": "material_external", "ILLNESS_BODY_DEATH": "material_external",
    "MONEY_PROPERTY_LAW": "social_institutional", "SOCIAL_RANK_CONVENTION": "social_institutional",
    "INTERPERSONAL_CONFLICT": "social_institutional", "INNER_STATE": "internal_psychological",
}
OUTDOOR = re.compile(r"frontier|west \(u\.s\.\)|western|ranch|cowboy|indians|alaska|klondike|yukon|northwest|"
                     r"canada|australia|africa|india|islands|sea stories|seafaring|ships|shipwreck|voyages|"
                     r"wilderness|mountain|lumber|mines|mining|hunting|arctic|explorers|\bwar\b|world war|soldiers|army|navy", re.I)
ARCHAIC = re.compile(r"\b(thee|thou|thy|thine|hath|doth|dost|art thou|'tis|'twas|ere|whilst|wherefore|"
                     r"methinks|nay|aye|prithee|hither|thither|whence|shalt|wilt|canst|wouldst)\b", re.I)


def era_of(y):
    return pd.cut(y, [1799, 1849, 1884, 1929], labels=ERAS).astype("object")


def load() -> pd.DataFrame:
    con = duckdb.connect(str(W / "ald.duckdb"), read_only=True)
    r = con.sql("select passage_id, output_json, quote_status from results "
                "where stage='label' and job_id like '%disc%'").df()
    o = pd.json_normalize(r.output_json.map(json.loads))
    r = pd.concat([r.drop(columns="output_json"), o], axis=1)
    p = pd.read_parquet(W / "passages.parquet", columns=["passage_id", "work_id", "split", "stratum", "text"],
                        filters=[("split", "==", "discovery")])
    r = r.merge(p, on="passage_id", how="inner")
    assert (r.split == "discovery").all()
    works = pd.read_parquet(W / "works.parquet", columns=[
        "work_id", "year", "date_confidence", "origin_locc", "author_key", "n_editions", "n_words",
        "in_primary_cap", "split", "Subjects"])
    nworks = works.groupby("author_key").size().rename("author_pg_works")  # metadata, both splits
    works = works.merge(nworks, left_on="author_key", right_index=True)
    g = pd.read_parquet(W / "genre.parquet")
    d = r.drop(columns="split").merge(works, on="work_id").merge(g, on="work_id")
    d = d[d.year.between(1800, 1929)].copy()
    d["era"] = era_of(d.year)
    d["obs"] = d.has_obstacle == "yes"
    d["dom1"] = d.domains.map(lambda x: x[0] if isinstance(x, list) and x else None)
    try:
        dates = pd.read_parquet(W / "date_audit/dates.parquet", columns=["work_id", "agree_5y"])
        d = d.merge(dates, on="work_id", how="left")
    except Exception:  # date audit still running
        d["agree_5y"] = pd.NA
    d["archaic"] = d.text.map(lambda t: len(ARCHAIC.findall(t)) / max(1, len(t.split())) * 1000)
    return d.drop(columns="text")


# ---------- work-level aggregation + bootstrap over works (stratified by era) ----------
def work_table(d: pd.DataFrame, by: list[str] = ()) -> pd.DataFrame:
    ob = d[d.obs]
    t = ob.assign(**{SHORT[l]: (ob.locus == l).astype(int) for l in LOCI}, n=1)
    keys = list(dict.fromkeys(["work_id", "era", "genre", *by]))
    return t.groupby(keys, observed=True)[["material", "social", "internal", "n"]].sum().reset_index()


def boot_idx(wt: pd.DataFrame, strata: list[str]):
    groups = list(wt.groupby(strata, observed=True).indices.values())
    for _ in range(B):
        yield np.concatenate([RNG.choice(ix, size=len(ix), replace=True) for ix in groups])


def share_by(wt: pd.DataFrame, keys: list[str], col: str) -> pd.Series:
    s = wt.groupby(keys, observed=True)[[col, "n"]].sum()
    return s[col] / s["n"]


def ci(a):
    a = np.asarray(a, float)
    a = a[~np.isnan(a)]
    return (np.nan, np.nan) if len(a) == 0 else tuple(np.percentile(a, [2.5, 97.5]))


def era_shares(d: pd.DataFrame, by: list[str] = (), cols=("material", "social", "internal")) -> pd.DataFrame:
    wt = work_table(d, list(by))
    keys = [*by, "era"]
    rows = []
    point = {c: share_by(wt, keys, c) for c in cols}
    boots = {c: [] for c in cols}
    for ix in boot_idx(wt, keys):
        bw = wt.iloc[ix]
        for c in cols:
            boots[c].append(share_by(bw, keys, c).reindex(point[c].index))
    cnt = wt.groupby(keys, observed=True).agg(works=("work_id", "nunique"), obs=("n", "sum"))
    au = d[d.obs].groupby(keys, observed=True).author_key.nunique().rename("authors")
    for c in cols:
        bb = pd.concat(boots[c], axis=1)
        for k in point[c].index:
            lo, hi = ci(bb.loc[k].values)
            rows.append({**dict(zip(keys, k if isinstance(k, tuple) else (k,))), "locus": c,
                         "share": point[c][k], "lo": lo, "hi": hi})
    out = pd.DataFrame(rows).merge(cnt.reset_index(), on=keys).merge(au.reset_index(), on=keys)
    return out


def diff_ci(d: pd.DataFrame, a: str, b: str, col: str, by: str | None = None):
    """share(b) - share(a) with work-bootstrap CI, optionally within each level of `by`."""
    wt = work_table(d, [by] if by else [])
    wt = wt[wt.era.isin([a, b])]
    keys = ([by] if by else []) + ["era"]

    def stat(x):
        s = share_by(x, keys, col)
        if by:
            s = s.unstack("era")
            return (s.get(b) - s.get(a)) if a in s and b in s else pd.Series(dtype=float)
        return pd.Series({"all": s.get(b, np.nan) - s.get(a, np.nan)})

    pt = stat(wt)
    bs = pd.concat([stat(wt.iloc[ix]).reindex(pt.index) for ix in boot_idx(wt, keys)], axis=1)
    if by:
        n = wt.groupby([by, "era"], observed=True).n.sum().unstack("era").reindex(pt.index)
        na_, nb_ = n.get(a), n.get(b)
    else:
        tot = wt.groupby("era", observed=True).n.sum()
        na_, nb_ = pd.Series({"all": tot.get(a)}), pd.Series({"all": tot.get(b)})
    return pd.DataFrame({f"n_{a}": na_, f"n_{b}": nb_, "diff": pt, "lo": bs.apply(lambda r: ci(r)[0], axis=1),
                         "hi": bs.apply(lambda r: ci(r)[1], axis=1),
                         "p_le0": (bs <= 0).mean(axis=1)})


# ---------- shift-share (symmetric Bennet) ----------
def shift_share_point(wt: pd.DataFrame, a: str, b: str, col: str, genres) -> tuple[float, float, float]:
    s = wt.groupby(["era", "genre"], observed=True)[[col, "n"]].sum()
    tot = wt.groupby("era", observed=True).n.sum()
    within = comp = 0.0
    for g in genres:
        na, nb = (s.loc[(e, g), "n"] if (e, g) in s.index else 0 for e in (a, b))
        wa, wb = na / tot[a], nb / tot[b]
        sa = s.loc[(a, g), col] / na if na else np.nan
        sb = s.loc[(b, g), col] / nb if nb else np.nan
        if np.isnan(sa) or np.isnan(sb):
            # genre absent in one era: its whole contribution is composition, valued at the observed share
            sv = sb if np.isnan(sa) else sa
            comp += (wb - wa) * (0 if np.isnan(sv) else sv)
            continue
        within += 0.5 * (wa + wb) * (sb - sa)
        comp += 0.5 * (sa + sb) * (wb - wa)
    return within + comp, within, comp


def shift_share(d: pd.DataFrame, a: str, b: str, col: str = "material"):
    wt = work_table(d)
    wt = wt[wt.era.isin([a, b])]
    genres = sorted(wt.genre.unique())
    pt = shift_share_point(wt, a, b, col, genres)
    bs = np.array([shift_share_point(wt.iloc[ix], a, b, col, genres) for ix in boot_idx(wt, ["era"])])
    return {"total": pt[0], "within": pt[1], "composition": pt[2],
            "ci_total": ci(bs[:, 0]), "ci_within": ci(bs[:, 1]), "ci_comp": ci(bs[:, 2])}


# ---------- regression ----------
def logit(d: pd.DataFrame, col: str = "material", extra: str = "", data_filter=None):
    import statsmodels.formula.api as smf
    ob = d[d.obs].copy()
    if data_filter is not None:
        ob = ob[data_filter(ob)]
    ob["y"] = (ob.locus == {v: k for k, v in SHORT.items()}[col]).astype(int)
    ob["era"] = pd.Categorical(ob.era, ERAS)
    ob["lwords"] = np.log(ob.n_words) - np.log(ob.n_words).mean()
    f = f"y ~ C(era, Treatment('M')) + C(genre, Treatment('domestic_realist')) + C(origin_locc) + lwords{extra}"
    out = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for cl in ("work_id", "author_key"):
            groups = pd.factorize(ob[cl])[0]
            m = smf.glm(f, ob, family=__import__("statsmodels.api").api.families.Binomial()).fit(
                cov_type="cluster", cov_kwds={"groups": groups})
            out[cl] = m
    m = out["work_id"]
    # g-computation: standardised era shares over the pooled covariate mix
    std = {}
    for e in ERAS:
        x = ob.copy()
        x["era"] = pd.Categorical([e] * len(x), ERAS)
        std[e] = float(m.predict(x).mean())
    return out, std, ob


def logit_std_boot(d, col="material", reps=300):
    """work-bootstrap CI for the g-computed L - M (and L - E) standardised contrast."""
    import statsmodels.api as sm
    import statsmodels.formula.api as smf
    ob = d[d.obs].copy()
    ob["y"] = (ob.locus == {v: k for k, v in SHORT.items()}[col]).astype(int)
    ob["lwords"] = np.log(ob.n_words) - np.log(ob.n_words).mean()
    f = "y ~ C(era, Treatment('M')) + C(genre, Treatment('domestic_realist')) + C(origin_locc) + lwords"
    works = ob.groupby("work_id").indices
    wids = np.array(list(works))
    era_w = ob.groupby("work_id").era.first().reindex(wids).values
    res = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for _ in range(reps):
            pick = np.concatenate([RNG.choice(wids[era_w == e], (era_w == e).sum()) for e in ERAS])
            x = ob.iloc[np.concatenate([works[w] for w in pick])].copy()
            x["era"] = pd.Categorical(x.era, ERAS)
            try:
                m = smf.glm(f, x, family=sm.families.Binomial()).fit()
            except Exception:
                continue
            s = {}
            for e in ERAS:
                z = x.copy()
                z["era"] = pd.Categorical([e] * len(z), ERAS)
                s[e] = m.predict(z).mean()
            res.append((s["L"] - s["M"], s["L"] - s["E"]))
    res = np.array(res)
    return ci(res[:, 0]), ci(res[:, 1])


# ---------- figure ----------
def figure(d: pd.DataFrame, genres: list[str]):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    es = era_shares(d[d.genre.isin(genres)], ["genre"])
    allg = era_shares(d).assign(genre="all genres")
    es = pd.concat([allg, es])
    panels = ["all genres", *genres]
    colors = {"material": "#b8312f", "social": "#3b3b3b", "internal": "#2f6db8"}
    marker = {"material": "o", "social": "s", "internal": "^"}
    fig, axes = plt.subplots(1, len(panels), figsize=(3.1 * len(panels), 3.6), sharey=True)
    xs = {"E": 0, "M": 1, "L": 2}
    for ax, gname in zip(axes, panels):
        sub = es[es.genre == gname]
        for i, loc in enumerate(["material", "social", "internal"]):
            s = sub[sub.locus == loc].set_index("era").reindex(ERAS)
            ok = s.obs >= 10
            x = np.array([xs[e] for e in ERAS]) + (i - 1) * 0.08
            ax.errorbar(x[ok], s.share[ok], yerr=[(s.share - s.lo)[ok], (s.hi - s.share)[ok]],
                        color=colors[loc], marker=marker[loc], ms=5, lw=1.4, capsize=2,
                        label=loc if gname == panels[0] else None)
        cnt = sub[sub.locus == "material"].set_index("era").reindex(ERAS)
        labels = []
        for e in ERAS:
            r = cnt.loc[e]
            labels.append(f"{e}\n{int(r.works) if r.works == r.works else 0}w/{int(r.authors) if r.authors == r.authors else 0}a"
                          + ("" if (r.obs == r.obs and r.obs >= 10) else "\n(n<10)"))
        ax.set_xticks([0, 1, 2], labels, fontsize=8)
        ax.set_title(gname.replace("_", "/"), fontsize=10)
        ax.set_ylim(0, 1)
        ax.grid(axis="y", color="#ddd", lw=0.6)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    axes[0].set_ylabel("share of obstacle passages")
    axes[0].legend(frameon=False, fontsize=8, loc="center left")
    fig.suptitle("Pilot (Discovery w01, raw model labels, n = %d obstacles): locus share by era, 95%% work-bootstrap CI"
                 % d.obs.sum(), fontsize=9)
    fig.text(0.01, 0.005, "E 1800–49, M 1850–84, L 1885–1929. w = works, a = authors. Uncorrected Tier-2 labels; "
             "points with < 10 obstacle passages are hidden.", fontsize=7, color="#555")
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG, dpi=160)
    print("wrote", FIG)


def pr(title, obj):
    print(f"\n### {title}")
    print(obj.to_string() if hasattr(obj, "to_string") else obj)


def main():
    d = load()
    ob = d[d.obs]
    pr("counts", d.groupby("era").agg(passages=("passage_id", "size"), obstacles=("obs", "sum"),
                                       works=("work_id", "nunique"), authors=("author_key", "nunique")))
    pr("has_obstacle rate by era", d.groupby("era").obs.mean().round(3))
    pr("raw locus shares (work bootstrap)", era_shares(d).round(3))
    pr("genre x era (obstacle passages)", pd.crosstab(ob.genre, ob.era).reindex(columns=ERAS))
    pr("genre share of obstacles by era", pd.crosstab(ob.genre, ob.era, normalize="columns").reindex(columns=ERAS).round(3))
    pr("material share genre x era", ob.assign(m=ob.locus == LOCI[0]).pivot_table("m", "genre", "era").reindex(columns=ERAS).round(3))
    pr("internal share genre x era", ob.assign(m=ob.locus == LOCI[2]).pivot_table("m", "genre", "era").reindex(columns=ERAS).round(3))

    for a, b in (("M", "L"), ("E", "L"), ("E", "M")):
        for col in ("material", "internal", "social"):
            pr(f"shift-share {a}->{b} {col}", pd.Series(shift_share(d, a, b, col)))
    pr("within-genre M->L material diff", diff_ci(d, "M", "L", "material", "genre").round(3))
    pr("within-genre M->L internal diff", diff_ci(d, "M", "L", "internal", "genre").round(3))

    for col in ("material", "internal", "social"):
        out, std, _ = logit(d, col)
        m = out["work_id"]
        era_rows = [i for i in m.params.index if "era" in i]
        t = pd.DataFrame({"OR": np.exp(m.params[era_rows]),
                          "lo_work": np.exp(m.conf_int().loc[era_rows, 0]),
                          "hi_work": np.exp(m.conf_int().loc[era_rows, 1]),
                          "lo_author": np.exp(out["author_key"].conf_int().loc[era_rows, 0]),
                          "hi_author": np.exp(out["author_key"].conf_int().loc[era_rows, 1]),
                          "p_author": out["author_key"].pvalues[era_rows]})
        pr(f"logit {col} ~ era + genre + origin + log length (ref era M)", t.round(3))
        pr(f"g-computed standardised {col} share by era", pd.Series(std).round(3))
        if col == "material":
            pr("genre ORs (material)", np.exp(m.params[[i for i in m.params.index if "genre" in i]]).round(2))
    lm, le = logit_std_boot(d, "material")
    pr("standardised material L-M, L-E 95% CI (work bootstrap, 300)", pd.Series({"L-M": lm, "L-E": le}))

    # stratifications
    d["edit"] = np.where(d.n_editions >= 2, "editions>=2", "editions=1")
    d["prolific"] = pd.cut(d.author_pg_works, [0, 3, 9, 1e6], labels=["auth<=3", "auth4-9", "auth10+"]).astype(str)
    d["dateconf"] = d.date_confidence
    d["primary"] = np.where(d.date_confidence.isin(["high", "medium"]) & d.in_primary_cap, "primary_set", "other")
    d["ol_agree"] = d.agree_5y.map({True: "OL_agree", False: "OL_disagree"}).fillna("OL_nomatch")
    d["quote_ok"] = np.where(d.quote_status == "hallucinated", "quote_rejected", "quote_ok")
    d["popular"] = np.where(d.genre.isin(POPULAR), "popular", np.where(d.genre == "domestic_realist", "domestic_realist", "rest"))
    for by in ("edit", "prolific", "dateconf", "primary", "ol_agree", "quote_ok", "origin_locc", "popular"):
        pr(f"material M->L by {by}", diff_ci(d, "M", "L", "material", by).round(3))
    for by in ("popular",):
        pr(f"internal M->L by {by}", diff_ci(d, "M", "L", "internal", by).round(3))
        pr(f"internal E->L by {by}", diff_ci(d, "E", "L", "internal", by).round(3))
        pr(f"material E->L by {by}", diff_ci(d, "E", "L", "material", by).round(3))
    pr("era shares by popular", era_shares(d, ["popular"]).round(3))
    # high-confidence only
    hc = d[d.date_confidence == "high"]
    pr("high-confidence dates only: era shares", era_shares(hc).round(3))
    pr("high-conf only: material M->L", diff_ci(hc, "M", "L", "material"))
    # drop juvenile + adventure
    na = d[~d.genre.isin(["juvenile", "adventure"])]
    pr("excluding juvenile+adventure: era shares", era_shares(na).round(3))
    pr("excluding juvenile+adventure: material M->L", diff_ci(na, "M", "L", "material"))
    # prompted reject rule (prereg 5.5): hallucinated quote -> no obstacle
    rj = d.copy()
    rj.loc[rj.quote_status == "hallucinated", "obs"] = False
    pr("prereg reject rule: era shares", era_shares(rj).round(3))
    pr("hallucinated quote rate by era", d.groupby("era").quote_status.apply(lambda s: (s == "hallucinated").mean()).round(3))
    pr("mean confidence by era (obstacles)", ob.groupby("era").confidence.mean().round(3))

    # interaction (c): does the M->L change differ between popular genres and domestic/realist?
    import statsmodels.api as sm
    import statsmodels.formula.api as smf
    ml = d[d.obs & d.era.isin(["M", "L"])].copy()
    ml["Lx"] = (ml.era == "L").astype(int)
    ml["pop"] = ml.genre.isin(POPULAR).astype(int)
    ml["dom"] = (ml.genre == "domestic_realist").astype(int)
    ml["lwords"] = np.log(ml.n_words) - np.log(ml.n_words).mean()
    for col in ("internal", "material"):
        ml["y"] = (ml.locus == {v: k for k, v in SHORT.items()}[col]).astype(int)
        for term in ("pop", "dom"):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                mm = smf.glm(f"y ~ Lx + C(genre) + C(origin_locc) + lwords + Lx:{term}", ml,
                             family=sm.families.Binomial()).fit(
                    cov_type="cluster", cov_kwds={"groups": pd.factorize(ml.author_key)[0]})
            k = f"Lx:{term}"
            pr(f"M->L x {term} interaction ({col}), author-clustered",
               pd.Series({"OR": np.exp(mm.params[k]), "lo": np.exp(mm.conf_int().loc[k, 0]),
                          "hi": np.exp(mm.conf_int().loc[k, 1]), "p": mm.pvalues[k]}).round(3))

    # domain contributions to the material M->L change (per obstacle passage)
    o3 = ob.assign(mat=ob.locus == LOCI[0])
    tot = o3.groupby("era").size()
    c = o3[o3.mat].groupby(["dom1", "era"]).size().unstack("era").reindex(columns=ERAS).fillna(0) / tot.reindex(ERAS)
    c["M->L"] = c["L"] - c["M"]
    pr("material share contributed by first domain (pp of all obstacles)", (100 * c).round(1))

    # finer composition: outdoor/frontier/sea subject headings (any genre)
    outdoor = d.Subjects.fillna("").str.contains(OUTDOOR)
    d["outdoor"] = np.where(outdoor, "outdoor_subject", "no_outdoor_subject")
    pr("material M->L by outdoor subject", diff_ci(d, "M", "L", "material", "outdoor").round(3))
    pr("outdoor-subject share of obstacles by era", d[d.obs].groupby("era").outdoor.apply(lambda x: (x == "outdoor_subject").mean()).round(3))
    d["drule"] = np.where(d.genre != "domestic_realist", "not_domestic",
                          np.where(d.genre_rule == "residual_general_fiction", "dom_residual", "dom_explicit"))
    pr("material M->L by domestic rule", diff_ci(d, "M", "L", "material", "drule").round(3))
    pr("internal M->L by domestic rule", diff_ci(d, "M", "L", "internal", "drule").round(3))
    # reconcile with decade-based era (1880s in M)
    dd = d.assign(era=np.where(d.year < 1850, "E", np.where(d.year < 1890, "M", "L")))
    pr("decade-cut eras (1880s in M): passages / material share",
       dd.groupby("era").agg(n=("obs", "size"), mat=("locus", lambda x: (x == LOCI[0]).sum() / max(1, (x != "none").sum()))).round(3))
    print("\n### sample obstacle summaries (seed 1)")
    for _, r in ob.sample(15, random_state=1).iterrows():
        print(f"  {r.era} {r.genre[:10]:10s} {r.locus[:8]:8s} {r.dom1} | {r.obstacle_summary}")

    # prompt artifact: does locus follow the default domain mapping?
    o = ob.copy()
    o["default"] = o.dom1.map(DEFAULT_LOCUS)
    k = o.default.notna()
    pr("locus == default mapping of first domain (non-COMM, non-OTHER)",
       o[k].groupby("era").apply(lambda x: (x.locus == x.default).mean(), include_groups=False).round(3))
    pr("n first-domain in default table", k.sum())
    pr("first-domain share among obstacles by era", pd.crosstab(o.dom1, o.era, normalize="columns").reindex(columns=ERAS).round(3))
    pr("locus by first domain", pd.crosstab(o.dom1, o.locus))
    pr("material passages by first domain and era", pd.crosstab(o[o.locus == LOCI[0]].dom1, o[o.locus == LOCI[0]].era).reindex(columns=ERAS))
    # archaic diction -> social? within-era association
    out, _, _ = logit(d.assign(arch=np.log1p(d.archaic)), "social", extra=" + arch")
    mm = out["author_key"]
    pr("social ~ log1p(archaic per 1k words) + era + genre + origin (author-clustered)",
       pd.Series({"OR_per_log_unit": np.exp(mm.params["arch"]), "p": mm.pvalues["arch"],
                  "mean_archaic_E": d[d.era == 'E'].archaic.mean(), "mean_archaic_M": d[d.era == 'M'].archaic.mean(),
                  "mean_archaic_L": d[d.era == 'L'].archaic.mean()}).round(3))
    # decade view
    ob2 = ob.assign(dec=(ob.year // 10 * 10).astype(int), m=ob.locus == LOCI[0], i=ob.locus == LOCI[2])
    pr("by decade (obstacles)", ob2.groupby("dec").agg(n=("m", "size"), material=("m", "mean"), internal=("i", "mean")).round(3))
    pr("obstacle rate by genre", d.groupby("genre").obs.mean().round(3))

    if "--fig" in sys.argv:
        figure(d, ["juvenile", "domestic_realist", "adventure"])


if __name__ == "__main__":
    main()
