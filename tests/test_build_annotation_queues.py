import json

import numpy as np
import pandas as pd
import pytest

from analysis import build_annotation_queues as baq
from analysis.select_annotation import DOMAINS, DOMAIN_GROUP, item_id

ANN = ["student", "peer1", "peer2", "peer3"]
LOCUS = {"DISTANCE_TRAVEL": "material_external", "DARKNESS_VISIBILITY": "material_external",
         "ILLNESS_BODY_DEATH": "material_external", "NATURE_WEATHER": "material_external",
         "COMMUNICATION_INFORMATION": "social_institutional", "MONEY_PROPERTY_LAW": "social_institutional",
         "SOCIAL_RANK_CONVENTION": "social_institutional", "INTERPERSONAL_CONFLICT": "social_institutional",
         "INNER_STATE": "internal_psychological"}
MODEL_FIELDS = {"has_obstacle", "domains", "locus", "confidence", "quote_status", "author_key", "work_id",
                "decade", "era", "group", "dgroup", "title", "author", "date", "stratum", "split", "weight"}


def synth(n=12000, seed=0) -> pd.DataFrame:
    r = np.random.default_rng(seed)
    decades = r.choice(np.arange(1800, 1921, 10), n)
    has = r.choice(["yes", "no"], n, p=[0.6, 0.4])
    dom = r.choice(DOMAINS, n)
    rows = []
    for i in range(n):
        y = has[i] == "yes"
        rows.append({"passage_id": f"pg{i % 900}_p{i:05d}", "work_id": f"w{i % 900}", "author_key": f"a{i % 300}",
                     "decade": int(decades[i]), "split": "discovery" if (i % 900) % 2 else "confirmation",
                     "stratum": r.choice(["random", "random", "random", "enrich_comm", "enrich_dark"]),
                     "text": f"text {i}", "ctx_before": f"before {i}", "ctx_after": f"after {i}",
                     "has_obstacle": has[i], "domains": [dom[i]] if y else [],
                     "locus": LOCUS[dom[i]] if y else None, "confidence": float(r.uniform(0.2, 1.0)),
                     "quote_status": r.choice(["exact", "normalized", "missing"])})
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def lab():
    return baq.prepare_labels(synth())


@pytest.fixture(scope="module")
def practice(lab):
    d = lab[(lab.split == "discovery")].sort_values("confidence", ascending=False).head(60)
    return d[["passage_id", "text", "ctx_before", "ctx_after"]].assign(
        set=["practice"] * 20 + ["cert"] * 20 + ["retake"] * 20,
        reference=[{"has_obstacle": "yes", "domain": "INNER_STATE", "locus": "internal_psychological",
                    "failure_cause": None, "rationale": "r"}] * len(d))


@pytest.fixture(scope="module")
def design(lab, practice):
    return baq.build_design(lab, ANN, "teacher", practice=practice)


def test_draw_passthrough(design, lab):
    s = design.summary
    assert s["n_target"] == 1800 and s["group_col"] == "dgroup"
    # draw_audit called exactly as registered: confirmation, teaching authors excluded, dgroup strata
    from analysis.select_annotation import draw_audit
    conf = lab[lab.split == "confirmation"]
    a, f = draw_audit(conf, set(design.teaching.author_key), np.random.default_rng(baq.SEED),
                      n_target=1800, group_col="dgroup")
    pd.testing.assert_frame_equal(a.reset_index(drop=True), design.audit)
    pd.testing.assert_frame_equal(f, design.frame)
    d2 = baq.build_design(lab, ANN, "teacher", n_target=900)
    assert d2.summary["n_target"] == 900 and len(d2.audit) < len(design.audit)


def test_audit_confirmation_only(design, lab):
    split = lab.set_index("passage_id").split
    assert (split.loc[design.audit.passage_id] == "confirmation").all()
    assert (split.loc[design.frame.passage_id] == "confirmation").all()
    assert not set(design.audit.author_key) & set(design.teaching.author_key)
    assert not set(lab[lab.passage_id.isin(design.frame.passage_id)].author_key) & set(design.teaching.author_key)


def test_every_audit_item_assigned(design):
    q = design.queues[design.queues.set == "audit"]
    assert set(q.passage_id) == set(design.audit.passage_id)
    assert q.era.notna().all()


def test_expert_items(design):
    q = design.queues
    exp = q[q.role == "expert"]
    assert exp.passage_id.nunique() == 30
    assert set(exp.passage_id) <= set(design.audit.passage_id)
    for _, g in exp.groupby("passage_id"):
        assert set(g.annotator) == set(ANN) | {"teacher"} and len(g) == 5
    assert set(q[q.annotator == "teacher"].role) == {"expert"}
    assert exp.drop_duplicates("passage_id").era.value_counts().to_dict() == {e: 10 for e in baq.ERAS}


def test_expert_is_srs_within_era():
    # each audit item in an era is equally likely to be an expert item
    aud = pd.DataFrame({"passage_id": [f"p{i}" for i in range(300)], "era": np.repeat(baq.ERAS, 100)})
    hits = pd.Series(0, index=aud.passage_id)
    for s in range(400):
        hits[baq.select_expert(aud, 30, np.random.default_rng(s))] += 1
    assert abs(hits.mean() - 40) < 1e-9 and hits.std() < 12  # binomial(400, .1) sd ~ 6


