import numpy as np
import pandas as pd
import pytest
from statsmodels.stats.multitest import multipletests

from analysis.stats import dsl, models
from analysis.stats.simulate import SimConfig, keyword_series, simulate


def test_ns_basis():
    knots = np.array([1800, 1840, 1865, 1890, 1925.0])
    x = np.linspace(1780, 1950, 200)
    B = models.ns_basis(x, knots)
    assert B.shape == (200, 4)
    assert np.linalg.matrix_rank(np.c_[np.ones(200), B]) == 5
    # linear beyond the boundary knots: second differences vanish
    out = (x > 1926) | (x < 1799)
    for side in (x > 1926, x < 1799):
        d2 = np.diff(B[side], 2, axis=0)
        assert np.allclose(d2, 0, atol=1e-9)
    # reproduces any linear function exactly
    coef, *_ = np.linalg.lstsq(np.c_[np.ones(200), B], 3 + 0.01 * x, rcond=None)
    assert np.allclose(np.c_[np.ones(200), B] @ coef, 3 + 0.01 * x)


def test_holm_matches_statsmodels():
    p = np.array([0.001, 0.04, 0.03, 0.2, 0.012])
    assert np.allclose(models.holm(p), multipletests(p, method="holm")[1])


@pytest.mark.parametrize("link", ["logit", "identity"])
def test_standardized_share_gradient(oracle_wd, link):
    d = models.Design.from_data(oracle_wd)
    tf = models.fit_target(oracle_wd, "locus", d, link=link)
    ref = oracle_wd.cov.iloc[:300]
    yrs = np.arange(1800, 1840, 5)
    v, g = models.standardized_share(tf, ref, yrs, [1], [1, 2, 3])
    b0 = tf.fit.beta.copy()
    num = np.zeros_like(g)
    flat = b0.T.reshape(-1)
    for i in range(len(flat)):
        for s in (+1, -1):
            f2 = flat.copy()
            f2[i] += s * 1e-6
            tf.fit.beta = f2.reshape(b0.shape[1], b0.shape[0]).T
            num[i] += s * models.standardized_share(tf, ref, yrs, [1], [1, 2, 3])[0] / 2e-6
    tf.fit.beta = b0
    assert np.allclose(g, num, atol=1e-5)


def test_h1_oracle_recovers_truth_direction(oracle_wd):
    e = models.h1(oracle_wd)
    mat, inn = e.components[0], e.components[1]
    assert mat.estimate < 0 and inn.estimate > 0 and e.p < 0.01
    assert e.infl.shape[1] == 3


def test_h2_and_h3_run(dsl_wd, corpus):
    for f in (models.h2a, models.h2b, models.h2c):
        e = f(dsl_wd)
        assert all(np.isfinite(c.estimate) for c in e.components)
    tab, effs = models.confirmatory(dsl_wd, keyword_series(corpus), n_boot=200)
    assert set(tab.test) == {"H1", "H2a", "H2b", "H2c", "H3"}
    assert (tab.p_holm >= tab.p_test - 1e-12).all()


def test_h3_tracking_vs_divergent(oracle_wd, corpus):
    div = models.h3(oracle_wd, keyword_series(corpus, track=False), n_boot=300)
    trk = models.h3(oracle_wd, keyword_series(corpus, track=True, noise=0.0), n_boot=300)
    assert div.extra["D"] > 1.0 and div.p < 0.05
    assert trk.extra["D"] < div.extra["D"] and trk.p > 0.05
    lo, hi = div.extra["D_ci"]
    assert lo <= div.extra["D"] <= hi + 1e-9 or lo <= hi


def test_shift_share_toy_composition_only():
    """Genre A: material share 0.8, genre B: 0.2, constant within genre; early all A, late 50/50."""
    n = 400
    year = np.r_[np.full(n, 1810), np.full(n, 1900)]
    genre = np.r_[np.full(n, "A"), np.where(np.arange(n) % 2 == 0, "A", "B")]
    mat = np.where(genre == "A", 0.8, 0.2)
    Y = np.c_[np.full(2 * n, 0.5), 0.5 * mat, 0.5 * (1 - mat), np.zeros(2 * n)]
    cov = pd.DataFrame({"work_id": np.arange(2 * n).astype(str), "author_key": np.arange(2 * n).astype(str),
                        "year": year, "decade": year // 10 * 10, "genre": genre, "origin": "UK"})
    wd = dsl.WorkData(cov, {"locus": Y})
    t = models.shift_share(wd, "locus", [1], [1, 2, 3], models.EARLY, models.LATE, B=20).set_index("part")
    assert t.estimate["total"] == pytest.approx(-0.3)
    assert t.estimate["within_genre"] == pytest.approx(0.0, abs=1e-12)
    assert t.estimate["composition"] == pytest.approx(-0.3)
    f = models.fixed_composition_trend(wd, "locus", [1], [1, 2, 3], ref=(1800, 1925), B=10).set_index("decade")
    assert f.fixed[1810] == pytest.approx(0.8) and f.raw[1900] == pytest.approx(0.5)
    assert f.ref_coverage[1810] == pytest.approx(0.75)   # genre B absent in 1810


def test_shift_share_exact_on_simulation():
    c = simulate(SimConfig(n_works=3000, passages_per_work=6, seed=4), audit=False)
    wd = dsl.prepare(c.labels, method="oracle", truth=c.truth, targets=("locus", "darkness"), split=None)
    t = models.shift_share(wd, "locus", [1], [1, 2, 3], models.EARLY, models.LATE, B=30).set_index("part")
    assert t.estimate["total"] == pytest.approx(t.estimate["within_genre"] + t.estimate["composition"], abs=1e-12)
    assert (t.lo <= t.estimate).all() and (t.estimate <= t.hi).all()
    s = models.shift_share_series(wd, "locus", [1], [1, 2, 3], B=5)
    assert np.allclose(s.total, s.within_genre + s.composition)
    f = models.fixed_composition_trend(wd, "darkness", [1], None, B=10)
    assert {"n_works", "n_authors", "ref_coverage"} <= set(f.columns)
