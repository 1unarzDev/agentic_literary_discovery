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
    rows = []
    for i in range(25):  # 25 expert items, early/late
        e = "early_1800_1849" if i % 2 else "late_1885_1920"
        rows += [(a, f"e{i}", "p_e%d" % i, "audit", "expert", None, e) for a in ("student", "peer1", "teacher")]
    for i in range(6):
        e = "early_1800_1849" if i % 2 else "late_1885_1920"
        rows += [("student", f"o{i}", f"p_o{i}", "audit", "overlap", "peer1", e),
                 ("peer1", f"o{i}", f"p_o{i}", "audit", "overlap", "student", e)]
    rows.append(("student", "s1", "p_s1", "audit", "single", None, "late_1885_1920"))
    return pd.DataFrame(rows, columns=["annotator", "item_id", "passage_id", "set", "role", "partner", "era"])


def lab(i, item, ann, **kw):
    r = row(i, item, ann, **kw)
    r["passage_id"] = "p_" + item
    return r


def test_progress_offline():
    q = _queues()
    pids = [f"pg1_p{i}" for i in range(4)]
    ent = lambda p, ho: {"passage_id": p, "reference": {"has_obstacle": ho, "domain": None, "locus": None,
                                                        "failure_cause": None}, "rationale": ""}
    ref = {"practice": [ent(pids[0], "no")], "cert": [ent(pids[1], "no"), ent(pids[2], "no")],
           "retake": [ent(pids[3], "no")]}
    rows, i = [], 0
    for k in range(25):
        i += 1
        rows.append(lab(i, f"e{k}", "teacher"))
        i += 1
        rows.append(lab(i, f"e{k}", "student"))  # agrees with teacher on all -> kappa 1 (pe=1 -> 1.0)
        i += 1
        # peer1 disagrees on locus for most items
        rows.append(lab(i, f"e{k}", "peer1", loc="material_external" if k % 3 else "internal_psychological"))
    for k in range(6):
        rows += [lab(100 + k, f"o{k}", "student", s=20), lab(200 + k, f"o{k}", "peer1",
                 ho="yes" if k < 4 else "no", dom=None if k >= 4 else "INNER_STATE")]
    rows.append(lab(300, "s1", "student", s=30, undone=True))
    rows += [lab(301, item_id(pids[0]), "student", ho="no", dom=None, loc=None, practice=True, set_="practice", s=999),
             lab(302, item_id(pids[1]), "student", ho="no", dom=None, loc=None, set_="cert"),
             lab(303, item_id(pids[2]), "student", ho="yes", set_="cert")]
    labs = an.flatten_labels(rows)
    out = {r["annotator"]: r for r in an.progress_table(labs, q, None, ref, "teacher")}
    st, p1 = out["student"], out["peer1"]
    assert st["queues"]["audit"] == (31, 32)
    assert st["median_s"] == 10.0  # 25 x 10s expert + 6 x 20s overlap; practice/cert/undone excluded
    assert st["expert_agr"]["n"] == 25 and st["expert_agr"]["locus4"]["pct"] == 1.0
    assert st["expert_rule"]["n_expert_items"] == 25 and not st["expert_rule"]["flag_exclude"]
    assert p1["expert_rule"]["flag_exclude"]  # locus kappa vs expert < 0.40
    assert st["overlap_agr"]["n"] == 6 and math.isclose(st["overlap_agr"]["has_obstacle"]["pct"], 4 / 6)
    c = st["cert_local"]
    assert c["practice"]["done"] == 1 and c["practice"]["passed"] is None
    assert c["cert"]["done"] == 2 and c["cert"]["obs_agree"] == 0.5 and c["cert"]["passed"] is False
    assert c["retake"]["done"] == 0
    assert "expert_agr" not in out["teacher"] and "cert_local" not in out["teacher"]
    ov = an.overlap_report(an.active(labs), q, "teacher")
    assert set(ov.subset) == {"all", "early_1800_1849", "late_1885_1920"}
    assert ov.set_index("subset").n_pairs.to_dict() == {"all": 6, "early_1800_1849": 3, "late_1885_1920": 3}
    txt = an.format_progress(list(out.values()), ov)
    assert "FLAG" in txt and "late_1885_1920" in txt and "cert" in txt


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
    out = an.attach_roles(df, q.assign(era="late_1885_1920"))
    assert out.role.iloc[0] == "overlap" and out.partner.iloc[0] == "peer1" and out.era.iloc[0] == "late_1885_1920"
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
