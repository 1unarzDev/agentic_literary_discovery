# Pre-registration: What Stands in the Way (confirmatory analysis), DRAFT v0.4

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

**Family.**
- **H1 is the single primary confirmatory test**: two-sided, tested at α = 0.05 (v0.4, see below).
- **H2a, H2b, H2c and H3 are secondary confirmatory tests**, Holm-corrected among themselves (§5.3). Each is reported with its registered MDE (§7.4), so a null is read against what the design could detect.

Eras, revised at G0 because PG is thin before 1840:

| Era | Years |
|---|---|
| E (early) | 1800–1849 |
| M (mid) | 1850–1884 |
| L (late) | 1885–1929 |

The study window is 1800–1929.

| ID | Hypothesis | Direction | Estimand (Confirmation half) |
|---|---|---|---|
| **H1** locus shift (primary; two-sided since v0.4) | The locus mix of plot obstacles (material / social / internal) shifts between E and L, holding the registered genre × origin × length mix fixed. Kahler's inward turn (material falls, internal rises) is the named thesis tested. | two-sided; the result is classified (below) | Standardised era shares of locus among obstacles; (Δ_material, Δ_internal) = L − E. 2-df Wald test of (Δ_material, Δ_internal) = 0 |
| **H2a** communication | Among communication failures, intentional withholding rises relative to infrastructure + accidental loss | Δ > 0 | Standardised share withholding / (withholding + infrastructure + accidental_loss), L − E |
| **H2b** mobility | DISTANCE_TRAVEL obstacles become less prevalent after railway diffusion | Δ < 0 | Standardised prevalence per passage, 1850–1884 minus 1800–1849 (G0 window) |
| **H2c** darkness | DARKNESS_VISIBILITY prevalence falls | Δ < 0 | Standardised prevalence per passage, L − E. The night-function part (danger + concealment share) is **exploratory**: humans do not label `night_function`, so it cannot be DSL-corrected (R4). |
| **H3** mention ≠ function | Decade keyword rates for technology terms do **not** track the corresponding obstacle-function rates | excess divergence > 0 | D = mean over 3 pairs of (1 − r) between z-scored decade series; excess = D − E_H0[D] |

**H1 classification** (pre-declared, applied only when the 2-df Wald test gives p < 0.05; `models.classify_h1`):
- **inward (Kahler pattern):** Δ_material < 0 **and** Δ_internal > 0, with both 95% CIs excluding 0;
- **outward / externalisation:** Δ_material > 0 with its 95% CI excluding 0, **and** Δ_internal ≤ 0 (point estimate);
- **mixed:** any other significant pattern, e.g. material falls with internal flat, or both rise.

The paper reports the class together with both component estimates and CIs. "Inward" confirms Kahler, "outward" contradicts him, and "mixed" is reported as such.

**H1-ML, mid vs late (descriptive, v0.4).** The same estimand and 2-df Wald test for M (1850–1884) vs L (1885–1929), where most of the data lie and where the Discovery pilot shows a step in the 1880s. It is reported with CIs, Wald p and class. It is **not** part of any multiplicity family and carries no verdict.

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
- the social share in H1;
- night's function shares (exploratory, uncorrected model labels);
- **the genre-split interaction** ("literary fiction turned inward, popular fiction turned outward"): era × genre-group locus shares and interaction contrasts, **exploratory only**. The pilot found no support: era × popular OR 0.86–0.88, CIs spanning 0.3–2.5. An interaction contrast would need about twice H1's MDE.

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
  - Enrichment passages are used for exemplars and descriptive deep dives only.
  - **Decision (v0.3): the enrichment strata are not in the audit frame.** No confirmatory estimate uses them, because DSL needs a positive audit probability for every analysed passage. The domain-stratified audit (§3.4) already over-samples predicted-communication passages. The binding constraint for H2a is human-label noise and volume, not the number of communication passages in the frame: §7.4 puts H2a's MDE at 35–200 pp under any audit allocation we can afford.

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

### 3.4 Human audit (DSL / PPI), registered final design
- **Population.** The Confirmation half only, random backbone, non-teaching authors.
- **Draw.**
  - `analysis/select_annotation.py::draw_audit(lab_conf, teaching_authors, rng, n_target=1800, group_col="dgroup")`, with seed 20261105.
  - `lab_conf` is the Confirmation label table, with `era` and `dgroup = domain_group(row)`.
