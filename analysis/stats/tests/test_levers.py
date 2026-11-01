import numpy as np
import pandas as pd

from analysis.stats import dsl, levers, models


def test_model_codes_hit_requested_accuracy():
    rng = np.random.default_rng(0)
    n = 60000
    y = np.where(rng.random(n) < 0.7, 1 + rng.choice(3, n, p=[0.3, 0.55, 0.15]), 0)
    era = rng.choice(["E", "M", "L"], n, p=[0.05, 0.15, 0.8])
    pop = rng.random(n) < 0.4
    for prec, acc in ((0.77, 0.90), (0.95, 0.85)):
        yh = levers.model_codes(y, era, pop, prec, acc, rng)
        p_real = ((yh > 0) & (y > 0)).sum() / (yh > 0).sum()
        tp = (yh > 0) & (y > 0)
        a_real = (yh[tp] == y[tp]).mean()
        assert abs(p_real - prec) < 0.01 and abs(a_real - acc) < 0.01
    # late popular errors over-call material
    yh = levers.model_codes(y, era, pop, 0.95, 0.85, rng)
    m = (era == "L") & pop & (y > 1) & (yh > 0) & (yh != y)
    assert (yh[m] == 1).mean() > 0.6


def test_neyman_alloc_properties():
    cells = np.array(["a"] * 1000 + ["b"] * 1000 + ["c"] * 30)
    al = levers.neyman_alloc(cells, {"a": 0.1, "b": 0.5, "c": 0.5}, 300)
    assert abs(sum(al.values()) - 300) <= 2
    assert al["b"] > al["a"] >= 8 and al["c"] <= 30


def test_confusion_correction_unbiased_with_true_M():
    rng = np.random.default_rng(1)
    M = np.array([[0.8, 0.1, 0.05, 0.05], [0.1, 0.7, 0.15, 0.05], [0.05, 0.15, 0.7, 0.1], [0.05, 0.05, 0.2, 0.7]])
    y = rng.choice(4, 50000, p=[0.3, 0.2, 0.4, 0.1])
    obs = np.array([rng.choice(4, p=M[k]) for k in y])
    corr = dsl.onehot(obs, 4) @ np.linalg.inv(M)
    assert np.allclose(corr.mean(0), dsl.onehot(y, 4).mean(0), atol=0.01)
    assert np.allclose(corr.sum(1), 1)


def test_linear_and_step_contrasts_run(oracle_wd):
    d = models.Design.from_data(oracle_wd)
    lin = models.h1_contrast(oracle_wd, d, time="linear", window=(1840, 1929), years_a=[1840], years_b=[1929])
    stp = models.h1_contrast(oracle_wd, d, time="step", window=(1840, 1929), cut=1880, years_a=[1879], years_b=[1880])
    for e in (lin, stp):
        assert e.extra["two_sided"] and 0 <= e.p <= 1 and e.extra["classification"] in {"none", "inward", "outward", "mixed"}
    assert lin.components[0].estimate < 0          # simulated inward truth: material falls
