"""Author identity v2: re-key works by Project Gutenberg agent id, merge aliases, and repair the split.

Inputs (metadata only; no labels are read):
  data/work/works.parquet            (v1 works, with the string `author_key` and v1 `split`)
  data/work/pg_rdf_ebooks.parquet    (pipeline/pg_rdf.py)
  data/work/pg_rdf_agents.parquet
  data/work/agent_wikidata.parquet   (pipeline/wikidata_authors.py; optional, enables QID merges)

Author agent of a work = its canonical edition's first PG `dcterms:creator` (role "Author"), else its first
`marcrel:aut`, else the first agent in any role (editor/compiler of an anthology), else none.

Author groups = connected components of PG agents under these edges (docs/canon_measure.md §1):
  E1 PG "see also" links: pgterms:webpage values of the form ebooks/author/<id> (PG's pseudonym <-> person links).
  E2 the same Wikidata QID (P1938 or the agent's Wikipedia page).
  E3 identical normalised name with identical birth AND death years (duplicate PG agent records).
  E4 Stratemeyer Syndicate: Edward Stratemeyer + every house pseudonym in STRATEMEYER_HOUSE_NAMES.
Placeholder agents (Anonymous, Unknown, Various) take part in no edge, and each of their works is its own group.
Works without any PG agent fall back to their v1 author_key ("key:<author_key>").

Split repair: a group whose works fall in both v1 splits goes entirely to Discovery (Discovery labels have already
been examined, Confirmation labels have not). Every other work keeps its v1 split.

  uv run python -I pipeline/author_identity.py      # writes data/work/works_v2.parquet (author part only)
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "data/work"
SYNDICATE = "syndicate:stratemeyer"

# Credited author names of Stratemeyer Syndicate series, from Deidre Johnson, *Stratemeyer Pseudonyms and Series
# Books* (Greenwood, 1982), as tabulated in Wikipedia "List of Stratemeyer Syndicate series" (revision fetched
# 2026-11-02, cached in data/raw/stratemeyer_src/). Arthur M. Winfield and Captain Ralph Bonehill were Edward
# Stratemeyer's personal pseudonyms before incorporation (1905); they are included, as is Stratemeyer himself.
# Excluded on purpose: Howard R. Garis and Mildred A. Wirt (real ghostwriters who also published under their own
# names; they join the group only if PG itself links them to a house name), and "Nicholas Carter" (a Street & Smith
# house name, not a Syndicate one).
STRATEMEYER_HOUSE_NAMES = [
    "Edward Stratemeyer", "Arthur M. Winfield", "Captain Ralph Bonehill", "Laura Lee Hope", "Roy Rockwood",
    "Allen Chapman", "Clarence Young", "Margaret Penrose", "Frank V. Webster", "Lester Chadwick", "Victor Appleton",
    "Captain Quincy Allen", "Graham B. Forbes", "Harrison Adams", "Raymond Stone", "Frederick Gordon",
    "Alice B. Emerson", "James Carson", "Amy Bell Marlowe", "Burbank L. Todd", "Helen Beecher Long",
    "Gertrude W. Morrison", "Roy Eliot Stokes", "Frank A. Warner", "Grace Brooks Hill", "Richard Barnum",
    "Raymond Sperry, Jr.", "Vance Barnum", "Annie Roe Carr", "Spencer Davenport", "Brooks Henderley",
    "Elmer Tracey Barnes", "Charles Amory Beach", "Ruth Belmore Endicott", "Janet D. Wheeler", "Mabel C. Hawley",
    "Ramy Allison White", "Helen Louise Thorndyke", "Alice Dale Hardy", "May Hollis Barton", "Elmer A. Dawson",
    "Nat Ridley, Jr.", "James Cody Ferris", "Franklin W. Dixon", "Harry Mason Roe", "Philip A. Bartlett",
    "Carolyn Keene", "Richard H. Stone", "Julia K. Duncan", "Fenworth Moore", "Clinton W. Locke", "Eugene Martin",
    "Frances K. Judd", "Francis Hunt", "John R. Cooper", "Jerry West", "Victor Appleton II", "Dan Scott",
    "Ann Sheldon", "Jack Lancer", "Alan Stone", "Eric Speed",
]
PLACEHOLDER_NAMES = {"anonymous", "unknown", "various"}
_DROP_TOKENS = {"captain", "capt", "jr", "sr", "house", "name", "pseud", "pseudonym", "ii"}
SEE_ALSO_RE = re.compile(r"^(?:https?://(?:www\.)?gutenberg\.org/)?ebooks/author/(\d+)$")


def name_tokens(name: str) -> frozenset[str]:
    """Order-free token set of a person name: 'Dixon, Franklin W.' == 'Franklin W. Dixon'.
    Parenthetical expansions, dates and honorifics are dropped. 'Victor Appleton II' == 'Victor Appleton'."""
    s = re.sub(r"\(.*?\)|\[.*?\]|\d{3,4}\??-?", " ", str(name).lower())
    toks = re.findall(r"[a-z]+", s)
    return frozenset(t for t in toks if t not in _DROP_TOKENS)


HOUSE_TOKENS = {name_tokens(n) for n in STRATEMEYER_HOUSE_NAMES}


def norm_name(name: str) -> str:
    """Strict normalised name for E3 duplicate detection (keeps token order)."""
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", str(name).lower())
    return re.sub(r"[^a-z]", "", s)


def is_placeholder(name: str) -> bool:
    return norm_name(name) in PLACEHOLDER_NAMES


def is_house_name(name: str, aliases: list[str] | None = None, birth=None) -> bool:
    """True if the agent's own name is a Syndicate house name. Aliases count only for agents without a birth year
    (pseudonym records): a real, dated writer who merely *used* a house name (e.g. St. George Rathborne, alias
    "Harrison Adams") is not pulled in by the alias; PG's see-also links (E1) decide that instead."""
    if name_tokens(name) in HOUSE_TOKENS:
        return True
    if birth is not None and not pd.isna(birth):
        return False
    return any(name_tokens(n) in HOUSE_TOKENS for n in (aliases or []) if n)


