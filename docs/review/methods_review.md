# Peer review: methods and statistics for "What Stands in the Way" (2026-11-01)

**Stance.** I reviewed this as an adversarial methods and statistics referee, at the standard of ACL and the *Journal of
Cultural Analytics*. The companion `docs/review/literary_review.md` covers the humanistic case and canon composition.
I cite it where we overlap and do not repeat it.

**What I read.**
- `docs/plan/research_plan_v2.md`, `docs/prereg.md` (v0.4 draft), `docs/codebook.md` (v0.9), `docs/data_quality.md`,
  `docs/gates.md`, `docs/pilot_analysis_1.md`, `docs/qa/label_pass_2.md`, `docs/model_selection.md`,
  `docs/perf_label_ab.md`, `docs/novelty_matrix.md` and `docs/decision_memo.md`.
- `analysis/stats/*` (code, README and `out/*.csv`), `analysis/select_annotation.py`,
  `analysis/build_annotation_queues.py`, `pipeline/make_jobs.py`, `pipeline/genre.py`, `research/date_audit/report.md`
  and `research/date_audit/gold/report.md`.

**What I checked in the data.** All queries were read-only.
- The v0.9 label pin `41ca3c7d`: 8,718 random-backbone passages, all Discovery, from 5,304 works by 1,461 authors.
- The v0.5 pilot pin `2c86999f`: 1,535 rows.
- The alternate-family pin `ca0c1188` (qwen3.5:9b, codebook v0.9): 600 passages overlap the main labels.
- `works.parquet`, `genre.parquet`, `workcheck_keep.parquet`, the job plan and the annotation reference files.

The scripts are in `/tmp/rev/q*.py`. They are not committed, but each one is a short pandas or duckdb query.

**Bottom line.**
- The engineering and the inference machinery are unusually careful for a project this young: cross-fitted DSL, π
  persisted for every pool passage, author-clustered sandwich SEs, simulation-calibrated coverage, and a mechanical
  verdict.
- The weak links are elsewhere:
  - the construct the machinery is pointed at;
  - the dates and the early-era sample it rests on;
  - a seal that the registered audit procedure breaks by design;
  - a primary test whose own simulations predict an uninformative null.
- The estimand is coherent and the code mostly matches it. **As registered, though, the most likely outcome is "no locus
  shift detected (MDE ≈ 17 pp)", measured on a construct that does not test the named thesis.** Every problem below can
  still be fixed before the planned Nov 8–9 registration. Several fixes cost less than a day.

---

## 1. Ranked problems

Severity scale:
- **fatal**: the confirmatory claim cannot be defended as designed;
- **major**: a reviewer will require it fixed or disclosed prominently;
- **minor**: it should be fixed, but it does not change the conclusions.

### P1 (fatal as framed): "locus" is a recode of domain, the construct depends on which model applies it, and neither supports a test of the inward turn

**Evidence.**
1. **Locus is a domain bucket.**
   - Under v0.9, locus equals the default mapping of the first domain in **94.6%** of obstacles (E 92.8%, M 94.3%,
     L 94.7%; n = 6,290 obstacles).
   - Under v0.5 the figure was 93–100%.
   - The QA reference departs from the mapping in 17% of cases (`perf_label_ab.md`).
   - v0.9 made `locus_reason` mandatory. It is now filled in **100%** of rows, yet the departure rate barely moved. The
     model writes a reason and keeps the default.
   - So the model's "internal" share is close to "first domain = INNER_STATE": 7.5–9.2% of obstacles in each era.
   - H1 is therefore effectively a test of the domain mix, with ILLNESS → material as a codebook stipulation.
2. **The construct depends on the model.**
   - Two models applied the same v0.9 codebook to the same 600 passages: gemma4-12B (the pinned labeller) and
     qwen3.5-9B (the registered alternate family, battery check 6).
   - Gemma says `yes` on **72.3%** of passages. Qwen says `yes` on **32.2%**.
   - Cohen's κ is **0.24** for has_obstacle and **0.25** for the 4-category locus target (none / material / social /
     internal), with raw agreement 0.48.
   - The first domain agrees on only **48%** of the passages both models call obstacles.
   - Plan gate G1 asks for "Tier-1/Tier-2 κ ≥ 0.6 on has_obstacle". By this measure it fails badly.
3. **The construct depends on the codebook version.**
   - The pilot (v0.5) motivated the v0.4 redesign with a +8.1 pp M → L material step "in the 1880s".
   - Under v0.9, on 8,718 Discovery passages, naive work-level material shares are E 0.168, M 0.186, L 0.211.
   - L − M = **+2.4 pp, author-bootstrap 95% CI [−3.1, +7.0]**. By decade the 1870s, 1880s and 1890s are 0.198 /
     0.207 / 0.221. The step is gone. See also P5.
4. **The scale does not match the thesis.**
   - The unit is a random 350-word window. The has_obstacle rate is 72% (Gemma), so nearly every window "has" an
     obstacle. The measure is closer to "local conflict present" than to "what blocks the plot" (literary review, P2).
   - The novelty matrix itself records that Kahler's thesis is about narrative *up to about 1800*. The 1800–1849 vs
     1885–1929 contrast therefore does not test his proposition.
   - The modernist inward turn (James, Woolf) concerns elite fiction. That is a minority of a late era in which 31% of
     works are juvenile.

