import argparse
import json

import numpy as np
import pandas as pd
import pytest

from analysis import build_annotation_queues as baq
from analysis.select_annotation import DOMAINS, item_id

ANN = ["student", "peer1", "peer2", "peer3"]
PEOPLE = [*ANN, "expert1", "teacher"]
LOCUS = {"DISTANCE_TRAVEL": "material_external", "DARKNESS_VISIBILITY": "material_external",
         "ILLNESS_BODY_DEATH": "material_external", "NATURE_WEATHER": "material_external",
         "COMMUNICATION_INFORMATION": "social_institutional", "MONEY_PROPERTY_LAW": "social_institutional",
         "SOCIAL_RANK_CONVENTION": "social_institutional", "INTERPERSONAL_CONFLICT": "social_institutional",
         "INNER_STATE": "internal_psychological"}
LABEL_FIELDS = ["has_obstacle", "domains", "locus", "confidence", "quote_status"]
MODEL_FIELDS = {*LABEL_FIELDS, "author_key", "work_id", "decade", "era", "genre", "title", "author", "date",
                "stratum", "split", "weight"}
GENRES = ["juvenile", "domestic_realist", "adventure", "historical"]
ERAS = ["E_1800_1849", "M_1850_1884", "L_1885_1929"]


def synth_meta(n_works=1200, per_work=12, seed=0):
    r = np.random.default_rng(seed)
    year = r.integers(1800, 1930, n_works)
    works = pd.DataFrame({"work_id": [f"w{i}" for i in range(n_works)], "pg_id": np.arange(n_works),
                          "year": year.astype(float),
                          "decade": year // 10 * 10,
                          "split": np.where(np.arange(n_works) % 2, "discovery", "confirmation"),
                          "author_key": [f"a{i % 400}" for i in range(n_works)]})
    genre = pd.DataFrame({"work_id": works.work_id, "genre": r.choice(GENRES, n_works)})
    n = n_works * per_work
    wid = np.repeat(works.work_id.values, per_work)
    passages = pd.DataFrame({"passage_id": [f"pg{i // per_work}_p{i:06d}" for i in range(n)], "work_id": wid,
                             "stratum": r.choice(["random", "random", "random", "enrich_comm", "enrich_dark"], n)})
    for c in baq.TEXT_COLS:
        passages[c] = [f"{c if c != 'text' else 'text'} {i}" for i in range(n)]
    return works, genre, passages


def synth_labels(works, passages, seed=1):
    r = np.random.default_rng(seed)
    lab = passages[["passage_id", "work_id", "stratum"]].merge(works, on="work_id")
    n = len(lab)
    has = r.choice(["yes", "no"], n, p=[0.6, 0.4])
    dom = r.choice(DOMAINS, n)
    lab["has_obstacle"] = has
    lab["domains"] = [[d] if h == "yes" else [] for d, h in zip(dom, has)]
    lab["locus"] = [LOCUS[d] if h == "yes" else None for d, h in zip(dom, has)]
    lab["confidence"] = r.uniform(0.2, 1.0, n)
    lab["quote_status"] = r.choice(["exact", "normalized", "missing"], n)
    return lab


@pytest.fixture(scope="module")
def meta():
    return synth_meta()


@pytest.fixture(scope="module")
def inputs(meta):
    works, genre, passages = meta
    sp = baq.resolve_works(works, None)
    pool = baq.confirmation_pool(passages, sp, genre).merge(passages[["passage_id", *baq.TEXT_COLS]], on="passage_id")
    lab = synth_labels(works, passages)
    disc = baq.prepare_discovery(lab[lab.split == "discovery"].merge(
        passages[["passage_id", *baq.TEXT_COLS]], on="passage_id"), sp)
    return pool, disc, sp.warning


@pytest.fixture(scope="module")
def practice(inputs):
    _, disc, _ = inputs
    d = disc.sort_values("confidence", ascending=False).head(60)
    return d[["passage_id", "text", "ctx_before", "ctx_after"]].assign(
        set=["practice"] * 20 + ["cert"] * 20 + ["retake"] * 20,
        reference=[{"has_obstacle": "yes", "domain": "INNER_STATE", "locus": "internal_psychological",
                    "failure_cause": None, "rationale": "r"}] * len(d))