def pick_author_agent(creators_json: str | None) -> int | None:
    cr = json.loads(creators_json) if creators_json else []
    for role in ("creator", "aut"):
        for aid, r in cr:
            if r == role:
                return int(aid)
    return int(cr[0][0]) if cr else None


class UnionFind:
    def __init__(self):
        self.p: dict = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # keep the syndicate sentinel (a str) as root, else the smaller agent id
            if isinstance(rb, str) or (not isinstance(ra, str) and rb < ra):
                ra, rb = rb, ra
            self.p[rb] = ra


def agent_groups(agents: pd.DataFrame, qids: pd.DataFrame | None = None) -> tuple[dict[int, str], dict[int, str]]:
    """agents: agent_id, name, aliases(JSON), birth, death, webpages(JSON).
    Returns ({agent_id: group_id}, {agent_id: rule that first attached it, for audit})."""
    uf = UnionFind()
    rule: dict[int, str] = {}
    ag = agents.set_index("agent_id")
    ok = {int(a) for a, n in ag.name.items() if not is_placeholder(n)}
    for a in ok:
        uf.find(a)
    # E1 see-also links
    for a in ok:
        for u in json.loads(ag.at[a, "webpages"] or "[]"):
            m = SEE_ALSO_RE.match(str(u))
            if m and int(m.group(1)) in ok:
                uf.union(a, int(m.group(1)))
                rule.setdefault(a, "E1_see_also")
                rule.setdefault(int(m.group(1)), "E1_see_also")
    # E2 shared Wikidata QID
    if qids is not None and len(qids):
        byq = defaultdict(list)
        for a, q in zip(qids.agent_id, qids.qid):
            if isinstance(q, str) and int(a) in ok:
                byq[q].append(int(a))
        for q, aa in byq.items():
            for b in aa[1:]:
                uf.union(aa[0], b)
                rule.setdefault(b, "E2_same_qid")
                rule.setdefault(aa[0], "E2_same_qid")
    # E3 duplicate records
    dup = defaultdict(list)
    for a in ok:
        b, d = ag.at[a, "birth"], ag.at[a, "death"]
        if pd.notna(b) and pd.notna(d):
            dup[(norm_name(ag.at[a, "name"]), int(b), int(d))].append(a)
    for aa in dup.values():
        for b in aa[1:]:
            uf.union(aa[0], b)
            rule.setdefault(b, "E3_duplicate")
    # E4 Stratemeyer Syndicate
    for a in ok:
        if is_house_name(ag.at[a, "name"], json.loads(ag.at[a, "aliases"] or "[]"), ag.at[a, "birth"]):
            uf.union(SYNDICATE, a)
            rule[a] = "E4_stratemeyer"
    out = {}
    for a in ok:
        r = uf.find(a)
        out[a] = r if isinstance(r, str) else f"pga:{r}"
    return out, rule


