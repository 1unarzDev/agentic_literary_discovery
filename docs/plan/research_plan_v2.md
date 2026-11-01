# What Stands in the Way: Research Plan (v2, 2026-10-31)

Working title: **"What Stands in the Way: Measuring How Modernity Rewrote the Obstacles of English Fiction, 1800–1925"**

## Context

The brief (`Historical_Literary_Discovery_Claude_Research_Brief.md`) proposes three angles: (A) narrative affordance shifts, (B) a historical-discovery benchmark, and (C) an evidence-falsification agent. The user asked for a **holistic analysis of historical shifts**, with limited compute focused on the most major ideas. So v2 replaces the single-domain design (communication only) with **one shared annotation pass** that measures *every kind of obstacle* in fiction at once. Three technology-hinged domains get deep dives.

**Constraints:**
- The user is a high-school researcher. Their English teacher is the second annotator, with gold labels ready about **Fri Nov 6**.
- 4–6 volunteers can run local models on Windows, macOS and Linux.
- Infrastructure: a new Cloudflare Worker with D1 and R2 (approved) for coordination, and Codex (`codex-lb`; key in `~/.config/caelestia/.env.secrets`) for grunt work.
- Deadlines:
  - **NAACL SRW mentorship: Nov 16 AoE.**
  - **AAAI-27 Eval-AI-Scientists: Nov 20 06:00 UTC (= Nov 19, 10 pm PST).** Someone can attend in person.
  - **DH2027: Nov 20 AoE.**
  - **NAACL SRW paper: Jan 11 AoE.**

The goal is a few strong, evidence-grounded findings with passages that would impress an English teacher, backed by valid statistics. It is not a dashboard of correlations.

---

## 1. Decision memo

**Central question:** *Across the nineteenth century, what kept fictional characters from what they wanted, and how did that change as the world modernized?*

For a novel to have a plot, something has to stand in the way. In 1810 the obstacles might be distance, darkness, slow news, fever and an entail. By 1910 the railway, the telegraph, gaslight and better medicine had removed many of them. Did novelists replace them with **social, institutional, and inward (psychological) obstacles**? This puts a famous critical thesis to a corpus-scale test: Erich Kahler's *The Inward Turn of Narrative* (1970, English translation 1973), and the broader "interiority" narrative of the modern novel (Woolf, "Modern Fiction", 1919). Ordinary readers already sense the thesis ("cell phones killed the plot"), and an English teacher would recognize it immediately.

**Recommended contribution, in three layers that share one compute pass:**
1. **Holistic finding (A, broad):** the changing *ecology of obstacles*. We measure the share of plot obstacles by **domain** and by **locus** (material/external → social/institutional → internal/psychological), decade by decade, within genre.
2. **Three hinged deep dives (A, sharp).** Each domain has a dated technology hinge and a named critical literature:
   - **Communication.** Penny Post 1840, telegraph, sixpenny telegram 1885, telephone 1876+. Critics: Menke 2008, Golden 2009, Thomas 2012, Koehler 2016.
   - **Mobility.** Railway 1830s–50s. Critics on railway fiction to be verified by the literature agent, e.g., Schivelbusch, *The Railway Journey*, 1977/1986, and the work on the Victorian railway novel.
   - **Darkness and light.** Gas 1810s–40s, electric 1880s+. Kim, Pethe & Skiena (EMNLP 2020) serves as a known-positive replication and a contrast between night's *role* and clock time.
3. **Built-in validation (B-lite + C-lite):** confounded-null and injected-shift corpora, plus a deterministic falsification battery. The AAAI paper presents this as "Agents narrate noise."

**Why this beats the alternatives:**
- **Room in the field.** No computational study of plot obstacles over a historical corpus surfaced in the verified search. Communication-as-plot-device is open, and the broad obstacle question is likely open too. Novelty test N1 must confirm this, because computational narratology (e.g., Piper, So & Bamman 2021) is adjacent.
- **One pass, many results.** A single label schema serves all three layers, so breadth costs little extra.
- **The other angles are crowded.**
  - B alone overlaps DiscoveryBench, BLADE, HypoBench, D5 and LSC-Eval.
  - C alone is pre-empted by POPPER (ICML 2025).
  - Both survive only as validation layers.
- **If no trend survives:** "Corpus-scale measurement of plot obstacles, validated against human readers, finds that the 'inward turn' is *[supported/not supported]* once genre and archive composition are controlled. LLM research agents given confounded corpora narrate such turns anyway." That stands on its own.