@pytest.fixture(scope="module")
def design(inputs, practice):
    pool, disc, warn = inputs
    return baq.build_design(pool, disc, ANN, practice=practice, split_warning=warn)


def test_pool_is_metadata_only(inputs, design):
    pool, _, _ = inputs
    assert not set(LABEL_FIELDS) & set(pool.columns)
    assert not set(LABEL_FIELDS) & set(design.audit.columns)
    assert (pool.split == "confirmation").all() and (pool.stratum == "random").all()
    assert design.summary["strata"].startswith("draw_audit_metadata")
    assert all(c.split("|")[1] in GENRES for c in design.frame.audit_cell)
    assert set(design.audit.era) == set(ERAS)
    # no N_cell in the summary: only the cell count and the cell-table hash
    s = design.summary
    assert "cells" not in s and len(s["cell_table_hash"]) == 64 and s["n_cells"] == design.frame.audit_cell.nunique()


def test_draw_passthrough(inputs, design):
    pool, _, _ = inputs
    from analysis.select_annotation import draw_audit_metadata
    a, f = draw_audit_metadata(pool[~pool.author_key.isin(design.teaching.author_key)],
                               np.random.default_rng(baq.SEED), 1800)
    extra = ["is_expert", "expert_cell_n", "pi_expert_given_audit"]
    pd.testing.assert_frame_equal(a.reset_index(drop=True), design.audit.drop(columns=extra))
    pd.testing.assert_frame_equal(f, design.frame)
    p = design.summary["params"]
    assert (p["n_target"], p["overlap_frac"], p["expert_frac"], p["n_teacher"], p["n_teaching"]) == (1800, 0.10, 0.5, 8, 60)
    assert not set(design.audit.author_key) & set(design.teaching.author_key)
    assert not set(pool[pool.author_key.isin(design.teaching.author_key)].passage_id) & set(f.passage_id)


def test_legacy_group_col(inputs):
    pool, disc, warn = inputs
    d = baq.build_design(pool, disc, ANN, group_col="genre", n_target=600)
    assert d.summary["strata"] == "draw_audit: era x genre (metadata)"
    with pytest.raises(ValueError):  # label-derived strata are refused by draw_audit(metadata_only=True)
        baq.call_draw_audit(pool.assign(dgroup="x"), set(), np.random.default_rng(0), 100, "dgroup")


def test_every_audit_item_labelled(design):
    q = design.queues[design.queues.set == "audit"]
    assert set(q.passage_id) == set(design.audit.passage_id)
    assert q.era.notna().all()


def test_expert_nested(design):
    q, a = design.queues, design.audit
    ex = q[q.role == "expert"]
    assert set(ex.annotator) == {"expert1"} and ex.passage_id.is_unique
    assert set(ex.passage_id) == set(a.passage_id[a.is_expert])
    # within-cell SRS with n_e = floor(.5 * n_cell + .5), >= 1 when n_cell >= 2
    for cell, g in a.groupby("audit_cell"):
        n = len(g)
        ne = max(int(np.floor(0.5 * n + 0.5)), 1 if n >= 2 else 0)
        assert g.is_expert.sum() == ne == g.expert_cell_n.iloc[0]
        np.testing.assert_allclose(g.pi_expert_given_audit, ne / n)
    assert abs(a.is_expert.mean() - 0.5) < 0.02
    # nested: every expert item is also peer-labelled; partner = the dealt peer
    peer = q[(q.set == "audit") & q.annotator.isin(ANN)]
    assert set(ex.passage_id) <= set(peer.passage_id)
    dealt = peer[(peer.role == "single") | ((peer.role == "overlap"))]
    for r in ex.itertuples():
        assert r.partner in set(dealt[dealt.passage_id == r.passage_id].annotator)
    # expert1: only expert audit items + review; never practice/cert/retake
    assert set(q[q.annotator == "expert1"].set) <= {"audit", "review"}
    assert set(q[(q.annotator == "expert1") & (q.set == "audit")].role) == {"expert"}
    qa = q[q.set == "audit"]
    m = qa.merge(a[["passage_id", "pi_expert_given_audit"]], on="passage_id", suffixes=("", "_a"))
    np.testing.assert_allclose(m.pi_expert_given_audit, m.pi_expert_given_audit_a)
    assert "cells" not in design.summary and design.summary["n_expert"] == a.is_expert.sum()