def repair_split(df: pd.DataFrame, group_col: str = "author_group", split_col: str = "split") -> pd.DataFrame:
    """Groups present in both splits go wholly to Discovery. Adds split_v2 and moved."""
    both = df.groupby(group_col)[split_col].nunique()
    straddle = set(both[both > 1].index)
    out = df.copy()
    out["split_v2"] = out[split_col].where(~out[group_col].isin(straddle), "discovery")
    out["moved"] = out.split_v2 != out[split_col]
    return out


def corpus_agents() -> pd.DataFrame:
    """PG agents relevant to the corpus: each work's author agent, every agent PG links to them (E1), and every
    agent carrying a Stratemeyer house name."""
    w = pd.read_parquet(WORK / "works.parquet", columns=["work_id", "pg_id"])
    eb = pd.read_parquet(WORK / "pg_rdf_ebooks.parquet")
    ag = pd.read_parquet(WORK / "pg_rdf_agents.parquet")
    m = w.merge(eb[["pg_id", "creators"]], on="pg_id", how="left")
    ids = {a for a in m.creators.map(pick_author_agent) if a is not None}
    web = dict(zip(ag.agent_id, ag.webpages))
    frontier = set(ids)
    while frontier:  # follow see-also links transitively
        nxt = set()
        for a in frontier:
            for u in json.loads(web.get(a) or "[]"):
                mm = SEE_ALSO_RE.match(str(u))
                if mm and int(mm.group(1)) not in ids:
                    nxt.add(int(mm.group(1)))
        ids |= nxt
        frontier = nxt
    house = {int(a) for a, n, al, b in zip(ag.agent_id, ag.name, ag.aliases, ag.birth)
             if is_house_name(n, json.loads(al or "[]"), b)}
    return ag[ag.agent_id.isin(ids | house)].reset_index(drop=True)


def build(works: pd.DataFrame, ebooks: pd.DataFrame, agents: pd.DataFrame,
          qids: pd.DataFrame | None = None) -> pd.DataFrame:
    """works -> works + author_agent, author_name, author_group, group_rule, split_v2, moved."""
    groups, rule = agent_groups(agents, qids)
    names = dict(zip(agents.agent_id, agents.name))
    w = works.merge(ebooks[["pg_id", "creators"]], on="pg_id", how="left")
    w["author_agent"] = w.creators.map(pick_author_agent).astype("Int64")
    w["author_name"] = w.author_agent.map(lambda a: names.get(int(a)) if pd.notna(a) else None)

    def grp(r):
        if pd.isna(r.author_agent):
            k = r.author_key or ""
            return f"work:{r.work_id}" if (not k or k in PLACEHOLDER_NAMES) else f"key:{k}"
        g = groups.get(int(r.author_agent))
        return g if g is not None else f"work:{r.work_id}"  # placeholder agent

    w["author_group"] = [grp(r) for r in w.itertuples()]
    w["group_rule"] = [("placeholder_singleton" if g.startswith("work:") else "no_agent_author_key" if g.startswith("key:")
                        else rule.get(int(a), "agent") if pd.notna(a) else "agent")
                       for g, a in zip(w.author_group, w.author_agent)]
    w = w.drop(columns=["creators"])
    return repair_split(w)


def main() -> None:
    works = pd.read_parquet(WORK / "works.parquet")
    eb = pd.read_parquet(WORK / "pg_rdf_ebooks.parquet")
    ag = pd.read_parquet(WORK / "pg_rdf_agents.parquet")
    qp = WORK / "agent_wikidata.parquet"
    q = pd.read_parquet(qp) if qp.exists() else None
    w = build(works, eb, ag, q)
    w.to_parquet(WORK / "works_v2.parquet", index=False)
    print(f"works {len(w)}; v1 author_key {works.author_key.nunique()}; v2 groups {w.author_group.nunique()}; "
          f"moved works {int(w.moved.sum())} in {w[w.moved].author_group.nunique()} groups")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