- **Strata.** Era (3) × predicted primary-domain group (8: comm, distance, darkness, material_other, social, internal, other, no_obstacle).
  - Allocation is equal, with `n_cell = min(per, N_cell)`.
  - Items are drawn by simple random sampling within each cell.
  - π = n_cell / N_cell.
  - These are about 24 cells. Expected unique items: about 1,760, because a few early-era cells are smaller than the allocation.
- **Records.** π is recorded for **every** pool passage in `audit_frame.parquet` at selection time (R5).
- **Annotators.** The student plus about 3 non-expert peers, about 500 labels each.
  - **Assignment** is random and balanced. The items are shuffled once, and annotator k receives items k, k+4, k+8, …, so every annotator gets a random sample of every cell.
  - **Overlap.** About 10% of items are labelled by a second, randomly chosen annotator, for κ.
  - **Blinding.** Annotators see only the passage and its context: no model label, no title, author or date, and the item order is random.
- **Expert-reference items.** 30 items, 10 per era, are drawn **as a simple random subsample of the audit sample**. The English teacher (the expert) labels them, and so does every annotator. They are used for:
  - **κ certification and the exclusion rule** (§5.1);
  - the **expert-nested sensitivity analysis** (§5.1).

  They are **not** weighted into the primary DSL estimate. The teacher's labels are excluded from the primary human label.
- **Teaching set.** About 60 Discovery items, labelled by the student only. These authors are excluded from the audit pool. The set is used for training and for the codebook only.
- **Human schema.** `has_obstacle`; a **single main domain**; `locus`; and `failure_cause` (only when the main domain is COMMUNICATION_INFORMATION). Humans do not label night_function.
- **Relabelling.** After the v1.0 relabel, the strata stay defined by the selection-time labels. The DSL predictor is the v1.0 label. This is valid because π is known.

### 3.5 Sample size
Fixed by the corpus: about 7,750 works per half, of which the early era has about 200 works and about 90–100 authors (G0).

Human audit: about 1,760 unique Confirmation items, about 2,000 labels including overlaps, plus 30 expert items.

There is no optional stopping on hypothesis outcomes.

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
- **Human labels:** `has_obstacle`, a single main domain (stored as a one-element `domains` list), `locus`, and `failure_cause` (communication only). Humans do not label `night_function`.
- **Estimand construct.** DSL targets the **human-label construct**: the mean label of the retained non-expert annotators. For H2b and H2c this means prevalence as the *main* domain. The model's second domain enters only through the calibration g.
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
  - genre: **the registered 8-class variable from `pipeline/genre.py` → `data/work/genre.parquet`** (metadata only: LCSH, bookshelves, year), frozen at the registration commit. Classes: juvenile, domestic_realist, historical, adventure, sensation_mystery, collection, romance, other. Reference level: juvenile, the most common. It is attached with `models.attach_genre` and replaces any other genre field. Standardisation over genre is **necessary, not optional**: the juvenile share differs between the halves in the mid era (Discovery 25.4% vs Confirmation 37.0%, `docs/pilot_analysis_1.md` §1);
  - origin (UK reference; US; unknown);
  - log(n_words), centred.
- **Battery variables:**
  - `date_confidence`
  - memorisation (name-cloze score)
  - alternate-family labels on a 10% work subsample **plus every audit item**
  - 250- and 500-word segmentation labels
  - ELTeC-eng and Chicago labels

### 4.1 Planned codebook v1.0 content (pending the QA A/B, `docs/qa/label_pass_2.md`)
The changes below go into codebook v0.9 (variant `v09a`). Whatever passes QA's A/B gates is frozen as **v1.0 before the relabel and before registration**. Anything that fails is dropped and logged here. Both the model prompt and the human annotation guide use v1.0.

