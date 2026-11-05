# Pre-registration: What Stands in the Way (confirmatory analysis), DRAFT v0.5

**OSF registration hash:** `OSF-HASH-PLACEHOLDER` (fill in on registration; `ald sync` / `POST /v1/admin/unseal` refuse to unseal Confirmation results until this line holds the real hash)

**Schedule and seal:**
- **Registration date:** _TBD (planned Nov 8–9, 2026). Confirmation labels are unsealed about Nov 9–11, for the Nov 20 submissions._
- **Template:** OSF Preregistration (secondary data / observational).

- **Sealed storage (from the platform migration, `docs/migration_plan.md`).**
  - Confirmation results are stored **ciphertext-only** on the shared research platform. They are encrypted client-side with age (X25519) to the **owner's pinned recipient key**; the private key is held **offline** by the owner (a USB key plus a paper backup).
  - Unsealing is **one-way**. It is logged in the platform's append-only audit log against this document's **OSF hash**, and `pipeline/unseal.py` refuses unless the logged hash matches the hash above and the unseal time is after registration.
  - Seal incidents are recorded in §8.1.

**Status of data at registration:**
- Discovery-half model labels (codebook v0.9 production, `v09lean_r2`, pin `41ca3c7d`), the QA references, the pilot and the reviews (`docs/review/*.md`) have been seen. The two-fictions hypothesis was **discovered on Discovery** (literary review P1) and is confirmed here on Confirmation.
- Confirmation model labels sit sealed under the R2 `sealed/` prefix and have not been read by any analyst. The audit draw reads **metadata only** (§3.4). This fixes the v0.4 design, whose predicted-label strata would have exposed the naive answer (methods review P4).
- **Raters and what they have seen:**

  | Rater | What they have seen |
  |---|---|
  | Project lead (student, peer annotator) | knows the hypotheses and the Discovery results |
  | Peers | the hypotheses at the level of the annotation guide |
  | Graduate-student expert (anonymous; about 8 h, about 900 labels) | the codebook and the guide only; **no** hypotheses, pilot, showcase or reviews. **Blindness attestation is a REQUIRED item** (§3.2) |
  | English teacher | the showcase (Nov 1); gives ~8 items and draft feedback, descriptive only |

**Code:**
- `analysis/stats/` at commit _TBD_. Running `uv run python -m analysis.stats.battery labels human frame --keywords …` produces every confirmatory number.
- Power for this design: `analysis/stats/power_v05.py`. Levers: `levers.py`. Validation: `validate.py`.

**Related documents:**
- `docs/plan/research_plan_v2.md`
- `docs/data_quality.md`
- `docs/codebook.md` (v0.9 production; no v1.0 relabel)
- `docs/gates.md`
- `docs/canon_measure.md`
- `docs/review/{methods,literary,feasibility}_review.md`

---

## 1. Hypotheses and family

Eras use **year** cuts: E 1800–1849, M 1850–1884, L 1885–1929. The window is 1800–1929, and E effectively means about 1835–1849 (see §2).

| ID | Role | Hypothesis | Estimand (Confirmation half, primary set) | Test |
|---|---|---|---|---|
| **TF** two fictions | **PRIMARY** (α = 0.05) | Canonical and non-canonical works differ in where their obstacles' resistance comes from (locus mix) | Standardised locus shares, canonical vs non-canonical. (Δ_material, Δ_internal) = canonical − non-canonical, by g-computation over the standard population, each work at its own year. Genre is **not** adjusted: genre composition is part of what separates the two fields. | Two-sided 2-df Wald, then the symmetric classification |
| **H1** locus shift | **SECONDARY** (Holm with H1\|canon and H1\|non-canon) | The locus mix of scene-level obstacles in PG-preserved fiction shifts between E and L, genre-standardised | v0.4 estimand: (Δ_material, Δ_internal), L − E | Two-sided 2-df Wald, then classification |
| H1\|canon, H1\|non-canon | SECONDARY (Holm) | H1's era contrast within each canon stratum | as H1, in each stratum | as H1 |
| TF-genre | descriptive | TF adjusted for genre | TF + genre fixed effects | CI and Wald p, no verdict |
| Composition | descriptive | How much of the aggregate E → L locus change is canon composition | Bennet shift-share by canonical stratum (§5.4) | CI only |
| H1-ML | descriptive | M vs L locus contrast | as H1 | CI and Wald p, no verdict |
| H2a, H2b, H2c, H3 | **estimation only** | as in v0.4 | as in v0.4 | effect and CI, **no test, no verdict** (methods review P11: power 0.05–0.15) |

Wording follows methods review P1. H1 is "the locus mix of scene-level obstacles". It is *motivated by* the inward-turn literature, and the paper does not claim to test Kahler, whose thesis concerns narrative up to about 1800. TF speaks to Woolf's "materialists" charge and to the canon/mass divide (Bourdieu's restricted versus large-scale production; Moretti; Underwood).