def test_expert_nested_small_cells():
    a = pd.DataFrame({"passage_id": [f"p{i}" for i in range(6)], "audit_cell": ["c1", "c2", "c2", "c3", "c3", "c3"]})
    out = baq.select_expert_nested(a, 0.5, np.random.default_rng(0)).groupby("audit_cell").is_expert.sum()
    assert out.to_dict() == {"c1": 1, "c2": 1, "c3": 2}  # half-up rounding: 0.5 -> 1
    out = baq.select_expert_nested(a, 0.1, np.random.default_rng(0)).groupby("audit_cell").is_expert.sum()
    assert out.to_dict() == {"c1": 0, "c2": 1, "c3": 1}


def test_teacher_items(design):
    q = design.queues
    t = q[q.role == "teacher"]
    assert set(t.annotator) == {"teacher"} and len(t) == 8
    assert set(q[q.annotator == "teacher"].role) == {"teacher"}
    assert set(t.passage_id) <= set(q[q.role == "expert"].passage_id)
    assert sorted(t.era.value_counts().tolist()) == [2, 3, 3]
    # teacher items keep exactly their expert + peer assignments, nothing added for other peers
    for pid in t.passage_id:
        g = q[(q.passage_id == pid) & (q.set == "audit")]
        assert set(g.role) <= {"teacher", "expert", "single", "overlap"}
        assert (g.annotator.isin(ANN)).sum() in (1, 2)


def test_peer_overlap(design):
    q = design.queues
    ov = q[q.role == "overlap"]
    assert set(ov.annotator) <= set(ANN) and set(ov.partner) <= set(ANN)
    assert all(len(g) == 2 for _, g in ov.groupby("passage_id"))
    assert abs(ov.passage_id.nunique() / len(design.audit) - 0.10) < 0.01
    pairs = {frozenset(g.annotator) for _, g in ov.groupby("passage_id")}
    assert len(pairs) == 6
    sec = pd.Series(design.summary["second_codings_per_annotator"])
    assert sec.max() - sec.min() <= 2
    # every audit item dealt to exactly one peer (+ at most one second peer)
    peers = q[(q.set == "audit") & q.annotator.isin(ANN)].groupby("passage_id").size()
    assert set(peers.index) == set(design.audit.passage_id) and peers.isin([1, 2]).all()


def test_balanced_peers(design):
    q = design.queues
    aq = q[(q.set == "audit") & q.annotator.isin(ANN)]
    tot = aq.groupby("annotator").size()
    assert tot.max() - tot.min() <= 2  # dealt +-1, least-loaded second codings (owner excluded) +-1
    pe = aq.groupby(["annotator", "era"]).size().unstack()
    assert ((pe.max() - pe.min()) <= 3).all() and (pe > 0).all().all()


def test_deal_balanced_by_era():
    items = pd.DataFrame({"passage_id": [f"p{i}" for i in range(301)],
                          "era": np.repeat(ERAS, [100, 100, 101])})
    owner = baq.deal(items, ANN, np.random.default_rng(0))
    era_of = dict(zip(items.passage_id, items.era))
    pe = pd.DataFrame({"a": list(owner.values()), "e": [era_of[p] for p in owner]}).groupby(["a", "e"]).size().unstack()
    assert ((pe.max() - pe.min()) <= 1).all()
    tot = pd.Series(owner).value_counts()
    assert tot.max() - tot.min() <= 1


def test_era_quota():
    assert baq.era_quota(8, {e: 100 for e in ERAS}) == dict(zip(ERAS, [3, 3, 2]))
    assert baq.era_quota(8, dict(zip(ERAS, [1, 100, 100]))) == dict(zip(ERAS, [1, 4, 3]))


def test_teaching(design, practice):
    t = design.teaching
    assert (t.split == "discovery").all()
    assert 50 <= len(t) <= 60
    assert not set(t.passage_id) & set(practice.passage_id)
    q = design.queues[design.queues.set == "teaching"]
    assert set(q.annotator) == {"student"} and len(q) == len(t)