| Change | Text in brief | Why (QA pass 2 / pilot) | Affects |
|---|---|---|---|
| **E1, three-part obstacle test** | Answer *yes* only if (a) WHO wants WHAT, (b) WHAT in the passage itself stands in the way (not in the context), and (c) it matters for what happens next. Plus an extended "not obstacles" list: mild discomfort, description or essay, banter, label taken from context. | Yes-precision is about 0.77; most false yeses are late popular fiction. | has_obstacle and every prevalence: H1 denominators, H2b, H2c |
| **E3, narrower SOCIAL_RANK_CONVENTION** | Only a social *rule* that would stop anyone in the character's position. A specific person's opposition is INTERPERSONAL; money is MONEY_PROPERTY_LAW; pride is INNER_STATE. | 12 of 19 RANK codings were wrong; RANK is inflated about 2×. | H1 domain mix (social share) |
| **E4, locus = proximate source** | Locus is the source of the resistance that, if removed, lets the character proceed. The default domain→locus mapping is a starting point. **`locus_reason` (≤ 10 words) is required whenever the locus differs from the default.** | The model followed the default mapping in 93–100% of cases, and `locus_reason` was filled in 0 / 1,361 rows. | H1 construct |

The category sets (locus and domain) are **not** changed, and ILLNESS keeps its material default. The domain-mapped locus is reported as a sensitivity (§5.8). DSL targets the human construct under v1.0, so codebook changes alter what the model must predict, not what is estimated. Humans label without the default-mapping hint (annotation UI b280007).

## 5. Analysis plan

### 5.1 DSL correction and human labels
For each target and passage i, with Ŷᵢ the model one-hot, Yᵢ the human label, Rᵢ the audit indicator and πᵢ the audit probability:

  Ỹᵢ = gᵢ + (Rᵢ / πᵢ)(Yᵢ − gᵢ)

- gᵢ is a **cross-fitted** calibration P(Y | Ŷ). It is learned on audited passages in the other 4 of 5 author folds, with 1/π weights and +1 pseudo-count on the model's own label. Discovery teaching labels may also be used to fit g, since any g is valid.
- E[Ỹᵢ] = Yᵢ for any g, so the estimates are design-unbiased for the human-label estimand.
- Passages are aggregated to works (within-work Hájek weights).
- Sensitivity: the raw model label as g, and an era-stratified g.
- Cross-check: stratified PPI for era means (Angelopoulos et al. 2023).

**How annotators enter (registered rules):**
1. **Human label = annotator mean.** Yᵢ is the **mean of the one-hot labels of all retained non-expert annotators** who labelled item i. An overlap pair that disagrees gives a soft label (0.5/0.5). There is no majority vote and no adjudication of overlaps: adjudicated items would be measured more accurately than single-coded ones, mixing two measurement processes within the sample. DSL is linear in Yᵢ, so soft labels are exact.
2. **Annotator noise.**
   - Non-expert error is treated as part of the construct being measured, and the inference is valid for it. Confirmatory p-values test H0: Δ = 0 for that construct.
   - If annotator error does not depend on era, which balanced random assignment is designed to ensure, the human-label contrast is an *attenuated* version of the expert contrast with the same sign and the same null. The **test** of H1's direction is therefore valid for the expert construct too; only the effect size is shrunk.
   - Simulation attenuation: × 0.62–0.66 at κ ≈ 0.6, × 0.82 at κ ≈ 0.75 (§7.4).
   - Effect sizes are reported as human-construct estimates, next to an attenuation-corrected range (below).
3. **Exclusion rule.**
   - Before any model label of the Confirmation half is unsealed, compute each annotator's Cohen's κ against the expert on the 30 expert items, on the 4-category H1 construct `locus` (none / material / social / internal).
   - **An annotator with κ < 0.40, or with fewer than 20 expert items, is excluded**, and all of their labels are dropped. Code: `annotators.expert_agreement` + `annotators.exclusions`.
   - κ on 30 items has an SE of about 0.1. In simulation, annotators whose true κ was 0.59–0.68 were wrongly excluded in 15–35% of replicates, about one annotator in five or six.
4. **π after exclusions or skipped items.**
   - π is recomputed per cell as (pool passages in the cell with at least one retained label) / N_cell (`dsl.audit_design(labelled_ids=…)`).
   - This is valid because items were randomly assigned to annotators.
   - Skips are assumed random within cells. Skip rates are reported by cell, and a cell with > 10% skips is flagged.
5. **Era-differential reliability check.**
   - Report overlap κ by era (`annotators.overlap_agreement`), and expert κ by era: 10 items per era, descriptive only.
   - Differential error can bias the contrast in either direction. In simulation, early-era error raised by 0.10 moved the H1 estimate by +27% of the contrast.
   - **If overlap κ differs between E and L by more than 0.15, H1 is reported with the expert-nested sensitivity estimate (6) beside it, and the verdict carries the flag "differential annotator reliability".**
