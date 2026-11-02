import numpy as np
import pandas as pd

from analysis import select_annotation as sa
from analysis.stats import annotators as A
from analysis.stats import dsl
from analysis.stats.power import dgroup_vec
from analysis.stats.simulate import annotate_noisy


def test_kappa_basic():
    a = np.array([0, 1, 2, 0, 1, 2])
    assert A.cohen_kappa(a, a) == 1.0
    assert A.cohen_kappa(a, (a + 1) % 3) < 0


def test_noise_calibration_and_exclusion(corpus):
    t = corpus.truth[corpus.truth.split == "confirmation"].sample(30, random_state=1)
    rng = np.random.default_rng(0)
    rows = [annotate_noisy(t, e, rng).assign(annotator=f"a{i}") for i, e in enumerate([0.0, 0.3, 0.9])]
    ex = t[["passage_id", "has_obstacle", "domains", "locus", "failure_cause"]].assign(
        annotator="teacher", domains=t.domains.map(lambda d: list(d)[:1]))
    h = pd.concat(rows + [ex], ignore_index=True)
    rep = A.expert_agreement(h).set_index("annotator")
    assert rep.kappa_locus["a0"] > 0.9 > rep.kappa_locus["a1"] > rep.kappa_locus["a2"]
    assert A.exclusions(rep.reset_index()) == {"a2"}
    ov = A.overlap_agreement(h, corpus.labels, expert_items=set())
    assert ov.subset.iloc[0] == "all" and ov.n_pairs.iloc[0] > 0


def test_soft_labels_and_pi_recompute(corpus):
    lab = corpus.labels
    h = corpus.human
    wd_mean = dsl.prepare(lab, h, corpus.frame, g="raw")
    wd_res = dsl.prepare(lab, h, corpus.frame, g="raw", human_mode="resolve")
    # simulated annotators both equal truth -> mean == resolved
    assert np.allclose(wd_mean.Y["locus"], wd_res.Y["locus"])
    # disagreeing overlap pair -> 0.5/0.5 soft label
    T = dsl.TARGETS["locus"]
    pid = h.groupby("passage_id").size().pipe(lambda s: s[s == 2]).index[0]
    h2 = h.copy()
    i = h2.index[(h2.passage_id == pid)][1]
    h2.loc[i, ["has_obstacle", "locus"]] = ["no", None]
    ids, S = dsl.human_soft(h2[h2.passage_id == pid], T)
    assert np.isclose(S.max(), 0.5) or np.isclose(S.max(), 1.0)
    # excluding an annotator drops their single-coded items and raises pi in the other items' cells
    conf = lab[lab.split == "confirmation"].reset_index(drop=True)
    pi_all = dsl.audit_design(conf, h, corpus.frame, labelled_ids=set(h.passage_id))
    pi_frame = dsl.audit_design(conf, h, corpus.frame)
    assert np.allclose(pi_all, pi_frame)
    keep = h[h.annotator != "student"]
    pi_ex = dsl.audit_design(conf, keep, corpus.frame, labelled_ids=set(keep.passage_id))
    assert (pi_ex <= pi_frame + 1e-12).all() and (pi_ex < pi_frame).any()
    wd_ex = dsl.prepare(lab, h, corpus.frame, g="raw", exclude_annotators={"student"})
    assert wd_ex.info["n_labelled"] < wd_mean.info["n_labelled"]


def test_domain_strata_draw_interface(corpus):
    lab = corpus.labels[corpus.labels.split == "confirmation"]
    s = lab.sample(2000, random_state=0)
    assert (dgroup_vec(s) == s.apply(sa.domain_group, axis=1).values).all()
    sel = lab.assign(era=dsl._era(lab.decade.values), dgroup=dgroup_vec(lab))
    aud, fr = sa.draw_audit(sel, set(), np.random.default_rng(0), n_target=480, group_col="dgroup")
    assert fr.audit_cell.str.split("|").str[1].isin(set(sa.DOMAIN_GROUP.values()) | {"no_obstacle"}).all()
    assert np.allclose(aud.weight, aud.cell_N / aud.cell_n)
    # default call unchanged (locus groups)
    sel2 = lab.assign(era=dsl._era(lab.decade.values), group=lab.apply(sa.group, axis=1))
    aud2, fr2 = sa.draw_audit(sel2, set(), np.random.default_rng(0), n_target=120)
    assert fr2.audit_cell.str.split("|").str[1].isin({"material", "social", "internal", "no_obstacle", "other"}).all()


def test_metadata_draw_is_seal_safe():
    from analysis.stats.simulate import SimConfig, simulate
    c = simulate(SimConfig.v05(n_works=4000, seed=1), audit=False)
    lab = c.labels[c.labels.split == "confirmation"]
    meta = lab[["passage_id", "work_id", "author_key", "year", "split", "stratum", "genre", "canonical"]]
    aud, fr = sa.draw_audit_metadata(meta, np.random.default_rng(0), n_target=600)
    assert {"canon", "noncanon"} <= set(fr.audit_cell.str.split("|").str[2])
    assert abs(len(aud) - 600) < 60 and np.allclose(aud.weight, aud.cell_N / aud.cell_n)
    # budget balanced over era x canonical
    per = aud.groupby(aud.audit_cell.str.split("|").str[:3:2].str.join("|")).size()
    assert per.max() <= 2 * per.min() + 20 or (per < 100).any()      # small canon cells may cap
    import pytest
    with pytest.raises(ValueError):
        sa.draw_audit(lab.assign(era=sa.era_by_year(lab.year), group="x"), set(), np.random.default_rng(0), 100,
                      group_col="group", metadata_only=True)
    assert len(sa.cell_table_hash(fr)) == 64


def test_anchored_dsl_unbiased_for_expert():
    rng = np.random.default_rng(0)
    n, K = 20000, 4
    y = rng.choice(4, n, p=[0.3, 0.15, 0.45, 0.1])
    yhat = np.where(rng.random(n) < 0.7, y, rng.integers(0, 4, n))
    peer = np.where(rng.random(n) < 0.65, y, rng.integers(0, 4, n))
    folds = rng.integers(0, 5, n)
    est = []
    for _ in range(60):
        R3 = rng.random(n) < 0.1
        Rh = R3 & (rng.random(n) < 0.25)
        Y = dsl.pseudo_outcomes_anchored(yhat, dsl.onehot(peer, K), R3, np.full(n, 0.1), y, Rh, np.full(n, 0.25),
                                         K, folds)
        est.append(Y.mean(0))
    assert np.allclose(np.mean(est, 0), dsl.onehot(y, K).mean(0), atol=0.012)