def test_cert_and_review_sets(design, practice):
    q = design.queues
    for st in baq.CERT_SETS:
        qs = q[q.set == st]
        assert len(qs) == 20 * 4 and set(qs.annotator) == set(ANN)
        items = [i for i in design.items if i["set"] == st]
        assert len(items) == 20 and all(set(i["reference"]) == {*baq.REF_KEYS, "rationale"} for i in items)
    assert not [i for i in design.items if i["set"] == "review"]  # review only via practice_items.json
    rv = baq.practice_items(practice, ANN, "expert1")
    rv = [i for i in rv if i["set"] == "review"]
    assert len(rv) == 60 and all(i["assign"] == ["expert1"] for i in rv)
    assert (q[q.set == "review"].annotator == "expert1").sum() == 60
    assert {i["passage_id"] for i in rv} == set(practice.passage_id)
    for i in rv:
        assert i["item_id"] == baq.review_item_id(i["passage_id"]) != item_id(i["passage_id"])
        assert "reference" in i


def test_item_whitelist(design):
    ids = set()
    for it in design.items:
        allowed = set(baq.ITEM_KEYS) | ({"reference"} if it["set"] in (*baq.CERT_SETS, "review") else set())
        assert set(it) == allowed
        assert not set(it) & MODEL_FIELDS
        assert it["item_id"].startswith("it_") and len(it["item_id"]) == 15
        assert it["passage_id"] not in it["item_id"]
        assert it["text"].startswith("text ")
        ids.add(it["item_id"])
    assert len(ids) == len(design.items)
    json.dumps({"items": design.items})


def test_assign_matches_queues(design):
    q = design.queues.groupby("item_id").annotator.apply(set)
    for it in design.items:
        assert set(it["assign"]) == q[it["item_id"]]


def test_pi_consistent(design):
    a, fr = design.audit, design.frame
    n = a.groupby("audit_cell").size()
    N = fr.groupby("audit_cell").size()
    pi = fr.groupby("audit_cell").pi_audit.agg(["min", "max"])
    assert (pi["min"] == pi["max"]).all()
    np.testing.assert_allclose(pi["min"].loc[n.index], (n / N.loc[n.index]).values)
    np.testing.assert_allclose(a.weight, a.cell_N / a.cell_n)
    m = a[["passage_id"]].merge(fr, on="passage_id")
    assert len(m) == len(a) and (m.pi_audit > 0).all()
    assert fr.passage_id.is_unique
    assert "do not change pi" in design.summary["pi_note"]


def test_deterministic(inputs, practice, design):
    pool, disc, warn = inputs
    d2 = baq.build_design(pool, disc, ANN, practice=practice, split_warning=warn)
    pd.testing.assert_frame_equal(d2.queues, design.queues)
    pd.testing.assert_frame_equal(d2.frame, design.frame)
    assert d2.items == design.items
    d3 = baq.build_design(pool, disc, ANN, practice=practice, seed=1)
    assert set(d3.audit.passage_id) != set(design.audit.passage_id)


# ------------------------------------------------------------------ file-level: seal + split_v2
def _write(tmp_path, works, genre, passages, labels, works_v2=None, ref=None, canon=None):
    works.to_parquet(tmp_path / "works.parquet")
    genre.to_parquet(tmp_path / "genre.parquet")
    if canon is not None:
        canon.to_parquet(tmp_path / "canon.parquet")
    passages.to_parquet(tmp_path / "passages.parquet")
    labels.to_parquet(tmp_path / "labels.parquet")
    if works_v2 is not None:
        works_v2.to_parquet(tmp_path / "works_v2.parquet")
    if ref is not None:
        (tmp_path / "ref.json").write_text(json.dumps(ref))


def _args(tmp_path, out="out", **kw):
    a = dict(labels=str(tmp_path / "labels.parquet"), alt=None, works=str(tmp_path / "works.parquet"),
             works_v2=str(tmp_path / "works_v2.parquet"), genre=str(tmp_path / "genre.parquet"),
             passages=str(tmp_path / "passages.parquet"), group_col="genre")
    a.update(kw)
    return argparse.Namespace(**a)


def _cli(tmp_path, out, extra=()):
    baq.main(["build", str(tmp_path / "labels.parquet"), "--out", str(tmp_path / out),
              "--works", str(tmp_path / "works.parquet"), "--works-v2", str(tmp_path / "works_v2.parquet"),
              "--genre", str(tmp_path / "genre.parquet"), "--passages", str(tmp_path / "passages.parquet"),
              "--canon", str(tmp_path / "canon.parquet"),
              "--practice-ref", str(tmp_path / "ref.json"), "--n-target", "600", "--n-teaching", "20",
              "--expert-frac", "0.5", *extra])


