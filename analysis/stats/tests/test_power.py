import pandas as pd

from analysis.stats import power


def test_power_point_orders_estimators():
    rows = power.one_point(((800, 12, 0.05, 0.45, "base", 3), (100, 600), ((2000, 200),)))
    df = pd.DataFrame(rows)
    se = df.groupby(["estimator", "n_human_nominal"]).se.mean()
    assert se[("oracle", -1)] < se[("dsl_calib", 600)]
    assert set(df.estimator) >= {"oracle", "naive", "dsl_raw", "dsl_calib", "dsl_calib_h1alloc", "two_phase"}
    s = power.summarise(df)
    assert (s.mde_pp_a01 > s.mde_pp_a05).all()