> **DECIDED (user, 2026-11-01):** TF is the single primary at α = 0.05; H1 is the first secondary. This stays in force unless the proposal below is confirmed.
>
> **PROPOSED v0.6 (statistician, 2026-11-04; pending user confirmation; do not treat as registered).** The proposal rests on new Discovery evidence: the full-Discovery Gemma pilot (`docs/pilot_analysis_2_two_fictions.md`) and the Claude reference labels (`docs/claude_reference_analysis.md`). It is evaluated in §7.8–7.9 under the registered design (about 900 expert and about 2,000 peer labels; corrected primary set of 4,048 Confirmation works). Choosing a statistic on Discovery and testing it on sealed Confirmation is legitimate, provided it is fixed before unsealing and does not fork on the era pattern.
>
> 1. **TF test statistic: keep the joint two-sided 2-df Wald test of (Δ_material, Δ_internal)** and the symmetric classification. This is the current registration. It is *not* "material alone", which is only the MDE row quoted earlier. The substantive claim ("canonical fiction places obstacles more inward") requires the class **inward**. The **inwardness index** Δ_I = Δ_internal − Δ_material is registered as the pre-specified one-number summary, reported with its CI.
>    - **Power at α = 0.05:**
>
>      | Truth | Material alone | Joint Wald | Index |
>      |---|---|---|---|
>      | Gemma-like raw-label truth (§7.8) | 0.24 | 0.33 | 0.40 |
>      | Claude-construct truth (§7.9) | 0.14 | **0.53** | 0.43 |
>
>    - **Material alone is dominated** in every scenario.
>    - **Wald and index are close.** The Wald test is preferred because it does not assume that both components move, and the internal share is the construct most sensitive to who labels (point 4). The index is the better choice only if the internal component is trusted to carry half the claim.
> 2. **Weighting: keep works-weighted, main-effect TF (registered).** Era-equal weights with canon × era terms raise power (Gemma truth: index 0.40 → 0.55; Claude truth: Wald 0.53 → 0.57). But they up-weight the early and mid eras, where Discovery shows the larger gaps, which is fitting to Discovery. They are reported as a sensitivity only.
> 3. **H1: make it a second primary under a fallback procedure** (Wiens), keeping family-wise α = 0.05:
>    - TF is tested at α₁ = 0.04;
>    - H1 is tested at 0.01, **or at 0.05 if TF rejects**.
>
>    Under the Claude construct the L − E material rise is about +13.6 pp in simulation (+17.7 pp in Discovery against Claude labels), so H1 is no longer hopeless. Power for H1, the joint Wald, under each option:
>
>    | Option | TF power, both effects present | H1 power, both effects present | H1 power, TF null |
>    |---|---|---|---|
>    | **Fallback (.04 / .01)** | **0.51** | **0.33** | **0.26** |
>    | Fixed sequence (TF, then H1 at 0.05) | 0.53 | 0.27 | 0.02 |
>    | Holm over the two | 0.47 | 0.35 | 0.35 |
>    | Split 0.025 each | 0.47 | 0.27 | 0.35 |
>    | Current (H1 secondary, Holm among 3) | 0.53 | ≈ 0.22 | ≈ 0.22 |
>
>    The fallback keeps TF almost at full power and gives H1 a real chance whether or not TF rejects. Simulated family-wise error under the double null is 0.07 ± 0.025 at 100 replicates. H1|canon and H1|non-canon stay secondary (Holm at 0.05).
> 4. **Measurement risk for the internal components.** The internal share depends strongly on the annotator construct: Claude assigns internal to 6% of obstacles, the QA reviewer 11–12%, Gemma 14.5%. Both TF's internal component (and so the Wald test and the index) and H1's internal component inherit this. The expert-anchored DSL estimates whatever construct the graduate student applies. The paper will report the expert's internal rate beside the Claude and QA rates, and say plainly that the TF internal gap is construct-dependent.
> 5. **Juvenile dependence.**
>    - **Estimand wording:** TF compares **canonical works with all non-canonical works, juvenile fiction included.** Genre composition, juvenile included, is part of the field difference by design. Canonical works are almost never juvenile.
>    - **Registered sensitivity:** TF on `genre ≠ juvenile` (`juvenile == False` in works_v2). In Discovery the material gap there falls to −0.9 pp while the internal gap stays +2.4 pp. Simulated power for the index on the non-juvenile subset is 0.21 under the Gemma-like truth.
>    - The two sentences reported side by side: "canon vs the whole mass market" and "canon vs the adult mass market".

**Classification** (TF and H1; v0.5 makes it symmetric, following methods review P10). It is applied only when the 2-df Wald test rejects at the test's α. Each component is judged *up*, *down* or *flat* by its **Bonferroni-adjusted CI at level 1 − α/2**, which gives directional error control across the two components (`models.classify_h1`):

| Class | Rule |
|---|---|
| **inward** | material down and internal not down, **or** internal up and material not up |
| **outward** | material up and internal not up, **or** internal down and material not down |
| **socialisation** | material down and internal down (the social share rises) |
| **de-socialisation** | material up and internal up (the social share falls) |
| **indeterminate** | the joint test rejects but neither component's CI excludes 0 |

For TF, "inward" means canonical fiction locates resistance more in people and minds than the mass market does.

## 2. Design and population

