# Historical Literary Discovery: Research Brief and Planning Reference

**Prepared:** 2026-10-31  
**Purpose:** Source-grounded handoff for Claude to decide the final research angle, develop methodology, design a statistically defensible benchmark, plan corpus construction, and produce concrete, publishable results.  
**Status:** Research planning brief—not a completed systematic review, a frozen protocol, a validated benchmark, or evidence of new empirical findings.

> **Core mandate:** Find *interpretable, surprising, independently defensible* patterns in how narrative functions and language evolve with historical change. Build an auditable AI + deterministic-statistics pipeline that discriminates actual corpus evidence from polished but spurious historical storytelling. The result must be a substantive humanities finding **and/or** a technically meaningful, reproducible benchmark—not a dashboard of n-grams or an AI-generated list of correlations.

## 0. Constraints and desired outcomes

- Scope: **English-language literary prose over time** for the primary study, with the option to add contemporary discourse, newspapers, or non-English corpora only as distinct comparison populations. Genre and geographic scope must be explicit.
- Priority: high-quality original literary-historical argument, anchored in quotations/passages, formal operational definitions, external historical context, transparent statistical analysis, and close-reading counterexamples.
- AI should *propose taxonomies, label complex narrative mechanisms, retrieve evidence, and help hypothesize*; conventional code should perform deterministic counting, metadata validation, sampling, inference, and evaluation. AI should not make up the empirical findings.
- User has substantial ML/software/simulation research experience and has published or submitted work on fidelity/auditing, evidence-grounded explanations, and human communication. The strongest methodological continuity is **auditable transformation from literary evidence to research claims**. Do not turn this into a robotics study.
- Do **not** focus this document on a teacher or outreach pitch. Optimize for a research lead developing a serious paper/benchmark.
- Research scope is negotiable; benchmark truth, corpus licenses, and historical causal claims must be treated cautiously.

## 1. Executive recommendation

**Recommended primary study:** **Narrative Affordance Shifts under Technological Change** (working label; not an established research construct). Ask how communications, mobility, and lighting technologies alter the ways plots create *obstacles, opportunities, suspense, concealment, delay, and resolution*, **rather than only increasing the mentions of new objects**.

**Recommended technical contribution:** a **provenance-grounded historical-pattern discovery evaluation suite** that tests whether systems can (a) detect a literary feature change, (b) show primary-text evidence, (c) distinguish association from causation, (d) survive confounder and model-sensitivity tests, and (e) abstain when evidence is insufficient. A benchmark with **recovered published findings, synthetic injected shifts, and null/confounded cases** is more defensible than annotating 100 alleged new discoveries as objectively true.

**Recommended first slice:** choose *one* technological domain (communication is especially clear), *one* narrative construct (e.g., communication blockage and its role in plot conflict), *one* English fiction corpus with reliable dates, and *one* prespecified statistical model. Replicate or sanity-check Kim et al. (2020) on time-of-day as an **engineering validation**, not as the main new claim.

**Avoid premature scope:** Do not start by running 500 AI-defined themes across all of literature and seeking historical explanations post hoc. That produces large multiple-testing burden, historical confounding, and low interpretability.

## 2. Literature map: established work and remaining room

### Foundations of large-scale literary/cultural study

1. **Michel et al. (2011), _Quantitative Analysis of Culture Using Millions of Digitized Books_**: culturomics; massive historical textual frequency analysis. https://pmc.ncbi.nlm.nih.gov/articles/PMC3279742/  
   *Implication*: size and historical language trends are not novel by themselves.
2. **Moretti, _Distant Reading_ (2013)**; **Jockers, _Macroanalysis_ (2013)**; **Underwood, _Distant Horizons_ (2019)**: foundational distant reading/macroanalysis and the interpretive/statistical stakes. Find authoritative editions and read relevant chapters before claiming philosophical novelty.
3. **Pechenick, Danforth & Dodds (2015), _Characterizing the Google Books Corpus: Strong Limits to Inferences of Socio-Cultural and Linguistic Evolution_**: corpus composition and publication dynamics can create misleading historical trends; especially important to methods. https://pmc.ncbi.nlm.nih.gov/articles/PMC4596490/

### Examples of concrete literary-historical findings

4. **Kim, Pethe & Skiena (2020), _What Time Is It? Temporal Analysis of Novels_**, EMNLP: 52,183 fiction books, inferred time of day, reported increase in events after 10 pm after ~1880, coinciding with electric lighting; coincidence ≠ verified causal effect. **Directly overlaps the motivating nighttime idea.** https://aclanthology.org/2020.emnlp-main.730/
5. **Underwood, Bamman & Lee (2018), _The Transformation of Gender in English-Language Fiction_**: longitudinal character portrayals, roles, and representation, plus counterintuitive differences in authorship composition. https://www.ischool.berkeley.edu/research/publications/2018/transformation-gender-english-language-fiction
6. **Stuhler (2024), _The Gender Agency Gap in Fiction Writing (1850 to 2010)_**, PNAS: syntax-derived character interactions over 87,531 fictional works. Exemplifies translating a humanistic construct into an auditable measurement. https://pmc.ncbi.nlm.nih.gov/articles/PMC11260095/
7. **Dubourg et al. (2025), _Quantifying and Explaining the Rise of Fiction_**: >65,000 works across varied media/cultures, LLM-derived fictiveness labels. **Critical caveat:** much of its annotation is inferred from title/author/date and model background knowledge, *not necessarily from full literary passages*. A genuinely passage-grounded system could test an important alternative design. https://pmc.ncbi.nlm.nih.gov/articles/PMC12344597/