**Fix.**
- **(a) Rename and re-scope H1.** Make it "the locus mix of scene-level obstacles in PG-preserved fiction". Drop
  "tests Kahler" from every claim; "motivated by the inward-turn literature" is enough. This costs nothing and is
  required.
- **(b) Register the estimand as the human construct of locus, and say plainly that the model contributes little
  locus information beyond its domain call.** DSL remains valid, because g absorbs this. But H1's power then comes
  almost entirely from human labels, which is what §7.4 already finds. Report the domain-mapped locus (§5.8) as
  co-equal, not as a sensitivity.
- **(c) Report the Gemma/Qwen disagreement and a third model on the same 600 passages.** Add a stronger API model or
  Tier-3 on 300 of them. Treat "construct stability across instruments" as a reported result (see redirection D).
  Do not pass battery check 6 by comparing naive estimates alone when the two instruments disagree on prevalence by
  40 pp.
- **(d) Pre-register a minimum construct-validity gate on the human audit.**
  - Annotator-mean vs expert κ ≥ 0.6 on locus.
  - Model vs human-mean κ reported per era.
  - If either fails, H1 is reported as descriptive.

### P2 (fatal for H1 as an informative test): the registered design has very little power against any effect the data now suggest, and the simulation inputs are optimistic

**Evidence.**
1. **The design's own power figures** (§7.4–7.5):
   - 0.55 against a large simulated Kahler effect (material −12.7 pp, internal +8.2 pp, expert construct);
   - **0.15–0.25** against the pilot-like truth;
   - MDE **17.6 pp** for material and **9.7 pp** for internal, human construct.
   The material share itself is only about 0.17–0.21. The design can detect roughly a doubling.
2. **What the v0.9 Discovery labels show.** The current naive estimate (not genre-standardised, not human-corrected) is:
   - L − E material **+4.3 pp**, author-bootstrap CI [−2.4, +11.2];
   - internal **−0.7 pp** [−4.4, +3.0].

   The simulations show that naive labels *exaggerate* contrasts (validate.py: naive bias roughly doubles H1), so the
   human-construct effect is plausibly 2–4 pp. Against a 17.6 pp MDE, **power is ≈ 0.05–0.08**.
3. **The simulation's early era is about twice the real primary set.**
   - §7 assumes about 190 early works and 65 authors per half.
   - The primary set (high or medium date confidence, author cap, workcheck keep) has **106 Confirmation works and 68
     authors** dated 1800–1849 (130 / 66 in Discovery).
   - Only 46 Confirmation early works have high-confidence dates (battery check 4).
   - The early-era terms dominate the SE.
4. **The ICC and prevalence assumptions are off.**
   - The simulation assumes a latent author ICC of 0.05, a work ICC of 0.02, and prevalence 0.45.
   - On the v0.9 labels, the observed-scale author ICC is **0.10** for the material indicator among obstacles (work ICC
     0.15), and prevalence is **0.72**.
   - An observed-scale ICC of 0.10 for a binary outcome is a latent ICC well above 0.05. §7.1(a) shows the MDE floor
     rises by about 25–60% between ICC 0.05 and 0.20.
5. **Monte Carlo error is large.**
   - The power tables use 20 replicates (±0.10 MC SE on a power), and some cells have 2 replicates.
   - The difference between "0.15" and "0.25" carries no information.
6. **The human-label volume is unverified.** About 2,000 non-expert labels are planned (4 × 500) from a high-school
   student and peers in the window Nov 6–8. At 504 labels, the MDE is 19–23 pp (§7.1b).

**Fix.**
- Re-run `power.py --final --v04` with:
  - the real primary-set early counts (about 106 works per half, from the frame, not G0);
  - an ICC estimated from Discovery labels;
  - prevalence 0.72;
  - the realised label count;
  - ≥ 100 replicates for the registered cell.
- Register **the expected-effect power**, using the v0.9 Discovery effect deflated for naive bias. Register the MDE
  table alongside it.
- Then choose one of the following before registration:
  - **(i)** keep H1 as a test, but state in the prereg that a null is the expected outcome and is uninformative below
    17 pp;
  - **(ii)** convert H1 into an *estimation* hypothesis with a pre-declared region of practical equivalence (e.g., ±5 pp)
    and report P(|Δ| < 5 pp). This only becomes informative with the measurement upgrade in redirection A;
  - **(iii)** buy power through annotator quality. The prereg's own ablation (§7.4) shows expert-quality annotators
    give an MDE of 11.5 pp and power 0.95 / 0.85. See redirection A.

### P3 (major, borderline fatal for the E era): dates are unreliable where H1 needs them most, and the confidence tiers that filter them are built on a bad source

