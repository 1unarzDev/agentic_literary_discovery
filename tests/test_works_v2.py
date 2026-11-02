"""Unit tests for author identity v2, split repair, the canon measure helpers, primary flags and split_v2_map.
Synthetic inputs only; no data/ files are needed."""
from __future__ import annotations

import gzip
import json

import pandas as pd
import pytest

from pipeline import author_identity as AI
from pipeline import build_works_v2 as B
from pipeline import pg_rdf
from pipeline import wikidata_authors as WD
from pipeline.split_v2_map import SplitV2, pg_of, queue_report

RDF = b"""<?xml version="1.0" encoding="utf-8"?>
<rdf:RDF xml:base="http://www.gutenberg.org/" xmlns:dcterms="http://purl.org/dc/terms/"
  xmlns:pgterms="http://www.gutenberg.org/2009/pgterms/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
  xmlns:marcrel="http://id.loc.gov/vocabulary/relators/">
  <pgterms:ebook rdf:about="ebooks/1400">
    <pgterms:downloads>38268</pgterms:downloads>
    <marcrel:ill><pgterms:agent rdf:about="2009/agents/999"><pgterms:name>Ill, Ustrator</pgterms:name></pgterms:agent></marcrel:ill>
    <dcterms:creator>
      <pgterms:agent rdf:about="2009/agents/37">
        <pgterms:name>Dickens, Charles</pgterms:name>
        <pgterms:birthdate>1812</pgterms:birthdate><pgterms:deathdate>1870</pgterms:deathdate>
        <pgterms:alias>Boz</pgterms:alias>
        <pgterms:webpage rdf:resource="https://en.wikipedia.org/wiki/Charles_Dickens"/>
      </pgterms:agent>
    </dcterms:creator>
    <dcterms:title>Great Expectations</dcterms:title>
  </pgterms:ebook>
</rdf:RDF>"""


def test_parse_rdf_extracts_author_downloads_and_agent():
    row, agents = pg_rdf.parse_rdf(RDF)
    assert row["pg_id"] == 1400 and row["downloads"] == 38268
    assert row["first_author_agent"] == 37  # creator beats the illustrator listed first
    a = {x["agent_id"]: x for x in agents}[37]
    assert a["birth"] == 1812 and json.loads(a["aliases"]) == ["Boz"]