### NLP techniques and benchmark precedents

8. **Hamilton, Leskovec & Jurafsky (2016), _Diachronic Word Embeddings Reveal Statistical Laws of Semantic Change_**: foundational temporal word-meaning analysis; useful baseline, but lexical semantics != narrative function. https://aclanthology.org/P16-1141/
9. **Baes et al. (2025), _LSC-Eval: A General Framework to Evaluate Methods for Assessing Dimensions of Lexical Semantic Change Using LLM-Generated Synthetic Data_**: synthesize controlled changes to evaluate detection ability. **Major direct benchmark precedent.** https://aclanthology.org/2025.findings-acl.570/
10. **Momen, Schaaf & Mehler (2025), _Filling the Temporal Void: Recovering Missing Publication Years in the Project Gutenberg Corpus Using LLMs_**: 53,774 selected volumes, 3.8 billion tokens, 11 languages, enriched years; source metadata includes uncertainty and requires validation. https://aclanthology.org/2025.findings-acl.890/ ; data https://github.com/OmarMomen14/pg-dates
11. **SemEval-2020 Task 1, Unsupervised Lexical Semantic Change Detection**: established task-based evaluation of word-meaning shifts. https://aclanthology.org/2020.semeval-1.1/
12. **Literary evidence retrieval (2025)**: check exact paper and benchmark definitions before citing in a final submission. Starting point: https://aclanthology.org/2025.acl-short.29/

### Intellectual boundary / novelty claim discipline

**Definitely established:** massive text mining; historical frequencies; diachronic semantics; corpus-derived changes in character/social representations; LLM annotation at tens of thousands of works; controlled synthetic change benchmarks; critical study of corpus bias.

**Potentially publishable intersection, NOT yet demonstrated unique:** an evaluation of **multi-stage, passage-grounded narrative-historical hypothesis discovery** with measured evidence traceability, shift detection, confounder-resistance, contamination resistance, uncertainty calibration, and abstention; and/or a *validated new* literary-historical result on **changes in plot affordances** linked to technology adoption.

Before asserting novelty, search ACL Anthology, CHR proceedings, _Journal of Cultural Analytics_, DH proceedings, Google Scholar/Semantic Scholar for: `narrative affordance historical fiction`, `plot devices technological change corpus`, `communication delay fictional narratives computational`, `literary history event study`, `historical discovery agent benchmark`, `narrative role change point analysis`, `computational narratology technology`, `robustness historical text annotation`. Maintain a 'closest prior work' table with actual technical distinctions.

## 3. Four candidate research angles: choose based on contribution strength

### A. Narrative Affordance Shifts (preferred humanities finding)

**Question:** After adoption of a technological capability, do fictional plot constraints shift from *external physical limitations* to *deliberate social/psychological decisions*, while accounting for genre, setting, geography, publication period, and corpus drift?

**One focused domain:** communication in long-form English fiction. Annotate plot-relevant `failure_to_reach`, `delayed_reply`, `lost_message`, `intentional_nonresponse`, `identity_verification`, `long_distance_communication`, `communication_as_resolution`, `communication_as_threat`. The plot function is distinct from mention of `letter`, `telephone`, `telegram`, etc. Formulate taxonomy iteratively with humanities close reading, then freeze before the confirmatory stage.

**Researchable hypotheses (illustrative, not established facts):**
- H1: The *distribution of reasons* why characters fail to communicate changes across periods of communication technology diffusion.
- H2: Conditional on a communication obstacle occurring, *intentional avoidance/concealment* increases in share relative to infrastructure/time constraints, potentially with genre-specific exceptions.
- H3: A narrative-function classifier finds changes not captured by simple technology mentions or word embeddings.

**What would be convincing:** a robust, replicated within-genre effect with blind annotated passages, contrasts between alternative explanations, and case studies including counterexamples. Technology diffusion is a contextual candidate, not automatic proof of cause.

### B. HISTORIA-style Historical Discovery Benchmark (preferred NLP/evaluation finding)

**Question:** Can an automated system produce historically grounded *claims* rather than compelling but nonreplicable textual associations?