**Evidence.**
1. **The automated audit** (`research/date_audit/report.md`) finds Open Library within ±5 years of pg-dates for only
   **27–47%** of matched works in every decade from 1800 to 1880 (1830s: 26.7%; 1840s: 32.7%). Agreement reaches 65–74%
   only after 1900. The audit proposes 625 era-changing corrections.
2. **The 120-work date-gold review** (`research/date_audit/gold/report.md`; agent-conducted, not yet human-signed):
   - pg-dates first-book errors > 5 years: **16/55 (29%)** on the enriched paired sample.
   - Early works without an external match: **7/23 (30%)**.
   - Weighted residual era misassignment on the covered frame: **10.1%** keeping pg-dates. The identification bounds are
     **5.2–43.9%**. The corpus-wide rate is "not identified".
3. **Open Library is wrong on the disagreements** (47–56%). Yet the primary-set filter `date_confidence` (high = OL
   agrees) is built from it. Agreement between OL and pg-dates is not independent corroboration, since OL already
   feeds the input confidence.
4. **The early era leans on the weakest dates.** Only **22.5%** of early-era works are high-confidence, against 49.7%
   in the late era. 33.7% are low-confidence. The primary set already loses about a third of the early era to this
   filter.
5. **Dates heap on round years.** **359** works are dated exactly 1900. 17.6% of mid-era years end in 0. These look
   like placeholders.
6. **The event being dated is undefined.** Composition, serial, first book and edition dates are all in play: Brontë
   *Twelve Adventurers* is PG 1838, first published 1925. The prereg never says which date the construct uses.
7. **Gate B / G1 is not met.** It requires a human hand-check of 60 works with ≥ 85% within ±5 years. The
   agent-conducted gold says plainly that it does not satisfy the gate.
8. **Boundary density.** 215 works lie within ±3 years of 1850, and 764 within ±3 years of 1885 (which matters for
   H1-ML).

**Fix (cheap, and the highest-value fix in this review).**
- **Hand-verify every work in the early-era primary set**: about 236 works over both halves, or 106 in Confirmation.
  Also verify every work dated 1847–1853, against a first-edition bibliography. Use Garside, Raven & Schöwerling for
  1800–1829, the *At the Circulating Library* (ATCL) database for British 1837–1901, and Wright for American fiction.
  At about 5 minutes per work this is roughly 30–40 person-hours. Agents can prepare the evidence, and a human signs.
- **Register the date variable** as "earliest documented book or serial publication; composition dates are not used".
- **Drop OL-agreement as the definition of "high"** and redefine the tiers from the verified dates.
- Add a date-error sensitivity analysis that perturbs years by the measured error distribution (SIMEX, or a
  multiple-imputation analysis over plausible years) and reports how H1 moves.
- Treat year = 1900 (and years ending in 00) as missing unless verified.

### P4 (major; fatal for the "sealed" claim if left as is): the registered audit draw reads the Confirmation labels before registration, and none of the human raters is blind to the hypotheses

**Evidence.**
1. **The audit draw reads Confirmation labels, and its summary shows the naive H1.**
   - `build_annotation_queues.py build` calls `draw_audit(lab_conf, …, group_col="dgroup")`. The strata are era ×
     *predicted Confirmation domain group*. The draw is scheduled for **Thu Nov 5**; registration is Nov 8–9.
   - The script writes `design_summary.json` with N_cell for every era × domain-group cell. `print_summary` prints the
     same.
   - From those counts anyone can read the **naive Confirmation locus and domain mix by era**, which is the naive H1
     and H2b/c answer, before the hash exists.
   - Prereg §0 says the Confirmation labels "have not been read by any analyst". The registered procedure breaks this.
2. **The expert reference is not blind to the hypotheses or the early results.** The English teacher is the expert and
   the arbiter for v1.0. On Nov 1 the teacher was shown the deployed showcase (`showcase/`, `data/work/showcase/stats.json`):
   - era-wise locus shares with CIs;
   - nine dated cross-era passage cards.
3. **The student annotator is not blind.** The student is the project lead, knows H1 and the pilot results, and labels
   about 500 Confirmation audit items.
4. **Blinding to era is impossible.** Diction dates the passage. Hiding title, author and date does not hide era, so
   "annotators see no date" does not deliver era-blind labelling.

**Fix.**
- **(a) Do the draw blind.**
  - Run it in a script that writes `audit_frame.parquet`, the queues and **only a SHA-256 hash** of the cell table.
  - It must print no N_cell and no era × group counts.
  - Deposit the hash on OSF, with an embargoed pre-registration addendum, *before* anyone opens the frame.
  - Alternatively, register first and draw after.
  - Or stratify on label-free variables (era × genre × length tercile) and get domain coverage by oversampling
    enrichment-lexicon hits, whose π is known from metadata. The prereg's own §7.4 found the domain strata bought no
    precision.
- **(b) Record in the prereg exactly what each rater has seen** (showcase, pilot, hypotheses). Report the expert-nested
  estimate as "expert exposed to Discovery results".
- **(c) Remove the project lead from the Confirmation audit pool,** or report the H1 estimate both with and without
  their labels. Their labels are random within cell, so DSL can be recomputed with π adjusted (prereg rule 4).