- **Corpus:** English fiction 1800–1929 preserved in Project Gutenberg, after the `docs/data_quality.md` filters.
- **Works table:** `data/work/works_v2.parquet`.
  - `author_group` re-keys authors by **PG agent ID**, with aliases merged and Stratemeyer Syndicate house names in one cluster (methods review P8). It is the clustering unit.
  - `split_v2` is the repaired split, built without reading labels.
  - `primary_v2_capv2` is the primary-set flag with the 5-per-author-per-decade cap re-applied on `author_group`.
  - Code: `models.apply_works_v2`.
- **Primary set:**
  - date resolved inside 1800–1929;
  - not `historical_setting` (works_v2 flag), replacing the unimplementable "contemporary setting" (methods review P7);
  - non-teaching authors;
  - the author cap.
- **Dates:**
  - **Date variable:** the earliest documented book or serial publication. Composition dates are not used.
  - **Early era:** every early-era work (year < 1850) and every work dated 1847–1853 is **hand-verified** against first-edition bibliographies (Garside/Raven/Schöwerling, ATCL, Wright). Agents prepare the evidence, and a human signs off. Works whose date cannot be resolved, or resolves outside the window, are **excluded**.
  - **Round-year placeholders:** years exactly 1900 (and other round hundreds) count as unverified, and those works are excluded unless verified (methods review P3.5).
  - **Tiers:** confidence tiers are redefined from the verified dates. Open Library agreement no longer defines "high".
- **Canonicity:**
  - `data/work/canon.parquet` (`docs/canon_measure.md`): a **metadata-only** binary `canonical` per work, built from `downloads`, `sitelinks` and `canon_score` at the `author_group` level, with no labels. It is frozen at the registration commit.
  - In the Confirmation primary set, after the verified early dates and the 1900-placeholder exclusion (2026-11-04, `docs/canon_measure.md` §3.1): **4,048 works (E 87, M 538, L 3,423)**, of which **37% / 19% / 9%** are canonical by era. (Before the dates: 4,211.)
- **Passages:** **12 random passages per work** (random backbone `rand_a`, k < 12). This replaces the unimplemented adaptive stopping (methods review P9). Early-era works may contribute up to 24 if those passages were labelled before the audit draw, and within-work Hájek weights handle this. Enrichment passages never enter a confirmatory estimate.
- **Unit and SEs:** the work is the unit. SEs are author-clustered (CR1) on the new author keys.
- **Model labels:** codebook v0.9 production (`v09lean_r2`, pinned). **There is no v1.0 relabel.** DSL is valid for any predictor; a better model buys efficiency, not validity (§7.6: model accuracy is a weak lever).

## 3. Sampling plan

### 3.1 Existing data
- Discovery labels exist and have been analysed (pilot, reviews).
- Confirmation labels are sealed.
- Power used Discovery-calibrated simulation only (§7.7).

### 3.2 Human audit (seal-safe, registered)
- **Population.** The audit is drawn from the Confirmation half (primary set, random backbone) **before registration, on metadata only**:
  ```
  draw_audit_metadata(meta_conf, rng(20261105), n_target=1820)
    == draw_audit(meta, set(), rng, 1820,
                  group_col=["genre", "canonical"],
                  balance_on=["era", "canonical"],
                  metadata_only=True)
  ```
  - `meta_conf` carries `passage_id, work_id, author_key, year, split, stratum, genre, canonical`, with `era = era_by_year(year)`.
  - No label column is read. `metadata_only=True` refuses label-derived strata.
- **Strata and allocation.**
  - Strata are era (3) × genre (8) × canonical (2).
  - The budget is split equally over the 6 era × canonical cells, then proportional to N within each cell. Each cell gets at least 2 items and at most N_cell.
  - The real draw (annotation agent, 2026-11-01) gives **41 non-empty cells** and about 1,820 unique items.
  - π = n_cell / N_cell is written for **every** pool passage in `audit_frame.parquet`.
  - Canon balancing is what makes TF estimable: canonical works are 4% of L. Without canon strata, TF's MDE nearly doubles (§7.7).
- **Hash deposit.** The frame's `cell_table_hash` is deposited (OSF addendum) before anyone opens it. The counts are metadata, so they are harmless, but they are not published before registration.
- **If `canon.parquet` is not ready at draw time,** the fallback is `use_canon=False` (era × genre). §7.7 shows this costs TF most of its power, so **the draw waits for the canon measure** unless that would delay the schedule past Nov 6.
- **Peers.**
  - About 1,820 unique items, labelled by the student and about 3 peers, roughly 500 labels each: about 2,000 labels including 10% overlap.
  - Assignment is random and balanced: every peer gets a random sample of every cell.
  - Peers are **certified first**: κ ≥ 0.60 on a 20-item Discovery pre-test against the graduate student's key.
- **Expert anchor (graduate student, about 8 h).**
  - **About 900 items: a stratified 50% random subsample of the audit, drawn within audit cells,** so P(expert | audit) is known per cell.
  - Every expert item is also peer-labelled (nested design). These items double as the overlap with peers for κ: about 225 shared items per peer.
  - **REQUIRED ITEM, the blindness attestation.** Before labelling, the graduate student signs a short attestation, deposited with the OSF registration. It states that they have not seen the hypotheses, the pilot or Discovery results, the showcase, the reviews or this document; that they label from the codebook and guide only; and that they do not know the dates, authors or titles of the items. If the attestation is missing, or is breached, the TF verdict carries the flag "expert not blind", and the peers-only and expert-only estimates are reported beside it.