def _ref(passages, works):
    disc = passages.merge(works, on="work_id").query("split == 'discovery'").passage_id
    ent = lambda p: {"passage_id": p, "reference": {"has_obstacle": "no", "domain": None, "locus": None,
                                                    "failure_cause": None}, "rationale": "x"}
    return {"version": "t", "practice": [ent(p) for p in disc.iloc[:5]], "cert": [ent(p) for p in disc.iloc[5:10]],
            "retake": [ent(p) for p in disc.iloc[10:15]]}


def test_discovery_only_labels_and_cli(tmp_path):
    works, genre, passages = synth_meta(500, 10, seed=3)
    lab = synth_labels(works, passages)
    _write(tmp_path, works, genre, passages, lab[lab.split == "discovery"], ref=_ref(passages, works))
    _cli(tmp_path, "out")
    out = tmp_path / "out"
    for f in ("teaching.parquet", "audit.parquet", "audit_frame.parquet", "queues.parquet", "ann_items.json",
              "design_summary.json"):
        assert (out / f).exists()
    s = json.loads((out / "design_summary.json").read_text())
    assert s["n_target"] == 600 and s["n_cert_sets"] == {"practice": 5, "cert": 5, "retake": 5}
    assert s["split_source"] == "works.split (OLD)" and any("works_v2" in w for w in s["warnings"])
    audit = pd.read_parquet(out / "audit.parquet")
    assert not set(LABEL_FIELDS) & set(audit.columns)
    baq.main(["practice", "--ref", str(tmp_path / "ref.json"), "--out", str(out),
              "--passages", str(tmp_path / "passages.parquet")])
    items = json.loads((out / "practice_items.json").read_text())["items"]
    assert [i["set"] for i in items] == ["practice"] * 5 + ["cert"] * 5 + ["retake"] * 5 + ["review"] * 15


def test_confirmation_labels_never_read(tmp_path, capsys):
    works, genre, passages = synth_meta(500, 10, seed=4)
    lab = synth_labels(works, passages)
    _write(tmp_path, works, genre, passages, lab, ref=_ref(passages, works))
    _cli(tmp_path, "o1")
    assert "dropped" in capsys.readouterr().out
    # scramble every Confirmation label column: output must be byte-identical
    conf = lab.split == "confirmation"
    lab2 = lab.copy()
    r = np.random.default_rng(9)
    lab2.loc[conf, "has_obstacle"] = r.choice(["yes", "no", "insufficient_context"], conf.sum())
    lab2.loc[conf, "locus"] = r.choice(list(set(LOCUS.values())), conf.sum())
    lab2.loc[conf, "domains"] = pd.Series([[d] for d in r.choice(DOMAINS, conf.sum())], index=lab2.index[conf])
    lab2.loc[conf, "confidence"] = r.uniform(0, 1, conf.sum())
    lab2.to_parquet(tmp_path / "labels.parquet")
    _cli(tmp_path, "o2")
    for f in ("audit.parquet", "audit_frame.parquet", "queues.parquet", "teaching.parquet"):
        pd.testing.assert_frame_equal(pd.read_parquet(tmp_path / "o1" / f), pd.read_parquet(tmp_path / "o2" / f))
    assert (tmp_path / "o1/ann_items.json").read_text() == (tmp_path / "o2/ann_items.json").read_text()
    # and the reader really filters rows: no Confirmation row comes back
    got, dropped = baq.read_discovery_labels(tmp_path / "labels.parquet", baq.resolve_works(works, None))
    assert dropped == conf.sum() and set(got.split) == {"discovery"}