6. **Expert-nested sensitivity (exploratory).** A two-phase DSL: annotator mean on the audit, and the expert on the 30-item probability subsample, with π_expert|audit = 10 / n_audit,era (`dsl.pseudo_outcomes_two_phase`). This targets the expert construct without bias, but its SE is about 17–30 pp. It is reported as a sensitivity range and never tested.
7. **Attenuation-corrected range (descriptive).** The human-construct estimate is divided by the attenuation implied by the annotators' expert agreement (the share-level misclassification matrix on the 30 items). It is reported with an interval but not tested.

### 5.2 Models
- **H1, H2a.** Multinomial logit of the work-level DSL soft outcomes on ns(year, df = 4) + genre + origin + log length. Fitting solves the estimating equations Σ w xᵢ(Ỹᵢ − pᵢ(β)) = 0. Work weights are as in §3.3.
- **H2b and H2c.** Binary logit with the same covariates. For H2b, the time term is the indicator year ≥ 1850, fitted on 1800–1884 works.
- **Link fallback (pre-registered).** If the logit fails to converge, the same model is fitted with the identity link and that fit is reported (`fit_target`). DSL pseudo-outcome totals can be negative in sparse cells, and then the MLE does not exist. The fallback is flagged in output; see §7.2 for how often it happens.
- **Estimand: g-computation.** For each era, average the fitted category probabilities over the **registered standard population** × **the era's empirical work-year distribution**. The standard population is a fixed-seed (seed 0) 3,000-work sample from the primary set of **both halves**: metadata only (registered genre, origin, log length), with nothing sealed. It is built by `models.reference_covariates(works, genre)`. Pooling both halves gives Discovery and Confirmation estimates the same standard, and the pooled genre mix is the standard. Uniform years would give the near-empty 1800s as much weight as the 1840s, which inflated the SE by about 1.7× in simulation. Then take the ratio of the relevant categories. The contrast is L − E (H2b: M-window − E).
- **SEs.** Delta method with the author-clustered (CR1) sandwich.
- **Tests.**
  - **H1 (v0.4):** a two-sided 2-df Wald test of (Δ_material, Δ_internal) = 0. It uses the joint delta-method covariance of the two contrasts, from the same fit and the CR1 author sandwich (`models.h1`, `models.wald`), followed by the classification in §1. The v0.3 directional intersection-union test stays available as `h1(two_sided=False)` and is reported as a sensitivity.
  - **Secondary tests:** two-sided z-tests; a claim requires the pre-declared sign.
- **H3.**
  - Decade series: DSL ratio estimates per decade. Decades with fewer than 30 works are dropped.
  - D: the mean over pairs of 1 − Pearson r of z-scored series.
  - p-value: a parametric bootstrap (B = 2000) under H0, "the true function series equals the keyword series in z-units (perfect positive tracking), observed with the estimated DSL sampling error".
  - **Calibration.** In 140 simulated replicates of the registered design, this p-value had size about 0.15 at nominal 0.05, and nominal 0.005 gave size about 0.05. The registered H3 p-value is therefore **p_cal = min(1, 10 × p)** (`models.H3_P_INFLATE`), and p_cal enters Holm.
  - CI for D: a circular moving-block bootstrap over decades (block = 3), with sampling error added.

### 5.3 Multiplicity
- **Primary.** H1 is tested at α = 0.05: the two-sided 2-df Wald test, then the classification.
- **Secondary.** Holm–Bonferroni across H2a, H2b, H2c and H3 at family-wise α = 0.05. They are reported whatever the H1 result.
- Effect sizes with 95% CIs are the headline numbers. Every secondary result is printed with its registered MDE (§7.4).
- At most 2 open-discovery promotions (plan §4.6) form a separate family, corrected with BH at q = 0.05.

### 5.4 Composition
- **Shift-share.** Every reported change, E→L and decade-to-decade, is decomposed into a within-genre part and a genre-composition part using the symmetric (Bennet) shift-share, which is exact. Composition is measured by each genre's share of the denominator mass.
- **Fixed-composition trend.** Trends are post-stratified to the pooled 1840–1900 genre × origin mix. Every figure shows the trend next to the raw trend, with the number of works and authors per decade.
- **CIs.** Author-cluster bootstrap (B = 200).
- **Headline.** The within-genre component is the headline. These analyses are descriptive and are not part of the five tests.

