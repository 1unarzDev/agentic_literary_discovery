import json
import math

import pandas as pd
import pytest

from pipeline import annotators as an
from analysis.select_annotation import item_id


def row(i, item, ann, ho="yes", dom="INNER_STATE", loc="internal_psychological", undone=False, practice=False,
        created=None, s=10, set_="audit"):
    return {"id": i, "item_id": item, "passage_id": "p" + item, "set": set_, "annotator": ann,
            "label": {"has_obstacle": ho, "domain": dom, "locus": loc, "failure_cause": None, "note": ""},
            "evidence_text": "e", "seconds_spent": s, "created": created or i, "undone": undone, "practice": practice}


def test_flatten_old_list_domain():
    df = an.flatten_labels([row(1, "a", "x", dom=["DISTANCE_TRAVEL", "INNER_STATE"]), row(2, "b", "x", dom=[]),
                            row(3, "c", "x", dom=None), row(4, "d", "x", dom="NATURE_WEATHER")])
    assert list(df.columns) == [*an.LABEL_COLS, "locus4", "obstacle", "domains"]
    assert df.domain.tolist()[0] == "DISTANCE_TRAVEL"
    assert df.domain.isna().tolist() == [False, True, True, False]
    assert df.domain.iloc[3] == "NATURE_WEATHER"


def test_chunks():
    c = an.chunks(list(range(601)))
    assert [len(x) for x in c] == [250, 250, 101]
    assert sum(c, []) == list(range(601))
    assert an.chunks([]) == []


def test_kappa():
    assert an.cohen_kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0
    assert math.isclose(an.cohen_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]), 0.0)
    k = an.cohen_kappa(["y", "y", "y", "n", "n"], ["y", "y", "n", "n", "y"])
    assert math.isclose(k, (0.6 - 0.52) / 0.48)
    assert an.cohen_kappa(["a", "a"], ["a", "a"]) == 1.0
    assert math.isnan(an.cohen_kappa([], []))
    ag = an.agreement([None, "x"], [None, "y"])
    assert ag["n"] == 2 and ag["pct"] == 0.5


def test_active_drops_undone_and_keeps_latest():
    df = an.flatten_labels([row(1, "a", "x", ho="no"), row(2, "a", "x", ho="yes"), row(3, "b", "x", undone=True)])
    a = an.active(df)
    assert len(a) == 1 and a.iloc[0].has_obstacle == "yes"


def test_constructs():
    df = an.flatten_labels([row(1, "a", "x"), row(2, "b", "x", ho="insufficient_context", loc="material_external"),
                            row(3, "c", "x", loc="social_institutional", dom=["MONEY_PROPERTY_LAW"])])
    assert df.locus4.tolist() == ["internal", "none", "social"]
    assert df.obstacle.tolist() == ["yes", "not_yes", "yes"]
    assert df.domains.tolist() == [["INNER_STATE"], ["INNER_STATE"], ["MONEY_PROPERTY_LAW"]]


def _queues():
    """Nested design: every audit item dealt to one peer; expert rows (partner = dealt peer) on a subsample;
    teacher rows on 8 expert items. Worker names (expert1); renamed to grad in the tests."""
    rows = []
    era = lambda i: ("E_1800_1849", "M_1850_1884", "L_1885_1929")[i % 3]
    for i in range(8):  # teacher items (also expert items)
        a = "student" if i < 4 else "peer1"
        rows += [(a, f"t{i}", f"p_t{i}", "audit", "single", None, era(i)),
                 ("expert1", f"t{i}", f"p_t{i}", "audit", "expert", a, era(i)),
                 ("teacher", f"t{i}", f"p_t{i}", "audit", "teacher", None, era(i))]
    for i in range(20):  # expert items dealt to student / peer1
        e = "E_1800_1849" if i % 2 else "L_1885_1929"
        a = "student" if i < 10 else "peer1"
        rows += [(a, f"x{i}", f"p_x{i}", "audit", "single", None, e),
                 ("expert1", f"x{i}", f"p_x{i}", "audit", "expert", a, e)]
    for i in range(6):  # peer overlap; o0 is also an expert item
        e = "E_1800_1849" if i % 2 else "L_1885_1929"
        rows += [("student", f"o{i}", f"p_o{i}", "audit", "overlap", "peer1", e),
                 ("peer1", f"o{i}", f"p_o{i}", "audit", "overlap", "student", e)]
    rows.append(("expert1", "o0", "p_o0", "audit", "expert", "student", "L_1885_1929"))
    rows.append(("student", "s1", "p_s1", "audit", "single", None, "L_1885_1929"))
    return pd.DataFrame(rows, columns=["annotator", "item_id", "passage_id", "set", "role", "partner", "era"])