**Five tasks:** (1) define/retrieve a narrative construct, (2) detect temporal shift, (3) attach primary-source evidence, (4) detect/confess confounding or null results, (5) generate a scoped, calibrated interpretation. Test stagewise and end-to-end. A benchmark name is a placeholder and needs a naming/trademark check.

**Gold/validation design:**
- *Known positive*: patterns reproduced from published scholarship, requiring independent reruns and careful mapping to current corpora; historical papers are not universal ground truth.
- *Controlled synthetic*: inject a known change into genuinely held-out text passages using transparent perturbations; report realism and distribution shift, not conflate synthetic accuracy with historical truth.
- *Matched negative / confounded*: date permutations preserving author/genre blocks, falsified temporal alignments, deliberately imbalanced genre mixtures, duplicate amplification, historically implausible event match-ups; some controls should retain real trends to test sensitivity to negative-case design.
- *Exploratory, unlabelled discovery set*: humanists evaluate whether claims are meaningful and novel, but label as human-judged candidates rather than objective binary truth.

### C. Falsification Agent for Digital Humanities (high-risk method)

Given a proposed discovery, require an agent to design and execute pre-registered robustness checks, retrieve independent counterevidence, and issue a verdict (`supported association`, `unstable`, `inconclusive`, `contradicted`, `causally underidentified`). Evaluate against precomputed cases; track whether tools ran successfully. Do not let an LLM judge itself without independent instruments.

### D. Literary Function of Light and Darkness (narrow, clear replication extension)

Building from Kim et al. (2020), ask how **night** functions as suspense, danger, anonymity, work, leisure, intimacy, etc. Use early vs late lighting eras to test changes in *role* rather than clock time alone. Prior literary scholarship on light/night must be reviewed. This is a good fallback pilot but may have a more crowded novelty space.

## 4. Corpora and large historical libraries: legally reusable, technically realistic

**Key distinction:** a library may have millions of catalog entries but only metadata, n-grams, page-level bags of words, or restricted full text. Full narrative-function inference requires text order and contiguous passages; counts alone cannot recover plot relations.

| Resource | Approximate scale / era | Data mode | Suitability and practical notes |
|---|---|---|---|
| **Project Gutenberg** — https://www.gutenberg.org/ | Large English + other-language public-domain catalog; strong 19th/early-20th coverage | Full text, catalog, official mirrors | Main scalable full-text source. Use **official bulk/mirror/robot channels**, NOT crawl the human-facing pages. US public-domain status does not guarantee identical rights in every jurisdiction; record work-level terms. Robot policy: https://www.gutenberg.org/policy/robot_access.html |
| **Gutenberg publication-year enrichments** — https://github.com/OmarMomen14/pg-dates | 53,774 refined multilingual books (1600–2000 in paper) | Bibliographic enrichment | Very useful start, **not an infallible source of first-publication year**. Preserve provenance and confidence; validate a stratified sample against bibliographic records. |
| **HathiTrust Research Center extracted features 2.0** — https://htrc.atlassian.net/wiki/spaces/COM/pages/43295914 | 17.12M volumes, 6.2B pages | CC BY 4.0 extracted per-page lexical/POS counts and metadata | Excellent independent check for word/genre/date trends. **Cannot reconstruct passage order or infer nuanced scenes from page bag-of-words.** HTRC offers separate governed analysis/data access routes: https://htrc.atlassian.net/wiki/spaces/COM/pages/43293057/HTRC%20data%20access |
| **Text Creation Partnership: EEBO-TCP** — https://www.textpartnership.net/pages/faq.html | ~60k freely accessible early English works (Phase I 25k + Phase II 35k), early print to ~1700 | Bulk TEI/XML transcripts (direct official downloads) | Great pre-1700 language and prose, **not a homogeneous novel corpus**. Genre drift enormous: religious, political, scholarly, theatrical, and other texts. |
| **ECCO-TCP** — same TCP FAQ | ~3k 18th-century books | Official bulk full-text XML | Bridges an era underrepresented in Gutenberg; genre/mode must be filtered. |
| **Evans-TCP** — same TCP FAQ | ~5k early American imprints | Official bulk full-text XML | Historical American discourse control, not interchangeable with novels. |
| **ELTeC-English** — https://github.com/COST-ELTeC/ELTeC-eng | 100 deliberately selected English novels, published 1840–1920 | Full TEI XML; public-domain originals and CC BY markup | **Best calibration/annotation corpus**, smaller but curated; use as external replication of broad Gutenberg patterns, and avoid overlap leakage. |
| **Oxford Text Archive** — https://libguides.bodleian.ox.ac.uk/english-language/Corpora | Many historical corpora | Download access varies by collection | Good for early literature and comparative registers; check individual license, time coverage, genre. |
| **Corpus of Historical American English (COHA)** — https://www.english-corpora.org/coha/ | >475M words, 1820s–2010s; genre-balanced | Search access; bulk download/licensing restricted | Useful independent trend validation. **Not freely bulk-downloadable for everyone**; contact institution/license. |
| **Chronicling America / Library of Congress** — https://www.loc.gov/collections/chronicling-america/ | Large US historical newspaper archive | OCR / metadata with rights and API constraints | Historical discourse/event context, not a direct fiction outcome corpus; inspect OCR and rights. |
| **Textual Optics Lab public corpora** — https://textual-optics-lab.uchicago.edu/public | Curated early print and historical novel subsets | Public corpus builds | Useful source-index for EEBO/ECCO and a ~1,245-work US novel corpus; confirm licensing + exact build versions. |
| **HathiTrust / NovelTM** | Broad library-held novels, incl. 87,531-work corpus used in Stuhler | Often governed access/derived features | Strong precedent and external coverage for late 19th–20th century, but do not assume full texts can be copied/distributed. |
| **Internet Archive / Open Library** — https://archive.org/ and https://openlibrary.org/ | Massive scans and bibliographic records | Mix of public-domain downloads, licensed/borrow-only materials | Good discovery and public-domain scans; avoid automating access to restricted borrowing material. |
| **Google Books Ngrams** | Very large n-gram series | Aggregate frequencies | Exploratory baseline only; severe composition concerns per Pechenick et al. (2015). |