**Scope locks:**
- English fiction 1800–1925, UK and US.
- One annotation schema.
- **At most 5 confirmatory tests:** H1, three domain hypotheses (H2a–c), and H3.
- At most 2 exploratory "surprise" findings promoted from open discovery, and only after Confirmation-half replication.
- Parking lot for anything else (e.g., money and inheritance, medicine): it is measured for free but not deep-dived before Jan 11.

---

## 2. Construct and annotation schema (one pass)

**Plot obstacle** = something in the passage that blocks, delays or endangers a character's goal *and* plausibly affects what happens next. Atmosphere or mere mention doesn't count.

The model fills these fields per passage (multi-obstacle allowed, at most 2):
- `has_obstacle`: yes / no / insufficient_context
- `domain`:
  - DISTANCE_TRAVEL
  - COMMUNICATION_INFORMATION (incl. secrets, identity)
  - DARKNESS_VISIBILITY
  - ILLNESS_BODY_DEATH
  - MONEY_PROPERTY_LAW
  - SOCIAL_RANK_CONVENTION (incl. marriage and gender norms)
  - INTERPERSONAL_CONFLICT
  - INNER_STATE (doubt, fear, desire, conscience)
  - NATURE_WEATHER
  - OTHER
- `locus`, derived from domain plus a mechanism check, so the taxonomy is principled rather than AI-invented: material/external | social/institutional | internal/psychological
- **Domain sub-fields**, filled only when the domain fires:
  - communication `failure_cause`: infrastructure | accidental loss | intentional withholding | misinterpretation | success-as-resolution
  - `technology_named`: letter | telegram | telephone | railway | coach | steamship | gas | electric | candle | none
  - `message_valence`: catastrophic | practical | romantic | financial
  - darkness `night_function`: danger | concealment | intimacy | labor | leisure | none
- `resolution_hint`: overcome-by-technology | by-person | by-chance | unresolved
- `obstacle_summary` (≤15 words, free text, used for open discovery)
- `evidence_quote` (exact substring) and `confidence`

The free-text `obstacle_summary` drives **open discovery** (§4.6) without extra inference.

---

## 3. Confirmatory hypotheses (pre-registered on OSF before the Confirmation split is unsealed)

| ID | Hypothesis (direction pre-declared) | Readout | Why a reader cares |
|---|---|---|---|
| **H1 Inward turn of obstacles** | Among plot obstacles, the material/external share falls and the internal/psychological share rises from 1800–1839 to 1885–1925, within genre | Multinomial share change with CI; locus streamgraph | Tests Kahler's thesis at scale: "Modern novels moved the enemy inside the hero." |
| **H2a Communication** | Communication failures shift from accident or infrastructure toward intentional withholding | Conditional share | "Once the mail worked, people became the obstacle." |
| **H2b Mobility** | DISTANCE_TRAVEL obstacles fall after railway diffusion (1840s–60s), and travel shifts in function from *barrier* to *setting of encounter or danger* (the railway carriage scene) | Prevalence + function share | The journey stops being the problem and becomes the stage. |
| **H2c Darkness** | DARKNESS_VISIBILITY obstacles decline, while night's function shifts from danger and concealment toward leisure and intimacy, earlier in urban settings | Function shares; contrast with Kim et al.'s clock-time trend | Kim et al. found *more* night. Is night still *dangerous*? |
| **H3 Mention ≠ function** | Keyword rates for technology terms (HTRC EF 2.0 + our corpus) do not track the obstacle-function rates in H2a–c | Divergence statistic | Shows why reading for function, as an English teacher does, beats counting words. |

**Multiplicity:** Holm across the 5 tests. Effect sizes with 95% CIs are the headline numbers.

**Impossibility checks** (they verify the pipeline, not the hypotheses): telephone or electric light as a plot device before about 1876 or 1879, and railway before 1825, should be about 0. Any hits are hand-inspected: date error, false positive, or genuine futurism.

---

## 4. Methodology

