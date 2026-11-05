# analysis/stats: DSL, confirmatory models, battery, power, validation

Run everything from the repo root (the modules import as `analysis.stats.*`):

```
uv run pytest analysis/stats                                    # tests (~1 min)
uv run python -m analysis.stats.simulate OUT_DIR                # synthetic labels/human/audit_frame parquet
OMP_NUM_THREADS=1 uv run python -m analysis.stats.validate --reps 250 --procs 8    # coverage + figs/dsl_coverage.png
OMP_NUM_THREADS=1 uv run python -m analysis.stats.power --reps 2 --procs 8         # MDE grid -> out/power_mde.csv
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

**Registered design, prereg v0.5. This supersedes the v0.3 notes below where they conflict.**

- **Audit draw (seal-safe).** `select_annotation.draw_audit_metadata(meta_conf, rng, n_target=1820)` draws on metadata only.
  - Strata are era (by year) × genre × canonical. The budget is balanced over era × canonical and proportional to N within.
  - `meta_conf` needs `passage_id, work_id, author_key, year, split, stratum, genre, canonical`.
  - `draw_audit(..., group_col=[...], balance_on=[...], metadata_only=True)` is the general form. It refuses label-derived strata.
  - `cell_table_hash(frame)` gives the hash to deposit.
- **Estimator.** The expert-anchored three-level DSL (`dsl.pseudo_outcomes_anchored`, `dsl.prepare_anchored`). The grad-student (`grad`) labels define the construct, and peers are the intermediate phase.
  - The expert items are a stratified **~50% subsample within audit cells (~900 of ~1,820)**, all of them also peer-labelled.
  - Teacher rows are descriptive only.
  - **Registered power: TF ≈ 0.70 at α = 0.05 (MDE ≈ 9 pp material, against a ~10 pp canon gap). H1 (secondary) has an MDE of ≈ 15 pp.** Source: `out/power_v05_expert.csv`, `efrac = 0.5`.
- **Population.** `models.apply_works_v2` maps `author_key` ← `author_group` and `split` ← `split_v2`, and keeps `primary_v2_capv2`. The CLI applies it when `--works data/work/works_v2.parquet` exists.
- **`select_annotation.main` is retired** and raises. Queues come from `analysis/build_annotation_queues.py` via `draw_audit_metadata`.
- **Family (REGISTERED, prereg v0.6).** `models.confirmatory()` defaults to `procedure="fallback"`.
  - TF (joint 2-df Wald, works-weighted, with the inwardness-index summary from `models.tf_statistics`) is tested at α₁ = 0.04.
  - H1 is tested at 0.01, or at 0.05 if TF rejects.
  - H1|canon and H1|non-canon are secondary (Holm).
  - TF-adult (`juvenile == False`) and TF-era-equal are registered sensitivities. TF-genre, H1-ML and composition are descriptive. H2a–c and H3 are estimation only.
  - `procedure="single"` reproduces v0.5.
- **Registration snapshot:** git tag `prereg-v0.6`. The audit frame `cell_table_hash` is `1b4580c7…24cc6` (40 cells, 1,801 items, 909 expert).
- **Models.** `models.two_fictions`. The symmetric `classify_h1` has the classes inward, outward, socialisation, de-socialisation and indeterminate. `models.attach_canon` reads `data/work/canon.parquet` (`work_id, canonical`).
- **Battery.** `battery.canon_permutation` serves the TF null. Replication is optional (n/a when missing).
- **Real-data CLI:**
  ```
  uv run python -m analysis.stats.battery labels.parquet human.parquet audit_frame.parquet \
      --keywords kw.csv --canon data/work/canon.parquet --works data/work/works_v2.parquet
  ```
- **Power and levers.**
  - `power_v05.py`, calibrated with `SimConfig.v05`; add `--expert-extra` for the expert-budget lever.
  - `levers.py`: model accuracy, Neyman allocation, contrasts, confusion correction and label count.

**Registered audit design (prereg v0.3)**:
- `draw_audit(lab_conf, teaching_authors, rng, n_target=1800, group_col="dgroup")`, where `dgroup = select_annotation.domain_group(row)`. The new `group_col` keyword defaults to `"group"`, so existing calls are unchanged.
- **Human label** = the mean one-hot over retained non-expert annotators (`dsl.human_soft`; `prepare(human_mode="mean")`).
- The expert (`teacher`) and any annotator excluded by the κ rule are passed as `exclude_annotators`. The rule is locus κ vs the expert < 0.40 on the 30 expert items (`annotators.py`).
- π is recomputed per cell from retained labels (`recompute_pi=True`).
- The battery CLI applies all of this and writes `annotator_agreement.csv` and `overlap_agreement.csv`.
- **H3's p-value is calibrated ×10** (`models.H3_P_INFLATE`).
- **H1 (prereg v0.4)** is a **two-sided 2-df Wald test** of (Δmaterial, Δinternal) = 0, E vs L, classified inward / outward / mixed (`models.h1`, `classify_h1`). `h1_mid_late` gives the descriptive M-vs-L contrast. `h1(two_sided=False)` is the v0.3 directional test. The battery re-checks the components whose CI excludes 0, against their observed signs.
- **Genre and standard.** The genre variable is `data/work/genre.parquet` (`models.attach_genre`). The standard population is `models.reference_covariates(works, genre)`: the primary set of both halves. The battery CLI uses both by default (`--genre`, `--works`).
- **Family:** H1 is the single primary test; H2a–c and H3 are Holm among themselves. H2c is darkness prevalence only; night function is exploratory (`h2c(include_night=True)`).
- Final-design power: `uv run python -m analysis.stats.power --final --reps 20`, written to `out/power_final.csv`. Add `--v04` for the two-sided H1 under the inward, pilot-like (`SimConfig.pilot_step`) and null truths, written to `out/power_final_v04.csv`.

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
- **Spline.** ns(year, df = 4) uses fixed knots at 1800/1850/1885/1905/1929 (`models.PREREG_KNOTS`). Quantile knots are badly placed in this late-heavy corpus.
- **Estimand.** The era contrast is a g-computation (standardised) share: the average of fitted probabilities over a fixed reference covariate table × the era's **empirical** work-year distribution, then the ratio of obstacle categories. Eras follow G0: E = 1800–1849, M = 1850–1884, L = 1885–1929, and H2b compares 1800–49 with 1850–84.
- **Work weights.** An optional `work_weight` column (1/P(work labelled) under adaptive stopping) is used by every estimator. The default reference is the analysis works (a 3,000-work fixed-seed subsample). Holding the genre × origin × length mix fixed is what "within genre" means operationally.
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