**About Anna's Archive / unofficial mirrors:** Do not use circumvention of paywalls/DRM or unauthorized copies as the default corpus foundation. Even if a specific research analysis might be lawful in a particular jurisdiction, that does not establish distribution rights or reproducible sharing rights. A peer-reviewed artifact benefits from lawful acquisition, traceable provenance, public identifiers, and redistributable benchmark examples. If rights-restricted works are studied, use authorized institutional channels, HTRC non-consumptive methods, or permitted derived features; do not distribute copyrighted full-text passages beyond authorized quotations.

**Core copyright/scale tradeoff:**
1. 1800–1920 English fiction: good chance of full-text, reproducible pilot from PG + ELTeC.
2. 1475–1800 printed English: abundant EEBO/ECCO-TCP, but not directly comparable to later fiction without rigorous genre definitions.
3. 1920–present: much harder to assemble genuinely shareable full-text fiction; use approved restricted access or metadata/derived-feature comparisons, with this limitation explicit.

## 5. Corpus construction protocol (must be documented before inference)

Create a machine-readable record per **work** and **edition/transcription** (separate IDs):

```json
{
  "work_id": "opaque_stable_id",
  "edition_id": "source_specific_id",
  "title": "...", "author_ids": ["..."],
  "first_publication_year": 1872,
  "first_pub_year_source": "catalog_link",
  "first_pub_year_confidence": "high|medium|low",
  "edition_year": 1891,
  "narrative_setting_period": "unknown|range",
  "language": "en", "original_language": "en|unknown",
  "translated": false,
  "genre_primary": "novel|short_story|...",
  "genre_secondary": [], "geographic_context": "...|unknown",
  "source_archive": "gutenberg", "source_url": "https://...",
  "license_rights": "public_domain_us|cc_by|restricted|unknown",
  "full_text_available_and_permitted": true,
  "text_sha256": "...", "normalized_sha256": "...",
  "ocr_quality_metric": null, "text_words": 0,
  "selection_rule_version": "cohort_v1",
  "provenance_notes": "..."
}
```

**Required pipeline**: official metadata ingest → author normalization/alias handling → work/edition deduplication → format parsing/boilerplate stripping → language verification → dates and edition validation → fiction/genre triage → OCR-quality checks → passage segmentation → source offsets & checksums → frozen cohort manifests.

**No-leakage rule:** split by *author and work*, not randomly by nearby passages; multiple editions and translations of one work must share a split group. For temporal confirmation, also hold out publication decades or source archives where possible, but understand that chronological distribution shift changes the evaluation target.

**Corpus distribution audit:** decade × geography × author gender (only when responsibly sourced) × genre × author productivity × language provenance × text length × edition/archival source. Plot **counts of unique works and unique authors per decade** alongside every trend; weighting choice must be justified. Document the corpus as the literature **available to your archive**, not all published/read literature.

## 6. Narrative construct taxonomy (proposed, to be defined with close reading)

Primary construct: **plot-relevant communication obstacle**. A passage qualifies only if a difficulty in obtaining, transmitting, trusting, withholding, or responding to a message plausibly influences a character's decisions or story progression. Mere mention of a letter or telephone is not sufficient.

Labels (multi-label):
- `TECH_INFRASTRUCTURE_LIMIT`: normal slowness, availability, physical distance, postal/line failure
- `ACCIDENTAL_LOSS_MISROUTING`: missed/misplaced/lost/undelivered communication
- `INTENTIONAL_WITHHOLDING`: refusal, deception, secrecy, nonresponse
- `MISINTERPRETATION`: ambiguous message, incorrect inference, misleading identity
- `SUCCESSFUL_LONG_DISTANCE_CONTACT`: technological success as plot resolution
- `COMMUNICATION_AS_THREAT`: pursuit, surveillance, coercion, intrusion
- `NOT_PLOT_RELEVANT`, `UNCERTAIN`, `INSUFFICIENT_CONTEXT`