- **Teacher.** About 8 items plus draft feedback. These are **descriptive only**: teacher–expert agreement is reported, and the teacher's labels never enter an estimate.
- **Human schema:** `has_obstacle`, a single main domain, `locus`, and `failure_cause` (communication only).
- **Teaching set:** about 60 Discovery items, labelled by the student only.

### 3.3 Sample size
Primary-set Confirmation:
- **Works:** about 4,000.
  - E about 85–105, after excluding historical novels and unverifiable dates;
  - M about 530;
  - L about 3,400.
- **Passages:** about 48k random passages.
- **Audit:** about 1,820 items, of which about 900 are expert-labelled.

There is no optional stopping.

## 4. Variables
- **Model labels (v0.9):** `has_obstacle`, `domains`, `locus`, `locus_reason`, `failure_cause`, `night_function`, `technology_named`, `message_valence`, `confidence`, `quote_status`.
- **Quote-rejected rows.** A row whose quote check failed keeps its model label and is flagged. It is **not recoded to "no"** (methods review P12). The flag enters the calibration g as its own category.
- **Human labels:** the schema in §3.2.
- **Estimand construct:** the **graduate-student expert's** labels.
- **Targets** (`dsl.TARGETS`): locus (none / material / social / internal); comm_cause; distance; darkness; comm_infra. H2b and H2c count the main domain.
- **Work covariates:**
  - ns(year, df = 4), with knots at 1800 / 1850 / 1885 / 1905 / 1929;
  - genre (`pipeline/genre.py`, 8 classes, reference juvenile);
  - origin (65% unknown, disclosed);
  - log length;
  - `canonical`.
- **Standard population:** a fixed-seed sample of 3,000 works from the primary set of **both** halves, metadata only (`models.reference_covariates`). Sensitivity analyses use the early-era mix and overlap weights (methods review P7).

## 5. Analysis plan

### 5.1 Measurement: expert-anchored DSL (registered estimator)
The estimator has three levels (`dsl.pseudo_outcomes_anchored`, `dsl.prepare_anchored`):

  Ỹ = g₁(model) + (R_audit/π_audit)·(g₂ − g₁) + (R_audit·R_expert)/(π_audit·π_expert|audit)·(expert − g₂)

- **g₂** is a cross-fitted multinomial logit of the expert label on (the peer annotator-mean soft label, the model label). **g₁** is a cross-fitted calibration of g₂ on the model label, by era stratum. Five author folds are used.
- **E[Ỹ] = the expert label for any g₁ and g₂.** So peer noise, peer bias (including the unblinded project lead), era-differential peer error and peer exclusions **cannot bias** the estimate. They change only its variance.
- This settles review P4(c), P6 and the era-differential-error concern by construction. The remaining assumption is the expert's own blinding and consistency.

**Annotator rules:**
1. **Certification.** Peers need κ ≥ 0.60 on locus against the expert key on 20 Discovery items before labelling audit items.
2. **Exclusion.** A peer whose locus κ against the expert, on their jointly labelled audit items (about 225 each, SE ≈ 0.04), is **below 0.40** is excluded. Their rows are dropped and π_audit is recomputed per cell (`annotators.exclusions`).
3. **Reporting.** Overlap κ is reported overall and by era. Peer–expert κ is reported by era (about 150 expert items per era). The teacher–expert agreement on about 8 items is descriptive.
4. **Sensitivity estimators.** Peers only (the v0.4 estimand, attenuated) and expert only (DSL with the about 900 expert labels).

### 5.2 Models
- **TF:** multinomial logit of the work-level DSL soft outcomes ~ canonical + ns(year) + origin + log length. Standardised over the standard population at each work's own year, with canonical set to 1 vs 0 (`models.two_fictions`).
- **H1:** as in v0.4, with genre fixed effects and spline (`models.h1`).
- **Shared rules:**
  - logit with the registered identity-link fallback;
  - author CR1 sandwich and delta method;
  - 2-df Wald test;
  - classification as in §1.
- **H1-ML:** descriptive.
- **The STEP-1880 and LINEAR-trend contrasts explored in §7.6 are not adopted** (forking paths, methods review P5).

### 5.3 Multiplicity
- **Primary:** TF at α = 0.05.
- **Secondary:** Holm at 0.05 over {H1, H1|canon, H1|non-canon}.
- **Descriptive and estimation analyses:** CIs only.
- **Open discovery:** BH-corrected, at most 2 promotions.

### 5.4 Composition
- **Shift-share by canonical stratum** (Bennet) of the E → L change in each locus share. It splits the change into a within-stratum part and a canon-composition part, with an author-bootstrap CI.
- **Shift-share by genre** as before.
- **Fixed-composition trend:** post-stratified to the pooled canon × genre mix.

### 5.5 Exclusions and missing data
As in v0.4, with these changes:
- the population rules in §2;
- quote-rejected rows keep their label and flag (§4);
- π is recomputed after peer exclusions or skips;
- a cell with more than 10% skips is flagged.