- **(d) Pre-register an era-differential-error check that has power.** At about 60 overlap pairs per era, the SE of an
  era κ is about 0.08 and the SE of a difference about 0.11. The "> 0.15" trigger therefore misses the +0.10 error
  shift that moved H1 by 27% in simulation.
  - Put **all** expert items and at least 20% overlap into E and L.
  - Or use a likelihood-ratio test of era-specific annotator confusion matrices.

### P5 (major): the garden of forking paths, already walked once, and the motivating pilot result has regressed toward zero

**Evidence.** Between v0.1 and v0.4, over about 48 hours, the following were all decided after Discovery labels had been
seen (the eras were the exception: they were fixed at G0, before labels):
- H1 made two-sided;
- the genre variable chosen and registered;
- the reference level changed;
- H1-ML added;
- codebook edits E1–E6 aimed at the errors the pilot exposed;
- the adoption bar for v0.9 **waived** (`perf_label_ab.md`: locus 0.827 against a bar of 0.895; quotes 0.93 against
  0.95).

The v0.5 work-in-progress goes further. `analysis/stats/levers.py` (untracked `out/levers.csv`) evaluates replacing the
E-vs-L contrast with **STEP (pre/post 1880)** or **LIN** contrasts. The power truth is `SimConfig.pilot_step`, a step in
**1883**, chosen from the pilot's shape.
- STEP power under that truth is **0.40–0.50**, against 0.15–0.20 for EL.
- **The step it is tuned to has already disappeared under v0.9:** the 1870s, 1880s and 1890s give 0.198 / 0.207 / 0.221,
  and L − M is +2.4 pp [−3.1, +7.0].
- Adopting a contrast tuned to the pilot step would be textbook HARKing.

Smaller forks:
- the ⌈7/9⌉ battery rule;
- the "missing check counts as failed" rule;
- the ×10 H3 calibration;
- the classification rules (P10);
- the choice of α for H1-ML.

**Fix.**
- Freeze the hypothesis set at v0.4. **Do not adopt STEP-1880 or any contrast chosen for its power under a
  pilot-shaped truth.**
- If the late-heavy data argue for a different primary contrast, justify it from *coverage and date quality alone*,
  with no Discovery outcome. Register it as a co-primary with α split (e.g., EL and ML at 0.025 each).
- Add a **multiverse appendix** listing each fork and the H1 estimate along it on Discovery. If the Discovery multiverse
  spans zero, say so.
- Log v0.5 in §8 even if nothing is adopted.

### P6 (major): the measurement model turns "human construct" into "what four non-experts trained on AI keys say", and the expert anchor is too thin to fix it

**Evidence.**
1. **The registered estimand** is the mean of retained non-expert annotators: the student plus about 3 peers.
   - The practice, certification and retake keys (`practice_ref.json`) are "practice: orchestrator agent; cert/retake:
     drafted by sub-agents, spot-checked".
   - The QA reference (`label_pass_2`) and the bench reference (`bench_ref_claude.jsonl`) are Claude readings.
   - So humans are certified against an LLM's construct, and the LLM labeller is then corrected toward those humans.
     The "validated against human readers" claim is partly circular.
2. **The κ ≈ 0.6 annotator quality is assumed, not measured.**
   - With κ estimated on 30 items (SE ≈ 0.1), true-κ 0.59–0.68 annotators were wrongly excluded in 15–35% of
     simulated replicates.
3. **The 30 expert items are unrepresentative.** They are 10 per era, drawn by SRS from an *equal-allocation* audit:
   75 per cell across 8 domain groups. Communication, distance, darkness and "other" are therefore over-represented
   about 5–20× relative to the population.
   - The κ-exclusion rule and the attenuation correction (§5.1 rule 7) are computed on a mix unlike the one H1
     averages over.
   - The two-phase π is right, but the κ is not representative.
4. **Attenuation shrinks effects by about ×0.62–0.66.** The "attenuation-corrected range" divides by a misclassification
   matrix estimated from 30 items, so its interval will be very wide. The headline effect sizes are therefore in a unit
   (non-expert construct) that no reader can interpret.

**Fix.**
- Re-anchor the estimand on experts (see redirection A). If that is impossible, at least:
  - have the teacher (or a second literary expert) label **≥ 150** items: 50 per era, drawn *within* the audit with
    weights so they are representative of the population after reweighting;
  - make the expert-nested estimate a reported co-estimate rather than a "sensitivity";
  - **replace the AI-drafted cert keys** with teacher-adjudicated keys, or disclose them as AI-drafted and report
    annotator–teacher κ alongside annotator–key κ;
  - report annotator κ against the expert on the *reweighted* population mix.

### P7 (major): the genre standardisation extrapolates the early era, and the "contemporary setting" filter cannot be built

