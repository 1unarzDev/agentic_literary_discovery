"""Design-based supervised learning (DSL; Egami, Hinck, Stewart & Wei, NeurIPS 2023) and
prediction-powered inference (PPI; Angelopoulos et al., Science 2023) for the obstacle study.

Pipeline (all estimators share it):
  1. targets: every estimand is a categorical outcome per passage, one-hot coded (`onehot`).
  2. design:  pi_audit for EVERY analysis passage (audit_frame.parquet, or re-derived) (`audit_design`).
  3. pseudo-outcomes: Ytilde = g + R/pi * (Y - g), with g = raw LLM one-hot or a cross-fitted
     calibration g(LLM label, era) learned on the audit (`pseudo_outcomes`). E[Ytilde | passage] = Y
     for any g, so every downstream estimator stays unbiased for the human-label estimand.
  4. work aggregation: within-work Hajek weights 1/inclusion_prob (`WorkData`), works weighted
     equally - the work is the unit, passages are never independent units.
  5. estimators: ratio-of-means shares per group with author/work-clustered linearised SEs
     (`ratio_shares`), and multinomial/binary logit on soft (pseudo) outcomes with a
     cluster-robust sandwich (`fit_mnlogit`).
PPI (`ppi_mean`, stratified) is a passage-level cross-check for means.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

import numpy as np
import pandas as pd
from scipy import stats

ERAS3 = ["early_1800_1849", "mid_1850_1884", "late_1885_1920"]
LOCUS_MAP = {"material_external": 1, "social_institutional": 2, "internal_psychological": 3}


def _has(df: pd.DataFrame, dom: str) -> np.ndarray:
    return np.fromiter((x is not None and dom in list(x) for x in df.domains.values), bool, len(df))


def _yes(df: pd.DataFrame) -> np.ndarray:
    return (df.has_obstacle.values == "yes")


# Each target maps a label table (model or human schema) to integer categories 0..K-1.
# Category 0 is always "not counted / other"; shares are ratios of other categories.
def _t_locus(df):
    loc = df.locus.map(LOCUS_MAP).fillna(0).astype(int).values
    return np.where(_yes(df), loc, 0)


def _t_comm_cause(df):
    fc = df.failure_cause.values
    comm = _yes(df) & _has(df, "COMMUNICATION_INFORMATION")
    return np.where(comm & (fc == "intentional_withholding"), 1,
                    np.where(comm & np.isin(fc, ["infrastructure", "accidental_loss"]), 2, 0))


def _t_dom(dom):
    return lambda df: (_yes(df) & _has(df, dom)).astype(int)


def _t_comm_infra(df):
    comm = _yes(df) & _has(df, "COMMUNICATION_INFORMATION")
    return (comm & np.isin(df.failure_cause.values, ["infrastructure", "accidental_loss"])).astype(int)


def _t_night(df):
    nf = df.night_function.values
    return np.where(np.isin(nf, ["danger", "concealment"]), 1,
                    np.where(np.isin(nf, ["intimacy", "labor", "leisure"]), 2, 0))


def _t_obstacle(df):
    return _yes(df).astype(int)


@dataclass(frozen=True)
class Target:
    name: str
    K: int
    fn: Callable[[pd.DataFrame], np.ndarray]
    human_fields: tuple = ("has_obstacle", "domains", "locus", "failure_cause")
    cats: tuple = ()


TARGETS: dict[str, Target] = {
    "locus": Target("locus", 4, _t_locus, cats=("other", "material", "social", "internal")),
    "comm_cause": Target("comm_cause", 3, _t_comm_cause, cats=("other", "withholding", "infra_accident")),
    "distance": Target("distance", 2, _t_dom("DISTANCE_TRAVEL"), cats=("other", "distance")),
    "darkness": Target("darkness", 2, _t_dom("DARKNESS_VISIBILITY"), cats=("other", "darkness")),
    "comm_infra": Target("comm_infra", 2, _t_comm_infra, cats=("other", "comm_infra")),
    "obstacle": Target("obstacle", 2, _t_obstacle, cats=("other", "obstacle")),
    # humans do not label night_function (plan 4.5): DSL only if human.parquet carries the column
    "night": Target("night", 3, _t_night, human_fields=("night_function",),
                    cats=("other", "danger_concealment", "intimacy_labor_leisure")),
}


def onehot(codes: np.ndarray, K: int) -> np.ndarray:
    out = np.zeros((len(codes), K))
    out[np.arange(len(codes)), codes] = 1.0
    return out


# ------------------------------------------------------------------ human labels

def resolve_human(human: pd.DataFrame, prefer: Iterable[str] = ("adjudicated", "teacher")) -> pd.DataFrame:
    """One row per passage: an `adjudicated` row if present; else agreement; else the first annotator
    in `prefer` (the teacher adjudicates per plan 4.5); else the first row."""
    order = {a: i for i, a in enumerate(prefer)}
    h = human.assign(_o=human.annotator.map(order).fillna(len(order)))
    return h.sort_values(["passage_id", "_o"]).drop_duplicates("passage_id").drop(columns="_o").reset_index(drop=True)


def human_soft(human: pd.DataFrame, target: "Target", exclude: Iterable[str] = ()) -> tuple[np.ndarray, np.ndarray]:
    """Registered human label: per passage, the MEAN of the one-hot labels of every retained
    non-expert annotator (overlap pairs average to 0.5/0.5 on disagreement). Returns (ids, Y)."""
    h = human[~human.annotator.isin(set(exclude))]
    codes = target.fn(h)
    oh = onehot(codes, target.K)
    pid, inv = np.unique(h.passage_id.values, return_inverse=True)
    S = np.zeros((len(pid), target.K))
    np.add.at(S, inv, oh)
    return pid, S / np.bincount(inv)[:, None]


# ------------------------------------------------------------------ design

def _era(decade: np.ndarray) -> np.ndarray:
    return np.array(ERAS3, dtype=object)[np.searchsorted([1850, 1885], decade, side="right")]


def audit_design(labels: pd.DataFrame, human: pd.DataFrame, frame: pd.DataFrame | None = None,
                 teaching_authors: set | None = None, tol: float = 0.01,
                 labelled_ids: set | None = None) -> np.ndarray:
    """First-order audit inclusion probability for each row of `labels` (0 = not in the audit pool).

    Preferred: `frame` = audit_frame.parquet written by select_annotation.draw_audit at selection time.
    Fallback: re-derive cells (era x predicted group x split, random stratum, excluding teaching
    authors) from `labels`; this is only valid if `labels` are the labels used at selection time,
    so N_cell is checked against human.weight * n_cell and a ValueError is raised on mismatch.
    """
    if frame is not None and len(frame):
        fr = frame[["passage_id", "audit_cell", "pi_audit"]] if "audit_cell" in frame else frame
        if labelled_ids is not None and "audit_cell" in fr:
            # registered rule: pi_cell = (# pool passages in the cell with a retained human label) /
            # N_cell. Valid when label loss (annotator exclusion, skips) is random within the cell,
            # which random assignment of items to annotators guarantees for exclusions.
            N = fr.groupby("audit_cell").size()
            n = fr[fr.passage_id.isin(labelled_ids)].groupby("audit_cell").size().reindex(N.index, fill_value=0)
            fr = fr.assign(pi_audit=fr.audit_cell.map(n / N).values)
        pi = labels[["passage_id"]].merge(fr[["passage_id", "pi_audit"]], on="passage_id", how="left").pi_audit
        return pi.fillna(0.0).values
    from analysis.stats.simulate import group_vec
    teach = teaching_authors or set()
    cell = pd.Series(_era(labels.decade.values), index=labels.index).astype(str) + "|" + group_vec(labels) + "|" + labels.split.astype(str)
    in_pool = (labels.stratum.values == "random") & ~labels.author_key.isin(teach).values
    h = resolve_human(human)
    n_cell = h.groupby("audit_cell").size()
    N_from_w = (h.groupby("audit_cell").weight.first() * n_cell)
    N_derived = cell[in_pool].value_counts()
    splits = set(labels.split.astype(str))
    N_from_w = N_from_w[[c.rsplit("|", 1)[-1] in splits for c in N_from_w.index]]
    common = N_from_w.index.intersection(N_derived.index)
    if len(common) < len(N_from_w) or len(common) < len(N_derived) or \
            (np.abs(N_derived[common] / N_from_w[common] - 1) > tol).any():
        raise ValueError("audit cells re-derived from labels do not match human.weight; "
                         "pass audit_frame.parquet (labels were probably relabelled after selection)")
    pi = cell.map(n_cell / N_from_w).fillna(0.0).values
    return np.where(in_pool, pi, 0.0)


# ------------------------------------------------------------------ pseudo-outcomes

def _fold_ids(keys: pd.Series, k: int, seed: int) -> np.ndarray:
    codes, uniq = pd.factorize(keys)
    perm = np.random.default_rng(seed).permutation(len(uniq)) % k
    return perm[codes]


def calibration_g(yhat_code: np.ndarray, Y: np.ndarray, w: np.ndarray, strata: np.ndarray | None,
                  K: int, prior: float = 1.0) -> Callable[[np.ndarray, np.ndarray | None], np.ndarray]:
    """g(j, s) = smoothed weighted P(Y = k | LLM = j [, stratum s]) from audited rows (weights 1/pi
    normalised to the labelled n). Prior: `prior` pseudo-counts on the LLM's own label, and strata
    shrink to the pooled table with strength 2*prior."""
    w = w / w.mean() if len(w) else w
    pooled = np.zeros((K, K)) + prior * np.eye(K)
    np.add.at(pooled, yhat_code, Y * w[:, None])
    pooled_p = pooled / pooled.sum(1, keepdims=True)
    tabs = {}
    if strata is not None:
        for s in np.unique(strata):
            m = strata == s
            t = 2 * prior * pooled_p.copy()
            np.add.at(t, yhat_code[m], Y[m] * w[m, None])
            tabs[s] = t / t.sum(1, keepdims=True)

    def g(j: np.ndarray, s: np.ndarray | None = None) -> np.ndarray:
        if s is None or not tabs:
            return pooled_p[j]
        out = pooled_p[j].copy()
        for key, t in tabs.items():
            m = s == key
            out[m] = t[j[m]]
        return out
    return g


def pseudo_outcomes(Yhat_code: np.ndarray, Y_code: np.ndarray, labelled: np.ndarray, pi: np.ndarray, K: int,
                    method: str = "raw", strata: np.ndarray | None = None, folds: np.ndarray | None = None,
                    ) -> np.ndarray:
    """DSL pseudo-outcomes (n x K). Y_code (codes, or an n x K soft-label matrix) is used only where
    labelled; pi > 0 required there.

    method: "raw"     g = one-hot LLM label (DSL with the LLM as predictor; equals weighted PPI)
            "calib"   g = cross-fitted P(Y | LLM label) pooled
            "calib_s" g = cross-fitted P(Y | LLM label, stratum) (e.g. era), shrunk to pooled
            "naive"   no correction (model labels as truth)
            "oracle"  Y for every row (needs Y_code everywhere; simulation only)
    """
    if method == "oracle":
        return onehot(Y_code, K)
    Yh = onehot(Yhat_code, K)
    if method == "naive":
        return Yh
    if np.any(labelled & (pi <= 0)):
        raise ValueError("labelled passages with pi_audit == 0")
    lab = labelled & (pi > 0)
    Y = np.zeros_like(Yh)
    if np.ndim(Y_code) == 2:                 # soft human labels (annotator mean), rows sum to 1
        Y[lab] = Y_code[lab]
    else:
        Y[lab] = onehot(Y_code[lab], K)
    if method == "raw":
        G = Yh
    elif method in ("calib", "calib_s"):
        if folds is None:
            raise ValueError("calibration needs cross-fitting folds")
        G = np.empty_like(Yh)
        s_all = strata if method == "calib_s" else None
        for f in np.unique(folds):
            tr = lab & (folds != f)
            te = folds == f
            g = calibration_g(Yhat_code[tr], Y[tr], 1 / pi[tr], None if s_all is None else s_all[tr], K)
            G[te] = g(Yhat_code[te], None if s_all is None else s_all[te])
    else:
        raise ValueError(method)
    out = G.copy()
    r = np.where(lab, 1 / np.where(lab, pi, 1), 0.0)
    out += r[:, None] * (Y - G) * lab[:, None]
    return out


# ------------------------------------------------------------------ work-level data

WORK_COLS = ["work_id", "author_key", "year", "decade", "genre", "origin", "split"]
OPT_WORK_COLS = ["n_words", "date_confidence", "memorization", "setting_period", "work_weight", "canonical"]
# work_weight: 1 / P(work labelled) under adaptive stopping (cell = decade x stratum closes early,
# whole works in seeded order), so closed decades are not under-weighted. Default 1.


@dataclass
class WorkData:
    """Work-level table: covariates `cov` + per-target (n_works x K) DSL-corrected passage shares."""
    cov: pd.DataFrame
    Y: dict[str, np.ndarray] = field(default_factory=dict)
    method: str = "dsl"
    info: dict = field(default_factory=dict)

    def subset(self, mask) -> "WorkData":
        mask = np.asarray(mask, bool)
        return WorkData(self.cov[mask].reset_index(drop=True), {k: v[mask] for k, v in self.Y.items()},
                        self.method, dict(self.info))

    def with_years(self, year: np.ndarray) -> "WorkData":
        cov = self.cov.copy()
        cov["year"] = np.asarray(year)
        cov["decade"] = cov.year // 10 * 10
        return WorkData(cov, self.Y, self.method, dict(self.info))

    def __len__(self) -> int:
        return len(self.cov)


def prepare(labels: pd.DataFrame, human: pd.DataFrame | None = None, frame: pd.DataFrame | None = None,
            targets: Iterable[str] = ("locus", "comm_cause", "distance", "darkness", "comm_infra", "night"),
            method: str = "dsl", g: str = "calib", truth: pd.DataFrame | None = None,
            split: str | None = "confirmation", strata: Iterable[str] = ("random",),
            teaching_authors: set | None = None, n_folds: int = 5, seed: int = 0,
            human_mode: str = "mean", exclude_annotators: Iterable[str] = (),
            recompute_pi: bool = True) -> WorkData:
    """Build the work-level DSL table used by every model.

    method: "dsl" (default), "naive" (LLM labels as truth), "oracle" (truth table, simulation only).
    g:      DSL predictor: "raw" | "calib" | "calib_s" (era-stratified calibration).
    human_mode: "mean" (registered: mean one-hot over retained annotators, soft) | "resolve" (one
            row per passage: adjudicated > teacher > first).
    exclude_annotators: expert-reference coder(s) (e.g. "teacher") and annotators excluded by the
            registered kappa rule (annotators.exclusions); their rows never enter DSL.
    recompute_pi: pi_cell = retained-labelled / N_cell from the frame (see audit_design).
    Passages with pi_audit = 0 (outside the audit pool: teaching authors, enrichment strata unless
    the frame covers them) are dropped for DSL - DSL needs positivity - and counted in info.
    """
    lab = labels
    if split is not None:
        lab = lab[lab.split == split]
    if strata is not None:
        lab = lab[lab.stratum.isin(list(strata))]
    lab = lab.reset_index(drop=True)
    info: dict = {"n_passages_in": len(lab)}
    if method == "dsl":
        if human is None:
            raise ValueError("DSL needs human labels")
        excl = set(exclude_annotators)
        hum = human[~human.annotator.isin(excl)]
        ids = set(hum.passage_id) if (recompute_pi and frame is not None) else None
        pi = audit_design(lab, hum, frame, teaching_authors, labelled_ids=ids)
        keep = pi > 0
        info["n_dropped_pi0"] = int((~keep).sum())
        lab, pi = lab[keep].reset_index(drop=True), pi[keep]
        h = resolve_human(hum)
        h = h[h.passage_id.isin(lab.passage_id)]
        pos = pd.Series(np.arange(len(lab)), index=lab.passage_id)
        hidx = pos.loc[h.passage_id].values
        labelled = np.zeros(len(lab), bool)
        labelled[hidx] = True
        info["n_labelled"] = int(labelled.sum())
        folds = _fold_ids(lab.author_key, n_folds, seed)
        era_s = _era(lab.decade.values)
    elif method == "oracle":
        if truth is None:
            raise ValueError("oracle needs truth")
        tpos = truth.set_index("passage_id")
        tlab = tpos.loc[lab.passage_id].reset_index()
    Ys: dict[str, np.ndarray] = {}
    for tname in targets:
        T = TARGETS[tname]
        if method == "naive":
            Yt = onehot(T.fn(lab), T.K)
        elif method == "oracle":
            Yt = onehot(T.fn(tlab), T.K)
        else:
            yhat = T.fn(lab)
            if not all(c in h.columns for c in T.human_fields):
                Yt = onehot(yhat, T.K)       # no human labels for this target: model labels, flagged
                info[f"{tname}_uncorrected"] = True
            else:
                if human_mode == "mean":
                    sid, S = human_soft(hum[hum.passage_id.isin(lab.passage_id)], T)
                    ycode = np.zeros((len(lab), T.K))
                    ycode[pos.loc[sid].values] = S
                else:
                    ycode = np.zeros(len(lab), int)
                    ycode[hidx] = T.fn(h)
                Yt = pseudo_outcomes(yhat, ycode, labelled, pi, T.K, method=g, strata=era_s, folds=folds)
        Ys[tname] = Yt
    return aggregate_to_works(lab, Ys, method if method != "dsl" else f"dsl_{g}", info)


def aggregate_to_works(lab: pd.DataFrame, Ys: dict[str, np.ndarray], method: str = "dsl",
                       info: dict | None = None) -> WorkData:
    """Within-work Hajek weights (1/inclusion_prob, normalised per work); works weighted equally."""
    wid, wcodes = np.unique(lab.work_id.values, return_inverse=True)
    w = 1 / lab.inclusion_prob.values
    wsum = np.bincount(wcodes, w)
    wn = w / wsum[wcodes]
    agg = {}
    for k, Yt in Ys.items():
        A = np.zeros((len(wid), Yt.shape[1]))
        np.add.at(A, wcodes, Yt * wn[:, None])
        agg[k] = A
    cols = WORK_COLS + [c for c in OPT_WORK_COLS if c in lab.columns]
    cov = lab.drop_duplicates("work_id").set_index("work_id").loc[wid].reset_index()[cols]
    cov["n_passages"] = np.bincount(wcodes)
    return WorkData(cov.reset_index(drop=True), agg, method, info or {})


def pseudo_outcomes_two_phase(Yhat2: np.ndarray, Y3: np.ndarray, Yh: np.ndarray, R3: np.ndarray, pi3: np.ndarray,
                              Rh: np.ndarray, pih3: np.ndarray, K: int) -> np.ndarray:
    """Nested two-phase DSL (recommended design): Tier-2 labels on all passages, a strong Tier-3
    model on a probability subsample (R3, pi3), humans on a probability subsample of that (Rh, pih3 =
    P(human | in phase 3)). Ytilde = Yhat2 + R3/pi3 (Y3 - Yhat2) + R3 Rh/(pi3 pih3) (Y - Y3);
    E[Ytilde] = Y. Y3 / Yh: integer codes or soft n x K matrices (read only where R3 / Rh). Also the
    registered expert-nested sensitivity analysis: phase 3 = non-expert mean, phase h = expert on a
    probability subsample of the audit."""
    A = onehot(Yhat2, K)
    B = np.zeros_like(A)
    C = np.zeros_like(A)
    m = R3 & Rh
    B[R3] = Y3[R3] if np.ndim(Y3) == 2 else onehot(Y3[R3], K)
    C[m] = Yh[m] if np.ndim(Yh) == 2 else onehot(Yh[m], K)
    out = A.copy()
    out[R3] += (B[R3] - A[R3]) / pi3[R3, None]
    out[m] += (C[m] - B[m]) / (pi3[m] * pih3[m])[:, None]
    return out


# ------------------------------------------------------------------ cluster-robust machinery

def cluster_sum(M: np.ndarray, clusters: np.ndarray) -> np.ndarray:
    codes, uniq = pd.factorize(pd.Series(clusters))
    out = np.zeros((len(uniq), M.shape[1]))
    np.add.at(out, codes, M)
    return out


def cluster_cov(scores: np.ndarray, clusters: np.ndarray) -> np.ndarray:
    """sum_c s_c s_c' with CR1 small-sample factor G/(G-1); scores already linearised."""
    S = cluster_sum(scores, clusters)
    G = len(S)
    return S.T @ S * (G / max(G - 1, 1))