### 5.6 Robustness battery
Applied to the primary test(s), with the v0.4 checks. Changes in v0.5:
- **TF permutation (check 8):** author-level canonical flags are permuted among authors within era (`battery.canon_permutation`).
- **Replication (check 9) is optional:** it is reported when available and excluded from the denominator otherwise, never a failed check (methods review P9.5). ELTeC is optional.
- **Registered sensitivities:**
  - H1 and TF with every cross-half canonical author removed;
  - standardisation to the early-era mix;
  - **TF on non-juvenile works** (`juvenile == False`), as proposed in v0.6;
  - **TF with era-equal weights** and canon × era terms, as proposed in v0.6.
- **Multiverse appendix** (Discovery only, exploratory): a specification curve of the TF and H1 estimates across model (Gemma vs Qwen), codebook version, date source, genre standard and clustering (methods review P5 and redirection D).

### 5.7 Verdict rule
- **Supported:** significant at the test's α, **and** passes at least ⌈7/9 × number of applicable checks⌉, **and** has the same sign in replication *if* replication is available.
- **Unstable:** significant, but fails the battery or an available replication.
- **Null:** not significant.

The verdict carries the class, e.g. "supported: inward". Nulls are reported with the registered MDE.

### 5.8 Exploratory
- the decade curves;
- the genre-split interaction;
- the 1880s step;
- the domain-mapped locus;
- the residual-domestic bucket;
- UK vs US (only if origin is resolved).

## 6. Inference criteria and validation gates
- **Benchmark gate:** as before.
- **Simulation gate:** expert-anchored DSL coverage of the expert-construct estimand. It was **0.92–1.00** across the TF and H1 cells at both expert budgets (§7.7).
- **Construct-validity gate (methods review P1d):** the peer-mean vs expert locus κ, and the model vs expert κ by era, are reported. If the peer-mean vs expert κ is below 0.6, peers act only as the variance-reducing phase, which the estimator tolerates. If the model vs expert κ is below 0.4 in any era, TF and H1 are still estimated, but the paper flags weak model information.

## 7. Power and validation

### 7.7 Registered v0.5 design: power and MDE (`power_v05.py`; 60 replicates per cell, 120 for the registered cell)

**Simulation inputs (methods review P2):**
- Corpus `SimConfig.v05`, calibrated to v0.9 Discovery:
  - true obstacle prevalence 0.70;
  - non-canonical locus shares about 0.21 / 0.69 / 0.10;
  - observed author ICC 0.10 and work ICC 0.15 for the material indicator, against the review's 0.096 / 0.146;
  - Confirmation primary set about 4,000 works, with E about 95, 12 passages per work;
  - canonical shares 31% / 22% / 4% by era.
- Model labels at QA level: has_obstacle precision 0.77, recall 0.98, locus accuracy 0.85, with errors that over-call material in late adventure and juvenile fiction.
- The registered human process (§3.2) with peers at κ about 0.6 or 0.75. The expert defines the construct.

**Truths:**

| Truth | TF Δ_material (expert construct) | Within-stratum trend | H1 E → L |
|---|---|---|---|
| tf_full | −9.6 pp | none | aggregate +2.2 pp, pure composition |
| tf_half | −6.6 pp | none | — |
| tf_trend | −10.9 pp | +4.4 pp material | +4.4 pp |
| null | 0 | none | 0 |

Power is P(Wald p < α). The Monte Carlo SE is about ±0.06 at 60 replicates and ±0.045 at 120.

**Registered design (v0.5 final): era × genre × canon strata, expert-anchored estimator, peers at κ ≈ 0.6, about 900 expert labels (50% of the audit). 60 replicates per row; `power_v05.py --expert-extra`**

| Statistic | Truth | Estimate (truth) | SE (pp) | MDE (pp), α = 0.05 | **Power, α = 0.05** | Coverage |
|---|---|---|---|---|---|---|
| **TF** material (**PRIMARY**) | tf_full | −9.4 (−9.6) | 3.2 | **9.0** | **0.70** | 0.98 |
| TF | tf_half | −6.2 (−6.6) | 3.3 | 9.2 | 0.37 | 0.98 |
| TF | tf_trend | −10.3 (−10.9) | 3.3 | 9.2 | 0.77 | 1.00 |
| TF | null | −0.1 (0) | 3.5 | 9.8 | **0.05** (size) | 1.00 |
| **H1** material (E vs L; secondary) | tf_trend | +3.7 (+4.4) | 5.3 | **14.7** | 0.10 | 0.98 |
| H1 | null | −0.3 (0.2) | 5.3 | 14.7 | 0.07 (size, α = 0.05) | 1.00 |
| H1\|non-canon | tf_trend | +1.3 (+2.4) | 6.1 | 17.0 | 0.08 | 0.98 |
| H1-ML (M vs L; descriptive) | tf_trend | +2.9 (+2.8) | 4.2 | 11.7 | 0.07 | 1.00 |
| Composition share of the E → L material change | tf_trend | +2.3 of +4.2 pp | — | — | — | — |

The internal-share MDE for TF is 8.8 pp at α = 0.025, i.e. about 8 pp at α = 0.05.