def lab(i, item, ann, **kw):
    r = row(i, item, ann, **kw)
    r["passage_id"] = "p_" + item
    return r


def test_progress_offline():
    mp = an.parse_rename("expert1=grad")
    q = an.apply_rename(_queues(), mp)
    assert "grad" in set(q.annotator) and "grad" not in set(q.partner.dropna())
    pids = [f"pg1_p{i}" for i in range(4)]
    ent = lambda p, ho: {"passage_id": p, "reference": {"has_obstacle": ho, "domain": None, "locus": None,
                                                        "failure_cause": None}, "rationale": ""}
    ref = {"practice": [ent(pids[0], "no")], "cert": [ent(pids[1], "no"), ent(pids[2], "no")],
           "retake": [ent(pids[3], "no")]}
    rows, i = [], 0
    for k in range(8):
        dealt = "student" if k < 4 else "peer1"
        for a in (dealt, "expert1", "teacher"):
            i += 1
            rows.append(lab(i, f"t{k}", a, loc="material_external" if (a == "peer1" and k < 6) else "internal_psychological"))
    for k in range(20):
        a = "student" if k < 10 else "peer1"
        rows.append(lab(100 + k, f"x{k}", a))
        rows.append(lab(200 + k, f"x{k}", "expert1",  # disagrees with peer1 on early items
                        loc="social_institutional" if (a == "peer1" and k % 2) else "internal_psychological"))
    for k in range(6):
        rows += [lab(300 + k, f"o{k}", "student", s=20), lab(400 + k, f"o{k}", "peer1",
                 ho="yes" if k < 4 else "no", dom=None if k >= 4 else "INNER_STATE")]
    rows.append(lab(450, "o0", "expert1"))
    rows.append(lab(500, "s1", "student", s=30, undone=True))
    rows += [lab(501, item_id(pids[0]), "student", ho="no", dom=None, loc=None, practice=True, set_="practice", s=999),
             lab(502, item_id(pids[1]), "student", ho="no", dom=None, loc=None, set_="cert"),
             lab(503, item_id(pids[2]), "student", ho="yes", set_="cert")]
    labs = an.apply_rename(an.flatten_labels(rows), mp)
    out = {r["annotator"]: r for r in an.progress_table(labs, q, None, ref, "grad")}
    assert "expert1" not in out and "grad" in out
    st, p1 = out["student"], out["peer1"]
    assert st["queues"]["audit"] == (20, 21)
    assert st["median_s"] == 10.0
    # expert agreement on ALL nested items the peer has: teacher items + expert singles + expert overlap item
    assert st["vs_expert"]["all"]["n"] == 15 and st["vs_expert"]["all"]["locus4"]["pct"] == 1.0
    v = p1["vs_expert"]
    assert v["all"]["n"] == 15 and math.isclose(v["all"]["locus4"]["pct"], 8 / 15)
    assert math.isclose(v["E_1800_1849"]["locus4"]["pct"], 1 / 6) and math.isclose(v["L_1885_1929"]["locus4"]["pct"], 6 / 7)
    assert st["vs_partners"]["all"]["n"] == 6 and math.isclose(st["vs_partners"]["all"]["has_obstacle"]["pct"], 4 / 6)
    assert st["vs_teacher"]["n"] == 4 and p1["vs_teacher"]["n"] == 4 and p1["vs_teacher"]["locus4"]["pct"] == 0.5
    assert out["grad"]["vs_teacher"]["n"] == 8
    assert "vs_expert" not in out["grad"] and "cert_local" not in out["grad"]
    assert "vs_teacher" not in out["teacher"]
    c = st["cert_local"]
    assert c["practice"]["done"] == 1 and c["practice"]["passed"] is None
    assert c["cert"]["done"] == 2 and c["cert"]["obs_agree"] == 0.5 and c["cert"]["passed"] is False
    assert c["retake"]["done"] == 0
    ov = an.overlap_report(an.active(labs), q, "grad")
    assert ov.set_index("subset").n_pairs.to_dict() == {"all": 6, "E_1800_1849": 3, "L_1885_1929": 3}
    txt = an.format_progress(list(out.values()), ov)
    assert "vs expert" in txt and "vs teacher (descriptive)" in txt and "L_1885_1929" in txt and "grad" in txt
    assert "expert1" not in txt


def test_rename_helpers():
    assert an.parse_rename("expert1=grad, a=b") == {"expert1": "grad", "a": "b"}
    assert an.parse_rename("") == {}
    st = an.rename_status({"annotators": [{"name": "expert1", "queues": []}, {"name": "peer1", "queues": []}]},
                          {"expert1": "grad"})
    assert [a["name"] for a in st["annotators"]] == ["grad", "peer1"]