@dataclass
class ShareResult:
    table: pd.DataFrame            # group, category, estimate, se, lo, hi
    est: np.ndarray                # (n_groups, n_cats)
    cov: np.ndarray                # full covariance of vec(est) (row-major)
    groups: list
    cats: list
    infl: np.ndarray               # (n_clusters, n_groups*n_cats) cluster influence (for jackknife)

    def contrast(self, a, b, cat) -> tuple[float, float]:
        """est[b, cat] - est[a, cat] with SE."""
        ia, ib = self.groups.index(a), self.groups.index(b)
        ic = self.cats.index(cat)
        nc = len(self.cats)
        v = np.zeros(self.cov.shape[0])
        v[ib * nc + ic], v[ia * nc + ic] = 1, -1
        return float(self.est[ib, ic] - self.est[ia, ic]), float(np.sqrt(v @ self.cov @ v))


def ratio_shares(wd: WorkData, target: str, num: Iterable[int], den: Iterable[int] | None,
                 by: np.ndarray, cluster: str = "author_key", weights: np.ndarray | None = None,
                 level: float = 0.95) -> ShareResult:
    """Ratio-of-means shares per group: for each num category k, sum_w a_w Y_wk / sum_w a_w D_w,
    D_w = sum_{den} Y_w (den=None -> D_w = 1, i.e. prevalence). Linearised (delta-method) cluster-
    robust covariance across ALL groups jointly, so contrasts between groups get correct SEs.
    """
    Y = wd.Y[target]
    num = list(num)
    if weights is None and "work_weight" in wd.cov:
        weights = wd.cov.work_weight.values
    a = np.ones(len(Y)) if weights is None else np.asarray(weights, float)
    Dw = Y[:, list(den)].sum(1) if den is not None else np.ones(len(Y))
    by = np.asarray(by)
    groups = [g for g in pd.unique(by) if g is not None]
    try:
        groups = sorted(groups)
    except TypeError:
        pass
    nc = len(num)
    est = np.zeros((len(groups), nc))
    Z = np.zeros((len(Y), len(groups) * nc))
    for gi, g in enumerate(groups):
        m = by == g
        Dsum = (a[m] * Dw[m]).sum()
        for ci, k in enumerate(num):
            th = (a[m] * Y[m, k]).sum() / Dsum
            est[gi, ci] = th
            Z[m, gi * nc + ci] = a[m] * (Y[m, k] - th * Dw[m]) / Dsum
    cl = wd.cov[cluster].values
    infl = cluster_sum(Z, cl)
    G = len(infl)
    cov = infl.T @ infl * (G / max(G - 1, 1))
    se = np.sqrt(np.diag(cov)).reshape(est.shape)
    z = stats.norm.ppf(0.5 + level / 2)
    rows = [{"group": g, "category": k, "estimate": est[gi, ci], "se": se[gi, ci],
             "lo": est[gi, ci] - z * se[gi, ci], "hi": est[gi, ci] + z * se[gi, ci]}
            for gi, g in enumerate(groups) for ci, k in enumerate(num)]
    return ShareResult(pd.DataFrame(rows), est, cov, groups, num, infl)