**Registered statement: TF has power ≈ 0.70 against a 10 pp canon gap in the material share (MDE ≈ 9 pp at α = 0.05), and about 0.37 against a 6–7 pp gap.**
- The real Confirmation primary set has more late canonical works than simulated (9% vs 4%), so these figures are slightly conservative.
- H1 (secondary) has an MDE of about 15 pp and is expected to be uninformative unless the true shift is large.

**Levers on TF power** (tf_full truth, α = 0.05 / 0.025):

| Change from the registered design | TF MDE (pp), α = 0.05 | TF power, α = 0.05 / 0.025 | Comment |
|---|---|---|---|
| **Registered: about 906 expert labels (50%)** | **9.0** | **0.70 / 0.60** | the strongest lever, adopted |
| About 450 expert labels (25%, the earlier plan) | 12.3 | 0.59 / 0.47 | |
| About 226 expert labels (12.5%) | 17.9 | 0.32 / 0.25 | |
| Peers κ 0.6 → 0.75 | 11.6 | 0.45 / 0.43 | within Monte Carlo error of the registered row; peers matter little once the expert anchors |
| **No canon strata** (era × genre only) | 22.6 | 0.23 / 0.18 | canon balancing is essential for TF. It costs H1 some precision: H1's MDE is 15.2–16.2 pp without canon strata against 19.7–20.6 pp with them, but H1 is under-powered either way. |
| Expert-only estimator (peers ignored) | 13.5 | 0.50 / 0.33 | peers add about 10–15 points of power through g₂ |
| Peers-only estimator (the v0.4 estimand) | 9.3 | 0.35 / 0.28 | **biased** toward 0 (estimate −6.3 vs −9.6) with coverage **0.84**; invalid for the expert construct |
| H1 with about 906 expert labels | 14.8 (H1) | 0.02 (tf_full) | H1 stays far below useful power |

**Conclusions for the registration:**
1. **TF is the confirmatory test this design powers:** 0.70 at α = 0.05 for a 10 pp canon gap (MDE 9 pp), with size ≤ 0.05.
2. **H1 is under-powered:** MDE about 15 pp with 900 expert labels and about 20 pp with 450. It is secondary, as decided in §1.
3. **Expert hours were the decisive lever,** and the user adopted about 8 h (about 900 labels).
4. **The draw uses canon strata.** Without them, TF's MDE doubles.

### 7.8 TF candidate statistics under the Discovery raw-label truth (`power_tf.py`; 100 replicates)
**Truth (`SimConfig.tf_disc`)** is calibrated to `docs/pilot_analysis_2_two_fictions.md`:
- material gap about E −8, M −7, L −4 pp; internal gap +3 to +6 pp;
- the late gap carried by juvenile fiction;
- corrected primary set: Confirmation about 4,050 works, canonical 37% / 19% / 9%.

The design is the registered one (about 900 expert and about 2,000 peer labels at κ ≈ 0.6; QA-level model noise). Tests are two-sided at α = 0.05.

| Truth (pooled works-weighted) | Weighting | (a) Material: truth / MDE / power | Internal: truth / MDE / power | **(b) 2-df Wald power** | **(c) Index: truth / MDE / power** |
|---|---|---|---|---|---|
| Discovery-size (material −4.8, internal +3.9) | works, main effect (registered) | −4.8 / 10.0 / 0.24 | +3.9 / 8.3 / 0.26 | **0.33** | +8.6 / 14.5 / **0.40** |
| same | works, + canon × era | −4.4 / 10.7 / 0.22 | +3.7 / 8.9 / 0.24 | 0.24 | +8.2 / 15.5 / 0.30 |
| same | era-equal, + canon × era | −5.4 / 8.9 / 0.41 | +4.2 / 8.5 / 0.33 | 0.45 | +9.6 / 13.5 / 0.55 |
| Deflated ×0.7 | works, main effect | −4.3 / 10.0 / 0.24 | +3.0 / 8.2 / 0.18 | 0.23 | +7.3 / 14.3 / 0.30 |
| Discovery-size, **non-juvenile** works | works, main effect | −2.5 / 10.4 / 0.17 | +3.7 / 9.0 / 0.23 | 0.22 | +6.2 / 15.2 / 0.21 |

The estimated correlation of the two components is about −0.2. The "scale 0" scenario (not shown) keeps a −3 pp composition gap, because canonical works are rarely juvenile: it is not a null for TF. TF's size was verified at ≤ 0.05 in §7.7.

### 7.9 TF and H1 under the Claude-reference construct, plus multiplicity options (`power_claude.py`; 100 replicates)
**Truth:** the cell rates and locus shares of the Claude reference (era × canonical):
- TF material about −4, internal about +8, index about +12 pp;
- H1 material L − E about +14 pp within strata.

**Model error:** the Gemma-vs-Claude confusion by cell (precision about 0.71, recall about 0.90, locus accuracy 0.67–0.94). Peers are at κ ≈ 0.62, with about 900 expert labels. Tests are two-sided at α = 0.05.

