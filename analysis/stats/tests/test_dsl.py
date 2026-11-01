import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm

from analysis.select_annotation import draw_audit
from analysis.stats import dsl, models
from analysis.stats.simulate import ERAS3, LLMNoise, SimConfig, group_vec, simulate


def _toy(n=3000, K=3, seed=0):
    rng = np.random.default_rng(seed)
    X = np.c_[np.ones(n), rng.normal(size=(n, 2))]
    B = np.array([[0.2, -0.3], [0.5, 1.0], [-0.7, 0.4]])
    P = dsl.mnl_probs(X, B[:, :K - 1])
    y = (P.cumsum(1) < rng.random(n)[:, None]).sum(1)
    return X, y, rng.integers(0, 300, n)


def test_mnlogit_matches_statsmodels():
    X, y, cl = _toy()
    f = dsl.fit_mnlogit(X, dsl.onehot(y, 3))
    ref = sm.MNLogit(y, X).fit(disp=0)
    assert np.allclose(f.beta, ref.params, atol=1e-5)
    # model-based (non-cluster) SEs: bread inverse equals statsmodels cov
    assert np.allclose(np.sqrt(np.diag(f.bread_inv)), np.sqrt(np.diag(ref.cov_params())).reshape(-1), rtol=1e-3) or \
        np.allclose(np.sort(np.diag(f.bread_inv)), np.sort(np.diag(ref.cov_params())), rtol=1e-3)


def test_binary_cluster_sandwich_matches_statsmodels():
    X, y, cl = _toy(K=2)
    f = dsl.fit_mnlogit(X, dsl.onehot(y, 2), clusters=cl)
    ref = sm.GLM(y, X, family=sm.families.Binomial()).fit(cov_type="cluster", cov_kwds={"groups": cl, "use_correction": False})
    G = len(np.unique(cl))
    assert np.allclose(f.beta[:, 0], ref.params, atol=1e-6)
    assert np.allclose(f.cov, ref.cov_params() * G / (G - 1), rtol=1e-4)


def test_linear_matches_ols_cluster():
    X, y, cl = _toy(K=2)
    f = dsl.fit_linear(X, dsl.onehot(y, 2), clusters=cl)
    ref = sm.OLS(y.astype(float), X).fit(cov_type="cluster", cov_kwds={"groups": cl, "use_correction": False})
    G = len(np.unique(cl))
    assert np.allclose(f.beta[:, 0], ref.params)
    assert np.allclose(f.cov, ref.cov_params() * G / (G - 1), rtol=1e-6)


def test_soft_outcomes_with_negative_entries_converge():
    X, y, cl = _toy()
    Y = dsl.onehot(y, 3)
    rng = np.random.default_rng(1)
    R = rng.random(len(y)) < 0.1
    Y2 = np.where(R[:, None], Y + (Y - np.roll(Y, 1, axis=1)) * 0.7, Y)   # rows still sum to 1, some < 0
    assert (Y2 < 0).any()
    f = dsl.fit_mnlogit(X, Y2, clusters=cl)
    assert f.converged and np.isfinite(f.cov).all()


def test_dsl_with_perfect_llm_equals_oracle():
    c = simulate(SimConfig(n_works=1200, passages_per_work=8, noise=LLMNoise.perfect(), seed=3, audit_n=300))
    a = dsl.prepare(c.labels, c.human, c.frame, g="raw")
    b = dsl.prepare(c.labels, method="oracle", truth=c.truth)
    assert np.allclose(a.Y["locus"], b.Y["locus"])


def test_dsl_raw_equals_stratified_ppi(corpus):
    lab = corpus.labels[(corpus.labels.split == "confirmation") & (corpus.labels.stratum == "random")].reset_index(drop=True)
    fr = lab[["passage_id"]].merge(corpus.frame, on="passage_id")
    h = dsl.resolve_human(corpus.human).set_index("passage_id")
    labd = lab.passage_id[lab.passage_id.isin(h.index)]
    yhat = (lab.has_obstacle == "yes").values.astype(float)
    y = (h.loc[labd].has_obstacle == "yes").values.astype(float)
    yh = (lab.set_index("passage_id").loc[labd].has_obstacle == "yes").values.astype(float)
    ppi = dsl.ppi_mean(yhat, y, yh, fr.audit_cell.values, h.loc[labd].audit_cell.values)
    pi = fr.pi_audit.values
    R = lab.passage_id.isin(h.index).values
    ycode = np.zeros(len(lab), int)
    ycode[R] = (h.loc[lab.passage_id[R]].has_obstacle == "yes").values
    Yt = dsl.pseudo_outcomes(yhat.astype(int), ycode, R, pi, 2, method="raw")
    assert Yt[:, 1].mean() == pytest.approx(ppi.estimate, abs=1e-10)
    tuned = dsl.ppi_mean(yhat, y, yh, fr.audit_cell.values, h.loc[labd].audit_cell.values, lam=None)
    assert tuned.se <= ppi.se + 1e-12 and 0 <= tuned.lam <= 1