Also annotate mechanism (`explicit technology`, `implied only`, `unknown`), speaker vs narrator, passage span, historical-setting indicator, an 1–2-sentence evidence rationale *quoting the exact source span* (only rights-permitted extracts), and confidence.

Use pilot close reading to revise construct definitions; freeze codebook and stratify validation across centuries. **Historical semantic drift** and metaphor/irony can break modern models; collect human annotations per period rather than assuming labels transfer. A model may infer stereotyped facts from the book title; passage-only and title-masked experiments help assess this.

## 7. Model and tool architecture

```
licensed corpus + dated source metadata
    -> deterministic ingest / QC / dedup / passage indexing
    -> candidate retrieval (lexical seeds + embeddings + balanced random negatives)
    -> human-labeled development set / inter-rater reliability
    -> annotation models (prompted LLM, small classifier, rule baseline)
    -> passage-level evidence objects with exact source offsets
    -> work-level counts / rates and calibrated error adjustments
    -> confirmatory temporal modeling and change-point tests
    -> independent event timelines and alternative explanations
    -> replication, null checks, sensitivity and adverse evidence
    -> machine-readable claim package + interpretation + close reading
```

**Recommended baselines:**
1. Keyword/regex and historically expanded dictionaries.
2. Bag-of-words / TF-IDF / simple topic-time baseline (non-generative).
3. Embedding retrieval + lightweight supervised classifier.
4. Direct passage-level LLM annotation with exact quoted evidence.
5. Proposed hybrid retrieval → model annotation → human audit → statistical testing.
6. Optional adversarial/falsification stage: attempt to refute every proposed discovery.

Use budget-matched comparisons where claiming computational advantages; report per-1,000-passage dollars/tokens/latency/quality and tested model versions. Distinguish **annotation accuracy** from **scientific-discovery validity**.

## 8. Statistical analysis plan: must precede the headline discovery

### Units and estimands

- Passage or scene is the *labeling unit*; **work** is the default *primary statistical unit*; author is a clustering/hierarchical unit. Do not treat millions of correlated sentences from the same 50 books as millions of independent studies.
- For work `i`, let `Y_i` be the count of verified plot-obstacle scenes and `N_i` be the number of eligible scenes. Estimate a feature rate per scene, or per 10,000 words if scene detection cannot be validated. Define this before fitting.
- Preferred estimand: **within-genre temporal difference in prevalence or composition of plot-obstacle mechanisms**, on a defined corpus population. A technology's causal effect is *not* the default estimand.
- If comparing percentages across subtypes, use a multinomial or compositional approach, or clearly separate incidence from conditional share.

### Main model

For event counts, a negative-binomial mixed model with exposure offset may be defensible:

\[
Y_i \sim \mathrm{NegBin}(\mu_i,\theta),\quad
\log \mu_i = \log N_i + f(t_i) + \beta^\top X_i + u_{a(i)}.
\]

`f(t_i)` = preregistered spline of publication year or declared era contrasts. `X_i` = genre, location/region, text length/archival source where appropriate and observable; `u_{a(i)}` = author random effect (or cluster-robust alternative). If `Y_i/N_i` is naturally binomial and overdispersed, use beta-binomial or logistic mixed models; compare diagnostics and fit.

**Do not assert** that a historical invention at year *T* has a sharp causal intervention effect: adoption was geographically heterogeneous and gradual, setting differs from date of publication, and social/industrial changes co-occurred. Historical dates should be verified and treated as domain-specific adoption curves when data permit.

### Robustness, significance and multiplicity

- Predeclare hypotheses, outcomes, exclusions, primary model and a small set of comparisons.
- Exploratory screening: correct false discovery rates (BH) or use hierarchical testing; preserve the universe of attempted hypotheses and rejected candidates.
- Confidence intervals, meaningful effect sizes and plots with denominators; avoid `p<0.05` as the principal finding.
- Sample-splitting at author/work level: discovery vs holdout confirmation; validate a second source collection if possible.
- Sensitivity checks: leave-one-author-out, leave-one-decade-out, different source archives, genre strata, balanced decade samples, unknown-date exclusions, alternate passage segmentation, classifier misclassification corrections.
- Permutation tests: **permute dates within appropriate genre/source strata or author blocks** to preserve the right null dependencies; simple global shuffling may be invalid.
- Annotation uncertainty: propagate empirically estimated precision/recall or run bootstrap/simulation under a misclassification model. Uncertain predictions are not all true labels.
- Study *negative findings* and conditions where models fail across centuries.
- When human reading contradicts the quantitative measure, report the contradiction rather than conceal it.

### Power / sample-size logic

