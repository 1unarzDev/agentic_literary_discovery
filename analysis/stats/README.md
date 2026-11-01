# analysis/stats: DSL, confirmatory models, battery, power, validation

Run everything from the repo root (the modules import as `analysis.stats.*`):

```
uv run pytest analysis/stats                                    # tests (~2 min)
uv run python -m analysis.stats.simulate OUT_DIR                # synthetic labels/human/audit_frame parquet
OMP_NUM_THREADS=1 uv run python -m analysis.stats.validate --reps 300 --procs 16   # coverage + figs/dsl_coverage.png
OMP_NUM_THREADS=1 uv run python -m analysis.stats.power --reps 3 --procs 16        # MDE grid -> out/power_mde.csv
OMP_NUM_THREADS=1 uv run python -m analysis.stats.power --curve --reps 12          # audit-size curve
uv run python -m analysis.stats.battery labels.parquet human.parquet keywords.csv \
    --frame audit_frame.parquet [--alt alt_labels.parquet] [--seg seg250.parquet --seg seg500.parquet] \
    [--rep-labels eltec_labels.parquet [--rep-human ...]]       # confirmatory table + battery + verdicts
```

Set `OMP_NUM_THREADS=1` for the multiprocess runs, because BLAS threads oversubscribe the cores otherwise.

| file | what |
|---|---|
| `simulate.py` | Synthetic corpora with known parameters (authors → works → passages). Has era-varying LLM confusion, genre-mix drift, author/work random effects and enrichment strata. The audit is drawn with `select_annotation.draw_audit`. |
| `dsl.py` | Targets, audit design (π), DSL pseudo-outcomes (raw / cross-fitted calibration / era-stratified calibration / two-phase), work aggregation, ratio shares with cluster-robust linearised SEs, and multinomial-logit and identity-link regressions with a cluster sandwich. Stratified PPI / PPI++ for means. |
| `models.py` | H1, H2a–c, H3, Holm, shift-share decomposition, fixed-composition trend. |
| `battery.py` | The 9 checks, the verdict rule, and a CLI for real data. |
| `power.py` | MDE simulation (single-phase DSL, the H1-aligned allocation, and two-phase Tier-3 + human). |
| `validate.py` | Coverage study and the methods figure. |

## Input schemas and assumptions

**labels.parquet**, one row per passage:

- `passage_id, work_id, author_key, decade, year, genre, origin, split, stratum, inclusion_prob, has_obstacle, domains (list[str]), locus, failure_cause, night_function, technology_named, message_valence, confidence, quote_status`.
- Optional work-level columns, used if present:
  - `n_words`: needed for the log-length covariate; the covariate is omitted if the column is missing.
  - `date_confidence` (high/medium/low): battery check 4.
  - `memorization` (name-cloze score): battery check 5.
  - `setting_period`.
- Assumptions:
  - `inclusion_prob` is the passage's first-order inclusion probability **within its work**, over the union of the sampling frames (random backbone ∪ enrichment). Within-work Hájek weights are `1/inclusion_prob`, normalised to sum to 1 per work. Works are then weighted equally (the work is the unit). For the random backbone this is just 1/24 per passage.
  - `has_obstacle == "yes"` is required for every obstacle-type target. `insufficient_context` counts as "not an obstacle" (category 0).
  - `locus` outside the three codebook values counts as category 0.
  - `failure_cause` and `night_function` use the codebook strings, and `"none"` means not applicable.
  - The primary analysis **excludes low-confidence dates and historical-setting works before calling `prepare`** (filter upstream; `prepare` does not drop them).

**human.parquet**, one row per (passage, annotator):

- `passage_id, annotator, has_obstacle, domains, locus, failure_cause, audit_cell, weight`. `night_function` is optional.
- Resolution: an `annotator == "adjudicated"` row wins. Otherwise the teacher's row wins, since the teacher adjudicates (plan §4.5). Otherwise the first row is used. Pass a different `prefer` order to `resolve_human` if needed.
- `weight` = N_cell / n_cell exactly as `select_annotation.py` writes it.

**audit_frame.parquet** (new; `select_annotation.py` now writes it): `passage_id, audit_cell, pi_audit` for **every** passage in the audit pool, not just the audited ones.

