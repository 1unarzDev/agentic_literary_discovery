import numpy as np
import pandas as pd

from analysis import select_annotation as sa
from analysis.stats import dsl
from analysis.stats.simulate import LLMNoise, SimConfig, group_vec, keyword_series, simulate


def test_schema(corpus):
    need = {"passage_id", "work_id", "author_key", "decade", "year", "genre", "origin", "split", "stratum",
            "inclusion_prob", "has_obstacle", "domains", "locus", "failure_cause", "night_function",
            "technology_named", "message_valence", "confidence", "quote_status"}
    assert need <= set(corpus.labels.columns)
    assert {"passage_id", "annotator", "has_obstacle", "domains", "locus", "failure_cause", "audit_cell",
            "weight"} <= set(corpus.human.columns)
    assert corpus.labels.genre.nunique() <= 8
    assert set(corpus.labels.origin) <= {"UK", "US", "unknown"}
    assert corpus.labels.groupby("work_id").size().eq(12).all()


def test_group_and_era_match_select_annotation(corpus):
    s = corpus.labels.sample(3000, random_state=0)
    assert (group_vec(s) == s.apply(sa.group, axis=1).values).all()
    assert (dsl._era(s.decade.values) == s.decade.map(sa.era).values).all()


def test_audit_is_select_annotation_probability_sample(corpus):
    h, fr = corpus.human, corpus.frame
    hu = dsl.resolve_human(h)
    # 40 double-coded items, the rest single-coded
    assert (h.groupby("passage_id").size() == 2).sum() == 40
    # weight = N_cell / n_cell = 1 / pi_audit, and frame covers the whole random, non-teaching pool
    m = hu.merge(fr, on="passage_id")
    assert np.allclose(m.weight * m.pi_audit, 1)
    lab = corpus.labels
    pool = lab[(lab.stratum == "random") & ~lab.author_key.isin(corpus.teaching_authors)]
    assert len(fr) == len(pool)
    # equal allocation over era x group x split cells: n_cell = min(per, N_cell)
    n = hu.groupby("audit_cell").size()
    N = fr.groupby("audit_cell").size()
    per = n.max()
    assert (n == np.minimum(per, N[n.index])).all()
    # teaching authors are Discovery and never audited
    audited = lab.set_index("passage_id").loc[hu.passage_id]
    assert not audited.author_key.isin(corpus.teaching_authors).any()
    # fallback re-derivation of pi agrees with the frame
    sub = lab[lab.split == "confirmation"].reset_index(drop=True)
    a = dsl.audit_design(sub, h, fr)
    b = dsl.audit_design(sub, h, None, corpus.teaching_authors)
    assert np.allclose(a, b)


def test_naive_labels_are_biased_by_era(corpus):
    wd_n = dsl.prepare(corpus.labels, method="naive")
    wd_o = dsl.prepare(corpus.labels, method="oracle", truth=corpus.truth)
    era = np.where(wd_o.cov.year < 1850, "early", "late")
    rn = dsl.ratio_shares(wd_n, "locus", [1], [1, 2, 3], era)
    ro = dsl.ratio_shares(wd_o, "locus", [1], [1, 2, 3], era)
    bias = rn.est[:, 0] - ro.est[:, 0]
    assert bias[0] > 0.05          # early era: errors pushed to material
    assert bias[1] < bias[0]


def test_perfect_noise_and_null_drift():
    c = simulate(SimConfig(n_works=1500, passages_per_work=8, noise=LLMNoise.perfect(), effect=0, genre_drift=0,
                           genre_effects=0, seed=5), audit=False)
    t = c.truth.set_index("passage_id").loc[c.labels.passage_id]
    assert (t.has_obstacle.values == c.labels.has_obstacle.values).all()
    assert t.locus.reset_index(drop=True).equals(c.labels.locus.reset_index(drop=True))


def test_enrichment_strata_and_probs():
    c = simulate(SimConfig(n_works=400, enrichment=True, seed=2), audit=False)
    s = c.labels.stratum.value_counts()
    assert {"random", "enrich_comm", "enrich_mob", "enrich_dark"} <= set(s.index)
    assert c.labels.inclusion_prob.between(0, 1).all()
    assert c.labels.passage_id.is_unique
    e = c.labels[c.labels.stratum == "enrich_comm"]
    has = e.domains.map(lambda d: "COMMUNICATION_INFORMATION" in d) & (e.has_obstacle == "yes")
    r = c.labels[c.labels.stratum == "random"]
    hr = r.domains.map(lambda d: "COMMUNICATION_INFORMATION" in d) & (r.has_obstacle == "yes")
    assert has.mean() > hr.mean()


def test_keyword_series(corpus):
    kw = keyword_series(corpus)
    assert set(kw.group) == {"comm", "travel", "dark"}
    assert kw.groupby("group").kw_rate.apply(lambda s: s.iloc[-1] > s.iloc[0]).all()


def test_pilot_step_calibration():
    """Pilot-like truth: material share +~8 pp M -> L (step in the 1880s), internal flat."""
    c = simulate(SimConfig.pilot_step(n_works=24000, passages_per_work=4, seed=3), audit=False)
    wd = dsl.prepare(c.labels, method="oracle", truth=c.truth, split=None, targets=("locus",))
    era = np.where(wd.cov.year < 1850, "E", np.where(wd.cov.year < 1885, "M", "L"))
    r = dsl.ratio_shares(wd, "locus", [1, 3], [1, 2, 3], era)
    d_mat, se = r.contrast("M", "L", 1)
    d_int, _ = r.contrast("M", "L", 3)
    assert 0.05 < d_mat < 0.11 and abs(d_int) < 0.03
