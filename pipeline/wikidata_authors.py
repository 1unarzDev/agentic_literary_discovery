"""Match PG agents to Wikidata items and fetch Wikipedia sitelink counts (metadata only).

Matching, in order (the first that yields a QID wins; `match_method` records which):
  1. p1938      Wikidata items carrying P1938 "Project Gutenberg author ID" = the PG agent id (one SPARQL query).
  2. webpage    the agent's pgterms:webpage Wikipedia URL -> that wiki's pageprops.wikibase_item.
  3. name_years wbsearchentities on "First Last"; accepted only if the candidate is human (P31=Q5) and its
                birth year (P569) is within +-1 of the PG birth year and, when both are known, its death year
                (P570) within +-1 of the PG death year. Agents without a PG birth year are never name-matched.

Sitelinks counted = Wikipedia language editions only (keys ``<lang>wiki``), excluding commonswiki, specieswiki,
metawiki, mediawikiwiki, wikidatawiki, sourceswiki, incubatorwiki, outreachwiki, foundationwiki, wikimaniawiki.

Politeness: descriptive User-Agent with contact, <= 1 request/s, QIDs batched 50 per wbgetentities call, every
response cached under data/raw/wikidata_cache/ (a re-run makes no network calls for cached keys).
Responses are untrusted JSON: only the specific fields above are read.

  uv run python -I pipeline/wikidata_authors.py          # writes data/work/agent_wikidata.parquet
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

import httpx
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data/raw/wikidata_cache"
WORK = ROOT / "data/work"
# Wikimedia robot policy (https://w.wiki/4wJS) wants "client/version (contact) library/version"; the bare form
# "ald-research (github.com/...) python-httpx" got 403 from query.wikidata.org on 2026-11-02.
UA = f"ald-research/0.1 (https://github.com/1unarzDev/agentic_literary_discovery; ald-research) httpx/{httpx.__version__}"
NON_WIKIPEDIA = {"commonswiki", "specieswiki", "metawiki", "mediawikiwiki", "wikidatawiki", "sourceswiki",
                 "incubatorwiki", "outreachwiki", "foundationwiki", "wikimaniawiki", "wikifunctionswiki"}
SITELINK_RE = re.compile(r"^[a-z][a-z0-9_]*wiki$")
QID_RE = re.compile(r"^Q\d+$")
WIKI_URL_RE = re.compile(r"^https?://([a-z\-]+)\.(?:m\.)?wikipedia\.org/wiki/(.+)$")
_last = [0.0]


def wikipedia_sitelinks(sitelinks: dict) -> int:
    """Number of Wikipedia language editions in a wbgetentities `sitelinks` object."""
    return sum(1 for k in sitelinks if SITELINK_RE.match(k) and k not in NON_WIKIPEDIA)


def year_of(claims: dict, prop: str) -> int | None:
    for c in claims.get(prop, []) or []:
        try:
            t = c["mainsnak"]["datavalue"]["value"]["time"]  # "+1812-02-07T00:00:00Z"
            return int(re.match(r"^[+-]?(\d{1,4})", t).group(1))
        except (KeyError, TypeError, AttributeError, ValueError):
            continue
    return None


def is_human(claims: dict) -> bool:
    for c in claims.get("P31", []) or []:
        try:
            if c["mainsnak"]["datavalue"]["value"]["id"] == "Q5":
                return True
        except (KeyError, TypeError):
            continue
    return False


def years_compatible(pg_birth, pg_death, wd_birth, wd_death, tol: int = 1) -> bool:
    if pg_birth is None or wd_birth is None or abs(pg_birth - wd_birth) > tol:
        return False
    if pg_death is not None and wd_death is not None and abs(pg_death - wd_death) > tol:
        return False
    return True


def display_name(pg_name: str) -> str:
    """'Dickens, Charles' -> 'Charles Dickens'; drops parenthetical full forms and suffixes like ', Jr.'."""
    s = re.sub(r"\(.*?\)", "", str(pg_name)).strip()
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if len(parts) >= 2:
        return f"{parts[1]} {parts[0]}".strip()
    return s


# ---------------------------------------------------------------------------- cached HTTP
def _get(client: httpx.Client, url: str, params: dict, key: str) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{key}.json"
    if p.exists():
        return json.loads(p.read_text())
    wait = 1.05 - (time.monotonic() - _last[0])
    if wait > 0:
        time.sleep(wait)
    for attempt in range(5):
        _last[0] = time.monotonic()
        r = client.get(url, params=params)
        if r.status_code in (429, 503):
            time.sleep(float(r.headers.get("retry-after", 10 * (attempt + 1))))
            continue
        r.raise_for_status()
        data = r.json()
        p.write_text(json.dumps(data))
        return data
    raise RuntimeError(f"giving up on {url}")


def _h(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:20]


def fetch_p1938(client: httpx.Client) -> dict[int, list[str]]:
    q = "SELECT ?item ?pg WHERE { ?item wdt:P1938 ?pg }"
    d = _get(client, "https://query.wikidata.org/sparql", {"query": q, "format": "json"}, "sparql_p1938")
    out: dict[int, list[str]] = {}
    for b in d["results"]["bindings"]:
        qid = b["item"]["value"].rsplit("/", 1)[-1]
        try:
            pg = int(b["pg"]["value"])
        except ValueError:
            continue
        if QID_RE.match(qid):
            out.setdefault(pg, []).append(qid)
    return out


def titles_to_qids(client: httpx.Client, lang: str, titles: list[str]) -> dict[str, str]:
    out = {}
    for i in range(0, len(titles), 50):
        batch = titles[i : i + 50]
        d = _get(client, f"https://{lang}.wikipedia.org/w/api.php",
                 {"action": "query", "prop": "pageprops", "ppprop": "wikibase_item", "redirects": 1,
                  "titles": "|".join(batch), "format": "json", "formatversion": 2},
                 f"pp_{lang}_{_h(batch)}")
        q = d.get("query", {})
        back = {}
        for n in q.get("normalized", []) + q.get("redirects", []):
            back[n["to"]] = back.get(n["from"], n["from"])
        for pg in q.get("pages", []):
            qid = (pg.get("pageprops") or {}).get("wikibase_item")
            t = pg.get("title")
            if qid and QID_RE.match(qid):
                orig = t
                while orig in back:
                    orig = back[orig]
                out[orig] = qid
                out[t] = qid
    return out


def get_entities(client: httpx.Client, qids: list[str]) -> dict[str, dict]:
    out = {}
    qids = sorted(set(q for q in qids if QID_RE.match(q)))
    for i in range(0, len(qids), 50):
        batch = qids[i : i + 50]
        d = _get(client, "https://www.wikidata.org/w/api.php",
                 {"action": "wbgetentities", "ids": "|".join(batch), "props": "sitelinks|claims|labels",
                  "languages": "en", "format": "json"}, f"ent_{_h(batch)}")
        for qid, e in (d.get("entities") or {}).items():
            if "missing" in e:
                continue
            if e.get("redirects"):
                qid = e["redirects"].get("to", qid)
            claims = e.get("claims") or {}
            out[qid] = {"sitelinks": wikipedia_sitelinks(e.get("sitelinks") or {}),
                        "wd_birth": year_of(claims, "P569"), "wd_death": year_of(claims, "P570"),
                        "human": is_human(claims),
                        "label": ((e.get("labels") or {}).get("en") or {}).get("value")}
    return out


def search(client: httpx.Client, name: str) -> list[str]:
    d = _get(client, "https://www.wikidata.org/w/api.php",
             {"action": "wbsearchentities", "search": name, "language": "en", "type": "item", "limit": 7,
              "format": "json"}, f"srch_{_h(name)}")
    return [r["id"] for r in d.get("search", []) if QID_RE.match(str(r.get("id", "")))]


# ---------------------------------------------------------------------------- driver
def match_agents(agents: pd.DataFrame, client: httpx.Client) -> pd.DataFrame:
    """agents: agent_id, name, birth, death, webpages(JSON). Returns agent_id, qid, match_method, sitelinks, ..."""
    p1938 = fetch_p1938(client)
    rows = {}
    for r in agents.itertuples():
        q = p1938.get(int(r.agent_id))
        if q:
            rows[r.agent_id] = (sorted(q, key=lambda x: int(x[1:]))[0], "p1938")
    # webpage
    by_lang: dict[str, dict[int, str]] = {}
    for r in agents.itertuples():
        if r.agent_id in rows:
            continue
        for u in json.loads(r.webpages or "[]"):
            m = WIKI_URL_RE.match(u)
            if m:
                title = urllib.parse.unquote(m.group(2)).split("#")[0].replace("_", " ")
                by_lang.setdefault(m.group(1), {})[r.agent_id] = title
                break
    for lang, amap in by_lang.items():
        t2q = titles_to_qids(client, lang, sorted(set(amap.values())))
        for aid, t in amap.items():
            if t in t2q:
                rows[aid] = (t2q[t], "webpage")
    ents = get_entities(client, [q for q, _ in rows.values()])
    # name + years fallback
    todo = [r for r in agents.itertuples() if r.agent_id not in rows and pd.notna(r.birth)]
    print(f"p1938/webpage matched {len(rows)}; name_years candidates {len(todo)}", flush=True)
    cand = {r.agent_id: search(client, display_name(r.name)) for r in todo}
    ents.update(get_entities(client, [q for qs in cand.values() for q in qs if q not in ents]))
    for r in todo:
        pb = int(r.birth)
        pdth = None if pd.isna(r.death) else int(r.death)
        for q in cand[r.agent_id]:
            e = ents.get(q)
            if e and e["human"] and years_compatible(pb, pdth, e["wd_birth"], e["wd_death"]):
                rows[r.agent_id] = (q, "name_years")
                break
    out = []
    for r in agents.itertuples():
        q, how = rows.get(r.agent_id, (None, None))
        e = ents.get(q, {}) if q else {}
        out.append({"agent_id": int(r.agent_id), "qid": q, "match_method": how,
                    "sitelinks": e.get("sitelinks") if q else None, "wd_label": e.get("label"),
                    "wd_birth": e.get("wd_birth"), "wd_death": e.get("wd_death"),
                    "wd_human": e.get("human") if q else None})
    return pd.DataFrame(out)


def main() -> None:
    from pipeline.author_identity import corpus_agents  # noqa: E402 (repo-root import)
    agents = corpus_agents()
    with httpx.Client(headers={"User-Agent": UA}, timeout=120) as c:
        res = match_agents(agents, c)
    res.to_parquet(WORK / "agent_wikidata.parquet", index=False)
    print(res.match_method.value_counts(dropna=False).to_string())
    print("wrote", WORK / "agent_wikidata.parquet")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