def test_adjudicate():
    from analysis.build_annotation_queues import review_item_id
    ent = lambda p, ho, loc=None: {"passage_id": p, "reference": {"has_obstacle": ho, "domain": None if ho != "yes" else "INNER_STATE",
                                   "locus": loc, "failure_cause": None}, "rationale": "orig"}
    ref = {"version": "v1", "practice": [ent("pa", "no"), ent("pb", "yes", "internal_psychological")],
           "cert": [ent("pc", "no")], "retake": [ent("pd", "no")]}
    rows = [lab(1, review_item_id("pa"), "expert1", ho="no", dom=None, loc=None, set_="review"),
            dict(lab(2, review_item_id("pb"), "expert1", loc="social_institutional", set_="review")),
            lab(3, review_item_id("pc"), "expert1", ho="yes", set_="review", undone=True),
            lab(4, item_id("pd"), "student", ho="yes", set_="retake")]  # not a review label
    rows[1]["label"]["note"] = "it is a social constraint"
    rows[1]["label"]["domain"] = "SOCIAL_RANK_CONVENTION"
    out, summ = an.adjudicate(ref, an.apply_rename(an.flatten_labels(rows), {"expert1": "grad"}), "grad")
    assert out["version"] == "v1+adjudicated"
    pa, pb = out["practice"]
    assert pa["review"]["verdict"] == "agree" and pa["rationale"] == "orig"
    assert pb["review"]["verdict"] == "corrected"
    assert pb["reference"] == {"has_obstacle": "yes", "domain": "SOCIAL_RANK_CONVENTION",
                               "locus": "social_institutional", "failure_cause": None}
    assert pb["rationale"] == "orig Expert correction: it is a social constraint"
    assert pb["review"]["original"]["locus"] == "internal_psychological"
    assert out["cert"][0]["review"]["verdict"] == "pending" and out["cert"][0]["reference"]["has_obstacle"] == "no"
    assert out["retake"][0]["review"]["verdict"] == "pending"
    assert summ.verdict.value_counts().to_dict() == {"pending": 2, "agree": 1, "corrected": 1}
    # output is again a valid practice_ref
    from analysis.build_annotation_queues import parse_practice_ref
    assert len(parse_practice_ref(out)) == 4


def test_progress_worker_cert_status():
    status = {"annotators": [{"name": "student", "queues": [{"queue": "cert", "done": 20, "total": 20}],
                              "cert": {"status": "failed_retake_available", "rounds": [
                                  {"round": "cert", "n": 20, "done": 20, "obs_agree": 0.7, "locus_kappa": 0.55,
                                   "passed": False}]}}]}
    out = an.progress_table(an.flatten_labels([]), None, status, None)
    assert out[0]["cert"]["status"] == "failed_retake_available"
    assert "failed_retake_available" in an.format_progress(out)


def test_attach_roles():
    df = an.flatten_labels([row(1, "o1", "student")])
    q = pd.DataFrame([("student", "o1", "audit", "overlap", "peer1")], columns=["annotator", "item_id", "set", "role", "partner"])
    out = an.attach_roles(df, q.assign(era="L_1885_1929"))
    assert out.role.iloc[0] == "overlap" and out.partner.iloc[0] == "peer1" and out.era.iloc[0] == "L_1885_1929"
    assert an.attach_roles(df, None).role.isna().all()


def test_save_ann_cfg_mode(tmp_path, monkeypatch):
    p = tmp_path / "c" / "ann.json"
    monkeypatch.setenv("ALD_ANNOTATORS_CONFIG", str(p))
    an.save_ann_cfg({"x": {"token": "t", "link": "l"}})
    assert (p.stat().st_mode & 0o777) == 0o600
    assert an.load_ann_cfg()["x"]["link"] == "l"


def test_request_retries(monkeypatch):
    import httpx
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503 if len(calls) < 3 else 200, json={"ok": True})

    monkeypatch.setattr(an.time, "sleep", lambda s: None)
    with httpx.Client(transport=httpx.MockTransport(handler), base_url="http://x") as c:
        r = an.request(c, "GET", "/v1/admin/ann_status")
    assert r.status_code == 200 and len(calls) == 3
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(400, text="bad")), base_url="http://x") as c:
        with pytest.raises(SystemExit):
            an.request(c, "GET", "/x")


def _key_ref():
    ent = lambda p, ho, loc=None: {"passage_id": p, "reference": {"has_obstacle": ho, "domain": None if ho != "yes" else "INNER_STATE",
                                   "locus": loc, "failure_cause": None}, "rationale": "orig"}
    return {"version": "v1", "practice": [ent("pg1_p1", "no"), ent("pg1_p2", "yes", "internal_psychological")],
            "cert": [ent("pg1_p3", "no")], "retake": [ent("pg1_p4", "no")]}


