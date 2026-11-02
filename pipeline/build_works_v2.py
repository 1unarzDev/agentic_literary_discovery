"""Build data/work/works_v2.parquet and data/work/canon.parquet (metadata only; no labels are read).

works_v2 = works.parquet + author identity v2 (pipeline/author_identity.py) + canon measure + primary flags:
  author_agent, author_name, author_group, group_rule, split (v1, unchanged), split_v2, moved,
  era, genre, juvenile, historical_setting, date_verified (null placeholder), wc_keep,
  in_primary_cap (v1, by author_key), cap_rank_v2 / in_primary_cap_v2 (same seeded rule, by author_group),
  primary_v2, primary_v2_capv2, downloads, sitelinks, canon_score, canonical.

canon.parquet = work_id, author_group, downloads, author_downloads, sitelinks, canon_score, canonical,
                canonical_dl (top-decile-downloads sensitivity), eltec_reprint (validation only).

All definitions are in docs/canon_measure.md and are frozen at the commit that adds this file.

  uv run python -I pipeline/build_works_v2.py [--report]
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import author_identity as AI  # noqa: E402
from pipeline import genre as G  # noqa: E402

WORK = ROOT / "data/work"
SEED = 20261031
AUTHOR_CAP_PER_DECADE = 5
# ---- pre-declared canon threshold (docs/canon_measure.md §2.3) ----
CANON_K = 30  # author group's Wikidata item has >= 30 Wikipedia language editions (docs/canon_measure.md §2.3)
DL_TOP_DECILE = 0.90
ERAS = [("E", 1800, 1849), ("M", 1850, 1884), ("L", 1885, 1929)]

HIST_LCSH = re.compile(r"historical fiction|biographical fiction", re.I)
HIST_SHELF = re.compile(r"historical novels|historical fiction", re.I)


def era_of(year) -> str | None:
    if pd.isna(year):
        return None
    for e, lo, hi in ERAS:
        if lo <= year <= hi:
            return e
    return None


def historical_setting(genre: str, subjects, shelves, year) -> bool:
    """genre == historical, or any LCSH/shelf historical cue regardless of genre precedence: 'Historical fiction',
    'Biographical fiction', a 'X -- History -- <period> -- Fiction' heading whose period ends >= 25 years before
    the work's year (genre._history_period; a heading without a period counts), or the 'Historical Novels' shelf."""
    if genre == "historical":
        return True
    subj = subjects if isinstance(subjects, str) else ""
    shelf = shelves if isinstance(shelves, str) else ""
    y = None if pd.isna(year) else float(year)
    return bool(HIST_LCSH.search(subj) or G._history_period(subj, y) or HIST_SHELF.search(shelf))


JUV_LCSH = G.LCSH_RULES[0][2]


def juvenile(genre: str, subjects) -> bool:
    return genre == "juvenile" or bool(JUV_LCSH.search(subjects if isinstance(subjects, str) else ""))


def cap_rank(df: pd.DataFrame, group_col: str) -> pd.Series:
    """Same seeded rule as build_corpus.stage_split, applied to an arbitrary author column."""
    r = df.work_id.map(lambda k: int(hashlib.sha256(f"{SEED}:cap:{k}".encode()).hexdigest()[:12], 16))
    order = r.sort_values().index
    return df.loc[order].groupby([group_col, "decade"]).cumcount().reindex(df.index)


def pct_rank(s: pd.Series) -> pd.Series:
    return s.rank(method="average", pct=True)


def canon_table(w: pd.DataFrame, ebooks: pd.DataFrame, qids: pd.DataFrame, agents_groups: dict[int, str],
                eltec: pd.DataFrame | None = None, k: int = CANON_K, agents: pd.DataFrame | None = None) -> pd.DataFrame:
    """Work-level canon measure. Author signals are taken at the author_group level (max over the group's agents
    for sitelinks; sum over all PG ebooks first-authored by the group's agents for author_downloads)."""
    # only items that are human (P31=Q5) count: corporate bodies (e.g. "New York Public Library") and collective
    # pseudonyms are not authors in the prestige sense
    q = qids.dropna(subset=["qid"])
    if "wd_human" in q:
        q = q[q.wd_human.fillna(False).astype(bool)]
    sl = q.assign(group=lambda d: d.agent_id.map(agents_groups)).dropna(subset=["group"])
    g_sl = sl.groupby("group").sitelinks.max()
    eb = ebooks.dropna(subset=["first_author_agent"]).copy()
    eb["group"] = eb.first_author_agent.astype(int).map(agents_groups)
    g_dl = eb.dropna(subset=["group"]).groupby("group").downloads.sum()
    dl = dict(zip(ebooks.pg_id, ebooks.downloads))
    c = pd.DataFrame({"work_id": w.work_id, "author_group": w.author_group})
    c["downloads"] = w.pg_id.map(dl).fillna(0).astype(int)
    c["author_downloads"] = c.author_group.map(g_dl).fillna(c.downloads).astype(int)
    c["sitelinks"] = c.author_group.map(g_sl).astype("Int64")
    house = c.author_group.eq(AI.SYNDICATE) | w.author_name.fillna("").str.contains(r"\(House name\)", regex=True)
    c["house_name"] = house.values
    c["canonical"] = (c.sitelinks.fillna(0) >= k) & ~c.house_name
    c["canon_score"] = 0.5 * pct_rank(np.log1p(c.sitelinks.fillna(0).astype(float))) + \
        0.5 * pct_rank(np.log1p(c.downloads.astype(float)))
    c.loc[c.house_name, "canon_score"] = np.minimum(c.loc[c.house_name, "canon_score"], 0.5)
    thr = c.downloads.quantile(DL_TOP_DECILE)
    c["canonical_dl"] = (c.downloads >= thr) & ~c.house_name
    if eltec is not None and agents is not None:
        c["eltec_reprint"] = c.author_group.map(eltec_by_group(eltec, w, agents))
    return c


