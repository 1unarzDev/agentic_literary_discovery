# Pre-registration: What Stands in the Way (confirmatory analysis), DRAFT v0.2

**OSF registration hash:** `OSF-HASH-PLACEHOLDER` (fill in on registration; `ald sync` / `POST /v1/admin/unseal` refuse to unseal Confirmation results until this line holds the real hash)

- **Registration date:** _TBD (planned Sun–Mon Nov 8–9, 2026, after codebook v1.0 freeze and before unsealing)_
- **Template:** OSF Preregistration (secondary data / observational).
- **Status of data at registration:**
  - Discovery-half model labels, the human audit and teaching labels have been seen.
  - Confirmation-half model labels sit sealed under the R2 `sealed/` prefix and have not been read by any analyst.
  - The Confirmation human audit items are labeled blind: annotators see neither model labels nor metadata.
- **Code:**
  - `analysis/stats/` at commit _TBD_. Running `uv run python -m analysis.stats.battery` produces every number below.
  - Simulation validation: `analysis/stats/validate.py`.
  - Power: `analysis/stats/power.py`.
- **Related documents:**
  - `docs/plan/research_plan_v2.md` §3–4
  - `docs/data_quality.md`
  - `docs/codebook.md` (frozen at v1.0)
  - `docs/gates.md` (G0 decisions, made before any labels were seen)

---

## 1. Hypotheses (directions pre-declared)

Every hypothesis is tested on the **Confirmation half** (authors hashed 50/50, stratified by decade × origin × genre).

Eras, revised at G0 because PG is thin before 1840:

| Era | Years |
|---|---|
| E (early) | 1800–1849 |
| M (mid) | 1850–1884 |
| L (late) | 1885–1929 |

The study window is 1800–1929.

| ID | Hypothesis | Direction | Estimand (Confirmation half) |
|---|---|---|---|
| **H1** inward turn | Among plot obstacles, the material/external share falls **and** the internal/psychological share rises from E to L, holding the genre × origin × length mix fixed | Δ_material < 0 **and** Δ_internal > 0 | Standardised era shares of locus among obstacles; Δ = L − E for material and for internal |
| **H2a** communication | Among communication failures, intentional withholding rises relative to infrastructure + accidental loss | Δ > 0 | Standardised share withholding / (withholding + infrastructure + accidental_loss), L − E |
| **H2b** mobility | DISTANCE_TRAVEL obstacles become less prevalent after railway diffusion | Δ < 0 | Standardised prevalence per passage, 1850–1884 minus 1800–1849 (G0 window) |
| **H2c** darkness | DARKNESS_VISIBILITY prevalence falls **and** night's danger + concealment share falls | both Δ < 0 | (i) standardised prevalence, L − E; (ii) standardised share (danger + concealment) / (danger + concealment + intimacy + labor + leisure) among night passages, L − E |
| **H3** mention ≠ function | Decade keyword rates for technology terms do **not** track the corresponding obstacle-function rates | excess divergence > 0 | D = mean over 3 pairs of (1 − r) between z-scored decade series; excess = D − E_H0[D] |

H3 pairs (keyword group → function rate per passage):

| Keyword group | Terms | Function rate |
|---|---|---|
| comm | post / letter / telegram / telephone … | communication failures caused by infrastructure or accidental loss |
| travel | coach / railway / train / carriage … | DISTANCE_TRAVEL |
| dark | candle / lamp / gas / electric … | DARKNESS_VISIBILITY |

Keyword rates come from HTRC EF 2.0 plus our corpus, per 10k words, using the lexicon frozen in `research/history/` on _TBD_.

Not confirmatory, and reported descriptively only:
- the H2b "barrier → setting" function shift (the schema has no travel-function field);
- H2c's "earlier in urban settings" (there is no setting-location field);
- the social share in H1.

## 2. Design

- **Corpus.** English fiction 1800–1929 preserved in Project Gutenberg, after the `docs/data_quality.md` filters. At G0 that is 15,511 works, about 7,400–8,100 per half.
- **Primary analysis set:**
  - date confidence high or medium;
  - contemporary setting (historical novels are analysed separately);
  - at most 5 works per author per decade (seeded random choice);
  - non-teaching authors.
