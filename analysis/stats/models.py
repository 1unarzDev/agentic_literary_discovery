"""Pre-registered confirmatory models (docs/prereg.md), all on DSL work-level tables (dsl.WorkData).

Family (prereg v0.4): H1 = single PRIMARY test, TWO-SIDED 2-df Wald test of (d_material,
d_internal) = 0, classified inward / outward / mixed; H2a, H2b, H2c, H3 = secondary (Holm over the
four, each reported with its registered MDE); H1-ML (mid vs late) descriptive.
H1  locus shares among obstacles (material / social / internal), multinomial logit on DSL soft
    outcomes ~ ns(year, df=4) + genre + origin + log length; standardised era contrast
    1800-1849 vs 1885-1929 (G0 eras; g-computation over the pooled covariate mix = "within genre");
    intersection-union test: material falls AND internal rises.
H2a share intentional_withholding / (withholding + infrastructure + accidental_loss) among
    communication failures; rises early -> late.
H2b DISTANCE_TRAVEL prevalence 1800-1849 vs 1850-1884 (G0), logit ~ post1850 + genre + origin +
    log length; falls.
H2c DARKNESS_VISIBILITY prevalence falls (night-function share: exploratory, include_night=True).
H3  divergence between z-scored decade keyword rates and function rates (1 - r, averaged over the
    three technology pairs); parametric null of affine tracking + measurement error; block-bootstrap CI.
Holm across the five p-values. Unit = work; SEs cluster-robust by author (works nest in authors).
Also: shift-share decomposition (within-genre vs composition) and fixed-composition trends.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

from analysis.stats.dsl import WorkData, fit_linear, fit_mnlogit, ratio_shares

EARLY = (1800, 1849)         # G0 decision (docs/gates.md): early era pooled 1800-1849
MID = (1850, 1884)
LATE = (1885, 1929)
HINGE_B = 1850               # H2b railway cut: 1800-1849 vs 1850-1884
H3_PAIRS = {"comm": "comm_infra", "travel": "distance", "dark": "darkness"}
H3_P_INFLATE = 10.0          # calibrated H3 p-value multiplier (see h3)


# ------------------------------------------------------------------ design

def ns_basis(x: np.ndarray, knots: np.ndarray) -> np.ndarray:
    """Natural cubic spline basis without intercept (ESL eq. 5.4-5.5): len(knots)-1 columns,
    linear beyond the boundary knots. df = len(knots) - 1."""
    k = np.asarray(knots, float)
    lo, hi = k[0], k[-1]
    xs = (np.asarray(x, float) - lo) / (hi - lo)
    ks = (k - lo) / (hi - lo)
    K = len(ks)

    def d(j):
        return (np.clip(xs - ks[j], 0, None) ** 3 - np.clip(xs - ks[K - 1], 0, None) ** 3) / (ks[K - 1] - ks[j])
    cols = [xs] + [d(j) - d(K - 2) for j in range(K - 2)]
    return np.column_stack(cols)


PREREG_KNOTS = (1800, 1850, 1885, 1905, 1929)   # boundary + era boundaries + late-era median


def default_knots(years: np.ndarray, df: int = 4, quantile: bool = False) -> np.ndarray:
    """Pre-registered fixed knots (df = 4). Quantile knots are a poor choice for PG: the work-year
    distribution is so late-heavy that quartiles fall at ~1891/1906/1917, leaving 1800-1890 as one
    cubic piece and an ill-conditioned basis."""
    if quantile or df != 4:
        qs = np.linspace(0, 1, df + 1)[1:-1]
        return np.r_[np.min(years), np.quantile(years, qs), np.max(years)].astype(float)
    return np.asarray(PREREG_KNOTS, float)


@dataclass
class Design:
    knots: np.ndarray
    genres: list
    origins: list
    loglen_mean: float | None
    time: str = "spline"        # "spline" | "step"
    cut: int = HINGE_B
    extra: tuple = ()           # extra numeric work covariates (e.g. "memorization")

    @classmethod
    def from_data(cls, wd: WorkData, df: int = 4, time: str = "spline", extra: tuple = (),
                  knots: np.ndarray | None = None) -> "Design":
        cov = wd.cov
        gl = cov.genre.value_counts().index.tolist()      # reference = most common genre
        ol = ["UK"] + sorted(set(cov.origin) - {"UK"})
        ll = float(np.log(cov.n_words).mean()) if "n_words" in cov else None
        return cls(default_knots(cov.year.values, df) if knots is None else np.asarray(knots, float),
                   gl, ol, ll, time, HINGE_B, extra)

    def X(self, cov: pd.DataFrame, year: np.ndarray | float | None = None) -> tuple[np.ndarray, list]:
        n = len(cov)
        yr = cov.year.values if year is None else np.broadcast_to(np.asarray(year, float), (n,))
        cols, names = [np.ones(n)], ["const"]
        if self.time == "spline":
            B = ns_basis(yr, self.knots)
            cols += list(B.T)
            names += [f"ns{i}" for i in range(B.shape[1])]
        elif self.time == "linear":
            cols.append((yr - 1885.0) / 100.0)
            names.append("year_lin")
        else:
            cols.append((yr >= self.cut).astype(float))
            names.append(f"post{self.cut}")
        for g in self.genres[1:]:
            cols.append((cov.genre.values == g).astype(float))
            names.append(f"genre[{g}]")
        for o in self.origins[1:]:
            cols.append((cov.origin.values == o).astype(float))
            names.append(f"origin[{o}]")
        if self.loglen_mean is not None and "n_words" in cov:
            cols.append(np.log(cov.n_words.values) - self.loglen_mean)
            names.append("log_len")
        for e in self.extra:
            cols.append(cov[e].values.astype(float))
            names.append(e)
        return np.column_stack(cols), names


@dataclass
class TargetFit:
    fit: object
    design: Design
    keep: np.ndarray            # columns kept (non-degenerate in this data)
    names: list

    def Xk(self, cov, year=None):
        return self.design.X(cov, year)[0][:, self.keep]


LINK = {"default": "logit"}   # set LINK["default"] = "identity" to switch every model (see README)


def fit_target(wd: WorkData, target: str, design: Design, cluster: str = "author_key",
               cats: list | None = None, link: str | None = None) -> TargetFit:
    """Fit the (multinomial) logit or identity-link DSL model for `target` (optionally collapsing to
    the categories `cats`, others -> 0). A logit that fails to converge (DSL pseudo-outcome totals
    can be negative in small cells, so the MLE may not exist) falls back to the identity link,
    as pre-registered; the fallback is recorded in fit.link."""
    X, names = design.X(wd.cov)
    keep = np.r_[True, X[:, 1:].std(0) > 1e-12]
    Y = wd.Y[target]
    if cats is not None:
        Y = np.c_[1 - Y[:, cats].sum(1), Y[:, cats]]
    link = link or LINK["default"]
    cols = [n for n, k in zip(names, keep) if k]
    cl = wd.cov[cluster].values
    w = wd.cov.work_weight.values if "work_weight" in wd.cov else None
    if link == "logit":
        fit = fit_mnlogit(X[:, keep], Y, weights=w, clusters=cl, columns=cols)
        if not fit.converged:
            fit = fit_linear(X[:, keep], Y, weights=w, clusters=cl, columns=cols)
            fit.link = "identity"; fit.n_iter = -1  # -1 marks the logit->identity fallback
    else:
        fit = fit_linear(X[:, keep], Y, weights=w, clusters=cl, columns=cols)
    return TargetFit(fit, design, keep, fit.columns)


def standardized_share(tf: TargetFit, ref_cov: pd.DataFrame, years: np.ndarray, num: list[int],
                       den: list[int] | None) -> tuple[float, np.ndarray]:
    """g-computation: average fitted category probabilities over ref works x years (years may repeat:
    the era's empirical work-year distribution), then
    share = sum_num A / sum_den A (den None -> prevalence sum_num A). Returns (share, d share / d vec(beta))."""
    p, Km1 = tf.fit.beta.shape
    A = np.zeros(Km1 + 1)
    dA = np.zeros((Km1 + 1, Km1 * p))
    M = 0
    if years is None:                          # each reference work at its own year
        X = tf.Xk(ref_cov)
        a, da = tf.fit.mean_and_grad(X)
        A, dA, M = A + a, dA + da, len(X)
        yrs, cnt = [], []
    else:
        yrs, cnt = np.unique(np.atleast_1d(years), return_counts=True)
    for y, k in zip(yrs, cnt):                 # repeated years weight by their counts
        X = tf.Xk(ref_cov, y)
        a, da = tf.fit.mean_and_grad(X)
        A += k * a
        dA += k * da
        M += k * len(X)
    A /= M
    dA /= M
    Nn = A[num].sum()
    gN = dA[num].sum(0)
    if den is None:
        return float(Nn), gN
    Dd = A[den].sum()
    gD = dA[den].sum(0)
    return float(Nn / Dd), (gN * Dd - Nn * gD) / Dd ** 2


# ------------------------------------------------------------------ results

@dataclass
class Component:
    label: str
    estimate: float
    se: float
    expected_sign: int          # +1 / -1 / 0 (no prediction)
    in_test: bool | None = None # part of the hypothesis test (default: expected_sign != 0)

    @property
    def p_two(self) -> float:
        return float(2 * stats.norm.sf(abs(self.estimate) / self.se)) if self.se > 0 else float("nan")

    @property
    def p_dir(self) -> float:
        """two-sided p if the sign is the pre-declared one, else 1 (claim needs the declared sign)."""
        if self.expected_sign == 0:
            return self.p_two
        return self.p_two if np.sign(self.estimate) == self.expected_sign else 1.0

    def ci(self, level=0.95):
        z = stats.norm.ppf(0.5 + level / 2)
        return self.estimate - z * self.se, self.estimate + z * self.se


@dataclass
class Effect:
    name: str
    components: list[Component]
    infl: np.ndarray | None = None         # (n_clusters, n_components): theta_{-c} ~= theta - infl[c]
    extra: dict = field(default_factory=dict)

    @property
    def tested(self) -> list[Component]:
        return [c for c in self.components if (c.in_test if c.in_test is not None else c.expected_sign != 0)]

    @property
    def tested_idx(self) -> list[int]:
        return [i for i, c in enumerate(self.components)
                if (c.in_test if c.in_test is not None else c.expected_sign != 0)]

    @property
    def p(self) -> float:
        """Registered test p: a joint (Wald) p if the effect carries one (two-sided H1), else the
        intersection-union p (every directional component significant in its declared direction)."""
        if self.extra.get("p_test") is not None:
            return float(self.extra["p_test"])
        return max(c.p_dir for c in self.tested)

    def summary(self) -> pd.DataFrame:
        return pd.DataFrame([{"test": self.name, "component": c.label, "estimate": c.estimate, "se": c.se,
                              "lo": c.ci()[0], "hi": c.ci()[1], "expected_sign": c.expected_sign,
                              "p_two_sided": c.p_two} for c in self.components])


def era_years(cov: pd.DataFrame, era: tuple) -> np.ndarray:
    """The era's empirical work-year distribution (the estimand weights years as the corpus does;
    uniform years would give the near-empty 1800s as much weight as the 1840s)."""
    y = cov.year.values
    y = y[(y >= era[0]) & (y <= era[1])]
    return y if len(y) else np.arange(era[0], era[1] + 1)


def _contrast_components(tf: TargetFit, ref: pd.DataFrame, specs: list[tuple], early, late,
                         cov: pd.DataFrame | None = None) -> tuple[list, np.ndarray, dict]:
    """specs: (label, num, den, expected_sign). Returns components, influence matrix, era shares.
    Era years: empirical distribution in `cov` (default ref) - see era_years."""
    yc = ref if cov is None else cov
    ye = era_years(yc, early)
    yl = era_years(yc, late)
    comps, grads, shares = [], [], {}
    for label, num, den, sign in specs:
        se_, ge = standardized_share(tf, ref, ye, num, den)
        sl_, gl = standardized_share(tf, ref, yl, num, den)
        g = gl - ge
        se = float(np.sqrt(max(g @ tf.fit.cov @ g, 0)))
        comps.append(Component(label, sl_ - se_, se, sign))
        grads.append(g)
        shares[label] = (se_, sl_)
    G = np.column_stack(grads)
    infl = tf.fit.cluster_influence() @ G
    shares["_cov"] = G.T @ tf.fit.cov @ G          # joint covariance of the contrasts (for Wald tests)
    return comps, infl, shares


def _ref(wd: WorkData, ref_cov: pd.DataFrame | None, max_ref: int = 3000) -> pd.DataFrame:
    """Reference covariate distribution for standardisation (default: the analysis works; capped
    by a fixed-seed subsample for speed)."""
    if ref_cov is not None:
        return ref_cov
    c = wd.cov
    return c.sample(n=max_ref, random_state=0) if len(c) > max_ref else c


def _direction(c: Component, level: float) -> int:
    lo, hi = c.ci(level)
    return 1 if lo > 0 else (-1 if hi < 0 else 0)


def classify_h1(d_mat: Component, d_int: Component, p_wald: float, alpha: float = 0.05) -> str:
    """Symmetric pre-registered classification (prereg v0.5 §1, fixing review P10), applied only when
    the joint Wald test rejects at alpha. Each component is 'up', 'down' or 'flat' by its
    Bonferroni-adjusted CI at level 1 - alpha/2 (directional error control over the 2 components):
      inward        : material down & internal not down, or internal up & material not up
      outward       : material up & internal not up, or internal down & material not down
      socialisation : material down & internal down   (the social share rises)
      de-socialisation: material up & internal up     (the social share falls)
      indeterminate : joint test rejects but neither component CI excludes 0
      none          : joint test not significant."""
    if not p_wald < alpha:
        return "none"
    lev = 1 - alpha / 2
    m, i = _direction(d_mat, lev), _direction(d_int, lev)
    if m == -1 and i == -1:
        return "socialisation"
    if m == 1 and i == 1:
        return "de-socialisation"
    if (m == -1 and i >= 0) or (i == 1 and m <= 0):
        return "inward"
    if (m == 1 and i <= 0) or (i == -1 and m >= 0):
        return "outward"
    return "indeterminate"


def wald(est: np.ndarray, cov: np.ndarray) -> tuple[float, float]:
    """Joint Wald chi-square test of est = 0; returns (W, p)."""
    est = np.asarray(est, float)
    W = float(est @ np.linalg.pinv(cov) @ est)
    return W, float(stats.chi2.sf(W, len(est)))


ALPHA_PRIMARY = 0.025         # prereg v0.5: two co-primary tests (TF, H1) at 0.025 each


def h1(wd: WorkData, design: Design | None = None, ref_cov=None, early=EARLY, late=LATE,
       two_sided: bool = True, name: str = "H1 locus shift", alpha: float = ALPHA_PRIMARY) -> Effect:
    """Registered H1 (prereg v0.4): two-sided 2-df Wald test of (d_material, d_internal) = 0, L - E,
    genre-standardised; result classified inward / outward / mixed (classify_h1).
    two_sided=False reproduces the v0.3 directional intersection-union test (material down AND
    internal up)."""
    design = design or Design.from_data(wd)
    tf = fit_target(wd, "locus", design)
    sm, si = (0, 0) if two_sided else (-1, +1)
    specs = [("material share", [1], [1, 2, 3], sm), ("internal share", [3], [1, 2, 3], si),
             ("social share", [2], [1, 2, 3], 0)]
    comps, infl, shares = _contrast_components(tf, _ref(wd, ref_cov), specs, early, late, wd.cov)
    extra = {"era_shares": shares, "converged": tf.fit.converged, "link": tf.fit.link, "fit": tf,
             "window": (early, late)}
    if two_sided:
        comps[0].in_test = comps[1].in_test = True
        W, p = wald([comps[0].estimate, comps[1].estimate], shares["_cov"][:2, :2])
        extra.update({"two_sided": True, "wald": W, "p_test": p, "alpha": alpha,
                      "classification": classify_h1(comps[0], comps[1], p, alpha)})
    return Effect(name, comps, infl, extra)


def h1_contrast(wd: WorkData, design: Design | None = None, ref_cov=None, time: str = "spline",
                window: tuple | None = None, years_a=None, years_b=None, cut: int = 1880,
                name: str = "H1 contrast", fit_cache: dict | None = None, alpha: float = ALPHA_PRIMARY) -> Effect:
    """General two-sided locus contrast (same Wald test + classification as h1) for alternative H1
    statistics (levers.py, prereg v0.5 §7.6):
      time="spline", years = empirical era years  -> E vs L / M vs L (h1, h1_mid_late)
      time="linear", window=(1840,1929), years_a=[1840], years_b=[1929]  -> linear-in-year trend
      time="step",   window=(1840,1929), cut=1880, years 1879 vs 1880    -> pre/post-1880 step
    fit_cache lets several contrasts share one fit (keyed by time/window/cut)."""
    base = design or Design.from_data(wd)
    d = Design(base.knots, base.genres, base.origins, base.loglen_mean, time, cut, base.extra)
    ref = _ref(wd, ref_cov)
    key = (time, window, cut)
    if fit_cache is not None and key in fit_cache:
        tf = fit_cache[key]
    else:
        sub = wd if window is None else wd.subset((wd.cov.year.values >= window[0]) & (wd.cov.year.values <= window[1]))
        tf = fit_target(sub, "locus", d)
        if fit_cache is not None:
            fit_cache[key] = tf
    comps, grads = [], []
    for label, num in (("material share", [1]), ("internal share", [3])):
        sa, ga = standardized_share(tf, ref, years_a, num, [1, 2, 3])
        sb, gb = standardized_share(tf, ref, years_b, num, [1, 2, 3])
        g = gb - ga
        comps.append(Component(label, sb - sa, float(np.sqrt(max(g @ tf.fit.cov @ g, 0))), 0, True))
        grads.append(g)
    G = np.column_stack(grads)
    V = G.T @ tf.fit.cov @ G
    W, p = wald([c.estimate for c in comps], V)
    infl = tf.fit.cluster_influence() @ G
    return Effect(name, comps, infl, {"two_sided": True, "wald": W, "p_test": p,
                                      "classification": classify_h1(comps[0], comps[1], p, alpha), "link": tf.fit.link,
                                      "alpha": alpha})


def two_fictions(wd: WorkData, design: Design | None = None, ref_cov=None, adjust_genre: bool = False,
                 alpha: float = ALPHA_PRIMARY, name: str = "TF two fictions") -> Effect:
    """Co-primary (prereg v0.5) TWO FICTIONS: canonical vs non-canonical works differ in locus mix.
    Multinomial logit of DSL soft outcomes ~ canonical + ns(year, df=4) + origin + log length
    (genre NOT adjusted in the primary: genre composition is part of what separates the two fields;
    adjust_genre=True is the registered secondary). Estimand: g-computation over the standard
    population at each work's own year, canonical set to 1 vs 0; (d_material, d_internal) =
    canonical - non-canonical; two-sided 2-df Wald; symmetric classification ('inward' = canon more
    inward). Needs cov.canonical (bool / 0-1)."""
    base = design or Design.from_data(wd)
    cov = wd.cov.assign(canon_num=wd.cov.canonical.astype(float).values)
    wd2 = WorkData(cov, wd.Y, wd.method, wd.info)
    d = Design(base.knots, base.genres if adjust_genre else base.genres[:1], base.origins, base.loglen_mean,
               "spline", base.cut, tuple(base.extra) + ("canon_num",))
    tf = fit_target(wd2, "locus", d)
    ref = _ref(wd2, ref_cov)
    if "canon_num" not in ref:
        ref = ref.assign(canon_num=0.0)
    comps, grads = [], []
    r1, r0 = ref.assign(canon_num=1.0), ref.assign(canon_num=0.0)
    shares = {}
    for label, num in (("material share", [1]), ("internal share", [3]), ("social share", [2])):
        s1, g1 = standardized_share(tf, r1, None, num, [1, 2, 3])
        s0, g0 = standardized_share(tf, r0, None, num, [1, 2, 3])
        g = g1 - g0
        comps.append(Component(label, s1 - s0, float(np.sqrt(max(g @ tf.fit.cov @ g, 0))), 0, label != "social share"))
        grads.append(g)
        shares[label] = (s0, s1)
    G = np.column_stack(grads[:2])
    W, p = wald([comps[0].estimate, comps[1].estimate], G.T @ tf.fit.cov @ G)
    infl = tf.fit.cluster_influence() @ np.column_stack(grads)
    return Effect(name, comps, infl, {"two_sided": True, "wald": W, "p_test": p, "alpha": alpha,
                                      "classification": classify_h1(comps[0], comps[1], p, alpha),
                                      "shares_noncanon_canon": shares, "link": tf.fit.link, "converged": tf.fit.converged})


def tf_statistics(wd: WorkData, design: Design | None = None, ref_cov=None, weights: str = "works",
                  adjust_genre: bool = False, interact: bool = False) -> dict:
    """Candidate TF primary statistics (prereg v0.5 §7.8) from ONE fit of the TF model.
    weights="works": g-computation over the standard population pooled across eras (each work at its
      own year; eras weighted by their share of works = the registered TF estimand);
    weights="era_equal": the canonical - non-canonical gap computed within each era's standard works,
      then averaged with equal era weights (1/3 each).
    interact=True adds canonical x era (M, L) terms so era-specific gaps can differ (needed for the
    era weighting to matter); interact=False is the registered constant-gap (main effect) model.
    Returns estimates, SEs and p-values (two-sided) for: material gap (1 df), internal gap, the joint
    2-df Wald test of (material, internal), and the inwardness index gap
    d_I = d_internal - d_material (1 df)."""
    base = design or Design.from_data(wd)
    def add(c):
        c = c.assign(canon_num=c.canonical.astype(float).values) if "canonical" in c and "canon_num" not in c else c
        if interact:
            y = c.year.values
            c = c.assign(canon_M=c.canon_num * ((y >= MID[0]) & (y <= MID[1])), canon_L=c.canon_num * (y >= LATE[0]))
        return c
    cov = add(wd.cov)
    wd2 = WorkData(cov, wd.Y, wd.method, wd.info)
    extra = tuple(base.extra) + ("canon_num",) + (("canon_M", "canon_L") if interact else ())
    d = Design(base.knots, base.genres if adjust_genre else base.genres[:1], base.origins, base.loglen_mean,
               "spline", base.cut, extra)
    tf = fit_target(wd2, "locus", d)
    ref = _ref(wd2, ref_cov)
    if weights == "works":
        parts = [(1.0, ref)]
    else:
        yr = ref.year.values
        groups = [ref[(yr >= a) & (yr <= b)] for a, b in (EARLY, MID, LATE)]
        parts = [(1 / 3, g) for g in groups if len(g)]
        tot = sum(w for w, _ in parts)
        parts = [(w / tot, g) for w, g in parts]
    est, grads = np.zeros(2), [0, 0]
    for w, r in parts:
        r1, r0 = add(r.assign(canon_num=1.0)), add(r.assign(canon_num=0.0))
        for j, num in enumerate(([1], [3])):
            s1, g1 = standardized_share(tf, r1, None, num, [1, 2, 3])
            s0, g0 = standardized_share(tf, r0, None, num, [1, 2, 3])
            est[j] += w * (s1 - s0)
            grads[j] = grads[j] + w * (g1 - g0)
    G = np.column_stack(grads)
    V = G.T @ tf.fit.cov @ G
    se = np.sqrt(np.diag(V))
    gI = grads[1] - grads[0]
    dI = est[1] - est[0]
    seI = float(np.sqrt(max(gI @ tf.fit.cov @ gI, 0)))
    W, pW = wald(est, V)
    p2 = lambda z: float(2 * stats.norm.sf(abs(z)))
    return {"d_mat": est[0], "se_mat": se[0], "p_mat": p2(est[0] / se[0]),
            "d_int": est[1], "se_int": se[1], "p_int": p2(est[1] / se[1]),
            "corr_mat_int": float(V[0, 1] / (se[0] * se[1])), "wald": W, "p_wald": pW,
            "d_index": dI, "se_index": seI, "p_index": p2(dI / seI), "link": tf.fit.link}


def within_strata(fn, wd: WorkData, col: str = "canonical", **kw) -> dict:
    """Secondary (v0.5): run an era contrast (e.g. h1) separately within each level of `col`."""
    return {lev: fn(wd.subset(wd.cov[col].values == lev), **kw) for lev in pd.unique(wd.cov[col])}


def h1_mid_late(wd: WorkData, design: Design | None = None, ref_cov=None) -> Effect:
    """Descriptive (prereg v0.4): the same two-sided locus contrast for M (1850-84) vs L (1885-1929),
    where most of the data lie and the pilot's 1880s step sits. Reported with CI and Wald p; not part
    of any multiplicity family."""
    return h1(wd, design, ref_cov, early=MID, late=LATE, name="H1-ML mid vs late (descriptive)")


def reference_covariates(works: pd.DataFrame, genre: pd.DataFrame | None = None, n: int = 3000,
                         seed: int = 0) -> pd.DataFrame:
    """Registered standard population for g-computation: a fixed-seed sample of the primary-set works
    of BOTH halves (metadata only, nothing sealed), with the registered genre variable
    (data/work/genre.parquet, pipeline/genre.py). Needs work_id, origin, n_words (+ genre or `genre`)."""
    w = works.copy()
    if genre is not None:
        w = w.drop(columns=["genre"], errors="ignore").merge(genre[["work_id", "genre"]], on="work_id", how="left")
    w = w[w.genre.notna()]
    return w.sample(n=min(n, len(w)), random_state=seed).reset_index(drop=True)


def attach_genre(labels: pd.DataFrame, genre: pd.DataFrame) -> pd.DataFrame:
    """Replace labels.genre by the registered 8-class genre (pipeline/genre.py)."""
    out = labels.drop(columns=["genre"], errors="ignore").merge(genre[["work_id", "genre"]], on="work_id", how="left")
    missing = out.genre.isna().mean()
    if missing > 0.01:
        raise ValueError(f"{missing:.1%} of passages have no registered genre")
    return out


def h2a(wd: WorkData, design: Design | None = None, ref_cov=None, early=EARLY, late=LATE) -> Effect:
    design = design or Design.from_data(wd)
    tf = fit_target(wd, "comm_cause", design)
    comps, infl, shares = _contrast_components(tf, _ref(wd, ref_cov), [("withholding share", [1], [1, 2], +1)],
                                               early, late, wd.cov)
    return Effect("H2a communication", comps, infl, {"era_shares": shares, "converged": tf.fit.converged})


def h2b(wd: WorkData, design: Design | None = None, ref_cov=None, cut: int = HINGE_B,
        window: tuple = (EARLY[0], MID[1])) -> Effect:
    """DISTANCE_TRAVEL prevalence, works in `window` only (G0: 1800-1849 vs 1850-1884), logit ~
    post-cut + genre + origin + log length; standardised over the pooled covariate mix."""
    base = design or Design.from_data(wd)
    d = Design(base.knots, base.genres, base.origins, base.loglen_mean, "step", cut, base.extra)
    full = wd
    wd = wd.subset((wd.cov.year.values >= window[0]) & (wd.cov.year.values <= window[1]))
    if ref_cov is None:
        ref_cov = _ref(full, None)
    tf = fit_target(wd, "distance", d)
    ref = _ref(wd, ref_cov)
    s0, g0 = standardized_share(tf, ref, [cut - 1], [1], None)
    s1, g1 = standardized_share(tf, ref, [cut], [1], None)
    g = g1 - g0
    comp = Component(f"DISTANCE prevalence post-pre {cut}", s1 - s0, float(np.sqrt(g @ tf.fit.cov @ g)), -1)
    infl = tf.fit.cluster_influence() @ g[:, None]
    # secondary (not tested): per-genre raw pre/post shares
    per = ratio_shares(wd, "distance", [1], None, by=np.where(wd.cov.year.values >= cut, "post", "pre"))
    return Effect("H2b mobility", [comp], infl, {"pre_post": (s0, s1), "converged": tf.fit.converged,
                                                  "raw": per.table})


def h2c(wd: WorkData, design: Design | None = None, ref_cov=None, early=EARLY, late=LATE,
        include_night: bool = False) -> Effect:
    """Registered (secondary) H2c: DARKNESS_VISIBILITY prevalence falls E -> L. The night-function
    share (danger + concealment) is exploratory only (humans do not label night_function, so it
    cannot be DSL-corrected); include_night=True adds it as an extra directional component."""
    design = design or Design.from_data(wd)
    ref = _ref(wd, ref_cov)
    tf1 = fit_target(wd, "darkness", design)
    comps, infl, shares = _contrast_components(tf1, ref, [("DARKNESS prevalence", [1], None, -1)], early, late, wd.cov)
    conv = tf1.fit.converged
    if include_night and "night" in wd.Y:
        tf2 = fit_target(wd, "night", design)
        c2, i2, s2 = _contrast_components(tf2, ref, [("night danger+concealment share", [1], [1, 2], -1)],
                                          early, late, wd.cov)
        comps, infl, shares = comps + c2, np.column_stack([infl, i2]), {**shares, **s2}
        conv = conv and tf2.fit.converged
    return Effect("H2c darkness", comps, infl,
                  {"era_shares": shares, "night_dsl_corrected": "night_uncorrected" not in wd.info, "converged": conv})


# ------------------------------------------------------------------ H3

def function_series(wd: WorkData, decades: np.ndarray | None = None) -> pd.DataFrame:
    """DSL decade series (prevalence per passage, work-averaged) for each H3 pair, with SEs."""
    rows = []
    for grp, tgt in H3_PAIRS.items():
        r = ratio_shares(wd, tgt, [1], None, by=wd.cov.decade.values)
        for _, x in r.table.iterrows():
            rows.append({"group": grp, "decade": int(x["group"]), "fn_rate": x.estimate, "fn_se": x.se})
    out = pd.DataFrame(rows)
    if decades is not None:
        out = out[out.decade.isin(decades)]
    return out


def _z(a: np.ndarray) -> np.ndarray:
    s = a.std()
    return (a - a.mean()) / s if s > 0 else a * 0


def divergence(kw: np.ndarray, fn: np.ndarray) -> float:
    """D = 1 - Pearson r of z-scored series = mean squared z-difference / 2. Range [0, 2]."""
    return float(np.mean((_z(kw) - _z(fn)) ** 2) / 2)


def h3(wd: WorkData, keywords: pd.DataFrame, n_boot: int = 2000, block: int = 3, seed: int = 0,
       min_works: int = 30) -> Effect:
    """keywords: columns decade, group (comm|travel|dark), kw_rate. Decades with < min_works works
    are dropped. Statistic: mean over pairs of D. Test: H0 = the true function series tracks the
    keyword series perfectly (identical in z-units, positive direction) and the observed series
    differs only by DSL sampling error (parametric bootstrap); estimate = D_obs - E_H0[D] (excess
    divergence, expected > 0). CI for D: circular moving-block bootstrap over decades
    (same blocks for every pair), each replicate also perturbed by the function-rate sampling error."""
    rng = np.random.default_rng(seed)
    ok = wd.cov.decade.value_counts()
    decs = sorted(ok[ok >= min_works].index)
    fs = function_series(wd, decs)
    m = fs.merge(keywords, on=["group", "decade"])
    groups = [g for g in H3_PAIRS if g in set(m.group)]
    kw = np.array([m[m.group == g].sort_values("decade").kw_rate.values for g in groups])
    fn = np.array([m[m.group == g].sort_values("decade").fn_rate.values for g in groups])
    se = np.array([m[m.group == g].sort_values("decade").fn_se.values for g in groups])
    T = kw.shape[1]
    Dobs = float(np.mean([divergence(kw[i], fn[i]) for i in range(len(groups))]))
    # H0 (perfect positive tracking): the TRUE function series is the keyword series in z-units,
    # fn_true = mean(fn) + sd_true * z(kw) with sd_true^2 = var(fn) - mean(se^2); observed = true + error
    null = np.empty(n_boot)
    fitted = []
    for i in range(len(groups)):
        sd_true = np.sqrt(max(fn[i].var() - np.mean(se[i] ** 2), 1e-12))
        fitted.append(fn[i].mean() + sd_true * _z(kw[i]))
    fitted = np.array(fitted)
    for r in range(n_boot):
        fstar = fitted + rng.normal(0, 1, fitted.shape) * se
        null[r] = np.mean([divergence(kw[i], fstar[i]) for i in range(len(groups))])
    p = float((1 + (null >= Dobs).sum()) / (n_boot + 1))
    excess = Dobs - float(null.mean())
    # block bootstrap CI for D
    nb = int(np.ceil(T / block))
    boot = np.empty(n_boot)
    for r in range(n_boot):
        starts = rng.integers(0, T, nb)
        idx = (starts[:, None] + np.arange(block)).ravel()[:T] % T
        fstar = fn[:, idx] + rng.normal(0, 1, (len(groups), T)) * se[:, idx]
        boot[r] = np.mean([divergence(kw[i, idx], fstar[i]) for i in range(len(groups))])
    lo, hi = np.quantile(boot, [0.025, 0.975])
    # simulation calibration (power.py --final, 140 replicates): the parametric null under-states
    # the variability of DSL decade series (thin early decades, construct mismatch), giving size ~0.15
    # at nominal 0.05; nominal 0.005 gives ~0.05. Registered: p_cal = min(1, H3_P_INFLATE * p).
    p_raw = p
    p = min(1.0, H3_P_INFLATE * p_raw)
    # z-equivalent SE so the Component carries the calibrated p
    z = stats.norm.isf(p / 2) if p < 1 else 0.0
    se_eq = abs(excess) / z if z > 0 else float("inf")
    comp = Component("excess divergence D - E_H0[D]", excess, se_eq, +1)
    per_pair = {g: divergence(kw[i], fn[i]) for i, g in enumerate(groups)}
    return Effect("H3 mention != function", [comp], None,
                  {"D": Dobs, "D_ci": (float(lo), float(hi)), "p_param": p_raw, "p_cal": p, "per_pair": per_pair,
                   "decades": decs, "null_mean": float(null.mean())})


# ------------------------------------------------------------------ multiplicity

def holm(p: list[float] | np.ndarray) -> np.ndarray:
    """Holm step-down adjusted p-values."""
    p = np.asarray(p, float)
    m = len(p)
    order = np.argsort(p)
    adj = np.empty(m)
    run = 0.0
    for i, j in enumerate(order):
        run = max(run, (m - i) * p[j])
        adj[j] = min(1.0, run)
    return adj


PRIMARIES = ("TF",)          # prereg v0.5 recommendation; ("TF", "H1") = the two-primary alternative


def confirmatory(wd: WorkData, keywords: pd.DataFrame | None = None, alpha: float = 0.05,
                 design: Design | None = None, n_boot: int = 2000, ref_cov: pd.DataFrame | None = None,
                 primaries: tuple = PRIMARIES) -> tuple[pd.DataFrame, dict[str, Effect]]:
    """Registered v0.5 family.
      primary (Bonferroni over the primaries: alpha / len(primaries)): default TF alone at 0.05;
        primaries=("TF", "H1") gives the two-primary alternative at 0.025 each
      secondary (Holm at alpha): H1 (if not primary), H1 within canonical, H1 within non-canonical
      descriptive (CIs, Wald p, no verdict): TF genre-adjusted, H1-ML, canon composition share
      estimation only (effect + CI, no test): H2a, H2b, H2c, H3."""
    design = design or Design.from_data(wd)
    a1 = alpha / len(primaries)
    pr = "co-primary" if len(primaries) > 1 else "primary"
    effs: dict[str, Effect] = {"H1": h1(wd, design, ref_cov, alpha=a1 if "H1" in primaries else alpha)}
    role = {"H1": pr if "H1" in primaries else "secondary"}
    has_canon = "canonical" in wd.cov and wd.cov.canonical.nunique() == 2
    if has_canon:
        effs["TF"] = two_fictions(wd, design, ref_cov, alpha=a1 if "TF" in primaries else alpha)
        role["TF"] = pr if "TF" in primaries else "secondary"
        for lev, nm in ((True, "H1|canonical"), (False, "H1|non-canonical")):
            sub = wd.subset(wd.cov.canonical.values.astype(bool) == lev)
            try:
                effs[nm] = h1(sub, design, ref_cov, alpha=alpha, name=nm)
                role[nm] = "secondary"
            except Exception:
                pass
        effs["TF-genre"] = two_fictions(wd, design, ref_cov, adjust_genre=True, alpha=alpha, name="TF genre-adjusted")
        role["TF-genre"] = "descriptive"
    effs["H1-ML"] = h1_mid_late(wd, design, ref_cov)
    role["H1-ML"] = "descriptive"
    for k, f in (("H2a", h2a), ("H2b", h2b), ("H2c", h2c)):
        effs[k] = f(wd, design, ref_cov)
        role[k] = "estimation"
    if keywords is not None:
        effs["H3"] = h3(wd, keywords, n_boot=n_boot)
        role["H3"] = "estimation"
    sec = [k for k, r in role.items() if r == "secondary"]
    sec_adj = dict(zip(sec, holm([effs[k].p for k in sec]))) if sec else {}
    rows = []
    for k, e in effs.items():
        r = role[k]
        if r in ("co-primary", "primary"):
            p_adj, lev = e.p, a1
        elif r == "secondary":
            p_adj, lev = sec_adj[k], alpha
        else:
            p_adj, lev = np.nan, np.nan
        for c in e.components:
            rows.append({"test": k, "role": r, "component": c.label, "estimate": c.estimate, "se": c.se,
                         "lo": c.ci()[0], "hi": c.ci()[1], "expected_sign": c.expected_sign,
                         "p_test": e.p if r not in ("estimation",) else np.nan, "p_adj": p_adj, "alpha": lev,
                         "reject": bool(p_adj < lev) if np.isfinite(p_adj) else None,
                         "classification": e.extra.get("classification")})
    return pd.DataFrame(rows), effs


def apply_works_v2(labels: pd.DataFrame, works: pd.DataFrame, primary_col: str | None = None) -> pd.DataFrame:
    """Registered population (prereg v0.5 §2) from data/work/works_v2.parquet:
    author_key <- author_group (PG-agent clusters, house names merged), split <- split_v2, and keep
    only primary-set works (primary_v2_capv2 if present, else primary_v2: date resolved in window,
    not historical_setting, author cap). The verified-date exclusions are part of the primary flags
    (build_works_v2.apply_verified_dates); year / decade are replaced by year_v2 / decade_v2 when present."""
    pcol = primary_col or next((c for c in ("primary_v2_capv2", "primary_v2") if c in works), None)
    dcols = [c for c in ("year_v2", "decade_v2") if c in works]
    cols = ["work_id", "author_group", "split_v2"] + ([pcol] if pcol else []) + dcols
    w = works[cols]
    out = labels.drop(columns=[c[:-3] for c in dcols if c[:-3] in labels], errors="ignore").merge(w, on="work_id", how="inner")
    out = out.rename(columns={c: c[:-3] for c in dcols})
    if pcol:
        out = out[out[pcol].fillna(False).astype(bool)].drop(columns=[pcol])
    return out.assign(author_key=out.author_group, split=out.split_v2).drop(columns=["author_group", "split_v2"])


def attach_canon(labels: pd.DataFrame, canon: pd.DataFrame) -> pd.DataFrame:
    """Attach the registered metadata-only canonicity flag (data/work/canon.parquet: work_id,
    canonical [bool], optional canon_score; docs/canon_measure.md)."""
    out = labels.drop(columns=["canonical"], errors="ignore").merge(canon[["work_id", "canonical"]], on="work_id", how="left")
    if out.canonical.isna().mean() > 0.01:
        raise ValueError("canonical flag missing for > 1% of passages")
    out["canonical"] = out.canonical.astype("boolean").fillna(False).astype(bool)
    return out


# ------------------------------------------------------------------ composition

def _cell_sums(wd, target, num, den, cell_codes, n_cells, a):
    Y = wd.Y[target]
    N = Y[:, num].sum(1)
    Dn = Y[:, den].sum(1) if den is not None else np.ones(len(Y))
    return (np.bincount(cell_codes, a * N, n_cells), np.bincount(cell_codes, a * Dn, n_cells),
            np.bincount(cell_codes, a, n_cells))


def _author_boot_weights(wd: WorkData, B: int, seed: int) -> np.ndarray:
    codes, uniq = pd.factorize(wd.cov.author_key)
    rng = np.random.default_rng(seed)
    cnt = rng.multinomial(len(uniq), np.full(len(uniq), 1 / len(uniq)), size=B)
    return cnt[:, codes].astype(float)          # (B, n_works)


def shift_share(wd: WorkData, target: str, num: list[int], den: list[int] | None,
                period_a: tuple, period_b: tuple, by: str = "genre", B: int = 200, seed: int = 0) -> pd.DataFrame:
    """Symmetric (Bennet) shift-share of the change in a ratio share between two year windows:
    total = within (sum_g sbar_g dtheta_g) + composition (sum_g thetabar_g ds_g), exact.
    s_g = genre share of the denominator mass (obstacles for shares, works for prevalence).
    CIs from an author-cluster bootstrap."""
    yr = wd.cov.year.values
    per = np.where((yr >= period_a[0]) & (yr <= period_a[1]), 0, np.where((yr >= period_b[0]) & (yr <= period_b[1]), 1, -1))
    m = per >= 0
    sub = wd.subset(m)
    per = per[m]
    gcodes, glev = pd.factorize(sub.cov[by])
    G = len(glev)
    cell = per * G + gcodes

    def decomp(a):
        Ns, Ds, _ = _cell_sums(sub, target, num, den, cell, 2 * G, a)
        Ns, Ds = Ns.reshape(2, G), Ds.reshape(2, G)
        with np.errstate(invalid="ignore", divide="ignore"):
            th = Ns / Ds
        th = np.where(np.isnan(th), th[::-1], th)          # missing cell: no within change
        th = np.nan_to_num(th)
        s = Ds / Ds.sum(1, keepdims=True)
        within = ((s[0] + s[1]) / 2 * (th[1] - th[0])).sum()
        comp = ((th[0] + th[1]) / 2 * (s[1] - s[0])).sum()
        tot = Ns[1].sum() / Ds[1].sum() - Ns[0].sum() / Ds[0].sum()
        return np.array([tot, within, comp])

    est = decomp(np.ones(len(sub)))
    W = _author_boot_weights(sub, B, seed)
    bs = np.array([decomp(w) for w in W])
    lo, hi = np.nanquantile(bs, [0.025, 0.975], axis=0)
    return pd.DataFrame({"part": ["total", "within_" + by, "composition"], "estimate": est,
                         "lo": lo, "hi": hi, "boot_se": bs.std(0)})


def shift_share_series(wd: WorkData, target: str, num, den, by: str = "genre", B: int = 100,
                       min_works: int = 30) -> pd.DataFrame:
    """Decade-to-decade shift-share decomposition (adjacent decades with >= min_works works)."""
    vc = wd.cov.decade.value_counts()
    decs = sorted(vc[vc >= min_works].index)
    rows = []
    for a, b in zip(decs[:-1], decs[1:]):
        t = shift_share(wd, target, num, den, (a, a + 9), (b, b + 9), by, B)
        rows.append({"from": a, "to": b, **{f"{p}": e for p, e in zip(t.part, t.estimate)},
                     **{f"{p}_lo": e for p, e in zip(t.part, t.lo)}, **{f"{p}_hi": e for p, e in zip(t.part, t.hi)}})
    return pd.DataFrame(rows)


def fixed_composition_trend(wd: WorkData, target: str, num: list[int], den: list[int] | None,
                            cells: tuple = ("genre", "origin"), ref: tuple = (1840, 1900), by: str = "decade",
                            B: int = 200, seed: int = 0) -> pd.DataFrame:
    """Post-stratified trend: theta*_t = sum_c s*_c Nbar_ct / sum_c s*_c Dbar_ct, s*_c = the work mix of
    genre x origin cells in the reference window (pooled 1840-1900). Empty cells in period t are
    dropped and s* renormalised; `ref_coverage` reports the share of s* that was available."""
    cov = wd.cov
    ckey = cov[list(cells)].astype(str).agg("|".join, axis=1)
    ccodes, clev = pd.factorize(ckey)
    C = len(clev)
    inref = (cov.year >= ref[0]) & (cov.year <= ref[1])
    sstar = np.bincount(ccodes[inref.values], minlength=C).astype(float)
    sstar /= sstar.sum()
    pcodes, plev = pd.factorize(cov[by])
    order = np.argsort(plev)
    cell = pcodes * C + ccodes

    def trend(a):
        Ns, Ds, Ws = _cell_sums(wd, target, num, den, cell, len(plev) * C, a)
        Ns, Ds, Ws = (x.reshape(len(plev), C) for x in (Ns, Ds, Ws))
        have = Ws > 0
        with np.errstate(invalid="ignore", divide="ignore"):
            Nb, Db = np.where(have, Ns / np.where(have, Ws, 1), 0), np.where(have, Ds / np.where(have, Ws, 1), 0)
        sw = sstar[None, :] * have
        fixed = (sw * Nb).sum(1) / (sw * Db).sum(1)
        raw = Ns.sum(1) / Ds.sum(1)
        return fixed, raw, sw.sum(1)

    f, r, covg = trend(np.ones(len(cov)))
    W = _author_boot_weights(wd, B, seed)
    bf = np.array([trend(w)[0] for w in W])
    br = np.array([trend(w)[1] for w in W])
    out = pd.DataFrame({by: np.asarray(plev), "raw": r, "raw_lo": np.nanquantile(br, 0.025, 0),
                        "raw_hi": np.nanquantile(br, 0.975, 0), "fixed": f,
                        "fixed_lo": np.nanquantile(bf, 0.025, 0), "fixed_hi": np.nanquantile(bf, 0.975, 0),
                        "ref_coverage": covg, "n_works": np.bincount(pcodes),
                        "n_authors": cov.groupby(pcodes).author_key.nunique().values})
    return out.iloc[order].reset_index(drop=True)