| Truth (TF scale, H1 scale) | TF (a) material | **TF (b) Wald** | TF (c) index | H1 (a) material | **H1 (b) Wald** | H1 (c) index |
|---|---|---|---|---|---|---|
| (1, 1) both present | 0.14 | **0.53** | 0.43 | 0.54 | **0.45** | 0.42 |
| (0.7, 0.7) deflated | 0.07 | 0.32 | 0.26 | 0.30 | 0.25 | 0.22 |
| (1, 0) TF only | 0.09 | 0.38 | 0.33 | 0.03 | 0.02 | 0.04 |
| (0, 1) H1 only | 0.03 | 0.03 | 0.05 | 0.53 | 0.47 | 0.34 |
| (0, 0) null | 0.06 | 0.08 | 0.06 | 0.06 | 0.06 | 0.07 |

Further results:
- **MDEs (registered TF):** material 13–14 pp, index 18–19 pp.
- **MDEs (H1):** material 18–19 pp, index 23–25 pp.
- **Era-equal TF:** Wald 0.57, index 0.49 when both effects are present.

**Multiplicity**, with TF on the Wald test and H1 on the Wald test, both effects present / TF null with H1 present:

| Option | P(TF) | P(H1) |
|---|---|---|
| **Fallback (TF .04, H1 .01 or .05 if TF rejects)** | 0.51 | 0.33 / 0.26 |
| Fixed sequence | 0.53 | 0.27 / 0.02 |
| Holm over the two | 0.47 | 0.35 / 0.35 |

Family-wise error under the double null: 0.07 (Holm) and 0.04–0.07 (fallback), with Monte Carlo SE ±0.025.

### 7.6 Levers explored before v0.5 (`levers.py`; pilot-like truth; 20 replicates per cell; for the record, none adopted unless stated)

| Lever | Finding |
|---|---|
| L1 model accuracy (precision 0.77–0.95, locus accuracy 0.85–0.95) | E-vs-L MDE 13.9 → 11.7 pp at κ 0.6 (12.1 → 10.0 at κ 0.75). A weak lever; the v1.0 relabel was dropped. |
| L2 Neyman allocation on predicted labels | ML MDE 10.4 → 8.9 pp, but EL 12.7 → 17.2 pp (labels drawn away from the thin early era). **It reads predicted Confirmation labels, so it is barred by the seal fix.** |
| L3 contrast choice | STEP-1880 had the highest power (0.40–0.65) but was tuned to a pilot step that vanished under v0.9: **dropped** (forking paths, methods review P5). LIN had the lowest power. ML stays descriptive. |
| L4 annotator-confusion correction (o·M⁻¹) | Removes attenuation (coverage against the expert 0.89 → 0.95) but adds variance. Per-annotator M from 30 items gives an MDE of 30 pp. **Superseded by the expert-anchored DSL**, which corrects without inverting M. |
| L5 +1,000 peer labels | E-vs-L power 0.29 → 0.44 (κ 0.6). Peer κ 0.6 → 0.75 gives 0.29 → 0.47. |

### 7.1–7.5 Earlier designs (v0.2–v0.4), kept as dated history
_These sections describe superseded designs: the 200-item audit, the four-peer estimand, and predicted-label strata. Their numbers are not the registered power. Two things carry over: the DSL coverage validation (§7.2) and the logic of the earlier MDE tables._

#### (history) Power and validation, v0.2–v0.4

Simulation settings:
- Corpora match G0: Confirmation decade counts from `docs/gates.md`; 7,750 works per half, or 5,700 after the author cap; heavy-tailed works per author (mean 3.7, median 1).
- Early era: about 190 works and about 65 authors per half.
- 24 random passages per work.
- Era-varying LLM confusion, early errors skewed toward material and late errors skewed toward internal/social, so naive labels exaggerate H1. Two noise levels:
  - "base": has_obstacle sensitivity 0.80–0.90, primary-domain accuracy 0.65–0.80;
  - "good": 0.88–0.94 and 0.78–0.88. This is close to the pilot, which had has_obstacle accuracy 0.86 and locus agreement 0.88 against the Claude reference (`docs/model_selection.md`).
- Simulated truth: Δ_material = −13 to −14 pp, Δ_internal = +8 pp.

#### 7.1 Minimum detectable effect, H1 material-share contrast (80% power, pp)

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

#### 7.2 CI coverage (validation, `validate.py`; 250 synthetic corpora per audit size, era-varying noise)

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

#### 7.3 Design recommendations from v0.2 (status in v0.3)

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

#### 7.4 Registered final design (v0.3): MDEs and power (`power.py --final`, 20 replicates per scenario)

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