Do not pick an arbitrary `n=5,000` as proof of adequate power. First estimate event prevalence and author/genre clustering from a pilot, then simulate minimum detectable effects at the **work/author** level. Model the number of distinct authors and works/decade, annotation budget, minority-era data scarcity, and dependence across passages. Predefine a stop/go threshold for the full study based on feasible annotation quality and coverage.

## 9. Ground truth / benchmark construction design

**Benchmark layers (machine-readable):**

**Layer 1: Metadata integrity.** Given source records, detect date/edition/genre mismatches, duplicate works, unavailable rights, translation mismatch; verify with known-correct records and deliberately corrupted metadata. Evaluate precision, recall, abstention/calibration.

**Layer 2: Passage-level literary inference.** Given literal text + minimal necessary context, label narrative mechanisms and cite spans. Gold consists of multiple trained human annotators, disagreements adjudicated/reported. Evaluate macro-F1, per-era sensitivity, retrieval precision@k, evidence-span IoU, abstention calibration.

**Layer 3: Change detection.** Given fixed verified feature counts and dates, identify true injected historical change, null, or sample-composition confound. Gold from simulations and well-defined transformations. Evaluate detection error, false positive under null, change-point confidence/coverage and ranking; optimize *empirically controlled* synthetic shifts, not artificial sentence style.

**Layer 4: Historical hypothesis audit.** Given proposed claim, statistical outputs, source passages, and candidate event timelines, classify claim scope and supported/unsupported inferences. Use expert ratings and agreement, not a single LLM-generated 'truth'. Evaluate whether causal overclaim was caught and whether caveats were specific and supported.

**Layer 5 (optional): End-to-end open discovery.** Ask systems to generate `claim + primary evidence + reproducible code/test + competing hypotheses + limitation` subject to a fixed compute budget. Humans rate significance, insight, credibility; **do not claim an exhaustive ground truth** for unknown discoveries.

Minimum benchmark composition could begin as **30 well-documented positive cases, 30 null/confounded cases, 30 synthetic cases**, with a small manual pilot first. These are *engineering targets only*, subject to feasible expert validation. Split development/test by phenomenon family and underlying corpus; ensure all controls do not share prompt templates and stereotyped cues.

**Evidence-object format (example):**
```json
{
 "claim_id":"discovery_0001",
 "claim_text":"...", "claim_scope":"English-language fiction in sampled corpus",
 "construct_id":"COMMUNICATION_DELAY",
 "period_comparison":{"early":[1840,1870],"late":[1890,1920]},
 "estimated_effect":null,"confidence_interval":null,
 "model_spec_hash":"...","dataset_manifest_hash":"...",
 "evidence":[{"work_id":"...","edition_id":"...","span_start":0,"span_end":0,"quote_or_secure_pointer":"...","rights_status":"..."}],
 "independent_history_sources":[{"url":"...","supports":"context only"}],
 "alternatives":["genre drift", "archive selection"],
 "robustness_results":[],
 "status":"exploratory|replicated|inconclusive|contradicted",
 "reasoning_limitations":"..."
}
```

## 10. Concrete, defensible paper outputs

Avoid writing a final paper dominated by model architecture and generic claims. Target:

1. **Corpus release manifest** (work identifiers, rights, metadata provenance, processing scripts, date uncertainty; not unauthorized text dumps).
2. **Public codebook + annotated gold sample** containing adjudicated literary constructs and evidence spans where sharing is permitted.
3. **Baseline comparison** with error analysis and per-century/per-genre breakdowns; show why simple keywords fail on narrative function.
4. **Historical result package:** 1–3 well-supported, nontrivial, replicable trends with denominators, effect sizes, CIs, controlled analysis, concrete quotations, qualitative counterexamples, and historically grounded alternate explanations.
5. **Benchmark package:** positives/nulls/synthetic cases, scoring harness, contamination controls, audit trail, evaluation report, and release terms.
6. **Paper narrative:** motivated humanities question → established work → measurable construct → corpus/annotation validity → historical analysis → adversarial validation → close readings → results and limits.
7. **Honest negative findings:** maybe no robust trend remains; that can be important if it reveals widespread fragility in AI-assisted historical interpretation.

A discovery is **not publication-ready** until its primary passages can be traced; its label validity has been checked in all relevant eras; the confounding alternatives have been tested; and it replicates outside the exact exploratory sample or the nonreplication is made explicit.

## 11. Venue shortlist — verified as of 2026-10-31

**Distinguish workshop *paper* submissions from proposals to *organize* a workshop.** Verify latest per-venue CFP before submission. Times below are event-local or AoE as explicitly indicated; do not silently convert.