- **Unit.**
  - The **work** is the unit. Passage-level labels are aggregated to within-work Hájek-weighted shares, using weights 1/inclusion_prob normalised within the work.
  - Works are weighted equally, times the adaptive-stopping work weight (§3.3).
  - Authors are the clustering unit for all SEs, since works nest in authors.
- **Measurement.**
  - The pinned Tier-2 model labels every sampled passage (codebook v1.0).
  - Humans (student + teacher) label a probability sample (§3.4).
  - Every estimate is DSL-corrected toward the **human-label** construct.

## 3. Sampling plan

### 3.1 Passages
- **Random backbone.** 24 random ~350-word passages per work (seeded), with offsets and sha256. All confirmatory estimates use the random backbone only.
- **Enrichment.** Up to 24 extra passages per work from the comm / mobility / darkness lexicon strata (≤ 8 each), with union-of-frames inclusion probabilities recorded.
  - Enrichment passages are used for exemplars and descriptive deep dives.
  - They enter a confirmatory estimate **only if** the human audit samples them with known probability (§3.4, recommendation R3). DSL requires a positive audit inclusion probability for every analysed passage.

### 3.2 Existing data
- Model labels exist for the Discovery half.
- The Confirmation half has been labelled but is sealed.
- No Confirmation outcome has been viewed.
- Power and design decisions used Discovery-half prevalences, the G0 work counts and simulation only.

### 3.3 Adaptive stopping rule (compute, not humans)
- **Cells.** Labelling proceeds in seeded waves over cells = decade × stratum. Whole works are labelled in a seeded random order within each cell, so a cell's labelled works are a simple random sample of its works.
- **Closing rule.** A cell closes when all of the following hold:
  - the author-clustered 95% CI half-width for obstacle prevalence, computed from screen-stage labels, is ≤ 3.5 pp;
  - at least 60 works are labelled;
  - at least 30 authors are labelled.

  A cell also closes when it is exhausted.