def test_adjudicate_offline_parquet(tmp_path):
    from pipeline.offline_annotation import KEY_COLS
    rows = [
        {"item_id": "kr_a", "annotator": "expert1", "decision": "agree", "has_obstacle": "", "domain": "",
         "locus": "", "failure_cause": "", "evidence": "", "note": "", "seconds": "", "passage_id": "pg1_p1", "set": "key_practice"},
        {"item_id": "kr_b", "annotator": "expert1", "decision": "correct", "has_obstacle": "yes",
         "domain": "SOCIAL_RANK_CONVENTION", "locus": "social_institutional", "failure_cause": "", "evidence": "e",
         "note": "rank forbids it", "seconds": "40", "passage_id": "pg1_p2", "set": "key_practice"},
        {"item_id": "kr_c", "annotator": "expert1", "decision": "correct", "has_obstacle": "cant_tell", "domain": "",
         "locus": "", "failure_cause": "", "evidence": "", "note": "too short", "seconds": "", "passage_id": "pg1_p3", "set": "key_cert"},
    ]
    df = pd.DataFrame(rows)
    assert set(KEY_COLS) <= set(df.columns)
    (tmp_path / "offline").mkdir()
    df.to_parquet(tmp_path / "offline" / "returned_key_r1.parquet", index=False)
    dec = an.review_decisions_offline(an.load_offline_returns(str(tmp_path / "offline" / "returned_key_*.parquet")))
    out, summ = an.adjudicate(_key_ref(), None, decisions=dec)
    pa, pb = out["practice"]
    assert pa["review"]["verdict"] == "agree" and pa["reference"]["has_obstacle"] == "no" and pa["rationale"] == "orig"
    assert pb["review"]["verdict"] == "corrected" and pb["reference"]["locus"] == "social_institutional"
    assert pb["rationale"] == "orig Expert correction: rank forbids it"
    c = out["cert"][0]
    assert c["reference"] == {"has_obstacle": "insufficient_context", "domain": None, "locus": None, "failure_cause": None}
    assert c["review"]["verdict"] == "corrected"
    assert out["retake"][0]["review"]["verdict"] == "pending"
    assert summ.verdict.value_counts().to_dict() == {"corrected": 2, "agree": 1, "pending": 1}
    # CLI path writes the adjudicated file
    (tmp_path / "ref.json").write_text(json.dumps(_key_ref()))
    an.main(["adjudicate", "--from-offline", str(tmp_path / "offline" / "returned_key_*.parquet"),
             "--practice-ref", str(tmp_path / "ref.json"), "--out", str(tmp_path / "adj.json")])
    adj = json.loads((tmp_path / "adj.json").read_text())
    assert adj["version"] == "v1+adjudicated" and adj["practice"][1]["review"]["verdict"] == "corrected"
    assert adj["practice"][1]["review"]["reviewer"] == "grad"  # default --rename expert1=grad
    df2 = an.load_offline_returns(str(tmp_path / "offline" / "returned_key_*.parquet"), "grad", {"expert1": "grad"})
    assert set(df2.annotator) == {"grad"}


def test_adjudicate_offline_raw_csv(tmp_path, monkeypatch):
    from pipeline import offline_annotation as oa
    monkeypatch.setattr(oa, "OFF", tmp_path)
    monkeypatch.setattr(oa, "MAP", tmp_path / "_map.json")
    (tmp_path / "_map.json").write_text(json.dumps({"kr_a": {"passage_id": "pg1_p1", "set": "key_practice"},
                                                    "kr_b": {"passage_id": "pg1_p2", "set": "key_practice"}}))
    (tmp_path / "ret.csv").write_text(
        "item_id,annotator,decision,has_obstacle,domain,locus,failure_cause,evidence,note,seconds\n"
        "kr_a,expert1,agree,,,,,,,\n"
        'kr_b,expert1,correct,no,,,,,"not an obstacle",30\n')
    dec = an.review_decisions_offline(an.load_offline_returns(str(tmp_path / "ret.csv")))
    out, _ = an.adjudicate(_key_ref(), None, decisions=dec)
    assert out["practice"][1]["reference"]["has_obstacle"] == "no"
    assert out["practice"][1]["review"]["verdict"] == "corrected"
    (tmp_path / "bad.csv").write_text("item_id,annotator,decision,has_obstacle,domain,locus,failure_cause,evidence,note,seconds\n"
                                      "kr_zz,expert1,maybe,,,,,,,\n")
    with pytest.raises(SystemExit):
        an.load_offline_returns(str(tmp_path / "bad.csv"))