**Evidence.**
1. **The standard population draws mostly on the late era.** It is 3,000 works pooled from both halves, and since about
   84% of the primary set is late, the standard is roughly 30% juvenile.
   - The Confirmation early era has **106** primary works spread over 8 genres: historical 27, domestic 21, other 16,
     juvenile 15, sensation 12, adventure 7, collection 5, romance 3.
   - Genre enters additively, with no era × genre interaction. The E-era standardised share is therefore what early
     fiction would look like with a late genre mix, under the assumption that genre effects estimated mostly from late
     works hold in 1800–1849. Boys' series fiction in 1910 and LCSH "juvenile" in 1830 are not the same stratum.
2. **Genre is LCSH and bookshelf metadata assigned by later cataloguers.** Tagging density and practice differ by era,
   as `genre.py`'s own residual-domestic bucket shows. Genre misclassification is then era-differential, and
   standardising on a misclassified covariate can add bias.
3. **The primary set cannot be built as written.** Prereg §2 excludes historical-setting works ("contemporary setting").
   But `works.parquet` has **no `setting_period` column**. The workcheck stage has run on **225** works, and
   `workcheck_keep.parquet` has no setting field. Historical novels make up **23%** of the Confirmation early primary
   set (Scott-type fiction set centuries earlier), against about 8% in the late era.
4. **Origin is mostly unknown.** It is **65% `unknown`** in every era: Wikidata returned 403 and LoCC alone was used.
   The origin covariate is largely uninformative, and UK/US contrasts are not identified.

**Fix.**
- **Register an implementable primary set now**: "genre ≠ historical". Treat setting_period as a sensitivity once
  workcheck has run, or drop it from §2.
- Report H1 standardised to **three** standards: the pooled mix, the early-era mix, and an overlap-weighted population
  (weights ∝ min propensity of era membership given genre, origin and length).
- Add an era × genre interaction sensitivity.
- Report that origin is 65% unknown, and remove the UK/US contrast from §5.8 unless origin is fixed (PG agent IDs →
  Wikidata or LC NAF birthplace).

### P8 (major): the Discovery/Confirmation split is not author-independent, and the author clusters are under-merged

**Evidence.**
- `author_key` is a normalised name string, so variant names become separate "authors". Examples from `works.parquet`:
  - Horatio Alger appears under **10 keys** across both halves (103 Discovery / 28 Confirmation works);
  - Dickens **9 keys** (5 / 38);
  - Twain **5 keys** (1 / 36);
  - Ouida **3 keys** (2 / 18);
  - Brontë 3 keys across both halves;
  - "anonymous" is one cluster of unrelated works.
- **The Stratemeyer Syndicate's house names straddle the halves.** "Victor Appleton" (34) and "Laura Lee Hope" (69) are
  in Discovery; "Franklin W. Dixon", "Allen Chapman", "Roy Rockwood", "Margaret Penrose" and "Alice Emerson" are in
  Confirmation. They were outlined by one man and ghost-written by a shared pool, in the juvenile class that makes up
  31% of the late era.
- Consequences:
  - (i) Confirmation is partly a resample of Discovery's authors and syndicates, so "replication" is overstated.
  - (ii) Within a half, one real author split across several clusters gives **CR1 SEs that are too small**.
  - (iii) The 5-per-author-per-decade cap is porous.

**Fix.**
- Do **not** re-split: that would unseal.
- Canonicalise authors with PG agent IDs from the RDF plus their aliases, LC NAF or VIAF where they resolve, and a hand
  list of syndicate house names mapped to a single "Stratemeyer" cluster.
- Use the canonical clusters for SEs and for the cap.
- Run H1 on Confirmation with every cross-half canonical author removed, as a registered sensitivity analysis.
- Report the number of works affected.

### P9 (major): the prereg describes procedures that the pipeline does not run

**Evidence.**
1. **Adaptive stopping does not exist in the code.**
   - §3.3 (adaptive stopping by decade × stratum cell, whole works in seeded order, `work_weight = N_d/n_d`, early
     cells labelled in full) has no implementation in `pipeline/make_jobs.py` or the coordinator.
   - The waves are passage-hash streams instead: `w02` takes random k < 12 for every Confirmation work, then the
     enrichment waves (priority 22–23) run **before** `w06`, the random k ≥ 12 (priority 25).
   - If compute runs short before unsealing (planned Nov 10) or before the v1.0 relabel (about 87k + 88k Confirmation
     random passages), Confirmation has **12, not 24,** passages per work. Every power figure assumes 24.
   - Discovery currently has 1.6 passages per work.
2. **`select_annotation.main` still runs the old design:** 200 items, both halves, two annotators, the teacher as
   adjudicator. The README and `resolve_human` still describe "the teacher's row wins" adjudication, which the prereg
   forbids. The registered path is `build_annotation_queues.py`. Two code paths with different designs is an error
   waiting to happen.
3. **The codebook text named in the prereg is not the one in production.** §4.1 names variant `v09a`; production v0.9
   is `v09lean_r2`.
4. **Audit eras and estimand eras use different cut rules.** The audit strata and the era-stratified g use **decade**
   cuts (`select_annotation.era`, `dsl._era`), so works from 1885–1889 sit in the "mid" audit cells. The estimand uses
   **year** cuts. This is valid because π is known, but it is undocumented. Era-wise κ and expert items are by decade
   era too. The label `late_1885_1920` contradicts the 1929 window.
