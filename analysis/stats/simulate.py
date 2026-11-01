"""Synthetic corpora with known parameters, for validating DSL / models / battery / power.

The generator mirrors the real pipeline's data structures:
  authors -> works (decade, genre <= 8, origin UK/US/unknown, n_words, date_confidence, memorization)
  -> 24 random passages per work (stratum "random", inclusion_prob = m / N_w)
  -> optional enrichment strata (enrich_comm / enrich_mob / enrich_dark; lexicon hits, <= 8 per work,
     union-of-frames inclusion probability recorded)
True labels drift with year (obstacle prevalence, domain mix -> locus shares, communication failure
cause, night function); genre mix drifts with year (the main confounder); author and work random
effects sit on every logit (ICC configurable). LLM labels are produced from the truth through an
era-specific confusion process. The human audit is drawn with analysis/select_annotation.draw_audit,
i.e. exactly as the real script draws it (equal allocation per era x predicted-group x split cell).

usage: uv run python -m analysis.stats.simulate OUT_DIR [--works 12000] [--seed 1]
       writes labels.parquet, human.parquet, audit_frame.parquet, truth.parquet, works.parquet
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
import pandas as pd

from analysis.select_annotation import ANNOTATORS, draw_audit
from analysis.select_annotation import era as sel_era

DOMAINS = ["DISTANCE_TRAVEL", "COMMUNICATION_INFORMATION", "DARKNESS_VISIBILITY", "ILLNESS_BODY_DEATH",
           "MONEY_PROPERTY_LAW", "SOCIAL_RANK_CONVENTION", "INTERPERSONAL_CONFLICT", "INNER_STATE",
           "NATURE_WEATHER", "OTHER"]
D = {d: i for i, d in enumerate(DOMAINS)}
GENRES = ["domestic", "gothic", "adventure", "detective", "sensation", "didactic", "juvenile", "collection"]
ORIGINS = ["UK", "US", "unknown"]
CAUSES = ["infrastructure", "accidental_loss", "intentional_withholding", "misinterpretation", "success_resolution"]
NIGHT = ["danger", "concealment", "intimacy", "labor", "leisure"]
LOCI = ["material_external", "social_institutional", "internal_psychological"]
ERAS3 = ["early_1800_1849", "mid_1850_1884", "late_1885_1920"]   # select_annotation names; late = decade >= 1885
DECADES = list(range(1800, 1930, 10))
# G0 (docs/gates.md): Confirmation-half works per decade 1800s..1920s
DECADE_PROFILE = [10, 13, 34, 62, 83, 204, 277, 365, 473, 1036, 1612, 2006, 1166]

# default locus of each primary domain (codebook table); COMMUNICATION depends on failure cause
DOMAIN_LOCUS = {"DISTANCE_TRAVEL": 0, "DARKNESS_VISIBILITY": 0, "NATURE_WEATHER": 0, "ILLNESS_BODY_DEATH": 0,
                "MONEY_PROPERTY_LAW": 1, "SOCIAL_RANK_CONVENTION": 1, "INTERPERSONAL_CONFLICT": 1,
                "INNER_STATE": 2, "OTHER": 1}
CAUSE_LOCUS = {"infrastructure": 0, "accidental_loss": 0, "intentional_withholding": 1,
               "misinterpretation": 1, "success_resolution": 0}


def _vec(d: dict, keys: list[str]) -> np.ndarray:
    return np.array([d.get(k, 0.0) for k in keys], dtype=float)


@dataclass
class LLMNoise:
    """Era-specific confusion process (era = select_annotation.era of the decade)."""
    sens: tuple = (0.80, 0.85, 0.90)          # P(pred obstacle | true obstacle)
    spec: tuple = (0.85, 0.88, 0.90)          # P(pred no obstacle | true none)
    dom_acc: tuple = (0.65, 0.72, 0.80)       # P(pred primary domain correct | both obstacle)
    cause_acc: tuple = (0.60, 0.68, 0.75)
    night_acc: tuple = (0.70, 0.72, 0.75)
    night_fp: float = 0.05                    # P(pred night function | not a night passage)
    locus_follow: float = 0.9                 # P(model follows a codebook locus override it saw)
    d2_keep: float = 0.5                      # P(model reports the true secondary domain)
    # where domain errors go, per era: early errors skew material, late errors skew inward/social,
    # i.e. naive labels exaggerate the hypothesised inward turn
    err_dom: tuple = (
        {"DISTANCE_TRAVEL": 3, "DARKNESS_VISIBILITY": 2, "NATURE_WEATHER": 2, "ILLNESS_BODY_DEATH": 1,
         "SOCIAL_RANK_CONVENTION": 1, "INTERPERSONAL_CONFLICT": 1, "INNER_STATE": 0.5, "COMMUNICATION_INFORMATION": 1},
        {d: 1.0 for d in DOMAINS[:9]},
        {"INNER_STATE": 4, "SOCIAL_RANK_CONVENTION": 2, "INTERPERSONAL_CONFLICT": 1, "COMMUNICATION_INFORMATION": 1,
         "DISTANCE_TRAVEL": 0.5, "DARKNESS_VISIBILITY": 0.5, "NATURE_WEATHER": 0.5, "ILLNESS_BODY_DEATH": 0.5},
    )
    err_cause: tuple = ({"infrastructure": 3, "accidental_loss": 2, "intentional_withholding": 1, "misinterpretation": 1},
                        {c: 1.0 for c in CAUSES[:4]},
                        {"intentional_withholding": 3, "misinterpretation": 1, "infrastructure": 1, "accidental_loss": 1})

    @staticmethod
    def perfect() -> "LLMNoise":
        return LLMNoise(sens=(1, 1, 1), spec=(1, 1, 1), dom_acc=(1, 1, 1), cause_acc=(1, 1, 1), night_acc=(1, 1, 1),
                        night_fp=0.0, locus_follow=1.0, d2_keep=1.0)


@dataclass
class SimConfig:
    n_works: int = 15500                  # both splits together (G0: 15,511 works)
    works_per_author: float = 3.7         # mean of 1 + NegBin (G0 Confirmation: 3.7, median 1)
    wpa_size: float = 0.35                # NegBin size (heavy tail: a few prolific authors)
    wpa_max: int = 60
    passages_per_work: int = 24
    prevalence: float = 0.45              # P(has_obstacle) at 1860, reference genre
    icc_author: float = 0.05              # latent-scale ICC from author RE (each logit)
    icc_work: float = 0.02                # latent-scale ICC from work RE
    effect: float = 1.0                   # scales all true within-genre year drifts (0 => within-genre null)
    genre_drift: float = 1.0              # scales genre-mix drift (0 => constant mix)
    genre_effects: float = 1.0            # scales genre differences in obstacle mix
    noise: LLMNoise = field(default_factory=LLMNoise)
    human_error: float = 0.0              # P(annotator gives a random locus/domain) per passage
    enrichment: bool = False
    audit_n: int = 200                    # n_target passed to draw_audit
    n_teaching_authors: int = 60          # Discovery authors excluded from the audit pool
    decade_profile: tuple = tuple(DECADE_PROFILE)
    # true obstacle-mix parameters (logit scale, slope per 60 years, centred at 1860)
    dom_base: dict = field(default_factory=lambda: {
        "DISTANCE_TRAVEL": 0.0, "COMMUNICATION_INFORMATION": 0.3, "DARKNESS_VISIBILITY": -0.5,
        "ILLNESS_BODY_DEATH": 0.0, "MONEY_PROPERTY_LAW": 0.0, "SOCIAL_RANK_CONVENTION": 0.2,
        "INTERPERSONAL_CONFLICT": 0.4, "INNER_STATE": 0.0, "NATURE_WEATHER": -0.4, "OTHER": -1.5})
    dom_slope: dict = field(default_factory=lambda: {
        "DISTANCE_TRAVEL": -0.5, "DARKNESS_VISIBILITY": -0.4, "ILLNESS_BODY_DEATH": -0.2,
        "SOCIAL_RANK_CONVENTION": 0.1, "INNER_STATE": 0.6, "NATURE_WEATHER": -0.3})
    cause_base: tuple = (0.3, 0.0, 0.2, 0.0, -0.5)
    cause_slope: tuple = (-0.6, -0.2, 0.5, 0.0, 0.3)
    night_base: tuple = (0.6, 0.3, 0.0, -0.5, -0.6)
    night_slope: tuple = (-0.4, -0.2, 0.3, 0.0, 0.5)
    seed: int = 1

    def with_(self, **kw) -> "SimConfig":
        return replace(self, **kw)


GENRE_DOM = {
    "domestic": {"SOCIAL_RANK_CONVENTION": 0.6, "INNER_STATE": 0.4, "MONEY_PROPERTY_LAW": 0.3, "DISTANCE_TRAVEL": -0.3},
    "gothic": {"DARKNESS_VISIBILITY": 1.0, "INTERPERSONAL_CONFLICT": 0.5, "NATURE_WEATHER": 0.3, "INNER_STATE": -0.3},
    "adventure": {"DISTANCE_TRAVEL": 0.8, "NATURE_WEATHER": 0.8, "INTERPERSONAL_CONFLICT": 0.3, "INNER_STATE": -0.4},
    "detective": {"COMMUNICATION_INFORMATION": 0.9, "INTERPERSONAL_CONFLICT": 0.6, "MONEY_PROPERTY_LAW": 0.2},
    "sensation": {"COMMUNICATION_INFORMATION": 0.5, "MONEY_PROPERTY_LAW": 0.5, "SOCIAL_RANK_CONVENTION": 0.3},
    "didactic": {"INNER_STATE": 0.5, "ILLNESS_BODY_DEATH": 0.4},
    "juvenile": {"NATURE_WEATHER": 0.3, "INTERPERSONAL_CONFLICT": 0.2},
    "collection": {},
}
GENRE_OBS = {"adventure": 0.3, "detective": 0.3, "didactic": -0.3, "collection": -0.1}
GENRE_DARKNIGHT = {"gothic": 0.15, "detective": 0.05}


def genre_logits(t: np.ndarray, drift: float) -> np.ndarray:
    """Genre-mix logits by (centred) year: gothic falls, detective rises late, sensation peaks mid."""
    base = np.array([0.8, 0.3, 0.0, -1.5, -0.5, 0.0, -0.5, -0.3])
    t = t[:, None]
    slope = np.array([0.0, -1.5, 0.3, 1.8, 0.0, -0.8, 0.5, 0.6])
    quad = np.array([0, 0, 0, 0, -1.0, 0, 0, 0])
    return base + drift * (slope * t + quad * t ** 2)


def _draw(rng: np.random.Generator, p: np.ndarray) -> np.ndarray:
    """Vectorised categorical draw from rows of p (rows need not be normalised)."""
    c = np.cumsum(p, axis=1)
    u = rng.random(len(p)) * c[:, -1]
    return (c < u[:, None]).sum(axis=1).clip(0, p.shape[1] - 1)


def _softmax(eta: np.ndarray) -> np.ndarray:
    e = np.exp(eta - eta.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def _sd(icc_a: float, icc_w: float) -> tuple[float, float]:
    tot = np.pi ** 2 / 3
    resid = 1 - icc_a - icc_w
    return float(np.sqrt(icc_a * tot / resid)), float(np.sqrt(icc_w * tot / resid))


# ------------------------------------------------------------------ works

def make_works(cfg: SimConfig, rng: np.random.Generator) -> pd.DataFrame:
    n_auth = max(1, int(round(cfg.n_works / cfg.works_per_author)))
    prof = np.asarray(cfg.decade_profile, float)
    prof = prof / prof.sum()
    centre = rng.choice(DECADES, size=n_auth, p=prof) + rng.uniform(0, 10, n_auth)
    mu = cfg.works_per_author - 1
    nw = 1 + np.minimum(rng.negative_binomial(cfg.wpa_size, cfg.wpa_size / (cfg.wpa_size + mu), n_auth), cfg.wpa_max - 1)
    # trim/pad to n_works exactly
    a_idx = np.repeat(np.arange(n_auth), nw)
    if len(a_idx) >= cfg.n_works:
        a_idx = np.sort(rng.choice(a_idx, cfg.n_works, replace=False))
    else:
        a_idx = np.sort(np.concatenate([a_idx, rng.integers(0, n_auth, cfg.n_works - len(a_idx))]))
    n = len(a_idx)
    year = np.clip(np.round(centre[a_idx] + rng.normal(0, 6, n)), 1800, 1929).astype(int)
    t = (year - 1860) / 60
    gl = genre_logits(t, cfg.genre_drift)
    # authors have a home genre (drawn at their career centre); works follow it with prob 0.7
    home = _draw(rng, _softmax(genre_logits((centre - 1860) / 60, cfg.genre_drift)))
    g = np.where(rng.random(n) < 0.7, home[a_idx], _draw(rng, _softmax(gl)))
    tc = (centre - 1860) / 60
    p_us = np.clip(0.18 + 0.15 * tc, 0.05, 0.6)
    ao = _draw(rng, np.c_[0.9 - p_us, p_us, np.full(n_auth, 0.1)])
    split = np.where(rng.random(n_auth) < 0.5, "discovery", "confirmation")
    n_words = np.exp(rng.normal(np.log(95_000), 0.5, n)).clip(15_000, 600_000).astype(int)
    dc = _draw(rng, np.tile([0.47, 0.27, 0.26], (n, 1)))     # G0 shares high/medium/low
    canon = rng.random(n_auth) < 0.1
    memo = np.clip(rng.beta(1.2, 8, n) + 0.4 * canon[a_idx] * rng.random(n), 0, 1)
    return pd.DataFrame({
        "work_id": [f"w{i:06d}" for i in range(n)],
        "author_key": [f"a{j:05d}" for j in a_idx],
        "author_idx": a_idx,
        "year": year, "decade": year // 10 * 10,
        "genre": np.array(GENRES)[g], "genre_idx": g,
        "origin": np.array(ORIGINS)[ao[a_idx]],
        "split": split[a_idx],
        "n_words": n_words,
        "date_confidence": np.array(["high", "medium", "low"])[dc],
        "memorization": memo,
        "setting_period": "contemporary",
    })


# ------------------------------------------------------------------ truth

def _truth(cfg: SimConfig, rng: np.random.Generator, wk: pd.DataFrame, w_of_p: np.ndarray,
           boost: np.ndarray | None = None) -> dict[str, np.ndarray]:
    """True labels for passages whose work index is w_of_p. boost: (n, 10) extra domain logits."""
    n = len(w_of_p)
    sa, sw = _sd(cfg.icc_author, cfg.icc_work)
    n_auth = wk.author_idx.max() + 1
    ndim = 1 + 10 + 5 + 5  # obstacle, domains, causes, night functions
    ua = rng.normal(0, sa, (n_auth, ndim))
    uw = rng.normal(0, sw, (len(wk), ndim))
    re = ua[wk.author_idx.values] + uw              # (n_works, ndim)
    re = re[w_of_p]
    t = ((wk.year.values - 1860) / 60)[w_of_p]
    gi = wk.genre_idx.values[w_of_p]
    ge = cfg.genre_effects
    g_obs = _vec(GENRE_OBS, GENRES)[gi] * ge
    p_obs = 1 / (1 + np.exp(-(np.log(cfg.prevalence / (1 - cfg.prevalence)) + g_obs + re[:, 0])))
    u = rng.random(n)
    has = np.where(u < p_obs, 1, np.where(u < p_obs + 0.03 * (1 - p_obs), 2, 0))  # 1 yes, 0 no, 2 insufficient
    gdom = np.array([_vec(GENRE_DOM[g], DOMAINS) for g in GENRES])[gi] * ge
    eta = _vec(cfg.dom_base, DOMAINS) + cfg.effect * np.outer(t, _vec(cfg.dom_slope, DOMAINS)) + gdom + re[:, 1:11]
    if boost is not None:
        eta = eta + boost
    p = _softmax(eta)
    d1 = _draw(rng, p)
    p2 = p.copy()
    p2[np.arange(n), d1] = 0
    d2 = np.where(rng.random(n) < 0.3, _draw(rng, p2), -1)
    ceta = np.asarray(cfg.cause_base) + cfg.effect * np.outer(t, cfg.cause_slope) + re[:, 11:16]
    cause = _draw(rng, _softmax(ceta))
    comm = (d1 == D["COMMUNICATION_INFORMATION"]) | (d2 == D["COMMUNICATION_INFORMATION"])
    dark = (d1 == D["DARKNESS_VISIBILITY"]) | (d2 == D["DARKNESS_VISIBILITY"])
    p_night = 0.12 + 0.5 * (dark & (has == 1)) + _vec(GENRE_DARKNIGHT, GENRES)[gi]
    night = rng.random(n) < p_night
    neta = np.asarray(cfg.night_base) + cfg.effect * np.outer(t, cfg.night_slope) + re[:, 16:21]
    nf = _draw(rng, _softmax(neta))
    locus = _locus(d1, cause)
    override = rng.random(n) < 0.03
    locus = np.where(override, rng.integers(0, 3, n), locus)
    obs = has == 1
    return {"has": has, "d1": np.where(obs, d1, -1), "d2": np.where(obs, d2, -1),
            "cause": np.where(obs & comm, cause, -1), "locus": np.where(obs, locus, -1),
            "night": np.where(night, nf, -1)}


def _locus(d1: np.ndarray, cause: np.ndarray) -> np.ndarray:
    """Codebook default mapping: domain -> locus; COMMUNICATION -> by failure cause."""
    dl = np.array([DOMAIN_LOCUS.get(d, 1) for d in DOMAINS])
    cl = np.array([CAUSE_LOCUS[c] for c in CAUSES])
    is_comm = d1 == D["COMMUNICATION_INFORMATION"]
    return np.where(is_comm, cl[np.clip(cause, 0, 4)], dl[np.clip(d1, 0, 9)])


# ------------------------------------------------------------------ LLM labels

def _llm(cfg: SimConfig, rng: np.random.Generator, tr: dict, era_i: np.ndarray) -> dict[str, np.ndarray]:
    nz = cfg.noise
    n = len(era_i)
    sens, spec = np.asarray(nz.sens)[era_i], np.asarray(nz.spec)[era_i]
    true_obs = tr["has"] == 1
    u = rng.random(n)
    pred_obs = np.where(true_obs, u < sens, u > spec)
    # insufficient_context: kept when true (w.p. spec), spuriously given for 30% of specificity errors
    ins = np.where(tr["has"] == 2, rng.random(n) < spec, rng.random(n) < 0.3 * (1 - spec))
    has = np.where(pred_obs, 1, np.where(ins, 2, 0))
    err_dom = np.array([_vec(e, DOMAINS) for e in nz.err_dom])[era_i]
    rnd_dom = _draw(rng, err_dom)
    keep = true_obs & (rng.random(n) < np.asarray(nz.dom_acc)[era_i])
    d1 = np.where(pred_obs, np.where(keep, tr["d1"], rnd_dom), -1)
    d2 = np.where(pred_obs & (tr["d2"] >= 0) & (rng.random(n) < nz.d2_keep) & (tr["d2"] != d1), tr["d2"], -1)
    comm = (d1 == D["COMMUNICATION_INFORMATION"]) | (d2 == D["COMMUNICATION_INFORMATION"])
    err_c = np.array([_vec(e, CAUSES) for e in nz.err_cause])[era_i]
    rnd_c = _draw(rng, err_c)
    keep_c = (tr["cause"] >= 0) & (rng.random(n) < np.asarray(nz.cause_acc)[era_i])
    cause = np.where(comm, np.where(keep_c, tr["cause"], rnd_c), -1)
    locus = _locus(d1, cause)
    same = (d1 == tr["d1"]) & (cause == tr["cause"]) & (rng.random(n) < nz.locus_follow)
    locus = np.where(pred_obs, np.where(same & (tr["locus"] >= 0), tr["locus"], locus), -1)
    tn = tr["night"] >= 0
    rnd_n = rng.integers(0, 5, n)
    keep_n = rng.random(n) < np.asarray(nz.night_acc)[era_i]
    night = np.where(tn, np.where(keep_n, tr["night"], rnd_n), np.where(rng.random(n) < nz.night_fp, rnd_n, -1))
    correct = (pred_obs == true_obs) & ((d1 == tr["d1"]) | ~pred_obs)
    conf = np.where(correct, rng.beta(8, 2, n), rng.beta(4, 3, n))
    return {"has": has, "d1": d1, "d2": d2, "cause": cause, "locus": locus, "night": night, "confidence": conf}


def _human(cfg: SimConfig, rng: np.random.Generator, tr: dict) -> dict:
    if cfg.human_error <= 0:
        return tr
    h = {k: v.copy() for k, v in tr.items()}
    n = len(h["has"])
    flip = (rng.random(n) < cfg.human_error) & (h["has"] == 1)
    h["locus"] = np.where(flip, rng.integers(0, 3, n), h["locus"])
    h["d1"] = np.where(flip, rng.integers(0, 9, n), h["d1"])
    return h


# ------------------------------------------------------------------ tables

HAS = np.array(["no", "yes", "insufficient_context"])


def _fields_to_frame(f: dict) -> dict:
    d1, d2 = f["d1"], f["d2"]
    doms = [([DOMAINS[a]] if a >= 0 else []) + ([DOMAINS[b]] if b >= 0 else []) for a, b in zip(d1.tolist(), d2.tolist())]
    loc = np.array(LOCI + [None], dtype=object)[np.where(f["locus"] >= 0, f["locus"], 3)]
    cause = np.array(CAUSES + ["none"], dtype=object)[np.where(f["cause"] >= 0, f["cause"], 5)]
    out = {"has_obstacle": HAS[f["has"]], "domains": doms, "locus": loc, "failure_cause": cause}
    if "night" in f:
        out["night_function"] = np.array(NIGHT + ["none"], dtype=object)[np.where(f["night"] >= 0, f["night"], 5)]
    return out


TECH = {"DISTANCE_TRAVEL": (["coach", "horse", "foot"], ["railway", "steamship", "carriage"]),
        "COMMUNICATION_INFORMATION": (["letter", "note", "messenger"], ["telegram", "letter", "telephone"]),
        "DARKNESS_VISIBILITY": (["candle", "lamp"], ["gas", "electric", "lamp"])}


def _tech(rng: np.random.Generator, d1: np.ndarray, year: np.ndarray) -> np.ndarray:
    out = np.full(len(d1), "none", dtype=object)
    for dom, (old, new) in TECH.items():
        m = d1 == D[dom]
        late = rng.random(m.sum()) < np.clip((year[m] - 1830) / 80, 0, 0.9)
        named = rng.random(m.sum()) < 0.5
        pick = np.where(late, rng.choice(new, m.sum()), rng.choice(old, m.sum()))
        out[np.where(m)[0]] = np.where(named, pick, "none")
    return out


@dataclass
class Corpus:
    labels: pd.DataFrame
    human: pd.DataFrame
    frame: pd.DataFrame          # audit frame: passage_id, audit_cell, pi_audit
    truth: pd.DataFrame          # passage_id + true fields (schema of human labels, plus night_function)
    works: pd.DataFrame
    cfg: SimConfig
    teaching_authors: set


def simulate(cfg: SimConfig | None = None, audit: bool = True) -> Corpus:
    cfg = cfg or SimConfig()
    rng = np.random.default_rng(cfg.seed)
    wk = make_works(cfg, rng)
    m = cfg.passages_per_work
    nW = len(wk)
    w_of_p = np.repeat(np.arange(nW), m)
    n_pass_work = np.maximum(m, wk.n_words.values // 350)
    j = np.tile(np.arange(m), nW)
    stratum = np.full(len(w_of_p), "random", dtype=object)
    incl = (m / n_pass_work)[w_of_p]
    boost = None
    if cfg.enrichment:
        w_of_p, stratum, incl, boost, j = _enrichment(cfg, rng, wk, n_pass_work, w_of_p, stratum, incl, j)
    tr = _truth(cfg, rng, wk, w_of_p, boost)
    year = wk.year.values[w_of_p]
    era_i = np.searchsorted([1850, 1885], year // 10 * 10, side="right")
    ll = _llm(cfg, rng, tr, era_i)
    hu = _human(cfg, rng, tr)

    pid = np.char.add(np.char.add(wk.work_id.values[w_of_p].astype(str), "_p"), j.astype(str))
    base = wk.iloc[w_of_p][["work_id", "author_key", "decade", "year", "genre", "origin", "split",
                            "n_words", "date_confidence", "memorization", "setting_period"]].reset_index(drop=True)
    base.insert(0, "passage_id", pid)
    base["stratum"] = stratum
    base["inclusion_prob"] = incl
    lab = base.assign(**_fields_to_frame(ll))
    lab["technology_named"] = _tech(rng, ll["d1"], year)
    lab["message_valence"] = np.where(lab.failure_cause != "none",
                                      rng.choice(["catastrophic", "romantic", "financial", "practical"], len(lab)), "none")
    lab["confidence"] = ll["confidence"]
    lab["quote_status"] = np.where(rng.random(len(lab)) < 0.97, "exact", "fuzzy")
    truth = base[["passage_id", "work_id", "year", "genre", "split", "stratum"]].assign(**_fields_to_frame(tr))
    corpus = Corpus(lab, pd.DataFrame(), pd.DataFrame(columns=["passage_id", "audit_cell", "pi_audit"]),
                    truth, wk, cfg, set())
    if audit:
        _audit(corpus, rng, hu)
    return corpus


def _enrichment(cfg, rng, wk, n_pass_work, w_of_p, stratum, incl, j):
    """Add lexicon-hit strata. Hits are a fraction of a work's passages; up to 8 hits are sampled per
    stratum; the union-of-frames inclusion probability 1-(1-m/N)(1-8/H) is recorded for hits.
    Random-backbone passages that are hits get the union probability too."""
    m = cfg.passages_per_work
    strata = [("enrich_comm", "COMMUNICATION_INFORMATION", 0.06), ("enrich_mob", "DISTANCE_TRAVEL", 0.04),
              ("enrich_dark", "DARKNESS_VISIBILITY", 0.04)]
    nW = len(wk)
    boost_rows, ws, ss, ps, js = [], [], [], [], []
    rb = np.zeros((len(w_of_p), 10))
    rand_incl = incl.copy()
    for s_name, dom, rate in strata:
        H = rng.binomial(n_pass_work, rate)
        k = np.minimum(8, H)
        pe = np.where(H > 0, k / np.maximum(H, 1), 0.0)
        # random-backbone passages that happen to be hits: Bernoulli(rate)
        hit = rng.random(len(w_of_p)) < rate
        rb[hit, D[dom]] += 1.5
        rand_incl = np.where(hit, 1 - (1 - rand_incl) * (1 - pe[w_of_p]), rand_incl)
        # enrichment-only draws: hits not already in the random sample (approx. k*(1 - m/N))
        k_new = rng.binomial(k, 1 - m / n_pass_work)
        wi = np.repeat(np.arange(nW), k_new)
        ws.append(wi)
        ss.append(np.full(len(wi), s_name, dtype=object))
        ps.append(1 - (1 - m / n_pass_work[wi]) * (1 - pe[wi]))
        b = np.zeros((len(wi), 10))
        b[:, D[dom]] = 1.5
        boost_rows.append(b)
        js.append(1000 * (1 + len(js)) + np.concatenate([np.arange(c) for c in k_new]) if len(wi) else np.array([], int))
    return (np.concatenate([w_of_p] + ws), np.concatenate([stratum] + ss), np.concatenate([rand_incl] + ps),
            np.vstack([rb] + boost_rows), np.concatenate([j] + js))


def _audit(c: Corpus, rng: np.random.Generator, hu: dict) -> None:
    lab = c.labels
    lab["era"] = _era_vec(lab.decade.values)
    lab["group"] = group_vec(lab)
    disc_auth = lab.loc[lab.split == "discovery", "author_key"].unique()
    k = min(c.cfg.n_teaching_authors, len(disc_auth))
    teach = set(rng.choice(disc_auth, k, replace=False)) if k else set()
    sel_rng = np.random.default_rng(rng.integers(1 << 31))
    audit, frame = draw_audit(lab, teach, sel_rng, n_target=c.cfg.audit_n)
    c.labels = lab = lab.drop(columns=["era", "group"])
    dbl = set(audit.passage_id.iloc[:40])
    rest = list(audit.passage_id.iloc[40:])
    pos = pd.Series(np.arange(len(lab)), index=lab.passage_id)
    idx = pos.loc[audit.passage_id].values
    hf = _fields_to_frame({k2: v[idx] for k2, v in hu.items()})
    rows = []
    rest_pos = {p: i for i, p in enumerate(rest)}
    for i, (pid, cell, w) in enumerate(zip(audit.passage_id, audit.audit_cell, audit.weight)):
        anns = ANNOTATORS if pid in dbl else [ANNOTATORS[rest_pos[pid] % 2]]
        for a in anns:
            rows.append({"passage_id": pid, "annotator": a, "has_obstacle": hf["has_obstacle"][i],
                         "domains": hf["domains"][i], "locus": hf["locus"][i], "failure_cause": hf["failure_cause"][i],
                         "night_function": hf["night_function"][i], "audit_cell": cell, "weight": w})
    c.human = pd.DataFrame(rows)
    c.frame = frame
    c.teaching_authors = teach


def _era_vec(decade: np.ndarray) -> np.ndarray:
    return np.array(ERAS3, dtype=object)[np.searchsorted([1850, 1885], decade, side="right")]


def group_vec(lab: pd.DataFrame) -> np.ndarray:
    """Vectorised select_annotation.group (tested for equality)."""
    g = lab.locus.map({"material_external": "material", "social_institutional": "social",
                       "internal_psychological": "internal"}).fillna("other").values
    return np.where(lab.has_obstacle.values != "yes", "no_obstacle", g)


def keyword_series(c: Corpus, track: bool = False, noise: float = 0.05, seed: int = 0) -> pd.DataFrame:
    """Decade keyword rates per 10k words for the H3 pairs (comm / travel / dark).

    track=False: technology words rise with diffusion (letters/telegrams, railway/carriage, lamp/gas)
                 while the obstacle functions fall -> H3 true.
    track=True:  keyword rate = affine function of the TRUE decade function rate + `noise` (relative)
                 -> H3 null (mention tracks function)."""
    rng = np.random.default_rng(seed)
    t = c.truth[c.truth.stratum == "random"].copy()
    t["decade"] = t.year // 10 * 10
    yes = t.has_obstacle == "yes"
    doms = t.domains.map(set)
    fn = {"comm": yes & doms.map(lambda s: "COMMUNICATION_INFORMATION" in s) & t.failure_cause.isin(["infrastructure", "accidental_loss"]),
          "travel": yes & doms.map(lambda s: "DISTANCE_TRAVEL" in s),
          "dark": yes & doms.map(lambda s: "DARKNESS_VISIBILITY" in s)}
    hinge = {"comm": 1850, "travel": 1845, "dark": 1840}
    rows = []
    for g, ind in fn.items():
        rate = ind.groupby(t.decade).mean()
        for dec, r in rate.items():
            if track:
                kw = 2 + 100 * r
            else:
                kw = 4 + 8 / (1 + np.exp(-(dec + 5 - hinge[g]) / 12))
            rows.append({"decade": int(dec), "group": g, "kw_rate": kw * (1 + noise * rng.normal())})
    return pd.DataFrame(rows)


def write(c: Corpus, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    c.labels.to_parquet(out / "labels.parquet", index=False)
    c.human.to_parquet(out / "human.parquet", index=False)
    c.frame.to_parquet(out / "audit_frame.parquet", index=False)
    c.truth.to_parquet(out / "truth.parquet", index=False)
    c.works.to_parquet(out / "works.parquet", index=False)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--works", type=int, default=12000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--enrichment", action="store_true")
    a = ap.parse_args()
    c = simulate(SimConfig(n_works=a.works, seed=a.seed, enrichment=a.enrichment))
    write(c, Path(a.out))
    print(f"labels={len(c.labels)} works={len(c.works)} audit_rows={len(c.human)} -> {a.out}")


def annotate_noisy(truth_rows: pd.DataFrame, error: float, rng: np.random.Generator,
                   dom_marginal: np.ndarray | None = None) -> pd.DataFrame:
    """A non-expert annotator's labels (human schema: has_obstacle, single main domain, locus,
    failure_cause only for COMMUNICATION) from expert/true labels, with per-item error rate `error`:
    obstacle status flipped w.p. error/2; main domain replaced by a draw from the domain marginal
    w.p. error; failure cause randomised w.p. error; locus re-derived by the codebook mapping
    (non-experts do not apply overrides). error ~0.25-0.35 gives locus kappa ~0.6-0.7 vs expert."""
    n = len(truth_rows)
    p = np.ones(9) / 9 if dom_marginal is None else np.asarray(dom_marginal, float)[:9] / np.sum(dom_marginal[:9])
    has = (truth_rows.has_obstacle.values == "yes")
    flip = rng.random(n) < error / 2
    has_n = has ^ flip
    d_true = np.array([D[list(x)[0]] if len(list(x)) else -1 for x in truth_rows.domains.values])
    d_rand = rng.choice(9, n, p=p)
    swap = rng.random(n) < error
    d = np.where(has_n, np.where((d_true >= 0) & ~swap, d_true, d_rand), -1)
    c_true = np.array([CAUSES.index(x) if x in CAUSES else -1 for x in truth_rows.failure_cause.values])
    c_rand = rng.integers(0, 4, n)
    is_comm = d == D["COMMUNICATION_INFORMATION"]
    c = np.where(is_comm, np.where((c_true >= 0) & (rng.random(n) >= error), c_true, c_rand), -1)
    loc = np.where(has_n, _locus(d, c), -1)
    f = _fields_to_frame({"has": has_n.astype(int), "d1": d, "d2": np.full(n, -1), "cause": c, "locus": loc})
    return pd.DataFrame({"passage_id": truth_rows.passage_id.values, **f})