### 4.1 Corpus
Population: "English-language fiction 1800–1925 preserved in Project Gutenberg."
- **Texts.** Official PG rsync (text files only) plus the RDF catalog. Keep English items with LCSH "Fiction" or LoCC PR/PS/PZ. No crawling of the human-facing pages.
- **Dates.** Use pg-dates (Momen et al., Findings ACL 2025; HF `Texttechnologylab/project-gutenberg-temporal-corpus`, CC BY-NC, not redistributed; about 84–90% exact-year accuracy).
  - Cross-check against Wikidata P577 and the author's lifespan.
  - Hand-check 60 works across decades. If fewer than 85% fall within ±5 years, use high-confidence dates only.
- **Origin.** LoCC PR (UK) vs PS (US), plus Wikidata P27; anything left unclear is coded `unknown`.
- **Dedup and genre.**
  - MinHash plus author/title keys collapse editions into one work; translations are excluded.
  - Genre uses at most 8 classes mapped from LCSH.
  - **Genre drift is the top confound** (detective fiction is full of telegrams; gothic fiction is full of darkness), so every model is fit within genre or with genre interactions.
- **Setting.** An LLM tags `setting_period` per work, validated on 40 works. Historical novels are analyzed separately.
- **Replication frames.** The Confirmation half, ELTeC-eng (100 UK novels, 1841–1920), and the Chicago US Novel Corpus public build (about 1,245 works, 1880–1923), deduped against Discovery authors.
- **Manifest and audit.** One JSON record per work/edition (schema in brief §5) with sha256. Show works and authors per decade × origin × genre beside every trend.

### 4.2 Splits (Day 1, before any labels)
- Authors are hashed into **Discovery (50%)** and **Confirmation (50%)**, stratified by decade × origin × genre.
- Confirmation results sit in a sealed R2 prefix. `ald sync` refuses to read them until `docs/prereg.md` contains the OSF hash.

### 4.3 Sampling: domain-neutral, so the holistic shares are unbiased
- **Random backbone:** a seeded sample of **24 random ~350-word passages per work**, plus ±1 passage of context and char offsets. For about 12k works that is about 290k passages. This alone supports unbiased obstacle shares per decade.
- **Domain enrichment:** lexicon and embedding hits for the three deep-dive domains (historian-curated period terms: post, penny post, wire, despatch, coach, diligence, railway, carriage, lamp, gas, candle, …). Each is capped at 8 per work, and its inclusion probability is recorded so it can be reweighted. That adds about 100k passages.
- **Adaptive stopping.** A decade × stratum cell closes once its CI half-width reaches about ±3–4 pp with sufficient authors. Expect about 60% of planned passages to actually be labeled.

### 4.4 Inference cascade (each stage has one pinned model, quant and prompt on every worker)
1. **Screen** (Tier-1, ~8 GB): `has_obstacle`, plus a coarse domain guess.
2. **Label** (Tier-2, ~16 GB): the full schema, run on screen positives plus a 5% sample of screen negatives to estimate recall.
3. **Deterministic gates:**
   - the quote must be an exact substring, or the label is rejected;
   - JSON schema validation;
   - impossibility flags.
4. **Adjudicate** (Tier-3 ≥24 GB, or API): human-audit items and model disagreements only.
5. **Memorization score:** a name-cloze test (Chang et al., EMNLP 2023) on a sample per work, used as a covariate and for stratified exclusion.
6. **Baselines** (budget-matched; cost per 1k passages reported):
   - keyword rules
   - TF-IDF + logistic regression
   - embeddings + logistic regression (trained on the same gold)
   - a single LLM
   - the full cascade + gates + DSL

   Each is evaluated per era (pre-1850, 1850–1884, 1885–1925).

### 4.5 Human annotation (user + teacher, ~Fri Nov 6, ~300 passages, about 4 h each)
- **Teaching set (~100).** Strong-indicator prototypes for each domain and locus, chosen where models agree with high confidence. It also includes boundary cases where the Tier-1 and Tier-2 models disagree, and a **cross-era pair for each domain** (1820s vs 1900s, same kind of obstacle). These come from Discovery authors who are then excluded from evaluation, and they tune the codebook and the few-shot block.
- **Audit set (~200).** A probability sample with known weights, stratified by era × predicted domain × origin, from both halves. It feeds **DSL** (Egami et al., NeurIPS 2023) and **PPI** (Angelopoulos et al., *Science* 2023) to produce valid CIs from model labels. Citations are to be verified.
- **Blind protocol:**
  - annotators see only the passage and its context;
  - 40 items are double-coded for κ;
  - the teacher adjudicates.