5. **The replication data are missing.** ELTeC-eng and Chicago are not in `data/`. Under §5.6 a check that cannot run
   counts as failed, and §5.7 requires replication for "supported". **As things stand, no hypothesis can be
   "supported".** Even with ELTeC, its early era (1841–1849) holds a handful of novels, and its labels would be naive
   (no audit), so they carry the roughly 2× naive bias.

**Fix.**
- Either implement §3.3 or delete it and register what actually runs: "random k < 12 for all works, then k ≥ 12;
  unsealing uses whatever is complete, with inclusion probability per work = labelled / 24". Within-work Hájek weights
  handle this.
- Move `w06` ahead of the enrichment waves.
- Delete or redirect `select_annotation.main`. Fix the README's adjudication text.
- Name the production codebook in §4.1.
- Document the decade-era audit cells.
- Make replication a *reported* item, not a verdict gate, for any hypothesis whose replication frame cannot cover the
  contrast. Or obtain ELTeC now and audit 100 of its passages.

### P10 (major): the two-sided H1's classification rules are asymmetric and leave out the social share

**Evidence.**
- `classify_h1` assigns:
  - **inward** when *both* component CIs exclude 0 in the Kahler direction;
  - **outward** when the material CI excludes 0 and the internal *point estimate* is ≤ 0.
- The internal share is about 10%, with an SE of about 3.5 pp, so its CI almost always spans 0.
- The rule therefore makes "outward" far easier to declare than "inward", and "inward-ish" truths fall into "mixed"
  (§7.5: inward truth classified 0.20 inward / 0.35 mixed).
- That asymmetry happens to favour the pilot's direction, which the v0.4 rationale says it does not do.
- Social is the residual: Δ_social = −(Δ_mat + Δ_int). A pure socialisation or de-socialisation shift is rejected by the
  2-df test but labelled "mixed", though it is the most likely large shift (social is about 70% of obstacles).
- The classes rely on unadjusted marginal 95% CIs after a joint test, which carries a Type-S risk.
- The battery then re-checks the *observed* sign (`battery._ref`), so the direction checked is chosen by the data.

**Fix.**
- Make the rules symmetric:
  - outward = material CI > 0 **and** internal CI ≤ 0, or the same "point estimate" rule for both classes;
  - name the "social up" and "social down" patterns explicitly;
  - classify by which pre-declared region of the simplex the 95% *joint* confidence ellipse sits in, and call any
    pattern whose ellipse spans two regions "indeterminate".
- Pre-register a directional error control for the classification, e.g. a Shaffer-style partitioning principle.

### P11 (major for credibility, minor for H1): H2a–c and H3 are registered tests that cannot succeed

**Evidence.**
- **H2 power.** The registered MDEs are H2a ≥ 35 pp (35–196 pp), H2b 5.3 pp and H2c 4.8 pp, against plausible effects
  of 1–2 pp. Power is 0.05–0.15. Holm over four near-powerless tests only adds noise.
- **The H2 data are tiny.** In the v0.9 Discovery labels so far:
  - DARKNESS appears in **0.6%** of early obstacles (1 passage of 178);
  - the early communication-cause target rests on **18** passages.
- **H3 tests a straw man.** Its null is "the function series equals the keyword series in z-units (perfect tracking)".
  Perfect tracking is impossible between a per-10k-word keyword rate and a DSL per-passage function rate over about 9
  decades, so rejecting it says nothing about "mention ≠ function".
- **The H3 calibration is ad hoc and does not hold.** The ×10 p-value inflation was tuned in 140 replicates. In
  `power_final_v04.csv` the tracking-null rejection rate is still 0.05–0.25 across scenarios.
- **H3's inputs do not exist yet.** The lexicon is not frozen ("on _TBD_"), and HTRC EF is not acquired.

**Fix.**
- Demote H2a–c and H3 to **pre-registered estimation**: effect and CI, no test, no verdict. That leaves H1 alone as the
  confirmatory test.
- If H3 stays, test a substantive null, e.g. "keyword and function series correlate at r ≥ 0.7". Run it as an
  equivalence-style test with a CI for r from the block bootstrap.

### P12 (minor): quote verification falls short of gate G1, and the rejection rule is a hidden recode

**Evidence.**
- Among 6,290 v0.9 yes rows, quotes verify as exact or normalised in **91.2%** of cases, rising to **95.9%** with
  `trimmed`. 3.3% are copied from context and 0.7% are hallucinated. G1 asks for ≥ 97%.
- Rejected labels become `has_obstacle = no` (§5.5). That is outcome-dependent. It is roughly balanced across eras
  (verified rate E 92.7%, M 91.5%, L 91.1%), and DSL corrects it, but it makes the model label worse and hides the
  failure rate.
- QA pass 2 found that a third of quote-from-context rows also took their label from context.

**Fix.**
- Report G1 as failed, with the actual rates.
- Keep rejected rows as their own model category (an extra column of g). Do not recode them to "no".
- Run the `quote_from_context` exclusion sensitivity on Confirmation as registered.

