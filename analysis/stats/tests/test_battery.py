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
    from analysis.stats.simulate import SimConfig, keyword_series, simulate, write
    c = simulate(SimConfig(n_works=1600, passages_per_work=8, seed=8, audit_n=800))
    write(c, tmp_path)
    keyword_series(c).to_csv(tmp_path / "kw.csv", index=False)
    alt = c.labels.sample(frac=0.3, random_state=0)
    alt.to_parquet(tmp_path / "alt.parquet")
    bt = battery.run_all(str(tmp_path / "labels.parquet"), str(tmp_path / "human.parquet"),
                         str(tmp_path / "audit_frame.parquet"), str(tmp_path / "kw.csv"),
                         alt_path=str(tmp_path / "alt.parquet"), rep_labels=str(tmp_path / "labels.parquet"),
                         n_perm=5, out_dir=str(tmp_path / "out"))
    assert set(bt.hypothesis) == {"H1", "H2a", "H2b", "H2c", "H3"}
    assert all(v.split(":")[0] in {"supported", "unstable", "null"} for v in bt.verdict)
    assert (tmp_path / "out" / "confirmatory.csv").exists()
