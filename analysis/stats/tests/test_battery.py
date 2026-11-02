import functools

import numpy as np
import pandas as pd

from analysis.stats import battery, dsl, models
from analysis.stats.battery import Check


def test_verdict_rule():
    ok = [Check(n, True) for n in battery.CHECKS]
    assert battery.verdict(True, ok)[0] == "supported"
    assert battery.verdict(False, ok)[0] == "null"
    two_fail = [Check(n, i >= 2) for i, n in enumerate(battery.CHECKS)]
    assert battery.verdict(True, two_fail)[0] == "supported"          # 7 of 9
    three_fail = [Check(n, i >= 3) for i, n in enumerate(battery.CHECKS)]
    assert battery.verdict(True, three_fail)[0] == "unstable"          # 6 of 9
    no_rep = [Check(n, n != "replication") for n in battery.CHECKS]
    assert battery.verdict(True, no_rep)[0] == "unstable"              # replication sign is required
    na = [Check(n, None if n == "date_permutation" else (n != "segmentation")) for n in battery.CHECKS]
    v, n_pass, n_app, need = battery.verdict(True, na)
    assert (n_app, need, v) == (8, 7, "supported")


def test_permute_years_modes(oracle_wd):
    cov = oracle_wd.cov
    rng = np.random.default_rng(0)
    lit = battery.permute_years(cov, rng, "literal")
    a = cov.assign(y=lit).groupby(["author_key", "genre"]).y.apply(sorted)
    b = cov.groupby(["author_key", "genre"]).year.apply(sorted)
    assert (a == b).all()
    prof = battery.permute_years(cov, rng)
    assert not np.array_equal(prof, cov.year.values)
    # within-author spread is preserved (up to clipping/rounding)
    sd0 = cov.groupby("author_key").year.std().fillna(0)
    sd1 = cov.assign(y=prof).groupby("author_key").y.std().fillna(0)
    assert np.median(np.abs(sd0 - sd1)) < 1.0


def test_author_profile_permutation_is_a_null_literal_is_not(oracle_wd):
    d = models.Design.from_data(oracle_wd)
    fn = functools.partial(models.h1, design=d)
    prim = fn(oracle_wd)
    lit = battery.date_permutation(fn, oracle_wd, prim, n_perm=8, mode="literal")
    pro = battery.date_permutation(fn, oracle_wd, prim, n_perm=24)
    est = prim.tested[0].estimate
    assert abs(pro.detail["null_mean"]) < 0.5 * abs(est)
    assert abs(lit.detail["null_mean"]) > 0.5 * abs(est)
    assert pro.passed


def test_run_battery_end_to_end(corpus, oracle_wd):
    d = models.Design.from_data(oracle_wd)
    fn = functools.partial(models.h1, design=d)
    naive = dsl.prepare(corpus.labels, method="naive")
    rep = dsl.prepare(corpus.labels, method="oracle", truth=corpus.truth, split="discovery")
    res = battery.run_battery("H1", fn, oracle_wd, holm_reject=True, alt=[(naive, naive)],
                              segmentation=None, replication_wd=rep, n_perm=9)
    t = res.table()
    assert list(t.check) == battery.CHECKS
    assert t.set_index("check").result["segmentation"] == "fail"     # not run -> fail
    assert t.set_index("check").result["leave_one_author_out"] == "pass"
    assert res.verdict.split(":")[0] in {"supported", "unstable"}
    assert res.verdict.endswith("inward")          # simulated truth is the Kahler pattern
    # H3-style effect without influence matrix -> grouped jackknife path
    e = models.Effect("x", [models.Component("c", -0.1, 0.01, -1)], None)
    chk = battery.leave_one_author_out(lambda w: e, oracle_wd, e, n_groups=4)
    assert chk.passed and chk.detail["method"].startswith("grouped")


def test_cli_run_all_on_simulated_files(tmp_path):
    """v0.5 pipeline end to end: metadata audit draw, 4 peers + grad-student anchor + teacher items,
    expert-anchored DSL, TF + H1 co-primaries, battery with canon permutation."""
    from analysis import select_annotation as sa
    from analysis.stats.power_v05 import peer_labels
    from analysis.stats.simulate import SimConfig, keyword_series, simulate
    c = simulate(SimConfig.v05(n_works=3000, seed=8), audit=False)
    lab = c.labels
    conf = lab[(lab.split == "confirmation") & (lab.stratum == "random")]
    rng = np.random.default_rng(0)
    aud, frame = sa.draw_audit_metadata(conf[["passage_id", "work_id", "author_key", "year", "split", "stratum",
                                              "genre", "canonical"]], rng, n_target=700)
    tpos = c.truth.set_index("passage_id")
    peers = peer_labels(aud.passage_id.values, tpos, (0.2, 0.25, 0.3, 0.3), rng)
    ex_ids = aud.groupby("audit_cell", group_keys=False).apply(lambda g: g.sample(frac=0.25, random_state=1)).passage_id
    ex = tpos.loc[ex_ids].reset_index()
    grad = pd.DataFrame({"passage_id": ex.passage_id, "annotator": "grad", "has_obstacle": ex.has_obstacle,
                         "domains": ex.domains.map(lambda d: list(d)[:1]), "locus": ex.locus,
                         "failure_cause": ex.failure_cause})
    teacher = grad.head(8).assign(annotator="teacher")
    human = pd.concat([peers, grad, teacher], ignore_index=True)
    lab.to_parquet(tmp_path / "labels.parquet"); human.to_parquet(tmp_path / "human.parquet")
    frame.to_parquet(tmp_path / "frame.parquet"); keyword_series(c).to_csv(tmp_path / "kw.csv", index=False)
    bt = battery.run_all(str(tmp_path / "labels.parquet"), str(tmp_path / "human.parquet"),
                         str(tmp_path / "frame.parquet"), str(tmp_path / "kw.csv"), n_perm=5, out_dir=str(tmp_path / "out"))
    assert set(bt.hypothesis) == {"H1", "TF"}
    assert all(v.split(":")[0] in {"supported", "unstable", "null"} for v in bt.verdict)
    tab = pd.read_csv(tmp_path / "out" / "confirmatory.csv")
    assert set(tab[tab.role == "co-primary"].test) == {"H1", "TF"}
    assert (tab[tab.role == "co-primary"].alpha == 0.025).all()
    assert set(tab[tab.role == "estimation"].test) >= {"H2a", "H2b", "H2c", "H3"}
    assert (tmp_path / "out" / "teacher_vs_grad_descriptive.csv").exists()