### P13 (minor): sampling and weighting choices

- **Equal work weights.** A 15k-word series book counts the same as *Middlemarch*. The work is a defensible unit, but
  report a length-weighted (per-passage) estimand too, since readers experienced novels, not catalogue entries.
- **The author cap is randomised per decade and capped at 5.** The Confirmation early primary set is still 27%
  concentrated in its top 5 authors (Bulwer, Cooper, "anonymous", Disraeli, Dickens). Leave-one-author-out
  (influence-based) handles this. Report the top-5 share.
- **The enrichment exclusion from DSL is correct.** Say in the paper that the enrichment exemplars are not
  representative.
- **The early era is mostly the 1840s.** g-computation uses each era's empirical year distribution, so E is "mostly the
  1840s": 50 of 116 Confirmation early works. Say that "1800–1849" effectively means about 1835–1849, and check how
  leave-one-decade-out without the 1840s behaves (it may fail by construction).

### P14 (minor): reproducibility

**Gaps.**
- **Labels are not deterministic.** Temperature 0 is not deterministic under parallel batching: identical v0 runs gave
  locus agreement 0.837–0.860 (`perf_label_ab.md` §7).
  - Tiers run with different NP (4 vs 6) and KV settings.
  - `twin_pairs` is empty, so test–retest has not been measured in production.