# ------------------------------------------------------------------ multinomial logit on soft outcomes

@dataclass
class MNLFit:
    beta: np.ndarray          # (p, K-1), category 0 = reference
    cov: np.ndarray           # ((K-1)*p)^2, ordering vec(beta.T) i.e. category-major
    bread_inv: np.ndarray
    scores: np.ndarray        # (n, (K-1)*p) per-observation estimating-function contributions
    clusters: np.ndarray
    converged: bool
    n_iter: int
    columns: list
    link: str = "logit"

    def probs(self, X: np.ndarray) -> np.ndarray:
        if self.link == "identity":
            L = X @ self.beta
            return np.c_[1 - L.sum(1), L]
        return mnl_probs(X, self.beta)

    def mean_and_grad(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """sum over rows of fitted category probabilities (K,) and its gradient (K, (K-1)p)."""
        p, Km1 = self.beta.shape
        K = Km1 + 1
        dA = np.zeros((K, Km1 * p))
        if self.link == "identity":
            P = self.probs(X)
            xs = X.sum(0)
            for j in range(1, K):
                dA[j, (j - 1) * p:j * p] = xs
                dA[0, (j - 1) * p:j * p] = -xs
            return P.sum(0), dA
        P = mnl_probs(X, self.beta)
        for c in range(K):
            for j in range(1, K):
                v = P[:, c] * ((c == j) - P[:, j])
                dA[c, (j - 1) * p:j * p] = v @ X
        return P.sum(0), dA

    def cluster_influence(self) -> np.ndarray:
        """(n_clusters, (K-1)p): beta_{-c} ~= beta - infl_c (one-step leave-cluster-out)."""
        U = cluster_sum(self.scores, self.clusters)
        return U @ self.bread_inv.T


def mnl_probs(X: np.ndarray, beta: np.ndarray) -> np.ndarray:
    eta = np.c_[np.zeros(len(X)), X @ beta]
    eta -= eta.max(1, keepdims=True)
    e = np.exp(eta)
    return e / e.sum(1, keepdims=True)


def fit_mnlogit(X: np.ndarray, Y: np.ndarray, weights: np.ndarray | None = None,
                clusters: np.ndarray | None = None, tol: float = 1e-9, max_iter: int = 100,
                ridge: float = 1e-8, columns: list | None = None) -> MNLFit:
    """Multinomial (K>2) or binary (K=2) logit with soft outcomes Y (rows sum to 1; entries may be
    negative / > 1 as DSL pseudo-outcomes). Estimating equations sum_i w_i x_i (y_ik - p_ik) = 0,
    solved by damped Newton; the Hessian does not depend on Y, so the objective stays concave.
    Cluster-robust sandwich A^-1 B A^-1 (CR1). Category 0 is the reference."""
    n, p = X.shape
    K = Y.shape[1]
    w = np.ones(n) if weights is None else np.asarray(weights, float)
    cl = np.arange(n) if clusters is None else np.asarray(clusters)
    if np.max(np.abs(Y.sum(1) - 1)) > 1e-6:
        raise ValueError("soft outcomes must sum to 1 per row")
    beta = np.zeros((p, K - 1))
    # start from intercept-only marginal shares when feasible
    mbar = (w[:, None] * Y).sum(0) / w.sum()
    if np.all(mbar > 0) and np.allclose(X[:, 0], 1):
        beta[0] = np.log(mbar[1:] / mbar[0])

    def objective(b):
        eta = np.c_[np.zeros(n), X @ b]
        mx = eta.max(1, keepdims=True)
        lse = (mx[:, 0] + np.log(np.exp(eta - mx).sum(1)))
        return float((w * ((Y * eta).sum(1) - lse)).sum())

    def grad_hess(b):
        P = mnl_probs(X, b)[:, 1:]
        R = Y[:, 1:] - P
        g = (X * w[:, None]).T @ R          # p x (K-1)
        H = np.zeros(((K - 1) * p, (K - 1) * p))
        Xw = X * w[:, None]
        for j in range(K - 1):
            for k in range(j, K - 1):
                v = P[:, j] * ((j == k) - P[:, k])
                blk = (Xw * v[:, None]).T @ X
                H[j * p:(j + 1) * p, k * p:(k + 1) * p] = blk
                H[k * p:(k + 1) * p, j * p:(j + 1) * p] = blk
        return g, H, P

    converged = False
    obj = objective(beta)
    it = 0
    for it in range(1, max_iter + 1):
        g, H, _ = grad_hess(beta)
        gv = g.T.reshape(-1)
        step = np.linalg.solve(H + ridge * np.eye(len(H)), gv)
        t = 1.0
        while True:
            nb = beta + t * step.reshape(K - 1, p).T
            nobj = objective(nb)
            if nobj >= obj - 1e-12 or t < 1e-6:
                break
            t /= 2
        beta, obj = nb, nobj
        if np.max(np.abs(t * step)) < tol or np.max(np.abs(gv)) < tol:
            converged = True
            break
    g, H, P = grad_hess(beta)
    # divergence (MLE does not exist, e.g. negative pseudo-outcome totals in a sparse cell): fitted
    # linear predictors run off to +-inf or the score is not ~0 at the end
    if np.max(np.abs(X @ beta)) > 30 or np.max(np.abs(g)) > 1e-6 * max(w.sum(), 1):
        converged = False
    else:
        converged = True
    Hinv = np.linalg.pinv(H)
    R = Y[:, 1:] - P
    scores = np.concatenate([(X * (w * R[:, j])[:, None]) for j in range(K - 1)], axis=1)
    B = cluster_cov(scores, cl)
    cov = Hinv @ B @ Hinv
    return MNLFit(beta, cov, Hinv, scores, cl, converged, it, columns or [f"x{i}" for i in range(p)])


def fit_linear(X: np.ndarray, Y: np.ndarray, weights: np.ndarray | None = None,
               clusters: np.ndarray | None = None, columns: list | None = None) -> MNLFit:
    """Linear (identity-link) DSL regression of each non-reference category share on X: the
    estimating equations are linear in the pseudo-outcomes, so a solution always exists however
    large the 1/pi corrections (Egami et al.'s canonical case). Same interface as fit_mnlogit."""
    n, p = X.shape
    K = Y.shape[1]
    w = np.ones(n) if weights is None else np.asarray(weights, float)
    cl = np.arange(n) if clusters is None else np.asarray(clusters)
    Xw = X * w[:, None]
    A = Xw.T @ X
    Ainv = np.linalg.pinv(A)
    beta = Ainv @ (Xw.T @ Y[:, 1:])
    R = Y[:, 1:] - X @ beta
    scores = np.concatenate([X * (w * R[:, j])[:, None] for j in range(K - 1)], axis=1)
    Hinv = np.kron(np.eye(K - 1), Ainv)
    cov = Hinv @ cluster_cov(scores, cl) @ Hinv
    return MNLFit(beta, cov, Hinv, scores, cl, True, 1, columns or [f"x{i}" for i in range(p)], "identity")


def pseudo_outcomes_anchored(yhat: np.ndarray, peer_soft: np.ndarray, R3: np.ndarray, pi3: np.ndarray,
                             expert: np.ndarray, Rh: np.ndarray, pih: np.ndarray, K: int,
                             folds: np.ndarray, strata: np.ndarray | None = None) -> np.ndarray:
    """Expert-anchored three-level DSL (registered v0.5). Estimand = the EXPERT construct.

    level 1: model labels on every passage (yhat codes);
    level 2: peer annotator-mean soft labels on the audit (R3, pi3 = audit probability);
    level 3: expert labels on a probability subsample of the audit (Rh, pih = P(expert | audit)).

      Ytilde = g1(yhat) + R3/pi3 (g2 - g1) + R3 Rh/(pi3 pih) (onehot(expert) - g2)

    g2 = cross-fitted multinomial logit of the expert label on (peer soft label, model label), fitted
    on expert items in the other folds: it uses the peers' information optimally, so the expert term
    has the smallest residual. g1 = cross-fitted calibration of g2 on the model label (by stratum).
    E[Ytilde] = expert label for ANY g1, g2 (cross-fitted), so peer noise, peer bias and annotator
    exclusions cannot bias the estimate; they only change its variance."""
    n = len(yhat)
    Yh1 = onehot(yhat, K)
    X = np.c_[np.ones(n), peer_soft[:, 1:], Yh1[:, 1:]]
    g2 = np.zeros((n, K))
    g1 = np.zeros((n, K))
    E = np.zeros((n, K))
    E[Rh] = onehot(expert[Rh], K)
    for f in np.unique(folds):
        tr_e = Rh & R3 & (folds != f)
        te = folds == f
        # g2: logit with a light ridge (few hundred training items)
        fit = fit_mnlogit(X[tr_e], E[tr_e], ridge=1e-3) if tr_e.sum() > 20 else None
        if fit is None or not fit.converged:
            # fall back: smoothed table P(expert | argmax peer)
            pk = np.argmax(peer_soft, 1)
            t = np.eye(K) + 0.0
            np.add.at(t, pk[tr_e], E[tr_e])
            g2[te] = (t / t.sum(1, keepdims=True))[pk[te]]
        else:
            g2[te] = mnl_probs(X[te], fit.beta)
    for f in np.unique(folds):
        tr = R3 & (folds != f)
        te = folds == f
        g = calibration_g(yhat[tr], g2[tr], 1 / pi3[tr], None if strata is None else strata[tr], K)
        g1[te] = g(yhat[te], None if strata is None else strata[te])
    out = g1.copy()
    out[R3] += (g2[R3] - g1[R3]) / pi3[R3, None]
    m = R3 & Rh
    out[m] += (E[m] - g2[m]) / (pi3[m] * pih[m])[:, None]
    return out


# ------------------------------------------------------------------ PPI (cross-check for means)

@dataclass
class PPIResult:
    estimate: float
    se: float
    lo: float
    hi: float
    lam: float


def ppi_mean(yhat_all: np.ndarray, y_lab: np.ndarray, yhat_lab: np.ndarray,
             strata_all: np.ndarray | None = None, strata_lab: np.ndarray | None = None,
             lam: float | None = 1.0, level: float = 0.95) -> PPIResult:
    """Prediction-powered mean (Angelopoulos et al. 2023), optionally stratified and power-tuned.

    theta = mean_N(lam*yhat) + sum_h (N_h/N) mean_{n_h}(y - lam*yhat)
    var   = lam^2 var_N(yhat)/N + sum_h (N_h/N)^2 var_{n_h}(y - lam*yhat)/n_h
    lam=1 is classic PPI; lam=None picks the variance-minimising PPI++ lambda. With strata given,
    labelled units are a stratified SRS (as in select_annotation's audit); without, a uniform SRS.
    Passage-level, so it ignores within-work clustering: a cross-check, not the confirmatory SE.
    """
    yhat_all, y_lab, yhat_lab = map(lambda a: np.asarray(a, float), (yhat_all, y_lab, yhat_lab))
    N = len(yhat_all)
    if strata_all is None:
        strata_all = np.zeros(N, int)
        strata_lab = np.zeros(len(y_lab), int)
    hs = np.unique(strata_lab)
    Wh = np.array([(strata_all == h).mean() for h in hs])
    if lam is None:
        # minimise var over lam: lam* = sum Wh^2 cov_h(y,yhat)/n_h / (var(yhat)/N + sum Wh^2 var_h(yhat)/n_h)
        num = den = 0.0
        for W, h in zip(Wh, hs):
            m = strata_lab == h
            nh = m.sum()
            if nh > 1:
                num += W ** 2 * np.cov(y_lab[m], yhat_lab[m])[0, 1] / nh
                den += W ** 2 * yhat_lab[m].var(ddof=1) / nh
        den += yhat_all.var(ddof=1) / N
        lam = float(np.clip(num / den, 0, 1)) if den > 0 else 1.0
    theta = lam * yhat_all.mean()
    var = lam ** 2 * yhat_all.var(ddof=1) / N
    for W, h in zip(Wh, hs):
        m = strata_lab == h
        r = y_lab[m] - lam * yhat_lab[m]
        theta += W * r.mean()
        var += W ** 2 * (r.var(ddof=1) if m.sum() > 1 else 0.0) / m.sum()
    se = float(np.sqrt(var))
    z = stats.norm.ppf(0.5 + level / 2)
    return PPIResult(float(theta), se, theta - z * se, theta + z * se, lam)


def dsl_mean_passage(Ytilde_col: np.ndarray, level: float = 0.95) -> tuple[float, float]:
    """Passage-level DSL mean with iid SE (for the PPI cross-check only)."""
    n = len(Ytilde_col)
    return float(Ytilde_col.mean()), float(Ytilde_col.std(ddof=1) / np.sqrt(n))