def eltec_by_group(eltec: pd.DataFrame, w: pd.DataFrame, agents: pd.DataFrame) -> dict[str, str]:
    """ELTeC-eng author (name tokens + birth year) -> 'high'/'low' reprint count, mapped onto corpus author groups
    via each work's PG author agent (name tokens + PG birth year). Validation only; never enters `canonical`."""
    key: dict = {}
    for n, b, rc in zip(eltec["author-name"], eltec["author-birth"], eltec["reprint-count"]):
        try:
            kk = (AI.name_tokens(n), int(b))
        except (TypeError, ValueError):
            continue
        key[kk] = "high" if (rc == "high" or key.get(kk) == "high") else str(rc)
    birth = dict(zip(agents.agent_id, agents.birth))
    out: dict[str, str] = {}
    for g, n, a in zip(w.author_group, w.author_name, w.author_agent):
        b = birth.get(int(a)) if pd.notna(a) else None
        if not isinstance(n, str) or b is None or pd.isna(b):
            continue
        r = key.get((AI.name_tokens(n), int(b)))
        if r:
            out[g] = "high" if (r == "high" or out.get(g) == "high") else r
    return out


def build(k: int = CANON_K) -> tuple[pd.DataFrame, pd.DataFrame]:
    works = pd.read_parquet(WORK / "works.parquet")
    eb = pd.read_parquet(WORK / "pg_rdf_ebooks.parquet")
    ag = AI.corpus_agents()
    q = pd.read_parquet(WORK / "agent_wikidata.parquet")
    w = AI.build(works, eb, ag, q)
    groups, _ = AI.agent_groups(ag, q)
    gen = pd.read_parquet(WORK / "genre.parquet")
    w = w.merge(gen[["work_id", "genre"]], on="work_id", how="left")
    w["era"] = w.year.map(era_of)
    w["juvenile"] = [juvenile(g, s) for g, s in zip(w.genre, w.Subjects)]
    w["historical_setting"] = [historical_setting(g, s, b, y) for g, s, b, y in zip(w.genre, w.Subjects, w.Bookshelves, w.year)]
    w["date_verified"] = pd.Series([pd.NA] * len(w), dtype="boolean")  # filled by the early-date verification task
    keep = pd.read_parquet(WORK / "workcheck_keep.parquet", columns=["work_id", "keep"])
    w = w.merge(keep.rename(columns={"keep": "wc_keep"}), on="work_id", how="left")
    w["wc_keep"] = w.wc_keep.astype("boolean")
    not_excluded = w.wc_keep.fillna(True)
    w["primary_v2"] = w.in_primary_cap & ~w.historical_setting & not_excluded
    w["cap_rank_v2"] = cap_rank(w, "author_group")
    w["in_primary_cap_v2"] = w.cap_rank_v2 < AUTHOR_CAP_PER_DECADE
    w["primary_v2_capv2"] = w.in_primary_cap_v2 & ~w.historical_setting & not_excluded
    el_p = ROOT / "data/raw/eltec/ELTeC-eng_metadata.tsv"
    eltec = pd.read_csv(el_p, sep="\t") if el_p.exists() else None
    c = canon_table(w, eb, q, groups, eltec, k, ag)
    w = w.merge(c[["work_id", "downloads", "sitelinks", "canon_score", "canonical"]], on="work_id", how="left")
    return w, c


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=CANON_K)
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args(argv)
    w, c = build(a.k)
    w.to_parquet(WORK / "works_v2.parquet", index=False)
    c[["work_id", "author_group", "downloads", "author_downloads", "sitelinks", "canon_score", "canonical",
       "canonical_dl", "house_name"] + (["eltec_reprint"] if "eltec_reprint" in c else [])].to_parquet(
        WORK / "canon.parquet", index=False)
    print(f"wrote works_v2 ({len(w)}) and canon ({len(c)}); canonical works {int(c.canonical.sum())}")
    if a.report:
        report(w, c)