def test_split_v2_author_group_primary_canon(tmp_path):
    works, genre, passages = synth_meta(500, 10, seed=5)
    n = len(works)
    flip = np.arange(n) % 5 == 0
    v2 = works[["work_id", "pg_id", "split"]].assign(
        split_v2=np.where(flip ^ (works.split == "discovery"), "discovery", "confirmation"),
        author_group=[f"ag{i % 150}" for i in range(n)],
        primary_v2=pd.array(np.arange(n) % 7 != 0, dtype="boolean"))
    # stale passage-level work ids: passages of w1 (discovery) claim to be w0's; reassignment by pg fixes it
    passages = passages.copy()
    stale = passages.work_id == "w1"
    passages.loc[stale, "work_id"] = "w0"
    canon = works[["work_id"]].assign(canonical=pd.array(np.arange(n) % 3 == 0, dtype="boolean"))
    lab = synth_labels(works, passages)
    _write(tmp_path, works, genre, passages, lab, works_v2=v2,
           ref=_ref(passages, v2.drop(columns="split").rename(columns={"split_v2": "split"})), canon=canon)
    _cli(tmp_path, "out")
    out = tmp_path / "out"
    s = json.loads((out / "design_summary.json").read_text())
    assert s["split_source"].startswith("works_v2.split_v2") and not any("works_v2" in w for w in s["warnings"])
    assert s["author_identity"] == "works_v2.author_group" and s["canonical_used"] is True
    assert s["strata"].endswith("x canonical")
    v2s = dict(zip(v2.work_id, v2.split_v2))
    prim = dict(zip(v2.work_id, v2.primary_v2))
    pw = {f"pg{pg}": w for pg, w in zip(v2.pg_id, v2.work_id)}
    work_of = lambda pid: pw[pid.split("_")[0]]
    frame = pd.read_parquet(out / "audit_frame.parquet")
    assert all(v2s[work_of(p)] == "confirmation" and prim[work_of(p)] for p in frame.passage_id)
    assert not set(passages[stale].passage_id) & set(frame.passage_id) or v2s["w1"] == "confirmation"
    assert any(c.split("|")[2] in ("canon", "noncanon") for c in frame.audit_cell)
    teach = pd.read_parquet(out / "teaching.parquet")
    assert all(v2s[work_of(p)] == "discovery" for p in teach.passage_id)
    assert teach.author_key.str.startswith("ag").all()
    audit = pd.read_parquet(out / "audit.parquet")
    assert audit.author_key.str.startswith("ag").all() and not set(audit.author_key) & set(teach.author_key)
    # teaching author GROUPS have no passage in the frame (pi = 0)
    ag = dict(zip(v2.work_id, v2.author_group))
    assert not {ag[work_of(p)] for p in frame.passage_id} & set(teach.author_key)
    _cli(tmp_path, "out_nc", ["--no-canonical"])
    s2 = json.loads((tmp_path / "out_nc/design_summary.json").read_text())
    assert s2["canonical_used"] is False and not s2["strata"].endswith("canonical")


def test_split_v2_map_moves_passages(meta):
    works, genre, passages = meta
    v2 = works[["work_id", "pg_id", "split"]].assign(
        split_v2=np.where(works.work_id == "w0", "discovery", works.split),  # w0 (confirmation) -> Discovery
        author_group=works.author_key, primary_v2=True)
    sp = baq.resolve_works(works, v2)
    pool = baq.confirmation_pool(passages, sp, genre)
    assert works.set_index("work_id").split["w0"] == "confirmation"
    assert not pool.work_id.eq("w0").any()
    assert sp.assign(passages[passages.work_id == "w0"][["passage_id"]]).split.eq("discovery").all()


def test_ann_items_offline_expert_export(design, tmp_path, monkeypatch):
    """pipeline/offline_annotation.py export-expert reads ann_items.json items whose assign has expert1."""
    from pipeline import offline_annotation as oa
    (tmp_path / "ann_items.json").write_text(json.dumps({"items": design.items}))
    monkeypatch.setattr(oa, "ANN", tmp_path)
    monkeypatch.setattr(oa, "OFF", tmp_path / "offline")
    monkeypatch.setattr(oa, "MAP", tmp_path / "offline" / "_map.json")
    oa.export_expert("expert1")
    rows = [json.loads(l) for l in (tmp_path / "offline/expert_items.jsonl").read_text().splitlines()]
    q = design.queues
    exp = q[q.annotator == "expert1"]
    assert set(exp[exp.set == "audit"].role) == {"expert"}
    assert len(rows) == (exp.set == "audit").sum()  # exactly the audit items (no review items)
    m = json.loads((tmp_path / "offline/_map.json").read_text())
    assert {v["passage_id"] for v in m.values()} == set(exp[exp.set == "audit"].passage_id)
    assert {v["set"] for v in m.values()} == {"audit"}
    for it in design.items:
        if "expert1" in it["assign"]:
            assert {"item_id", "passage_id", "text", "ctx_before", "ctx_after", "set", "assign"} <= set(it)