#### 7.5 Power of the two-sided H1 (v0.4; `power.py --final --v04`, 20 replicates per scenario)

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
  15. **v0.5, the seal fix.** The audit draw stratifies on metadata only (era × genre × canonical). The v0.4 predicted-label strata would have exposed the naive Confirmation answer before registration (methods review P4).
  16. **v0.5, two fictions.** TF is the lead hypothesis. It was discovered on Discovery labels (literary review P1) and registered before Confirmation is unsealed. The canonicity measure is metadata-only (`docs/canon_measure.md`).
  17. **v0.5, family (decided by the user).** TF is the single primary at α = 0.05. H1 is the first secondary, Holm-corrected with the within-stratum contrasts. H2a–c and H3 are demoted to estimation (methods review P11).
  18. **v0.5, measurement.** The estimand is the expert (graduate-student, about 900 labels = a 50% within-cell subsample of the audit; blindness attestation required) construct, estimated with the expert-anchored three-level DSL. Peers enter as an intermediate phase. The teacher's items are descriptive. Exclusion uses κ against the expert. This replaces the v0.3–v0.4 peer-mean estimand.
  19. **v0.5, population.** `works_v2` with PG-agent author keys and the split repair; primary set `genre ≠ historical`; hand-verified early-era dates; unresolved or out-of-window works excluded; round-year placeholders excluded unless verified; 12 passages per work, with adaptive stopping deleted.
  20. **v0.5, classification.** The classification is symmetric, with Bonferroni-adjusted component CIs. The social patterns are named.
  21. **v0.5, replication.** Replication is optional: it never counts as a failed check.
  22. **v0.5, codebook.** No v1.0 relabel. The v0.9 production codebook (`v09lean_r2`) is registered as the model's codebook. The planned v1.0 content in former §4.1 is not adopted.
  23. **v0.5, levers.** The STEP-1880 and LINEAR contrasts and Neyman allocation on predicted labels were explored (§7.6) and **not adopted**. They are logged here as forks (methods review P5).
- **Unforeseen problems.** If an analysis cannot be run as registered (e.g., an era with no audited obstacles), the nearest pre-specified fallback is used: the identity link, then the raw DSL ratio contrast without covariates. The fallback is reported as such.


### 8.1 Seal-integrity log (factual entries; disclosure recommended by the orchestrator, final decision by the user)

| Date | Entry | Assessed impact |
|---|---|---|
| 2026-11-02 | 2026-11-02 ~20:58 CST: during testing of the platform-migration export tool, 5 sealed (confirmation-split) model-label result blobs (job ids `v09b_w02_conf_rand_a_conf_*`, ≈2,000 passages of model labels; no human labels) were exported, encrypted to a throwaway test key and decrypted to local disk by an automated test. They were deleted within minutes. No contents were read, displayed, analysed, uploaded or committed; only job ids appeared in logs. The R2 originals are untouched. Safeguards added: real sealed blobs can only be encrypted to the owner's pinned key; dry runs are restricted to synthetic data and refuse to write under `data/`. Assessed impact on the confirmatory analysis: none (no information about results was observed). | none |

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
- v0.5 (2026-11-01): responses to peer review and user decisions:
  - seal-safe metadata audit draw (`draw_audit_metadata`);
  - TWO FICTIONS as the lead hypothesis;
  - expert-anchored three-level DSL (graduate student, about 450 items, plus peers);
  - population and date rules; 12 passages per work;
  - symmetric classification; optional replication; H2/H3 estimation-only;
  - levers record (§7.6);
  - registered-design power (§7.7): TF power 0.59 at α = 0.05 (0.70 with 900 expert labels), and H1 MDE about 20 pp;
  - primaries decision box (§1).
- v0.5 final (2026-11-01, user decisions):
  - TF is the single primary at α = 0.05; H1 is the first secondary.
  - Expert subsample 50%: about 900 grad-student labels, with a required blindness attestation.
  - Canonical strata confirmed: 41 cells in the real draw.
  - `works_v2` fields registered (`author_group`, `split_v2`, `primary_v2_capv2`, `historical_setting`), with real primary-set counts.
  - `select_annotation.main` retired.
  - Registered power: TF 0.70, MDE 9 pp.
- v0.5 (2026-11-02): seal-integrity log §8.1 (migration-tool test incident), and the ciphertext-only sealed storage with offline owner key and one-way logged unseal (header).
- v0.5 (2026-11-04): verified early dates applied to `works_v2` (`year_v2`, `era_v2`, `date_verified`, `date_exclusion`, `placeholder_1900`); primary-set counts in §2 updated; the audit draw and `models.apply_works_v2` use `year_v2` and `primary_v2_capv2`. Metadata only. The date review is agent-conducted and still needs the human sign-off required in §2.

---

## Appendix A. OSF registration text (draft excerpts)

**Seal integrity (proposed disclosure; the user decides).**
"2026-11-02 ~20:58 CST: during testing of the platform-migration export tool, 5 sealed (confirmation-split) model-label result blobs (job ids `v09b_w02_conf_rand_a_conf_*`, ≈2,000 passages of model labels; no human labels) were exported, encrypted to a throwaway test key and decrypted to local disk by an automated test. They were deleted within minutes. No contents were read, displayed, analysed, uploaded or committed; only job ids appeared in logs. The R2 originals are untouched. Safeguards added: real sealed blobs can only be encrypted to the owner's pinned key; dry runs are restricted to synthetic data and refuse to write under `data/`. Assessed impact on the confirmatory analysis: none (no information about results was observed)."

**Sealing.** Confirmation-split model labels are stored ciphertext-only (age/X25519), encrypted to an owner-held offline key. Unsealing is a one-way operation, logged against this registration's hash. Confirmation human-audit items were drawn using metadata only (era × genre × canonical), so the draw reveals no model-label information.
- v0.6 PROPOSAL (2026-11-04; pending the user):
  - TF statistic kept as the joint 2-df Wald, with the inwardness index as the registered summary;
  - H1 as a second primary under a fallback procedure (.04 / .01);
  - juvenile sensitivity and estimand wording;
  - internal-construct risk;
  - §7.8–7.9 power.