### 5.5 Exclusions and missing data
- **Excluded:** non-fiction, translations, quality failures, and works with conflicting dates (`docs/data_quality.md`).
- **Rejected labels.** Passages whose label failed the deterministic gates (non-verbatim quote, schema failure) are treated as `has_obstacle = no` for the model label. The DSL correction handles any resulting bias because audited items keep their human label. The rejection rate is reported per decade.
- **Humans.**
  - A missing human label (a skipped item, or an excluded annotator's item with no other label) has R = 0.
  - π is recomputed per cell from the retained labels (§5.1, rule 4).
  - Counts are reported.
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
- **Two-sided H1: which components must hold (v0.4).** The battery re-checks the components that define the observed class: those whose 95% CI excludes 0 in the primary fit, each against its **observed** sign (`battery._ref`). For example, "outward" re-checks the material rise, and "inward" re-checks both. The permutation p is one-sided in the observed direction of each such component.

### 5.7 Verdict rule
- **Supported:**
  - for H1: Wald p < 0.05, and the verdict carries the class, e.g. "supported: outward";
  - for a secondary test: Holm-significant among the secondary tests;
  - **and** passes at least ⌈7/9 × number of applicable checks⌉;
  - **and** has the same sign in replication.
- **Unstable:** significant at its level, but fails the battery or replication.
- **Null:** not significant at its level. A significant effect in the opposite direction is reported as "null (opposite sign)".
- **Reporting nulls.** A null secondary result is reported as "not detected (registered MDE = X pp)", never as evidence of absence.

The verdict is computed mechanically by `battery.verdict`.

### 5.8 Exploratory analyses (labelled as such)
- uncapped authors;
- the low-confidence-date sensitivity;
- historical-setting novels;
- the 1800s–1830s by decade;
- UK vs US contrasts;
- the naive (uncorrected) estimates, shown only to illustrate measurement bias;
- (v0.4, from the pilot) locus shares **by decade**, including the 1880s step;
- the residual "general fiction" bucket of domestic_realist, reported separately;
- the domain-mapped locus (default mapping) as a construct sensitivity;
- the genre-split interaction (§1);
- the "romance revival" reading of the 1880s step, as at most one open-discovery promotion (§5.3).

## 6. Inference criteria and validation gates
- α = 0.05 family-wise (Holm).
- **Benchmark gate** before trusting H1–H3: the pipeline recovers ≥ 8 of 10 injected shifts and claims ≤ 1 of 10 confounded nulls (plan §4.8).
- **Simulation gate:** DSL 95% CI coverage within [0.92, 0.98] on synthetic corpora that match the registered design (§7.2). At ≥ 500 labels it was met for the human construct. Under the registered annotator noise, the model SE matched the empirical SD of the H1 estimate (6.3 vs 6.9 pp). If the gate fails at the registered audit size, the affected test is reported as underpowered or descriptive, never as confirmatory.

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

**Decision rule (plan §4.7), superseded in v0.3 by §7.4.** If the H1 MDE exceeds 8 pp, collapse before freezing. **At any human-audit size below about 3,800 Confirmation labels, the MDE exceeds 8 pp.** The registered version must therefore adopt one of the following before unsealing (recommendations R1–R6, §7.3):
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

### 7.3 Design recommendations from v0.2 (status in v0.3)

Status:
- **R1:** adopted. 1,800 Confirmation items.
- **R3:** adopted, with domain strata. §7.4 finds no measurable gain from them.
- **R4:** adopted. Night function is exploratory.
- **R5:** adopted.
- **R6:** adopted.
- **R2:** still advised.
- **R1. Audit size.**
  - Put the whole human audit into the **Confirmation** half. Discovery already has the teaching set, and Discovery audit labels may still be used to train the calibration g, since any g is valid.
  - Cut the human task to `has_obstacle` + `locus` (+ `failure_cause` when communication is in play), so about 1,000 Confirmation labels become feasible. That gives an H1 MDE of about 12.5–16 pp.
  - With volunteer annotators, each must pass a κ ≥ 0.6 check on the 40 double-coded items.
- **R2. Model accuracy.** This is the cheapest lever. Moving from "base" to "good" noise cut the MDE at 1,008 labels from 15.8 to 12.5 pp, equivalent to about 60% more human labels. Prompt work on locus, and validation against the human audit, should precede the freeze.
- **R3. H2 strata.** H2a, H2b and H2c(i) need audit strata defined by predicted *domain*, as plan §4.5 describes, not only locus groups. They also need audit coverage of the enrichment strata if enrichment passages are to be used. Otherwise H2a–c have DSL CIs too wide to test anything, and they should be registered as secondary.
- **R4. Night labels.** Humans (or the 60-item Tier-3/user check, drawn as a probability sample) must label `night_function`, or H2c(ii) is uncorrected and should be dropped from the confirmatory family.
- **R5. Audit frame.** Persist `audit_frame.parquet` (π for every pool passage) at selection time. This is now implemented in `select_annotation.py`. DSL cannot be computed after the v1.0 relabel without it.
- **R6. Replication.** ELTeC (1841+) and Chicago (1880+) cannot replicate E-vs-L contrasts. The battery's replication item for H1 and H2b–c is therefore the ELTeC 1841–49 vs L contrast plus the slope sign. The verdict rule is unchanged.

### 7.4 Registered final design (v0.3): MDEs and power (`power.py --final`, 20 replicates per scenario)

Design simulated:
- 7,750 Confirmation works.
- `draw_audit(…, n_target=1800, group_col="dgroup")`, giving about 1,760 unique items.
- 4 non-expert annotators with item error 0.25 / 0.28 / 0.31 / 0.34, i.e. true locus κ vs expert of about 0.68 / 0.66 / 0.62 / 0.59 (mean measured on the 30 items: 0.59).
- 10% overlap; 30 expert items; the κ < 0.40 exclusion rule applied.
- Annotator-mean soft labels; calibrated DSL; logit with fallback; "good" (pilot-like) LLM noise.
- The "truth" is the expert construct on the human schema.
- MDE = (z₁₋α/₂ + z₀.₈) × SE, using the RMS model SE. Secondary tests are also shown at α = 0.0125, the first Holm step for 4 tests.

| Test | Simulated effect (expert construct) | Mean estimate (human construct) | Attenuation | SE (pp) | MDE (pp) α = 0.05 | MDE (pp) at test level | Power at simulated effect |
|---|---|---|---|---|---|---|---|
| **H1** material share (primary) | −12.7 pp | −8.4 pp | 0.66 | 6.3 | **17.6** | 17.6 | 0.35 |
| **H1** internal share (primary) | +8.2 pp | +5.2 pp | 0.63 | 3.5 | **9.7** | 9.7 | 0.50 |
| H2a withholding share | +24.4 pp | +17.5 pp | 0.72 | 70 (empirical SD 34) | ≥ 35 (35–196 across scenarios) | ≥ 42 | 0.15 |
| H2b DISTANCE prevalence, 1850–84 vs 1800–49 | −1.2 pp | −0.2 pp | — | 1.9 | 5.3 | 6.3 | 0.05 |
| H2c DARKNESS prevalence | −1.1 pp | −1.5 pp | — | 1.7 | 4.8 | 5.7 | 0.10 |
| H3 excess divergence | divergent scenario | — | — | — | — | — | 0.40 at calibrated α (size 0.05 under tracking) |

The H1 test needs both parts, so its power is at most the material part's power, about 0.35.

Ablations (same design except the named change):

| Change | H1 material: estimate / SE / MDE (pp) | Power, material / internal |
|---|---|---|
| Registered (κ ≈ 0.6 annotators) | −8.4 / 6.3 / 17.6 | 0.35 / 0.50 |
| "Base" LLM noise | −7.8 / 6.6 / 18.4 | 0.20 / 0.15 |
| **Trained annotators (κ ≈ 0.74 measured)** | −10.4 / 5.5 / 15.3 | **0.45 / 0.60** |
| Expert-quality annotators | −14.0 / 4.1 / 11.5 | 0.95 / 0.85 |
| Locus-group strata instead of domain strata | −3.7 / 5.1 / 14.4 (empirical SD 7.5 vs 6.9) | 0.25 / 0.40 |
| Annotators worse on early prose (+0.10 error, E only) | −10.6 / 6.8 / 19.0 | 0.30 / 0.30 |

Further findings:
- **Domain strata** (R3) bought no detectable precision for H2. SE for H2b / H2c was 1.9 / 1.7 pp under domain strata against 1.7 / 1.4 pp under locus strata. For H1 the two designs agree within Monte Carlo error. Domain strata are kept because they guarantee audited communication passages for H2a.
- **Expert-nested sensitivity:** SE 17–31 pp, so it is unusable for testing. It is retained only as the registered sensitivity range.
- **Exclusion rule:** at least one annotator was excluded in 15–35% of replicates, even though every annotator's true κ was ≥ 0.59, because κ estimated on 30 items is noisy.
- **H3:** the uncalibrated size was 0.15 at nominal 0.05, hence the ×10 calibration (§5.2).

**Interpretation for the registration:**
- H1 is valid as a test of direction, but it is power-limited (≈ 35–50%) by **annotator noise** rather than by the number of labels. Moving annotators from κ ≈ 0.6 to κ ≈ 0.75 is worth more than another 1,000 labels.
- **Recommended before the probability sample starts:** a training round on the Discovery teaching items with feedback, and a **certification pre-test: κ ≥ 0.60 on 20 Discovery items vs the student's adjudicated key**. Only certified peers then label audit items. The registered exclusion floor (κ < 0.40 on the expert items) stays as written.
- **H2a, H2b, H2c** have MDEs of 35+ / 5 / 5 pp against plausible effects of about 1–2 pp in prevalence, so they are expected nulls at this design. They are registered as secondary, so that their estimates and CIs are reported honestly and not read as evidence of absence.

### 7.5 Power of the two-sided H1 (v0.4; `power.py --final --v04`, 20 replicates per scenario)

The design is §7.4's registered annotation design: about 1,760 Confirmation items, 4 annotators, 30 expert items, the exclusion rule, and "good" LLM noise unless stated. Three truths are simulated:
- **inward:** the v0.3 simulated Kahler pattern;
- **pilot-like:** no smooth drift, and the NATURE / DISTANCE / DARKNESS logits step up in 1883. In the expert construct this gives material +11.0 pp E → L and +7.0 pp M → L, with internal −1.7 / −1.2 pp (`SimConfig.pilot_step`);
- **null:** no within-genre drift, with genre-mix drift kept.

"Power" is P(Wald p < 0.05). With 20 replicates, the Monte Carlo SE of a proportion is about ±0.10.

| Truth | Annotators (κ vs expert) | Material Δ: truth / mean estimate | Material MDE (pp) | Internal MDE (pp) | **H1 power (2-df Wald)** | Classified inward / outward / mixed | H1-ML power | H1-ML material: truth / estimate |
|---|---|---|---|---|---|---|---|---|
| inward | ≈ 0.6 (registered) | −12.7 / −8.4 | 17.6 | 9.7 | **0.55** (v0.3 IU test: 0.35) | 0.20 / 0.00 / 0.35 | 0.30 | −7.1 / −5.9 |
| **pilot-like** | ≈ 0.6 (registered) | +11.0 / +6.5 | 17.2 | 10.8 | **0.15** | 0.00 / 0.15 / 0.00 | 0.20 | +7.0 / +4.2 |
| pilot-like | ≈ 0.74 (trained) | +11.0 / +6.8 | 15.1 | 8.9 | **0.25** | 0.00 / 0.15 / 0.10 | 0.20 | +7.0 / +4.8 |
| pilot-like | ≈ 0.6, "base" LLM noise | +11.0 / +7.8 | 17.9 | 11.5 | 0.20 | 0.00 / 0.10 / 0.10 | 0.05 | +7.0 / +3.2 |
| null | ≈ 0.6 | +0.5 / +0.2 | 17.3 | 10.9 | **0.05 (size)** | 0.00 / 0.00 / 0.05 | 0.00 | 0 / −1.1 |

**Reading:**
- **Size.** The two-sided Wald test holds its size under the null with genre-mix confounding (0.05). It never assigned the wrong direction (no "inward" calls under the pilot truth, no "outward" calls under the inward truth).
- **Inward truth.** The two-sided test is *more* powerful than the v0.3 intersection-union test (0.55 vs 0.35), because either component can carry it. When it rejects, the class is often "mixed" (the internal CI includes 0).
- **Pilot-like truth.** It is **under-powered: about 15–25%**. Annotator noise attenuates the effect from +11 to about +6.5 pp (human construct), against an MDE of about 17 pp. H1-ML has the smaller SE (5.0 vs 6.1 pp), but the pilot step is only +7 pp (≈ +4.2 after attenuation), so its power is about 0.20.
- **What the registered design can detect.** E-vs-L material shifts of about **17 pp in the human construct (≈ 26 pp in expert units at κ ≈ 0.6; ≈ 18 pp at κ ≈ 0.75)**, and internal shifts of about 10 pp. The paper reports these MDEs next to the H1 result. A null H1 is reported as "no locus shift detected (MDE = 17 pp material / 10 pp internal, human construct)".
- **Raising power.** The levers, in order of value:
  1. annotator training and certification (§7.4: κ 0.6 → 0.75);
  2. the v1.0 construct fixes (§4.1), which reduce model error and so the variance of the DSL correction;
  3. more expert-quality labels.

  The design is otherwise unchanged.

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
  7. **Family (v0.3).** H1 is the single primary test. H2a, H2b, H2c and H3 are secondary, Holm among themselves. The plan's single Holm family of 5 is replaced.
  8. **Night function.** H2c is reduced to DARKNESS prevalence, and night function is exploratory.
  9. **Human audit (v0.3).**
     - About 1,800 Confirmation-only items, drawn with era × predicted-domain strata, labelled by non-expert annotators.
     - Human label = annotator mean. The teacher is the expert reference on 30 items; there is no adjudication of overlaps.
     - Exclusion rule κ < 0.40.
     - π is recomputed after exclusions.
  10. **H3 calibration.** The H3 p-value is simulation-calibrated (×10).
  11. **H1 made two-sided (v0.4; pre-freeze deviation, decided after viewing Discovery labels).**
      - **Justification:** the Discovery pilot (`docs/pilot_analysis_1.md`; raw Tier-2 labels, 1,361 passages, no human correction). It shows a material-share rise from M to L of +7–8 pp, within genre, as a step in the 1880s. Internal is flat. The pilot has no information about E.
      - Under the v0.3 directional test this pattern would be recorded as "null (opposite sign)". The two-sided test does **not** bet on the pilot's direction: the estimand is unchanged, and any significant shift is classified by pre-declared rules.
      - The pilot used Discovery data only. Confirmation labels remain sealed.
  12. **Registered genre variable (v0.4).** `pipeline/genre.py` 8 classes, plus a pooled two-half standard population.
  13. **H1-ML (v0.4).** The mid-vs-late contrast is added as a descriptive estimate.
  14. **Codebook (v0.4).** v1.0 is planned to contain the three-part obstacle test, a narrower SOCIAL_RANK_CONVENTION, and locus = proximate source with a required `locus_reason` (§4.1). These are pending the QA A/B; whatever passes is frozen in v1.0 before the relabel and before registration.
- **Unforeseen problems.** If an analysis cannot be run as registered (e.g., an era with no audited obstacles), the nearest pre-specified fallback is used: the identity link, then the raw DSL ratio contrast without covariates. The fallback is reported as such.

## 9. Change log
- v0.1 (2026-10-31): first draft from plan v2 §3–4.
- v0.2 (2026-10-31): G0 eras; fixed spline knots; empirical era-year g-computation; work weights for adaptive stopping; power and coverage simulation; design recommendations R1–R6.
- v0.3 (2026-11-01): coordinator/user decisions:
  - H1 primary; H2a–c and H3 secondary; H2c reduced to darkness prevalence.
  - Final audit design (1,800 Confirmation items, domain strata, 4 non-expert annotators, 30 expert items).
  - Annotator rules: mean soft labels, κ exclusion, π recomputation, era-differential reliability check, expert-nested sensitivity.
  - Enrichment strata excluded from the audit frame.
  - H3 calibration.
  - Final-design MDEs (§7.4).
- v0.4 (2026-11-01): pre-freeze deviation from the Discovery pilot:
  - H1 is two-sided: 2-df Wald test plus inward / outward / mixed classification.
  - H1-ML (mid vs late) added as descriptive.
  - Registered genre variable (`pipeline/genre.py`) and a pooled two-half standard.
  - Genre-split interaction is exploratory only.
  - Planned codebook v1.0 content (§4.1).
  - Power for the two-sided H1 (§7.5): size 0.05; power 0.55 for the inward truth and 0.15–0.25 for the pilot-like truth.