def test_ppi_uniform_srs_coverage_smoke():
    rng = np.random.default_rng(0)
    cover = 0
    for r in range(200):
        y_all = rng.random(20000) < 0.4
        yhat_all = np.where(rng.random(20000) < 0.8, y_all, rng.random(20000) < 0.6).astype(float)
        idx = rng.choice(20000, 300, replace=False)
        res = dsl.ppi_mean(yhat_all, y_all[idx].astype(float), yhat_all[idx])
        cover += res.lo <= y_all.mean() <= res.hi
    assert cover / 200 > 0.9


def test_dsl_unbiased_over_audit_redraws():
    """Fixed corpus with era-varying noise; redraw the audit many times: mean DSL estimate = truth."""
    c = simulate(SimConfig(n_works=1600, passages_per_work=8, seed=21), audit=False)
    lab = c.labels[(c.labels.split == "confirmation")].reset_index(drop=True)
    tru = c.truth.set_index("passage_id").loc[lab.passage_id].reset_index()
    T = dsl.TARGETS["locus"]
    yhat, y = T.fn(lab), T.fn(tru)
    early = (lab.year.values < 1850)
    truth = (y[early] == 1).mean() / (y[early] > 0).mean()
    naive = (yhat[early] == 1).mean() / (yhat[early] > 0).mean()
    sel = lab.assign(era=np.array(ERAS3, dtype=object)[np.searchsorted([1850, 1885], lab.decade, side="right")],
                     group=group_vec(lab))
    rng = np.random.default_rng(0)
    pos = pd.Series(np.arange(len(lab)), index=lab.passage_id)
    folds = dsl._fold_ids(lab.author_key, 5, 0)
    ests = {"raw": [], "calib": []}
    for _ in range(150):
        aud, fr = draw_audit(sel, set(), rng, n_target=240)
        pi = fr.set_index("passage_id").pi_audit.loc[lab.passage_id].values
        R = np.zeros(len(lab), bool)
        R[pos.loc[aud.passage_id].values] = True
        for g in ests:
            Yt = dsl.pseudo_outcomes(yhat, y, R, pi, 4, method=g, folds=folds)
            ests[g].append(Yt[early, 1].sum() / Yt[early, 1:].sum())
    for g, v in ests.items():
        v = np.array(v)
        # ratio estimator: allow small O(1/n) bias, but far less than the naive bias
        assert abs(v.mean() - truth) < 0.25 * abs(naive - truth), g


def test_two_phase_pseudo_outcomes_unbiased():
    rng = np.random.default_rng(0)
    n, K = 4000, 3
    y = rng.integers(0, K, n)
    yhat = np.where(rng.random(n) < 0.7, y, rng.integers(0, K, n))
    y3 = np.where(rng.random(n) < 0.9, y, rng.integers(0, K, n))
    est = []
    for _ in range(400):
        pi3 = np.full(n, 0.2)
        R3 = rng.random(n) < pi3
        pih = np.full(n, 0.25)
        Rh = rng.random(n) < pih
        est.append(dsl.pseudo_outcomes_two_phase(yhat, y3, y, R3, pi3, Rh, pih, K).mean(0))
    assert np.allclose(np.mean(est, 0), dsl.onehot(y, K).mean(0), atol=0.01)


def test_audit_design_detects_relabel(corpus):
    lab = corpus.labels[corpus.labels.split == "confirmation"].reset_index(drop=True).copy()
    lab["has_obstacle"] = np.where(np.random.default_rng(0).random(len(lab)) < 0.3, "no", lab.has_obstacle)
    with pytest.raises(ValueError):
        dsl.audit_design(lab, corpus.human, None, corpus.teaching_authors)


def test_ratio_shares_contrast_and_prepare_info(dsl_wd):
    assert dsl_wd.info["n_dropped_pi0"] == 0 and dsl_wd.info["n_labelled"] > 100
    era = np.where(dsl_wd.cov.year < 1850, "a", "b")
    r = dsl.ratio_shares(dsl_wd, "locus", [1, 2, 3], [1, 2, 3], era)
    assert np.allclose(r.est.sum(1), 1)
    d, s = r.contrast("a", "b", 1)
    assert s > 0 and np.isfinite(d)