| Venue | Deadline / status | Fit and deliverable | Attendance/publication notes | Official URL |
|---|---|---|---|---|
| **NAACL 2027 Student Research Workshop** | **Mentorship request Nov 16, 2026**; paper **Jan 11, 2027**, both AoE | **Top priority for early-stage research**: validated pilot, resource, methods, short 4-page or long 8-page paper; explicitly welcomes **high-school researchers** and work in progress | San Francisco June 1–5, 2027; archival and nonarchival tracks; first-author proof of enrollment | https://naacl27-srw.github.io/ |
| **DH2027 / ADHO Digital Humanities** | **Nov 20, 2026 AoE**; official call open | Best *digital humanities* audience; short paper/poster on corpus/annotation design and pilot or compelling historical finding | Galway, Ireland June 28–July 3, 2027; formats also include long paper and preconference workshops. Verify presentation policy and format. | https://dh2027.adho.org/call-for-proposals/ ; announcement https://eadh.org/news/2026/10/06/call-proposals-digital-humanities-2027-dh2027?page=1 |
| **AAAI 2027, Effective and Efficient Evaluation for AI Scientists workshop** | **Nov 20, 2026, 06:00 UTC**, **NOT AoE** | Best for **benchmark evaluation**, instrument validity, null cases; 2–4p position/resource/reproduction or 6–8p full; only submit if artifact or principled proposal is ready | Montréal Feb 22, 2027; **in-person required**, **nonarchival**; fixed submission cutoff is unusually early | https://eval-ai-scientists.github.io/aaai27/ |
| **EACL 2027 LaTeCH-CLfL** | Confirmed accepted workshop; umbrella *tentative* EACL workshop direct deadline **Dec 15, 2026**; workshop-specific CFP not yet confirmed | **Excellent topical fit**: cultural heritage, literary/linguistic computing; target corpus/annotation/benchmark work | Athens March 2027. Check actual workshop CFP and presentation policies | https://2027.eacl.org/program/workshops/ ; https://2027.eacl.org/calls/workshops/ |
| **DACH Computational Social Science 2027** | **Dec 4, 2026**, 300-word abstract | Good interdisciplinary data-corpus/historical measurement design; poster/lightning talk | Cologne Apr 22–23, 2027; exact eligibility beyond “early career” should be confirmed | https://computational-social-science.org/workshops/2027.html |
| **CAIR 2027 (Curators in the Loop)** | **Dec 11, 2026** | Adjacent fit if contribution centers on ethical archives, human-in-loop curation, provenance; **less direct** for plot-change study | Lisbon Feb 9, 2027, in-person; check format/proceedings | https://bru.iscte-iul.pt/call-for-papers-cair-2027/ |
| **Society for Textual Scholarship 2027** | **Mar 1, 2027**, 250-word abstract | Strong humanities option for archival selection, editions and textual representativeness; not an NLP workshop | Athens, Georgia, May 26–28, 2027 | https://textualsociety.org/annual-conference/2027-conference-call-for-papers/ |
| **ACL 2027 StyleMatters workshop** | **March/April 2027 (TBA)**, organizer CFP | Potential if studying diachronic literary style; weaker for technology/plot functions without explicit style model | Kyoto Aug 2027; workshop says hybrid, offers archival and nonarchival | https://stylematters.info/cfp.html |
| **ACL 2027 main conference** (stretch, **not a workshop**) | ARR **Jan 4, 2027**, AoE | Resource/benchmark with substantive NLP contribution; extremely competitive | Kyoto Aug 2027. Only submit if study ready and check double-submission rules | https://2027.aclweb.org/calls/main/ |
| **NLP4DH / CHR future cycle** | **2027 paper calls not verified for a later cycle** | Recurring strongest long-range subject-area options | **CHR2027 paper deadline passed Aug 14, 2026** even though conference Jan 2027; NLP4DH 2027 CFP not verified | https://aclanthology.org/venues/nlp4dh/ ; https://2027.computational-humanities-research.org/cfp/ |

**Eligibility warning:** EACL 2027 Student Research Workshop says research-paper first authors must be **undergraduate or graduate** students; it does **not explicitly accept high-school students**. Do not treat it as a confirmed option without organizer clarification. The EACL SRW mentorship deadline is Nov 6 but also requires a paper draft and appears mismatched to the first-author status. https://2027.eacl.org/calls/srw/

**Deadline conflicts to confirm:** official ACL 2027 pages disagree on dates of workshop days; use the chosen individual workshop's final CFP for schedule. Some EACL SRW page contains an apparent ARR commitment-date typo ('Dec 22, 2027'); do not propagate that into planning.

**Practical venue strategy:**
- **Now:** NAACL SRW mentorship request; prepare a 1–2 page concept + early annotation/risk pilot. Could submit DH2027 short/poster only if a specific technical or literary pilot exists by Nov 20.
- **Dec–Jan:** LaTeCH-CLfL if its CFP confirms; NAACL SRW substantive manuscript by Jan 11.
- **Later:** StyleMatters if shifting to diachronic style; future CHR/NLP4DH if paper matured.
- **Avoid archival double submissions:** Check policies if circulating one paper; prefer non-archival early presentation only where expressly permitted, disclose overlap, and maintain genuine differences between papers.
- **Travel:** AAAI workshop explicitly requires in-person; others require checking. Venue acceptances should not be assumed to provide travel funding.