def test_parse_rdf_rejects_entities_and_garbage():
    assert pg_rdf.parse_rdf(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><x>&a;</x>') is None
    assert pg_rdf.parse_rdf(b"not xml") is None


def test_name_tokens_and_house_names():
    assert AI.name_tokens("Dixon, Franklin W.") == AI.name_tokens("Franklin W. Dixon")
    assert AI.is_house_name("Appleton, Victor, II")
    assert AI.is_house_name("Allen, Quincy", ["Allen, Captain Quincy"])
    # a dated real writer is not pulled in by an alias alone
    assert not AI.is_house_name("Rathborne, St. George", ["Adams, Harrison"], birth=1854)
    assert not AI.is_house_name("Dickens, Charles")


def test_pick_author_agent_prefers_creator_then_any_role():
    assert AI.pick_author_agent(json.dumps([[5, "ill"], [7, "creator"]])) == 7
    assert AI.pick_author_agent(json.dumps([[5, "edt"]])) == 5
    assert AI.pick_author_agent(None) is None


def _agents():
    return pd.DataFrame([
        {"agent_id": 1, "name": "Alger, Horatio, Jr.", "aliases": "[]", "birth": 1832, "death": 1899, "webpages": "[]"},
        {"agent_id": 2, "name": "Alger, Horatio, Jr.", "aliases": "[]", "birth": 1832, "death": 1899, "webpages": "[]"},
        {"agent_id": 3, "name": "Hope, Laura Lee", "aliases": "[]", "birth": None, "death": None, "webpages": "[]"},
        {"agent_id": 4, "name": "Stratemeyer, Edward", "aliases": "[]", "birth": 1862, "death": 1930, "webpages": "[]"},
        {"agent_id": 5, "name": "Chadwick, Lester", "aliases": "[]", "birth": 1873, "death": 1962,
         "webpages": '["ebooks/author/6"]'},
        {"agent_id": 6, "name": "Garis, Howard Roger", "aliases": "[]", "birth": 1873, "death": 1962, "webpages": "[]"},
        {"agent_id": 7, "name": "Anonymous", "aliases": "[]", "birth": None, "death": None, "webpages": "[]"},
        {"agent_id": 8, "name": "Twain, Mark", "aliases": "[]", "birth": 1835, "death": 1910, "webpages": "[]"},
        {"agent_id": 9, "name": "Clemens, Samuel", "aliases": "[]", "birth": None, "death": None, "webpages": "[]"},
    ])


def test_agent_groups_edges():
    q = pd.DataFrame({"agent_id": [8, 9], "qid": ["Q7245", "Q7245"]})
    g, rule = AI.agent_groups(_agents(), q)
    assert g[1] == g[2] == "pga:1"                       # E3 duplicate record
    assert g[3] == g[4] == g[5] == g[6] == AI.SYNDICATE  # E4 + E1 (Garis via Chadwick link)
    assert g[8] == g[9]                                   # E2 shared QID
    assert 7 not in g                                     # placeholder never grouped
    assert rule[3] == "E4_stratemeyer"


def test_repair_split_moves_straddlers_to_discovery_only():
    df = pd.DataFrame({"work_id": list("abcdef"),
                       "author_group": ["g1", "g1", "g2", "g3", "g3", "g4"],
                       "split": ["discovery", "confirmation", "confirmation", "confirmation", "confirmation",
                                 "discovery"]})
    out = AI.repair_split(df).set_index("work_id")
    assert out.loc["b", "split_v2"] == "discovery" and out.loc["b", "moved"]
    assert not out.loc[["a", "c", "d", "e", "f"], "moved"].any()
    assert (out.split_v2[out.split == "discovery"] == "discovery").all()  # never Discovery -> Confirmation


def test_build_assigns_placeholder_singletons_and_repairs():
    works = pd.DataFrame({"work_id": ["w1", "w2", "w3", "w4"], "pg_id": [10, 11, 12, 13],
                          "author_key": ["hopelauralee", "stratemeyeredward", "anonymous", "anonymous"],
                          "split": ["discovery", "confirmation", "confirmation", "discovery"]})
    eb = pd.DataFrame({"pg_id": [10, 11, 12, 13],
                       "creators": [json.dumps([[3, "creator"]]), json.dumps([[4, "creator"]]),
                                    json.dumps([[7, "creator"]]), json.dumps([[7, "creator"]])]})
    w = AI.build(works, eb, _agents()).set_index("work_id")
    assert w.loc["w1", "author_group"] == w.loc["w2", "author_group"] == AI.SYNDICATE
    assert w.loc["w2", "moved"] and w.loc["w2", "split_v2"] == "discovery"
    assert w.loc["w3", "author_group"] == "work:w3" and not w.loc["w3", "moved"]


def test_wikipedia_sitelinks_counts_only_language_wikipedias():
    sl = {"enwiki": {}, "frwiki": {}, "commonswiki": {}, "enwikiquote": {}, "enwikisource": {}, "specieswiki": {},
          "zh_min_nanwiki": {}}
    assert WD.wikipedia_sitelinks(sl) == 3


def test_years_compatible_and_display_name():
    assert WD.years_compatible(1812, 1870, 1812, 1870)
    assert WD.years_compatible(1812, None, 1813, 1870)
    assert not WD.years_compatible(1812, 1870, 1812, 1890)
    assert not WD.years_compatible(None, None, 1812, 1870)
    assert WD.display_name("Dickens, Charles") == "Charles Dickens"
    assert WD.display_name("Alger, Horatio, Jr.") == "Horatio Alger"


def test_era_and_flags():
    assert B.era_of(1849) == "E" and B.era_of(1850) == "M" and B.era_of(1885) == "L" and B.era_of(1930) is None
    assert B.historical_setting("juvenile", "Scotland -- History -- 1371-1567 -- Juvenile fiction", None, 1880)
    assert not B.historical_setting("adventure", "United States -- History -- Civil War, 1861-1865 -- Fiction", None, 1863)
    assert B.historical_setting("domestic_realist", None, "Historical Novels", 1900)
    assert B.juvenile("adventure", "Boys -- Juvenile fiction") and not B.juvenile("adventure", "Sea stories")


def test_canon_table_house_names_never_canonical():
    w = pd.DataFrame({"work_id": ["w1", "w2", "w3"], "pg_id": [1, 2, 3],
                      "author_group": ["pga:37", AI.SYNDICATE, "pga:50"],
                      "author_name": ["Dickens, Charles", "Keene, Carolyn", "Nobody, A."]})
    eb = pd.DataFrame({"pg_id": [1, 2, 3], "downloads": [5000, 900, 3], "first_author_agent": [37, 58985, 50]})
    q = pd.DataFrame({"agent_id": [37, 58985, 50], "qid": ["Q5686", "Q1", None], "sitelinks": [120, 40, None]})
    groups = {37: "pga:37", 58985: AI.SYNDICATE, 50: "pga:50"}
    c = B.canon_table(w, eb, q, groups, k=20).set_index("work_id")
    assert c.loc["w1", "canonical"] and not c.loc["w2", "canonical"] and not c.loc["w3", "canonical"]
    assert c.loc["w1", "canon_score"] > c.loc["w3", "canon_score"]
    assert c.loc["w2", "canon_score"] <= 0.5


def test_split_v2_map_and_queue_report(tmp_path, monkeypatch):
    w = pd.DataFrame({"pg_id": [461, 12], "work_id": ["w461", "w12"], "split": ["confirmation", "confirmation"],
                      "split_v2": ["discovery", "confirmation"]})
    m = SplitV2.from_frame(w)
    assert pg_of("pg461_p00087") == 461 and pg_of("junk") is None
    assert m.split_of("pg461_p00087") == "discovery" and m.moved("pg461_p00087")
    assert m.split_of("pg12_p00001") == "confirmation" and not m.moved("pg12_p00001")
    df = m.reassign(pd.DataFrame({"passage_id": ["pg461_p1", "pg12_p2", "pg999_p3"]}))
    assert df.moved.tolist() == [True, False, False] and df.split_v2.tolist()[:2] == ["discovery", "confirmation"]
    assert pd.isna(df.split_v2.iloc[2])
    # queue report over a synthetic shard
    import pipeline.split_v2_map as S
    monkeypatch.setattr(S, "WORK", tmp_path)
    (tmp_path / "shards/x").mkdir(parents=True)
    with gzip.open(tmp_path / "shards/x/j1.jsonl.gz", "wt") as f:
        for pid in ["pg461_p1", "pg461_p2", "pg12_p1"]:
            f.write(json.dumps({"passage_id": pid}) + "\n")
    jobs = tmp_path / "conf_job_status.json"
    jobs.write_text(json.dumps([{"results": [{"job_id": "j1", "wave": "x", "stage": "label", "status": "done",
                                              "shard_key": "shards/x/j1.jsonl.gz", "has_result": 1}]}]))
    r = queue_report(jobs, m)
    assert r.n_moved.tolist() == [2] and r.n_moved_labelled.tolist() == [2] and r.moved_works.tolist() == [1]