def test_overlap(design):
    q = design.queues
    ov = q[q.role == "overlap"]
    assert all(len(g) == 2 for _, g in ov.groupby("passage_id"))
    for r in ov.itertuples():
        assert r.partner != r.annotator and ((ov.passage_id == r.passage_id) & (ov.annotator == r.partner)).any()
    n_items = ov.passage_id.nunique()
    assert abs(n_items / len(design.audit) - 0.10) < 0.01
    assert not set(ov.passage_id) & set(q[q.role == "expert"].passage_id)
    by_era = ov.drop_duplicates("passage_id").era.value_counts()
    era_n = design.audit.era.value_counts()
    for e in baq.ERAS:
        assert abs(by_era[e] - 0.10 * era_n[e]) <= 1
    sec = pd.Series(design.summary["second_codings_per_annotator"])
    assert sec.max() - sec.min() <= 2
    pairs = {frozenset(g.annotator) for _, g in ov.groupby("passage_id")}
    assert len(pairs) == 6  # all pairs occur: random partners, not a ring


def test_balanced_deal(design):
    q = design.queues
    aq = q[(q.set == "audit") & (q.annotator != "teacher")]
    tot = aq.groupby("annotator").size()
    # dealt items differ by <= 1; expert (+30 each) and least-loaded second codings on top
    assert tot.max() - tot.min() <= 1
    per_era = aq[aq.role == "single"].groupby(["annotator", "era"]).size().unstack()
    owner = baq.deal(design.audit[design.audit.era.notna()], ANN, np.random.default_rng(0))
    dealt = pd.Series(owner).value_counts()
    assert dealt.max() - dealt.min() <= 1
    era_of = dict(zip(design.audit.passage_id, design.audit.era))
    pe = pd.DataFrame({"a": list(owner.values()), "e": [era_of[p] for p in owner]}).groupby(["a", "e"]).size().unstack()
    assert ((pe.max() - pe.min()) <= 1).all()
    assert (per_era > 0).all().all()
    s = design.summary
    assert s["n_expert"] + (q[q.role == "overlap"].passage_id.nunique()) + (q.role == "single").sum() == s["audit_drawn"]


def test_teaching(design, practice):
    t = design.teaching
    assert (t.split == "discovery").all()
    assert 50 <= len(t) <= 60
    assert not set(t.passage_id) & set(practice.passage_id)
    q = design.queues[design.queues.set == "teaching"]
    assert set(q.annotator) == {"student"} and len(q) == len(t)


def test_cert_sets(design, practice):
    q = design.queues
    for st in baq.CERT_SETS:
        qs = q[q.set == st]
        assert len(qs) == 20 * 4 and set(qs.annotator) == set(ANN) and (qs.role == st).all()
        items = [i for i in design.items if i["set"] == st]
        assert len(items) == 20 and all(set(i["reference"]) == {*baq.REF_KEYS, "rationale"} for i in items)
        assert all("teacher" not in i["assign"] for i in items)


def test_item_whitelist(design):
    ids = set()
    for it in design.items:
        allowed = set(baq.ITEM_KEYS) | ({"reference"} if it["set"] in baq.CERT_SETS else set())
        assert set(it) == allowed
        assert not set(it) & MODEL_FIELDS
        assert it["item_id"] == item_id(it["passage_id"]) and it["item_id"].startswith("it_")
        assert it["passage_id"] not in it["item_id"] and len(it["item_id"]) == 15
        assert it["text"].startswith("text ")
        ids.add(it["item_id"])
    assert len(ids) == len(design.items)  # one item per id, assign lists merged
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


def test_deterministic(lab, practice, design):
    d2 = baq.build_design(lab, ANN, "teacher", practice=practice)
    pd.testing.assert_frame_equal(d2.queues, design.queues)
    pd.testing.assert_frame_equal(d2.frame, design.frame)
    assert d2.items == design.items
    d3 = baq.build_design(lab, ANN, "teacher", practice=practice, seed=1)
    assert set(d3.audit.passage_id) != set(design.audit.passage_id)


def test_write_and_cli(tmp_path, lab, practice):
    raw = synth(6000, seed=3)
    raw.to_parquet(tmp_path / "labels.parquet")
    disc = raw[raw.split == "discovery"].passage_id
    ent = lambda p: {"passage_id": p, "reference": {"has_obstacle": "no", "domain": None, "locus": None,
                                                    "failure_cause": None}, "rationale": "x"}
    ref = {"version": "t", "practice": [ent(p) for p in disc.iloc[:5]], "cert": [ent(p) for p in disc.iloc[5:10]],
           "retake": [ent(p) for p in disc.iloc[10:15]]}
    (tmp_path / "ref.json").write_text(json.dumps(ref))
    raw[["passage_id", "text", "ctx_before", "ctx_after"]].to_parquet(tmp_path / "passages.parquet")
    out = tmp_path / "out"
    baq.main(["build", str(tmp_path / "labels.parquet"), "--out", str(out), "--passages", str(tmp_path / "passages.parquet"),
              "--practice-ref", str(tmp_path / "ref.json"), "--n-target", "600", "--n-teaching", "20"])
    for f in ("teaching.parquet", "audit.parquet", "audit_frame.parquet", "queues.parquet", "ann_items.json",
              "design_summary.json"):
        assert (out / f).exists()
    s = json.loads((out / "design_summary.json").read_text())
    assert s["n_target"] == 600 and s["n_cert_sets"] == {"practice": 5, "cert": 5, "retake": 5}
    baq.main(["practice", "--ref", str(tmp_path / "ref.json"), "--out", str(out),
              "--passages", str(tmp_path / "passages.parquet")])
    items = json.loads((out / "practice_items.json").read_text())["items"]
    assert len(items) == 15 and items[0]["reference"]["rationale"] == "x"
    assert [i["set"] for i in items] == ["practice"] * 5 + ["cert"] * 5 + ["retake"] * 5