- **To keep the job feasible for humans:** annotators label `has_obstacle`, `domain`, `locus` and the communication cause only. The other sub-fields are validated on a 60-item Tier-3 / user check.
- **Codebook:** v0.9 (from Discovery pilot reading) is written before Nov 6. v1.0 is frozen Nov 8, followed by a relabel of the label stage only (cache-keyed; about 1 day).

### 4.6 Open discovery (the holistic net, with guardrails)
1. On the Discovery half only: embed the `obstacle_summary` strings, cluster them (HDBSCAN), and fit decade trends per cluster.
2. An LLM proposes natural-language descriptions of rising and falling clusters (D5/HypotheSAEs-style; cited).
3. The **ideator ↔ critic** agents rank the candidates for meaningfulness, novelty against the critical literature, and confound risk.
4. **At most 2 candidates** are written into the pre-registration as exploratory-confirmatory tests on the Confirmation half (BH-corrected). Every candidate that was tried is logged.
5. A candidate counts as "discovered" only if it replicates. This is where surprises come from (e.g., a rise of *nerves* or *the doctor's verdict* as an obstacle), and it costs no new inference.

### 4.7 Statistics (pre-registered)
- **Unit and model:**
  - The unit is the work, with an author random effect; passages are never treated as independent units.
  - H1 / H2 use a multinomial or logistic mixed model with:
    - a natural spline of year (df = 4);
    - genre and origin fixed effects;
    - setting, log length and memorization covariates;
    - DSL-corrected labels.
  - The primary contrasts are eras 1800–39 vs 1885–1925. H2b/H2c also get pre-declared hinge windows.
- **H3:** z-scored lexical and functional decade series, compared with a block-bootstrap divergence CI.
- **Power:** simulated from Discovery prevalence and ICC on Nov 7. If the minimum detectable effect exceeds 8 pp, collapse eras or domains before freezing.
- **C-lite battery**, all deterministic and all reported:
  1. leave-one-author-out
  2. leave-one-decade-out
  3. drop genre X for each major genre
  4. high-confidence dates only
  5. drop the top-decile memorized works
  6. alternate model family on a 10% subsample
  7. 250/500-word segmentation
  8. date permutation within author × genre blocks
  9. ELTeC/Chicago replication
- **"Supported" requires** Holm significance, ≥ 7 of 9 battery checks passed, and the same sign in replication. Otherwise the claim is "unstable" or "null" and reported as such.

### 4.8 Built-in benchmark: "Plausible Stories from Null Corpora" (the AAAI paper)
We build 30 corpora by **resampling** already-labeled works, which needs no new inference and no synthetic text:
- **10 known-positive.** Telephone mentions after 1876; Kim et al.'s rise in night scenes; the decline of epistolary form.
- **10 injected-shift.** Labeled works are reassigned across dates to create a shift of known size.
- **10 confounded-null.** No real within-genre shift, but a planted artifact: genre-mix drift (gothic → detective), reprint-date contamination, duplicate-edition amplification, memorized-canon oversampling, or a decade with poor coverage.

**Evaluation:**
- Claude and Codex research agents, and our pipeline, analyze each corpus under a fixed token budget.
- Gold labels come from the generating process.
- Metrics:
  - detection accuracy;
  - **false-claim rate on confounded nulls**;
  - whether the named confounder was identified;
  - abstention and calibration;
  - verified evidence rate.
- **Gate:** the pipeline must recover ≥ 8 of 10 injected shifts and claim ≤ 1 of 10 nulls before H1–H3 results are trusted.

---

## 5. Novelty matrix (verified 2026-10-31; full version goes in `docs/novelty_matrix.md`)

| Prior work | What it does | Threat to us | Our distinction |
|---|---|---|---|
| Kahler 1973; Woolf 1919; interiority scholarship | Qualitative "inward turn" thesis | H1: med (source of the hypothesis) | First corpus-scale test via plot obstacles, with controls |
| Menke 2008; Golden 2009; Thomas 2012; Koehler 2016 | Postal and telegraphic plots, close reading | H2a: med | Tested at scale with counterexamples |
| Schivelbusch; railway-fiction critics (**to verify**) | Railway and perception | H2b: med | Obstacle function rather than representation |
| Kim, Pethe & Skiena 2020 | Time-of-day trends | H2c: med | Night's *function*; replicates their trend as a known positive |
| NLP4DH 2025, LLM topic labels | Pre/post-1850 topics | med-low | Mechanism, not topic; human-validated and inference-corrected |
| Piper, So & Bamman 2021; Sims et al. 2019; BookNLP | Narrative theory and events in NLP | med (must check for obstacle/conflict work) | Historical-trend application of a conflict construct |
| Stuhler 2024; Underwood et al. 2018; Dubourg et al. 2025 | Large-scale LLM/NLP cultural measurement | low | Passage-grounded, verified quotes |
| Bamman, Underwood et al. CHR 2024; Chang et al. 2023 | LLM validity; memorization | required controls | Adopted |
| DiscoveryBench, BLADE, HypoBench, D5, HypotheSAEs, LSC-Eval | Synthetic ground truth for discovery | B: high | Confounded nulls built from real literary-history artifacts; evaluates overclaiming |
| POPPER 2025 | Agentic falsification | C: high | Not claimed; deterministic battery |

**Novelty tests (each must pass before a claim enters a paper):**
- **N1.** Codex sweep (ACL Anthology, JCA, CHR, DH abstracts, Scholar) for "plot obstacle/conflict trend corpus," "inward turn computational," "railway novel computational," and "night function fiction." Queries and hits are logged.
- **N2.** The claim is phrased as a test of a named thesis.
- **N3.** The historian confirms each hinge date from 2 sources.
- **N4.** The critic searches the named critic's work for the same claim; if found, the claim is reframed as a confirmation or refutation.

---

## 6. Figures (one visual language: paper, ink and postal red; built with the `dataviz` skill)
1. **"What stands in the way."** Hero figure: a streamgraph of obstacle **locus** shares by decade, with material in sepia, social in slate and inward in deep red. Thin rules mark the hinges (railway, Penny Post, gas, telegraph, telephone, electric light). Ribbons below show works and authors per decade, and CIs sit on the share boundaries.
2. **Domain small multiples** (communication, mobility, darkness). Each has its own sub-function stream and hinge, all on the same axes.
3. **"Night changes its job."** Kim et al.'s clock-time rise overlaid on night's function shares (danger → leisure/intimacy).
4. **"Counting words vs reading plots"** (H3).
5. **Passage cards:** 1820s vs 1900s quotations of the same obstacle type, with the exact span highlighted and the offset printed. These are the "wow" examples, mined by the exemplar agent from verified outputs only.
6. **"Agents narrate noise."** False-claim rates on confounded nulls.
7. **Appendix:** the corpus audit.

---

## 7. Team and orchestration (Claude orchestrates specialist subagents; Codex does grunt work)

| Role | Runner | Deliverable |
|---|---|---|
| Literature | Codex in `research/lit/` + Claude verification | Novelty matrix, verified `refs.bib` (DOIs resolved), and each critic's thesis with page references |
| Historian | Claude subagent + Codex fact-check | `history/timeline.csv` (UK/US hinges for post, telegraph, telephone, railway, gas, electric; 2 sources each) and the period lexicon |
| Venue analyst | Codex | `venues/fit_report.md`: CFP clauses, prior accepted papers, format checklists for AAAI-eval, DH2027 and NAACL SRW |
| Corpus engineer | Claude | Ingest, manifest, splits, audit |
| Exemplar miner | Claude subagent over pipeline outputs only, never model memory | Ranked cross-era passage pairs with verified offsets |
| Statistician | Claude subagent | Pre-registration, power simulation, DSL/PPI, battery |
| Benchmark builder | Codex + Claude review | 30 resampled corpora + scoring harness |
| Ideator ↔ Critic | 2 adversarial Claude subagents per gate | At most 2 open-discovery promotions; kill log |
| Efficiency monitor | Claude subagent on `/loop` polling `/status` | Throughput/ETA reports and speedups: prompt trimming, KV-cache hit rate, screen pass rate, idle workers, cell closing |
| Viz + Writer | Claude (`dataviz`) | Figures; prose for literary readers, reviewed by the teacher |

**Codex invocation:** `set -a; . ~/.config/caelestia/.env.secrets; set +a; codex exec -C <scoped dir> "<task>"`.
- The key is never echoed.
- Codex runs with `danger-full-access`, so each task gets its own working directory and its output is reviewed before merging.

---

## 8. Distributed compute: the `ald` CLI and Cloudflare coordinator

**Layout:**
- `ald/` is a Python wheel built with typer, httpx, psutil and platformdirs. Install with `uv tool install --python 3.12 <wheel-url>`.
- `coordinator/` is a TypeScript Worker with:
  - **D1** tables: workers, jobs, leases, a per-shard result index, cells, annotation tables;
  - **R2** storage: shards of about 500 passages, and JSONL.gz results;
  - a **Cron** trigger that reclaims expired leases.

**Commands:**
- **`ald doctor`**
  - Detects OS, CPU, RAM, GPU (nvidia-smi; about 65% of Apple unified memory counts as usable), disk, and bandwidth via a 10 MB R2 object.
  - Picks a tier from `registry/models.v1.json`: CPU = retrieval/embedding/name-cloze prep, ~8 GB = screen, ~16 GB = label, ≥24 GB = adjudicate.
  - Runs a 60 s benchmark of the real prompt at concurrency 1/4/8, then reports passages/hour, how many shards fit on disk, and the ETA for this worker's share.
- **`ald setup`**
  - Checks the Ollama version range. If Ollama is missing, prints the OS install command and asks before running it.
  - Pulls the pinned model and verifies its digest.
  - Uses Ollama only: vLLM's different kernels would be a confound.
- **`ald join <url> <invite>`** trades the invite for a worker token. Only its sha256 is stored.
- **`ald work`**
  - Leases jobs atomically (`UPDATE … RETURNING`), filtered by tier: 60 s heartbeat, 10 min TTL, dead-letter after 3 attempts.
  - Downloads only the leased shards.
  - Runs at temperature 0, seed 0, `keep_alive=-1`, with the static codebook prefix first (KV-cache reuse) and Ollama `format` JSON schema.
  - Verifies quotes in `evidence.py`:
    - NFKC, quote and whitespace normalization, de-hyphenation;
    - exact substring with offsets;
    - fuzzy matches flagged, never counted as verified.
  - Uploads idempotently by content sha256.
- **`ald sync`** (this machine)
  - Writes Parquet + `ald.duckdb` and re-verifies quotes.
  - Never mixes pins in one view.
  - Enforces the Confirmation seal.

**Pins:** `pin_hash` = sha256(template + codebook version + schema + options + model digest). Workers refuse mismatched jobs and the coordinator rejects mismatched uploads. **One model per stage across all workers**: the tier decides only which stages a worker may run.

**Waves:**
- Each cell gets a seeded permutation.
- Each wave takes the next block from every open cell, shuffled across decades, so no worker or OS is tied to an era.
- 5% of jobs are duplicated onto a different worker or OS, with κ reported by OS and backend.
- Results are cached by (passage_id, pin_hash), so a codebook revision re-runs only the label stage.

**Status and annotation endpoints:**
- **`/status`** (admin) reports per-worker throughput, queue depth, open cells and ETA, for the efficiency monitor.
- **`/annotate/<token>`** is the blind UI:
  - It never returns model labels, other annotators' labels, or title/author/date.
  - Annotators see items in different random orders, and 40 items are double-coded.
  - Keys: `1–9`, `0`, `e` = evidence, Enter, `u`.

**Model registry:** no models are named until Day 1. Codex and Claude verify the current open-weight options that fit 8 GB and 16 GB (license, JSON reliability), benchmark 2 per tier on 200 Discovery passages, then freeze.

**Compute budget:**
- About 390k sampled passages (60% after adaptive stopping, so about 235k).
- Screen: 8B Q4 at about 400 tok/s on the 4070 Ti Super takes about 0.2 s per passage, roughly 13 GPU-hours.
- Label: about 80k positives at about 250 output tokens, roughly 15 GPU-hours.
- With 4–6 machines plus overnight runs here, that is about 1–1.5 days. Name-cloze probes run on CPU or tier-1.

**Windows and D1:**
- Windows: UTF-8 explicitly, no `:` in filenames, `os.replace` with retry, check System32 for nvidia-smi, release the lease on Ctrl-C, and a `--keep-awake` flag.
- D1: index results per shard only, to stay under the free-tier write cap; switch to the $5 plan if needed.

**Risks and mitigations:**

| Risk | Mitigation |
|---|---|
| Temperature-0 drift across CUDA, Metal and CPU | Record the backend; check duplicate κ; restrict a stage to one platform class if needed |
| Hallucinated quotes | Gated; rate reported per decade |
| Volunteer churn | Small shards, overnight local runs, ETA alerts |
| Codebook drift | Pins |

**Compute priority before Nov 20:**
1. Discovery-half labels
2. Audit/teaching candidates (needed before Fri Nov 6)
3. Sealed Confirmation half
4. Enrichment pool for exemplars

The benchmark corpora are resampled, so they cost no inference.

---

## 9. Timeline and go/no-go gates

| Date | Work | Gate |
|---|---|---|
| **Sat Oct 31–Sun Nov 1** | Scaffold the repo; PG rsync and catalog; pg-dates join; splits; `ald` MVP and Worker deployed (the user runs `! npx wrangler login`); Codex starts the literature, venue and historian tasks; model registry benchmark | **G0:** ≥ 60 works and ≥ 30 authors per decade 1820–1920 in each half; otherwise narrow to 1830–1920 |
| **Mon Nov 2** | Volunteers onboard; segmentation and sampling; screen starts | Projected ETA for the Discovery label stage ≤ 60 h; otherwise tighten adaptive stopping |
| **Tue–Thu Nov 3–5** | Label stage (Discovery first, then sealed Confirmation); codebook v0.9; teaching and audit sets; date hand-check; memorization probes; annotation UI live | **G1:** quote verification ≥ 97%; Tier-1/Tier-2 κ ≥ 0.6 on `has_obstacle`; date check ≥ 85% |
| **Fri–Sat Nov 6–7** | Human annotation; power simulation; first open-discovery clusters | **G2:** human κ ≥ 0.6 `has_obstacle`, ≥ 0.5 domain/locus; LLM macro-F1 ≥ 0.65 overall and ≥ 0.55 in every era; otherwise merge domains and re-test |
| **Sun–Mon Nov 8–9** | Freeze codebook v1.0; relabel; ideator/critic promote at most 2 open findings; OSF pre-registration | Pre-registration hash recorded before unsealing |
| **Tue–Fri Nov 10–13** | Unseal; run H1–H3 and the promoted tests; battery; ELTeC/Chicago replication; benchmark agent runs | **G3:** if nothing survives, switch the lead to the null result + "agents narrate noise" (both outlines pre-written) |
| **Sat–Mon Nov 14–16** | Figures, passage cards; **NAACL SRW mentorship request (Nov 16)** | The teacher reads the DH draft for literary voice |
| **Tue–Thu Nov 17–19** | AAAI 2–4 pp resource paper (anonymized, AAAI kit); DH2027 short paper (1000–1250 words, open review, GenAI disclosure) | **Submit AAAI by Nov 19, 10 pm PST; DH by Nov 20 AoE** |
| Nov 20–Jan 10 | Tier-3 adjudication, more annotation, close readings, error analysis; NAACL SRW long paper (8 pp) | Decide archival vs non-archival by Dec 15 |

**Venue notes:**
- **AAAI:** non-archival, presented in person on Feb 22. Its timing overlaps SRW review (Jan 11–Mar 8), so check the SRW anonymity policy.
- **DH2027:** submit as a short paper; long papers become archival in the Anthology. Because DH review is open, cite it in the third person later.
- **Skip LaTeCH-CLfL:** its 2026 rules banned concurrent review.
- **Journal of Cultural Analytics** is the long-term journal home.

---

## 10. Repo layout (`/home/lunarz/agentic_literary_discovery`)
- `ald/` CLI
- `coordinator/` Worker
- `pipeline/` ingest, segment, sample, retrieve, gates
- `analysis/` stats, DSL, battery, open discovery, figures
- `bench/`
- `research/{lit,history,venues}/`
- `docs/` decision_memo, novelty_matrix, codebook, prereg
- `registry/models.v1.json`
- `data/`: gitignored; manifests committed

## 11. Verification
- **pytest:**
  - quote normalization on PG typography
  - pin-hash stability
  - Wilson/design-effect math
  - wave determinism
  - split seal
  - segmentation offsets (golden files)
- **Miniflare / `wrangler dev` contract tests:**
  - 50 concurrent lease races
  - expiry and reassignment
  - idempotent and conflicting PUTs
  - annotator responses contain no model fields
- **End-to-end smoke:** 20 books, two machines, `ald sync`, and identical labels on the duplicate jobs.
- **Simulation checks:**
  - 95% CI coverage of about 0.95 on data with known parameters;
  - the pipeline passes the benchmark gate (≥ 8/10 injected shifts recovered, ≤ 1/10 nulls claimed) before results are trusted.
- **Passage check:** every passage in every figure is relocated in its source file by offset + sha256.