## 12. Proposed milestones and decision gates (not organizer deadlines)

**Gate 0 — 7 days:** Narrow 3 candidate claims to 1 primary study; verify corpus/license; write 1-page humanistic construct definition; audit 15–25 papers nearest the idea. Deliverable: falsifiable preregistration draft and novelty matrix.

**Gate 1 — ~2 weeks:** Obtain a legally reusable, versioned initial corpus; 100–250 passages as pilot; two human annotators on a stratified subset; estimate label prevalence and disagreement. Deliverable: codebook v0.2, QC notebook, annotator agreement results, corpus histogram. If a category cannot be labeled reliably, revise/simplify taxonomy.

**Gate 2 — ~4 weeks:** Baselines and first validated classifier on held-out authors; historical distribution plots with correct denominators; prespecified model / sensitivity. Deliverable: negative and positive examples, quantitative table, error analysis. No publication claim without this stage.

**Gate 3 — ~6–10 weeks:** Independent corpus replication, event/context evidence, benchmark null cases, completed figures, small humanistic close reading and manuscript. For earlier submission deadlines, honestly report a pilot or methodological proposal, not a finished study that doesn't exist.

**Go/no-go thresholds to set after pilot:** minimum annotator agreement; acceptable per-era precision/recall; sufficient number of *authors* and *works* per cohort; date coverage; sensitivity to alternate codebooks; feasible compute/time.

## 13. Questions Claude must settle, not gloss over

1. What is the **one-sentence contribution** if no surprising historical trend is found? Can the benchmark or negative result stand on its own?
2. Why is each literary mechanism theoretically meaningful and distinguishable from an AI-invented taxonomy?
3. What is the inferential population (published English novels, archived copies, American library holdings, etc.)? Can we really claim to represent it?
4. How are publication date, *story setting date*, writing date, edition date, and technology-adoption date separated?
5. Is `technology -> plot mechanism` causally defensible, or should claims be purely associational? What plausible counterfactual/comparison exists?
6. How is model historical-period bias audited, especially when period-specific wording differs?
7. Are splits by author/work/decade/archive robust against memorized popular novels and dataset leakage?
8. What is the genuine benefit of an LLM over regex, syntax-based features, IR, or a small supervised classifier? Show ablations.
9. How are hypotheses ranked without rewarding significance-chasing, explanatory fluency, or popularity of famous examples?
10. What can realistically be publicly released under licenses and what must remain provenance pointers or derived counts?
11. Which 1–3 figures and 2–3 actual passages would make the paper interesting **to a literary scholar**?
12. What failure modes or null results would force a change of direction, rather than being concealed?

## 14. Suggested final manuscript structure

1. Introduction: one vivid, traceable literary contrast; substantive humanistic question, not generic “AI analyzes big data”.
2. Related work: distant reading, historical narrative analysis, diachronic semantics, LLM cultural annotation, benchmark measurement validity, corpus bias.
3. Operational theory: narrative affordance / plot function—definitions and historical scope.
4. Corpus: legal source, selection, coverage, metadata uncertainties, leakage precautions.
5. Annotation and validation: codebook, sampling, agreement, period/genre error analysis.
6. Models: baselines and new component; compute-matched evaluations.
7. Historical results: plots, effect sizes, CIs, holdout findings and alternative explanations.
8. Close reading + falsification: inspect primary passages, exceptions, rival readings.
9. Generalized benchmark/resource and scoring validity if this is a core contribution.
10. Limitations: archive survivorship, rights, chronology, geography, historical causal identification, LLM training contamination.
11. Conclusion: a restrained, replicable, nontrivial claim that improves what scholars can *know*, not just what they can process.

## 15. Source-status legend and further retrieval

All specific submission dates in this brief were verified against currently available organizer/association pages on 2026-10-31, but may change. A workshop listed on an umbrella accepted-workshops page is **not proof** its own CFP deadline or publication terms are final.

The literature list above is a targeted review and should be extended through citation chaining, including recent 2026/2027 proceedings, before asserting a first-of-its-kind benchmark. The **strongest evidence** for method and chronology comes from articles and official data-provider documentation; **proposed designs** and sample sizes in this brief are hypotheses/planning targets, not findings.

**Reference search venues:** https://aclanthology.org/ , https://computational-humanities-research.org/ , https://culturalanalytics.org/ , https://adho.org/ , https://www.semanticscholar.org/ . Check exact identifiers and publication years before final citation.

---

**Bottom line:** Build an auditable, passage-grounded, statistically defensible system for explaining **how the constraints that create fictional conflict evolve over time**. If the method is genuinely generalizable and reliably rejects fake relationships, turn it into a discovery benchmark; if the new literary patterns are sufficiently strong, lead with the historical insight. Do not sacrifice the quality of one clear scholarly claim to achieve the appearance of analyzing all of human literature.