def report(w: pd.DataFrame, c: pd.DataFrame, seed: int = 20261102) -> None:
    """Metadata-only tables for docs/canon_measure.md (no label is read)."""
    pd.set_option("display.width", 200)
    print("## moved by decade (works / author groups)")
    t = w.groupby("decade").agg(works=("work_id", "size"), moved_works=("moved", "sum"),
                                moved_groups=("author_group", lambda s: s[w.loc[s.index, "moved"]].nunique()))
    print(t.to_string())
    print("total moved works", int(w.moved.sum()), "groups", w[w.moved].author_group.nunique())
    print(w[w.moved].groupby("author_group").agg(n=("work_id", "size"), name=("author_name", "first"))
          .sort_values("n", ascending=False).to_string())
    print("## split sizes v1 -> v2")
    print(pd.crosstab(w.split, w.split_v2).to_string())
    print("## canon share by decade x split_v2 (works)")
    x = w.groupby(["decade", "split_v2"]).canonical.mean().unstack().round(3)
    x["n_disc"] = w[w.split_v2 == "discovery"].groupby("decade").size()
    x["n_conf"] = w[w.split_v2 == "confirmation"].groupby("decade").size()
    print(x.to_string())
    print("## primary_v2 counts era x split_v2 x canonical")
    p = w[w.primary_v2 & w.era.notna()]
    print(pd.crosstab([p.era, p.split_v2], p.canonical, margins=True).to_string())
    p2 = w[w.primary_v2_capv2 & w.era.notna()]
    print("## (sensitivity) primary_v2_capv2 era x split_v2 x canonical")
    print(pd.crosstab([p2.era, p2.split_v2], p2.canonical, margins=True).to_string())
    print("## flags")
    print({"historical_setting": int(w.historical_setting.sum()), "juvenile": int(w.juvenile.sum()),
           "wc_keep_false": int((w.wc_keep == False).sum()), "in_primary_cap": int(w.in_primary_cap.sum()),  # noqa: E712
           "primary_v2": int(w.primary_v2.sum()), "in_primary_cap_v2": int(w.in_primary_cap_v2.sum()),
           "primary_v2_capv2": int(w.primary_v2_capv2.sum())})
    g = (w.groupby("author_group").agg(name=("author_name", "first"), works=("work_id", "size"),
                                       sitelinks=("sitelinks", "first"), canonical=("canonical", "first"),
                                       downloads=("downloads", "sum"))
         .query("~index.str.startswith('work:')"))
    print("## face validity: 30 random author groups per side (seed %d)" % seed)
    for side in (True, False):
        s = g[g.canonical == side].sample(min(30, int((g.canonical == side).sum())), random_state=seed)
        print("canonical" if side else "popular/other", f"(of {int((g.canonical == side).sum())} groups)")
        print(s.sort_values("sitelinks", ascending=False).to_string())
    print("## sanity")
    for pat in ["Austen, Jane", "Eliot, George", "Dickens, Charles", "Hardy, Thomas", "James, Henry",
                "Alger, Horatio", "Fenn, George Manville", "Henty, G. A.", "Stratemeyer", "Scott, Walter",
                "Trollope, Anthony", "Ballantyne, R. M.", "Le Queux", "Oppenheim, E. Phillips", "Braddon",
                "Collins, Wilkie", "Haggard, H. Rider", "Stevenson, Robert Louis", "Oliphant", "Yonge, Charlotte"]:
        hit = g[g.name.fillna("").str.startswith(pat) | (g.index == AI.SYNDICATE) & (pat == "Stratemeyer")]
        print(pat, hit[["name", "works", "sitelinks", "canonical"]].to_dict("records")[:2])
    if "eltec_reprint" in c:
        e = c.dropna(subset=["eltec_reprint"]).drop_duplicates("author_group")
        print("## ELTeC-eng reprint-count vs canonical (author groups matched):")
        print(pd.crosstab(e.eltec_reprint, e.canonical).to_string())
    print("## sitelinks distribution over author groups")
    print(g.sitelinks.astype(float).describe(percentiles=[.5, .75, .9, .95, .99]).to_string())
    print("## K sensitivity: canonical share of primary_v2 works by era x split_v2")
    p = w[w.primary_v2 & w.era.notna()]
    for kk in (20, 25, 30, 40, 50):
        can = (p.sitelinks.fillna(0) >= kk) & ~p.author_group.eq(AI.SYNDICATE) & \
            ~p.author_name.fillna("").str.contains(r"\(House name\)", regex=True)
        print(kk, can.groupby([p.era, p.split_v2]).mean().round(3).to_dict())
    print("## agreement canonical vs canonical_dl (works)", pd.crosstab(c.canonical, c.canonical_dl).to_string())


if __name__ == "__main__":
    main(sys.argv[1:])