- DSL needs π for unaudited passages too.
- Without the frame, `dsl.audit_design` re-derives the cells from `labels.parquet` (era × predicted group × split, random stratum, minus teaching authors). It raises if the re-derived N_cell disagree with `weight × n_cell`, which is what happens after the Nov 8 relabel. **Persist the frame at selection time (Thu Nov 5).**
- I refactored `select_annotation.py` minimally: the audit draw moved into `draw_audit()`, with identical RNG use, and the frame is now written. Its behaviour is otherwise unchanged.

**keywords.csv** (H3): `decade, group (comm|travel|dark), kw_rate`. The rate is per 10k words, from HTRC EF 2.0 and our corpus. Pairs:

| group | function target |
|---|---|
| comm | communication failure by infrastructure or accidental loss |
| travel | DISTANCE_TRAVEL obstacle |
| dark | DARKNESS_VISIBILITY obstacle |

All three function targets are prevalences per passage.

**Alternate-label / segmentation tables** (battery 6–7) use the labels schema. They are compared **naively** against the primary model's naive labels on the same works. Variant segmentations have no audited passages, so DSL cannot correct them. The check asks whether the model family or segmentation changes the answer, holding everything else fixed.

## Positivity (DSL needs π_audit > 0 for every analysed passage)

- The audit pool is the random stratum only. **Enrichment passages therefore have π_audit = 0, so DSL cannot use them.** `prepare` analyses the random stratum by default and reports `n_dropped_pi0`. Using enrichment strata needs audit coverage of them (recommended for H2, see the prereg).
- Teaching authors (Discovery only) have π = 0, so Discovery-half DSL estimates describe the non-teaching population.
- Humans do not label `night_function`. The H2c night component is therefore **not** DSL-corrected (`info["night_uncorrected"]`) unless a probability-sampled check adds human night labels.

## Modelling choices worth knowing

- **Link.** The pre-registered link is the logit (multinomial for H1/H2a/night, binary for H2b/H2c-darkness). With small audits, DSL pseudo-outcomes (±1/π ≈ ±1000) can make a category's total negative in a sparse region (the early spline tail, a small genre). The logit MLE then does not exist. `fit_target` detects non-convergence and falls back to the identity link (`fit.n_iter == -1`), which always has a solution. `models.LINK["default"] = "identity"` switches every model. The validation reports how often the fallback happens.
- **Estimand.** The era contrast is a g-computation (standardised) share: the average of fitted probabilities over a fixed reference covariate table × every year in the window, then the ratio of obstacle categories. The default reference is the analysis works (a 3,000-work fixed-seed subsample). Holding the genre × origin × length mix fixed is what "within genre" means operationally.
- **SEs.** Cluster-robust (CR1) by author, since works nest in authors. Ratio shares use the same linearisation jointly across groups, so contrasts get correct covariances.
- **Tests.** Two-sided p-values, but a claim needs the pre-declared sign (`Component.p_dir`). Multi-part hypotheses (H1: material falls **and** internal rises; H2c: darkness falls **and** night danger/concealment falls) use the intersection-union p = max of the parts.
- **H3.**
  - Statistic: D = 1 − r between z-scored decade series, averaged over the three pairs.
  - Test: H0 is perfect positive tracking (the true function series equals the keyword series in z-units) plus DSL sampling error, via a parametric bootstrap.
  - CI: a circular moving-block bootstrap (block = 3 decades), with sampling error added to each replicate.
  - Decades with fewer than 30 works are dropped.
- **Permutation (battery 8).** Permuting dates *within author × genre blocks* (the plan's wording) leaves between-author chronology intact. Its "null" distribution centres on the observed effect (shown in `test_battery.py`). The default permutes **author-level date profiles among authors within genre** instead. `mode="literal"` is kept for reporting.
- **Leave-one-author-out** uses the one-step influence approximation β₋ₐ ≈ β̂ − A⁻¹Uₐ, which is exact to first order for M-estimators. H3 has no influence matrix, so it uses a 20-group delete-a-group jackknife.
- A GLMM with an author random effect is not implemented. Cluster-robust GEE-type inference is the pre-registered primary. A GLMM can be added as a sensitivity check on naive labels only, because DSL soft outcomes are not a likelihood.

## Outputs

- `out/coverage*.csv`: coverage study.
- `out/power_mde*.csv`: MDE in pp (`mde_pp_a05`, `mde_pp_a01`).
- `figs/dsl_coverage.png`: methods figure.
- `out/confirmatory/`: real-data runs.