- **Several references cannot be reproduced.** The QA reference, the bench reference, the date gold and the
  practice/cert keys were all produced by AI agents through tools that cannot be re-run (`collect_web.js` "not
  standalone").
- **pg-dates is CC BY-NC.** It cannot be redistributed with the derived dataset.
- **The registry is ahead of the prereg.** It changes over time (v09b re-push excluding 857 works), and the prereg
  commit is still TBD.

**Fix.**
- Record `num_parallel` and the KV type per result row.
- Re-label a fixed 500-passage set on every worker class and report κ.
- Archive agent transcripts and every cached source.
- Release derived labels with pg-dates *keys* only.
- Pin the registry SHA in the prereg.

### P15 (minor): leakage audit (mostly clean)

What I checked:
- The two few-shot passages in the codebook are Discovery: *Zenobia* (pg8938, 1827) and Evarts (pg72909, 1923).
- The QA, bench, practice/cert and showcase passages are Discovery. All 9 showcase cards are Discovery.
- 0 authors fall in both halves by `author_key`.
- The real leakage paths are three:
  - **P8:** the same author under different keys, and syndicates;
  - **P4:** Confirmation labels read at the audit draw;
  - **memorisation:** a canonical early era that the 12B labeller may know. The name-cloze probe uses the same model,
    with 3 masks per work, so it is a weak canonicity measure (literary review, P1).
- "Teaching authors excluded from the audit pool" does nothing: teaching authors are Discovery by construction. Say so,
  rather than presenting it as a safeguard.

---

## 2. Redirection ideas

### A. Buy measurement, not labels: expert-anchored audit and a later unseal (most defensible, biggest power gain)

**What changes.**
- Replace the 4 non-expert annotators with **2–3 trained literary readers**: the teacher plus one or two English
  graduate students or colleagues.
- Each labels about 400–600 Confirmation items under the v1.0 guide, with 15% overlap.
- The estimand becomes the expert construct. Non-expert labels, if collected, become a second phase.

**Why.**
- The prereg's own ablation (§7.4) puts H1 at MDE 11.5 pp with power **0.95 / 0.85** for expert-quality annotators,
  against 17.6 pp and 0.35 / 0.50 for the registered κ ≈ 0.6 crowd. No other lever comes close.
- It also removes the circularity of AI-drafted keys and the uninterpretable "attenuated" units.

**Cost.**
- About 40–60 expert-hours, roughly $1–2k if paid.
- More importantly, **unsealing moves past Nov 20.** Submit AAAI and DH on Nov 19–20 as design, measurement and
  Discovery papers; AAAI's "agents narrate noise" is unaffected. Unseal for the NAACL SRW paper (Jan 11).
- That decouples a confirmatory result from a 3-week deadline, which is what a JCA reviewer would want anyway.

### B. Fix the population before testing it: verified dates, an implementable primary set, and a coverage-justified contrast

**What changes.**
- Hand-verify the dates of every early-era and 1847–1853 work, about 350 works in both halves (P3).
- Register "genre ≠ historical" as the primary set, and canonical author clusters (P7, P8).
- Register **EL and ML as co-primary contrasts at α = 0.025 each**. Justify this by coverage and date quality only
  (ML has about 5× the early era's works, and the 1850–1884 dates are better), never by the pilot's step.
- Keep 1800–1839 descriptive.

**Why.**
- In `levers.csv` (no annotator-noise correction), ML has a lower MDE than EL (10.9 vs 13.8 pp under the null truth; 11.5 vs 13.9 pp under the pilot truth), and it
  rests on better-dated works.
- Verified dates remove the largest unquantified bias in E.

**Cost.**
- About 30–40 person-hours of bibliographic checking.
- Half the α for each contrast.
- Losing the "since 1800" headline unless EL succeeds.

### C. Make the confound the finding: reweight to the publication population, or split canon from mass

**What changes.**
- Post-stratify PG works to an external bibliography of what was actually published, by year × genre (× sex of
  author): ATCL for British fiction 1837–1901, Garside et al. 1800–1836, Wright for American fiction 1851–1900. This
  estimates "the fiction published" rather than "the fiction PG kept".
- Or, cheaper: register a canon × era interaction (literary review, R1) with a pre-declared canonicity variable.

**Why.**
- It turns the PG selection problem (P7; literary review P1) from a threat into the estimand.
- An "outward" result that is entirely composition would itself be publishable.

**Cost.**
- ATCL matching and coverage weights take 1–2 weeks. They are realistic for SRW or JCA, not for Nov 20.
- The canonicity-interaction version costs about a day, but it is a new hypothesis and has to be registered before
  unsealing.

### D. Lead the AAAI/DH papers with the instrument: a multiverse of construct instability

**What changes.** Report, on Discovery only (no seal is touched), how much the "historical trend" depends on the
instrument:
- the model: Gemma 72% yes vs Qwen 32% yes, κ 0.24;
- the codebook version: under v0.5 the M → L material step is +8.1 pp; under v0.9 it is +2.4 pp;
- the date source: pg-dates vs OL vs the rule;
- the genre standard;
- clustering by author or by work.

Present it as a specification curve with every H1 estimate.

**Why.**
- It is fully defensible whatever H1 does.
- It speaks directly to the AAAI Eval-AI-Scientists theme: agents, and pipelines, narrate noise.
- It answers in advance the first question any computational-humanities reviewer will ask.

**Cost.**
- About 1–2 days of compute and analysis, using existing labels plus one more model on 600 passages.
- Low risk. It does not replace the humanities finding; it frames it.

---

## 3. What a hostile *Journal of Cultural Analytics* reviewer would write

The authors claim a corpus-scale test of the "inward turn". Their own data show that the model's "locus" is a fixed
recode of its domain label 95% of the time, and that a second model applying the same codebook calls only 32% of
passages obstacles, against the first model's 72% (κ = 0.24). What is being measured is therefore the instrument as
much as the fiction. The decisive early era rests on roughly a hundred Project Gutenberg survivors per half, heavy with
canonical authors and historical novels, whose dates are wrong by more than five years in about a third of audited
cases. They are then standardised to a late-era genre mix dominated by juvenile series fiction, so the "within-genre"
comparison is largely an extrapolation. The registered design's own simulations put power at 15–55% against a
detectable effect of about 17 percentage points, so the most likely result is an uninformative null. And that null
would come from "human" labels supplied by four non-experts certified against AI-written answer keys, with an expert
anchor of 30 items. Finally, the hypothesis was made two-sided, and new contrasts were explored, in response to a pilot
pattern that disappeared when the codebook changed. The audit draw also reads the "sealed" Confirmation labels before
registration, so I cannot accept the confirmatory framing as it stands.

---

## Appendix: numbers computed for this review (v0.9 pin `41ca3c7d`, Discovery, random backbone)

| Quantity | E (1800–49) | M (1850–84) | L (1885–1929) |
|---|---|---|---|
| Passages / works / authors labelled | 255 / 157 / 63 | 1,137 / 672 / 246 | 7,326 / 4,475 / 1,249 |
| has_obstacle = yes | 0.698 | 0.723 | 0.722 |
| Locus among obstacles, material / social / internal (passage level) | 0.163 / 0.725 / 0.112 | 0.190 / 0.686 / 0.124 | 0.210 / 0.690 / 0.101 |
| Work-level material share | 0.168 | 0.186 | 0.211 |
| Locus = default domain mapping | 0.928 | 0.943 | 0.947 |
| Quote exact or normalised (yes rows) | 0.927 | 0.915 | 0.911 |
| Primary-set works / authors, Confirmation (metadata) | 106 / 68 | 527 / 235 | 3,399 / 1,334 |
| Date confidence high / medium / low (all works) | 0.225 / 0.438 / 0.337 | 0.376 / 0.325 / 0.299 | 0.497 / 0.248 / 0.255 |

Other figures:
- **Contrasts (author-cluster bootstrap, B = 500, naive):**
  - L − E material +4.3 pp [−2.4, +11.2];
  - L − E internal −0.7 pp [−4.4, +3.0];
  - L − M material +2.4 pp [−3.1, +7.0].
- **ICC (observed scale, ANOVA estimator), material indicator among obstacles:** author 0.096, work 0.146. For
  has_obstacle the author ICC is 0.035.
- **Gemma vs Qwen (v0.9, 600 passages):** yes 0.723 vs 0.322; κ has_obstacle 0.24; κ 4-category locus 0.25; first
  domain agreement among both-yes 0.48.
- **Quote status, all 6,290 yes rows:** normalised 77.7%, exact 13.5%, trimmed 4.6%, context 3.3%, hallucinated 0.7%.
- **Origin `unknown`:** 64–67% in every era.
- **Date heaping:** 359 works dated exactly 1900.