- **Stopping information.** The rule uses only screen-stage precision. It never uses locus, domain or any hypothesis quantity, so it is (approximately) ancillary to the estimands.
- **Work weights.** In a closed decade d, each labelled work gets `work_weight = N_d / n_d` (works in the decade's primary set over works labelled), so decades are not under-weighted.
- **Early era.** The cells 1800s–1840s are never closed early: the whole of every early work is labelled.

### 3.4 Human audit (DSL / PPI)
- **Draw.** The audit is drawn by `analysis/select_annotation.py::draw_audit` (seed 20261105):
  - strata: era (3) × predicted group (material / social / internal / no obstacle) × split;
  - equal allocation, with `n_cell = min(per, N_cell)`;
  - simple random sampling within each cell;
  - first-order inclusion probability π = n_cell / N_cell.
- **Records.** π is recorded for **every** pool passage in `audit_frame.parquet` at selection time.
- **Double coding.** 40 items are double-coded for κ, and the teacher adjudicates disagreements.
- **Planned size** at the time of writing: about 200 items over both halves, so about 100–110 in Confirmation.
  - §7 shows this is far too small for the confirmatory tests.
  - The final size and allocation will be fixed in the registered version (see R1–R3), before unsealing.
- **Relabelling.** After the v1.0 relabel, the strata stay defined by the selection-time labels. The DSL predictor is the v1.0 label. This is valid because π is known.

### 3.5 Sample size
Fixed by the corpus: about 7,750 works per half, of which the early era has about 200 works and about 90–100 authors (G0). There is no optional stopping on hypothesis outcomes.

## 4. Variables

- **Model labels (per passage):**
  - `has_obstacle`
  - `domains` (≤ 2)
  - `locus`
  - `failure_cause`
  - `night_function`
  - `technology_named`
  - `message_valence`
  - `confidence`
  - `quote_status`
- **Human labels:** `has_obstacle`, `domains`, `locus`, `failure_cause`. Humans do not label `night_function`.
- **Derived outcome categories** (`analysis/stats/dsl.py::TARGETS`). Category 0 means "not counted"; `insufficient_context` counts as no obstacle.

| Target | Categories |
|---|---|
| locus | none, material, social, internal |
| comm_cause | none, withholding, infrastructure+accidental (only when has_obstacle = yes and COMMUNICATION_INFORMATION ∈ domains) |
| distance | DISTANCE_TRAVEL ∈ domains and obstacle |
| darkness | DARKNESS_VISIBILITY ∈ domains and obstacle |
| night | danger+concealment, intimacy+labor+leisure |
| comm_infra | for H3 |

- **Covariates (work level):**
  - year (natural cubic spline, df = 4, with **fixed knots at 1800, 1850, 1885, 1905, 1929**: the boundaries, the era cut points and the late-era median). Quantile knots fall at about 1891/1906/1917 in this late-heavy corpus, which leaves 1800–1890 as one cubic piece.
  - genre (≤ 8 LCSH-mapped classes; reference = the most common);
  - origin (UK reference; US; unknown);
  - log(n_words), centred.
- **Battery variables:**
  - `date_confidence`
  - memorisation (name-cloze score)
  - alternate-family labels on a 10% work subsample **plus every audit item**
  - 250- and 500-word segmentation labels
  - ELTeC-eng and Chicago labels

## 5. Analysis plan

### 5.1 DSL correction
For each target and passage i, with Ŷᵢ the model one-hot, Yᵢ the human one-hot, Rᵢ the audit indicator and πᵢ the audit probability:

  Ỹᵢ = gᵢ + (Rᵢ / πᵢ)(Yᵢ − gᵢ)

- gᵢ is a **cross-fitted** calibration P(Y | Ŷ). It is learned on audited passages in the other 4 of 5 author folds, with 1/π weights and +1 pseudo-count on the model's own label.
- E[Ỹᵢ] = Yᵢ for any g, so the estimates are design-unbiased for the human-label estimand.
- Passages are aggregated to works (within-work Hájek weights).
- Sensitivity: the raw model label as g, and an era-stratified g.
- Cross-check: stratified PPI for era means (Angelopoulos et al. 2023).

### 5.2 Models
- **H1, H2a, H2c(ii).** Multinomial logit of the work-level DSL soft outcomes on ns(year, df = 4) + genre + origin + log length. Fitting solves the estimating equations Σ w xᵢ(Ỹᵢ − pᵢ(β)) = 0. Work weights are as in §3.3.
- **H2b and H2c(i).** Binary logit with the same covariates. For H2b, the time term is the indicator year ≥ 1850, fitted on 1800–1884 works.
- **Link fallback (pre-registered).** If the logit fails to converge, the same model is fitted with the identity link and that fit is reported (`fit_target`). DSL pseudo-outcome totals can be negative in sparse cells, and then the MLE does not exist. The fallback is flagged in output; see §7.2 for how often it happens.
- **Estimand: g-computation.** For each era, average the fitted category probabilities over the pooled reference covariate table (a fixed-seed 3,000-work subsample of the primary set) × **the era's empirical work-year distribution**. Uniform years would give the near-empty 1800s as much weight as the 1840s, which inflated the SE by about 1.7× in simulation. Then take the ratio of the relevant categories. The contrast is L − E (H2b: M-window − E).
- **SEs.** Delta method with the author-clustered (CR1) sandwich.
- **Tests.**
  - Two-sided z-tests; a claim requires the pre-declared sign.
  - Multi-part hypotheses (H1, H2c) use the intersection-union p = max of the parts.
- **H3.**
  - Decade series: DSL ratio estimates per decade. Decades with fewer than 30 works are dropped.
  - D: the mean over pairs of 1 − Pearson r of z-scored series.
  - p-value: a parametric bootstrap (B = 2000) under H0, "the true function series equals the keyword series in z-units (perfect positive tracking), observed with the estimated DSL sampling error".
  - CI for D: a circular moving-block bootstrap over decades (block = 3), with sampling error added.

### 5.3 Multiplicity
- Holm–Bonferroni across the five tests (H1, H2a, H2b, H2c, H3) at family-wise α = 0.05.
- Effect sizes with 95% CIs are the headline numbers.
- At most 2 open-discovery promotions (plan §4.6) form a separate family, corrected with BH at q = 0.05.

### 5.4 Composition
- **Shift-share.** Every reported change, E→L and decade-to-decade, is decomposed into a within-genre part and a genre-composition part using the symmetric (Bennet) shift-share, which is exact. Composition is measured by each genre's share of the denominator mass.
- **Fixed-composition trend.** Trends are post-stratified to the pooled 1840–1900 genre × origin mix. Every figure shows the trend next to the raw trend, with the number of works and authors per decade.
- **CIs.** Author-cluster bootstrap (B = 200).
- **Headline.** The within-genre component is the headline. These analyses are descriptive and are not part of the five tests.

### 5.5 Exclusions and missing data
- **Excluded:** non-fiction, translations, quality failures, and works with conflicting dates (`docs/data_quality.md`).
- **Rejected labels.** Passages whose label failed the deterministic gates (non-verbatim quote, schema failure) are treated as `has_obstacle = no` for the model label. The DSL correction handles any resulting bias because audited items keep their human label. The rejection rate is reported per decade.
- **Humans.** A missing human label (skipped item) keeps R = 0 for that passage. π is not recomputed. The count is reported.
- **No outlier removal.**

### 5.6 Robustness battery (`analysis/stats/battery.py`)
Each check is pass / fail.

| # | Check | Method | Pass rule |
|---|---|---|---|
| 1 | Leave one author out | one-step influence jackknife | every directional component keeps its sign and ≥ 50% of the primary magnitude, for every author |
| 2 | Leave one decade out | refit | same as 1 |
| 3 | Drop each genre with ≥ 5% of works | refit | same as 1 |
| 4 | High-confidence dates only | refit | same as 1 |
| 5 | Drop the top-decile memorised works | refit | same as 1 |
| 6 | Alternate model family | naive labels compared with the primary model's naive labels on the same works | same sign and ≥ 50% |
| 7 | 250- and 500-word segmentation | naive, as 6 | same sign and ≥ 50% |
| 8 | Date permutation | see below | one-sided permutation p < 0.05 for every directional component |
| 9 | Replication (ELTeC-eng, Chicago) | see below | the declared sign |

Battery notes:
- **Check 8 (deviation from the plan's wording, see §8).** 200 permutations of **author-level date profiles among authors within genre**. Each author's mean year is reassigned within the genre, keeping the within-author spread and the genre's date mix.
- **Check 9.**
  - ELTeC begins in 1841, so its early era is 1841–1849 plus a slope check over 1841–1929.
  - Chicago starts in 1880, so it cannot replicate H1 or H2b–c. It is used only for H2a and H3 trends over 1880–1923, and is otherwise reported as not run.
- **H3.** The permutation check does not apply to H3. A check that cannot run because data are missing counts as **failed**.

### 5.7 Verdict rule
- **Supported:** Holm-significant, **and** passes at least ⌈7/9 × number of applicable checks⌉, **and** has the same sign in replication.
- **Unstable:** Holm-significant, but fails the battery or replication.
- **Null:** not Holm-significant. A significant effect in the opposite direction is reported as "null (opposite sign)".

The verdict is computed mechanically by `battery.verdict`.

### 5.8 Exploratory analyses (labelled as such)
- uncapped authors;
- the low-confidence-date sensitivity;
- historical-setting novels;
- the 1800s–1830s by decade;
- UK vs US contrasts;
- the naive (uncorrected) estimates, shown only to illustrate measurement bias.

## 6. Inference criteria and validation gates
- α = 0.05 family-wise (Holm).
- **Benchmark gate** before trusting H1–H3: the pipeline recovers ≥ 8 of 10 injected shifts and claims ≤ 1 of 10 confounded nulls (plan §4.8).
- **Simulation gate:** DSL 95% CI coverage within [0.92, 0.98] on synthetic corpora that match the registered design (§7.2). If the gate fails at the registered audit size, the affected test is reported as underpowered or descriptive, never as confirmatory.

## 7. Power and validation (simulation, `analysis/stats/power.py`, `validate.py`)

Simulation settings:
- Corpora match G0: Confirmation decade counts from `docs/gates.md`; 7,750 works per half, or 5,700 after the author cap; heavy-tailed works per author (mean 3.7, median 1).
- Early era: about 190 works and about 65 authors per half.
- 24 random passages per work.
- Era-varying LLM confusion, early errors skewed toward material and late errors skewed toward internal/social, so naive labels exaggerate H1. Two noise levels:
  - "base": has_obstacle sensitivity 0.80–0.90, primary-domain accuracy 0.65–0.80;
  - "good": 0.88–0.94 and 0.78–0.88. This is close to the pilot, which had has_obstacle accuracy 0.86 and locus agreement 0.88 against the Claude reference (`docs/model_selection.md`).
- Simulated truth: Δ_material = −13 to −14 pp, Δ_internal = +8 pp.

### 7.1 Minimum detectable effect, H1 material-share contrast (80% power, pp)

**(a) Perfect labels on every passage** (the floor, set by works, authors and ICC; 2 replicates per cell, α = 0.05):

| ICC (author, latent) | 0.02 | 0.05 | 0.10 | 0.20 |
|---|---|---|---|---|
| 7,750 works, 24 passages | 2.8–3.6 | 3.4–4.0 | 4.2–4.9 | 6.1–6.6 |
| 7,750 works, 12 passages | 3.9–5.4 | 4.7–5.4 | 6.0–6.3 | 7.5–8.2 |
| 5,700 works, 24 passages | 3.3–4.5 | 4.4–5.3 | 5.6–6.1 | 7.8–8.2 |

Ranges are over obstacle prevalence 0.30–0.60. The corpus itself is not the constraint: the early era's ~65 authors and the ICC are.

**(b) DSL-corrected, by number of human audit labels in the Confirmation half** (7,750 works, 24 passages, ICC 0.05, prevalence 0.45; 10 replicates; MDE in pp at α = 0.05 / at α = 0.01, the first Holm step):

| Human labels (Confirmation) | ~108 (current plan) | 252 | 504 | 1,008 | 2,004 | ~3,850 |
|---|---|---|---|---|---|---|
| base noise | 57 / 69 | 28 / 34 | 23 / 28 | 16 / 19 | 11 / 14 | 8.0 / 9.8 |
| good noise (≈ pilot) | 39 / 48 | 26 / 31 | 19 / 23 | 12.5 / 15 | 8.9 / 11 | 7.5 / 9.1 |
| naive model labels | 3.3 MDE, but biased by **−12 pp** (estimate −26.5 vs truth −14.1); CI coverage 0.00 | | | | | |

More findings from the power runs:
- **Two-phase design.** A strong Tier-3 model on 10,000 Confirmation passages with humans nested in it gives 13.8 pp (base) and 11.9 pp (good) at 1,008 human labels. That is only a 10–15% gain, because a Tier-3 accuracy of 86–92% leaves the human-correction term dominant. It pays only if Tier-3 agrees with humans at ≥ 95%.
- **Allocation.** Over-allocating the audit to the E and L eras (45/10/45) did **not** help (17.5 vs 15.8 pp at 1,008), so equal allocation across eras is kept.
- **H2 tests are weaker still.** In the coverage study at 504 labels, the SE of the DARKNESS E→L prevalence contrast was 2.0–2.2 pp against a simulated effect of −2.8 pp. Communication-cause and night-function shares rest on a few dozen audited passages.

**Decision rule (plan §4.7).** If the H1 MDE exceeds 8 pp, collapse before freezing. **At any human-audit size below about 3,800 Confirmation labels, the MDE exceeds 8 pp.** The registered version must therefore adopt one of the following before unsealing (recommendations R1–R6, §7.3):
- (i) enlarge the audit;
- (ii) declare H1 the single primary test and H2a–c secondary (still Holm-corrected, but expected to be underpowered);
- (iii) report the registered MDE alongside every result.

### 7.2 CI coverage (validation, `validate.py`; 250 synthetic corpora per audit size, era-varying noise)

| Human labels (Confirmation) | DSL (calibrated g): range over 13 quantities | DSL (raw g) | Naive model labels |
|---|---|---|---|
| ~108 | 0.88–0.96 (era ratio shares undercover, 0.88–0.92: heavy-tailed 1/π terms; model contrasts 0.96 but median SE 0.15 vs empirical SD 0.20) | 0.91–0.97 | 0.00 for every locus quantity |
| 504 | 0.90–0.97 (median 0.94) | 0.93–0.98 | 0.00 |
| ~2,000 | 0.93–0.97 (median 0.94) | 0.93–0.97 | 0.00 |

Monte Carlo SE of a coverage proportion: ±0.014.

Further validation findings:
- **Naive bias.** Naive labels are biased in the hypothesised direction: the 1800–49 material share is +14.7 pp too high and the 1885–1929 share −2.6 pp too low, which roughly doubles the H1 contrast.
- **Logit fallback rate:** 88% at ~108 labels, 12% at 504, 1% at ~2,000.
- **Simulation gate (§6)** is met at ≥ 500 labels. At ~108 labels, era-share CIs undercover, so they must be reported as approximate.
- **PPI cross-check.** Stratified passage-level PPI agrees with DSL point estimates to machine precision under raw g (unit test). Its iid SE undercovers (0.85–0.94) because it ignores within-work clustering, so it is a cross-check only.

Figure: `analysis/stats/figs/dsl_coverage.png`.

### 7.3 Design recommendations (to resolve before the registered version)
- **R1. Audit size.**
  - Put the whole human audit into the **Confirmation** half. Discovery already has the teaching set, and Discovery audit labels may still be used to train the calibration g, since any g is valid.
  - Cut the human task to `has_obstacle` + `locus` (+ `failure_cause` when communication is in play), so about 1,000 Confirmation labels become feasible. That gives an H1 MDE of about 12.5–16 pp.
  - With volunteer annotators, each must pass a κ ≥ 0.6 check on the 40 double-coded items.
- **R2. Model accuracy.** This is the cheapest lever. Moving from "base" to "good" noise cut the MDE at 1,008 labels from 15.8 to 12.5 pp, equivalent to about 60% more human labels. Prompt work on locus, and validation against the human audit, should precede the freeze.
- **R3. H2 strata.** H2a, H2b and H2c(i) need audit strata defined by predicted *domain*, as plan §4.5 describes, not only locus groups. They also need audit coverage of the enrichment strata if enrichment passages are to be used. Otherwise H2a–c have DSL CIs too wide to test anything, and they should be registered as secondary.
- **R4. Night labels.** Humans (or the 60-item Tier-3/user check, drawn as a probability sample) must label `night_function`, or H2c(ii) is uncorrected and should be dropped from the confirmatory family.
- **R5. Audit frame.** Persist `audit_frame.parquet` (π for every pool passage) at selection time. This is now implemented in `select_annotation.py`. DSL cannot be computed after the v1.0 relabel without it.
- **R6. Replication.** ELTeC (1841+) and Chicago (1880+) cannot replicate E-vs-L contrasts. The battery's replication item for H1 and H2b–c is therefore the ELTeC 1841–49 vs L contrast plus the slope sign. The verdict rule is unchanged.

## 8. Deviations policy
- **Before registration.** Any change in this draft is logged in the change log below.
- **After registration:**
  - Every deviation is reported in the paper's "Deviations from pre-registration" table, giving what changed, why, when, and whether Confirmation data had been seen.
  - Both the registered and the deviating analysis are reported. The registered analysis keeps the confirmatory label unless it is impossible to run.
- **Already-known deviations from `research_plan_v2.md`:**
  1. **Eras.** The early era is 1800–1849, not 1800–1839, and H2b compares 1800–49 vs 1850–84 (G0 decision, made before labels).
  2. **Permutation check.** It permutes author-level date profiles within genre. Permuting within author × genre blocks leaves between-author chronology intact, so it is not a null: in simulation its "null" distribution centres on the observed effect (`test_battery.py`).
  3. **Link.** The identity-link fallback, needed because DSL pseudo-outcomes can make the logit MLE non-existent.
  4. **Model.** The primary model is author-cluster-robust (GEE-type) rather than a GLMM. A GLMM on naive labels is a sensitivity check only, since DSL soft outcomes are not a likelihood.
  5. **Night function.** The night_function component of H2c is not DSL-corrected unless humans label it on a probability sample (R4).
  6. **Replication.** ELTeC and Chicago cannot replicate the full E-vs-L contrasts (coverage).
- **Unforeseen problems.** If an analysis cannot be run as registered (e.g., an era with no audited obstacles), the nearest pre-specified fallback is used: the identity link, then the raw DSL ratio contrast without covariates. The fallback is reported as such.

## 9. Change log
- v0.1 (2026-10-31): first draft from plan v2 §3–4.
- v0.2 (2026-10-31): G0 eras; fixed spline knots; empirical era-year g-computation; work weights for adaptive stopping; power and coverage simulation; design recommendations R1–R6.
