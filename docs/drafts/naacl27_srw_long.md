# What Stands in the Way: Validating LLM-Based Measurement of Plot Obstacles in English Fiction, 1800–1929

*NAACL 2027 Student Research Workshop, long paper (8 content pages + references). DRAFT v0.1, 2026-11-04.*
*Anonymous submission. All self-references are in the third person ("Anonymous, 2026").*

> **Drafting notes (delete before submission).**
> - **Sources for every number** are in the repo docs named in `[src: …]` tags. Strip the tags at typesetting.
> - `TODO(unseal)` = filled from the registered output after the Nov 9–11 unseal (see `naacl27_srw_unseal_checklist.md`).
>   `TODO(audit)` = filled once the human/expert labels arrive (Nov 6–8). `TODO(claude-ref)` = filled from
>   `docs/claude_reference_analysis.md` (another agent is computing it). `TODO(verify)` = a fact still to check.
> - **Discovery numbers are raw model labels with no human correction.** They are labeled *exploratory* everywhere. Do
>   not quote them as effect sizes.
> - **Claim discipline (`docs/novelty_matrix.md`).** Never write "first computational history of conflict", "first test of
>   the inward turn" or "first measurement of lighting-era change". Kahler's thesis ends ~1800, so we are *motivated by*
>   it and do not test it.
> - **Length.** At ~6,800 words of body text this runs about 1 page over in two-column ACL format with 3 figures and 3
>   tables. Cut candidates are marked `[CUT?]`.
> - Figures: `naacl27_srw_figure_plan.md`.

---

## Abstract

Every English student learns that stories run on conflict: a person against nature, against society, against
themselves. We turn that classroom triad into a measurement. From 15,511 English-language works of fiction in
Project Gutenberg (1800–1929, about 1.1 billion words), we sample 350-word passages. A local open-weight LLM decides
whether something blocks a character's goal, says whether the resistance comes from the material world, from other
people and rules, or from the character's own mind, and must quote a verbatim sentence as evidence, which we check
against the text. We treat the model as a noisy instrument rather than an oracle. A pre-registered, sealed
confirmation half; an audit sample drawn on metadata alone; and design-based supervised learning (DSL) anchored on a
blind expert's labels turn imperfect LLM labels into estimates with valid confidence intervals. We report three
lessons from building it. (1) The archive is part of the object: Project Gutenberg keeps the canon of the 1820s and
the mass market of the 1900s, so an apparent "outward turn" is partly a change in *which books* survive. That led us
to register a "two fictions" hypothesis: canonical and popular fiction differ in where their obstacles come from. (2)
The instrument is unstable: two open models applying the same codebook disagree sharply (κ = 0.24), so we report a
multiverse over models instead of a single trend. (3) In exploratory labels from 15,583 passages, technology is the
obstacle in only 2% of cases, and inner obstacles stay near one in ten with no sign of an inward turn.
**TODO(unseal):** one sentence with the registered TF verdict and estimate.

---

## 1 Introduction

Every plot needs something standing between a character and what they want. Ask an English class what that
something is, and they will give you a triad: *person versus nature, person versus society, person versus self*.
Teachers use it because it works. It is also, in all but name, a hypothesis about literary history. Critics have long
told a story in which the novel moves from the second and first kinds of trouble toward the third: storms and
highwaymen give way to doubts and fears (Kahler, 1973). When Virginia Woolf wanted to say what was wrong with the most
successful novelists of her day, she reached for the same distinction. "If we tried to formulate our meaning in one
word," she wrote of Wells, Bennett and Galsworthy, "we should say that these three writers are materialists"; they
"write of unimportant things" (Woolf, 1925).

Woolf's charge is, oddly, a testable claim about the fiction most people read. Here are two sentences that a model
flagged, with verified quotes, from our corpus:

> "she had been under a wild illusion in expecting a response to her feeling from Mr. Casaubon"
> (George Eliot, *Middlemarch*, 1871)

> "I'm caught in the coils! Quick--quick if you would save me!"
> (Victor Appleton, *Tom Swift in the Land of Wonders*, 1910; the coils belong to a giant iguana)

In *Middlemarch* a husband stands in the way. In *Tom Swift*, a lizard does. One reading of the "inward turn" is that
the novel changed over time. Another is that there were always **two fictions**: a canon that locates resistance in
people and minds, and a mass market that keeps the physical world as the antagonist. On this second reading, what
changes over the century is mostly the mix of books that survive in our archives (Moretti, 2000; Bode, 2018). The two
readings make different predictions, and with enough passages read for *function* rather than for keywords we can
tell them apart.

This paper describes an instrument for doing that, and the validation that a measurement like this needs before
anyone should believe a trend drawn from it. We make four contributions:

1. **A task and codebook** for scene-level plot obstacles (has_obstacle, ten domains, a three-way *locus*), with a
   verbatim evidence quote that is checked against the passage (§4).
2. **A corpus pipeline** over Project Gutenberg fiction that treats dates, author identity and canonicity as
   measurements in their own right: an agent-assisted source review of 630 early dates, PG-agent author groups that
   merge pseudonyms and publisher house names, and a canon measure fixed from metadata before any audit (§3).
3. **A confirmatory design for LLM-labeled cultural analytics**: a sealed confirmation half, an audit drawn on metadata
   only, expert-anchored DSL, a pre-registered power analysis, and a deterministic robustness battery (§5–7). The
   primary test is the two-fictions hypothesis (TF); the inward-turn-style era contrast (H1) is secondary.
4. **Negative lessons** that we think generalize: the model's locus is mostly a recode of its domain; two models given
   the same codebook disagree about whether 40% of passages contain an obstacle; and research agents asked to find
   trends in our labels tend to narrate noise (§8; Anonymous, 2026).

We do not claim that technology caused anything, and our population is "fiction preserved in Project Gutenberg",
not the novel. Nor are we the first to compute conflict in fiction (Häußler and Gius, 2023) or to test the inward turn
at scale (Radak et al., 2024). What is new is a corpus-scale, human-validated measurement of *what blocks characters'
goals*, and a design that keeps the confirmatory question separate from the questions we found by looking.

---

## 2 Related work

[src: `research/lit/related_work_notes.md`, which records for each work the URL read and whether we read the full
text or only the abstract.]

**Conflict and goals in narrative.** Piper et al. (2021) propose a minimal model of narrative (an agent doing something
somewhere, at some time, for some reason) and urge computational work to model *disequilibrium* and change of state.
They also ask how family relations, including conflict, changed historically. Obstacles to a goal are one way to make
that disequilibrium countable. The closest historical precedent is Häußler and Gius (2023). They operationalize
conflict in 217 German novels (115 Romantic, 102 Realist/Naturalist), following Glasl, as *incompatibility* between
agents plus *impairment* of what an agent wants. They annotate only incompatibility and leave impairment to future
work. Their two annotators reach κ = 0.325, and embedding-based scores match the manual labels poorly (F1 0.15–0.19).
We take up the half they left open, impairment, and we read their low agreement as a warning about how hard the
construct is. Smeets et al. (2021) model dyadic and triadic character conflict in 170 present-day Dutch novels and
link it to social groups (we read only the abstract). Their conflict is person-against-person, in one period.
Christou and Tsoumakas (2025) are closest in corpus and method. GPT-4o extracts over 120,000 relation mentions from 96
English Gutenberg novels (1850–1950), and they report that enmity crests in the final twentieth of a book and that
alliance rises and kinship declines across the period. They count relationships rather than obstacles, use
uncorrected LLM labels, and do not pre-register. Our design addresses those last two gaps.

**Interiority and the inward turn.** Radak et al. (2024) test the inward-turn hypothesis across ELTeC collections of
roughly 100 novels per language, 1840–1920, using the share of inner-life verbs. They find no statistically significant
rise in any language, and a significant decline over a longer French series. Strikingly, "only in the English data"
of canonical novels do they see the expected upward trend. We read that as a hint that the inward turn may belong to
the canon, which is our TF hypothesis. Their measure is lexical; ours asks whether the mind is what *blocks* the plot.
A null in both would be informative, and so would a split between them. Underwood et al. (2018) show at a scale of
104,000 volumes how a narrative property, how gendered character description is, can be traced across two
centuries. They also show that collection composition (women's share of authors halves between 1850 and 1950) shapes
what such trends mean.

**Technology and time in fiction.** Kim et al. (2020) assign clock times to passages in 52,183 Gutenberg and
HathiTrust books and find that the share of events after 10 p.m. jumps after 1880, which they connect, without
testing it, to electric light. Their historical analysis groups books by *author birth year* and reports descriptive
shares. We date by first publication after a source audit and report corrected intervals. We also measure darkness as
an obstacle rather than night as a setting. Youngman and Carmichael (2014) study railway vocabulary in
nineteenth-century German fiction. The chapter is paywalled and we could not read it, so we cite it only as a topical
precedent and attribute no finding to it.

**LLMs as instruments in cultural analytics.** Bamman et al. (2024) compare prompted LLMs with supervised models on ten
cultural-analytics classification tasks. Prompted models are competitive on established tasks but weaker on *de
novo* ones: GPT-4o scores 0.564 against BERT's 0.879 on technological strangeness. Plot obstacles by locus are a de
novo construct, so we expect noisy zero-shot labels and plan for it. Chang et al. (2023) show that GPT-4 has memorized
public-domain canon far more than other fiction (name-cloze 0.244 on pre-1923 LitBank novels vs. ≈0.02 on Global
Anglophone fiction), and that downstream accuracy tracks memorization. Since our main contrast *is* canonical against
non-canonical, this is a direct threat. We answer it with passage-internal evidence quotes, a memorization covariate
and battery check, and gold labels balanced on canon. To turn imperfect labels into valid estimates we use
design-based supervised learning (DSL; Egami et al., 2023). Egami et al. show that even a 90%-accurate surrogate can
give 95% intervals that cover only about 40% of the time. Prediction-powered inference (Angelopoulos et al., 2023) is
the general framework; we prefer DSL because it builds in known, unequal sampling probabilities and covariate-dependent
correction.

**Automated discovery.** Benchmarks for AI-driven data analysis score whether agents recover a known answer.
DiscoveryBench (Majumder et al., 2025) finds that the best system scores 25% on 264 real and 903 synthetic tasks. BLADE
(Gu et al., 2024) finds language models mostly limited to basic analyses, with low coverage of expert analysis
choices. HypoBench (Liu et al., 2025, preprint) shows recovery of planted hypotheses falling from 93.8% to 38.8% as
noise and distractors grow. D5 (Zhong et al., 2023) describes differences between corpora, including time splits, and
warns that it finds correlation, not causation. POPPER (Huang et al., 2025) gives agents a sequential falsification
procedure with Type-I error control, valid when each test the agent designs is. None of these scores the failure
we care about: a fluent, confident story about a trend that is really a change in the archive. We test that directly
in a companion benchmark (§8.2) and, on the human side, rely on deterministic, pre-registered checks rather than an
agentic falsifier.

**The archive as object.** Moretti (2000) estimates that a canon of 200 nineteenth-century British novels is about
0.5% of the novels published, and calls for literary history of the canonical and the forgotten together. Bode (2018)
argues that digitized collections are themselves historical artifacts, shaped by transmission, and must be modelled as
such. Underwood and Sellers (2016) separate reviewed from random *poetry* volumes, 1820–1919, and find that the
standard of prestige is stable across the century. We borrow the framing but measure prestige from present-day
cultural visibility, and we look at plot function, not diction. Bourdieu's (1993) contrast between restricted and
large-scale production gives the two-fictions hypothesis its vocabulary.

---

## 3 Data

### 3.1 Corpus

We start from the official Project Gutenberg (PG) text mirror and RDF catalog and keep English items with an LCSH
fiction heading or LoCC PR/PS/PZ class. Cleaning removes PG boilerplate. Text-quality filters drop works with high
rates of very short lines, all-caps lines or repeated lines (tables, indexes, running headers), and works under 15k
words. A work-level check combines catalog headings with a small model's form judgment. On a 200-work QA pass the
4B model collapsed to a constant answer ("novel, confidence 0.95") and missed 10 of 12 non-fiction works, so the keep
rule trusts catalog non-fiction headings over the model, and never excludes on the model's translation flag
(0/5 precision) [src: `docs/qa/workcheck_pass_1.md`, `analysis/workcheck_rule.py`].

**Dedup.** MinHash plus author/title keys collapse editions, abridgements and multi-volume splits into one work. The
canonical edition is the one with the best date evidence, then the longest text. The result is **15,511 works,
≈1.14 billion words** [src: `docs/data_quality.md` §A.4, handoff §3].

**Splits.** Before any labeling, authors were hashed into a Discovery half and a Confirmation half, stratified by
decade, origin and genre. Discovery is open to analysis. Confirmation results are sealed (§5.2).

**Sampling.** Each work contributes 24 seeded random passages of ≈350 words with character offsets and a SHA-256 hash
(≈607k passages); confirmatory estimates use the first 12 (`rand_a`, k < 12). Separate keyword-enrichment strata
exist for communication, travel and light, with known inclusion probabilities, but they never enter a confirmatory
estimate.

**Genre.** An eight-class genre variable is derived from LCSH subjects and PG bookshelves (juvenile, domestic/realist,
historical, adventure, sensation/mystery, collection, romance, other). Juvenile fiction is about 30% of PG fiction
from 1850 to 1929. Early-era PG fiction is dominated by historical novels (26–31%) [src: `docs/pilot_analysis_1.md` §1].
Works with a historical setting (2,711 by LCSH, genre and bookshelf rules) are excluded from the primary set, since a
Scott novel tells us little about 1820s obstacles.

### 3.2 Author groups

Clustered standard errors and the split both need the right notion of "author". PG's catalog has one record per
pseudonym, and series fiction was often published under house names. We build **author groups** as connected
components over PG agents, using PG's own pseudonym links, shared Wikidata QIDs, duplicate records, and a Stratemeyer
Syndicate rule that joins 37 house-name agents (519 works) into one cluster. Anonymous and "Various" records become
singletons. This gives 4,010 groups. Thirteen groups (345 works) had works in both halves; under a rule fixed in
advance, each moved wholly to Discovery, since Discovery had already been examined [src: `docs/canon_measure.md` §1].
The Confirmation half now has 7,062 works and Discovery 8,449.

### 3.3 Dates

Publication year is the variable everything else depends on, and PG does not record it. We start from pg-dates
(Momen et al., 2025), an LLM-plus-retrieval estimate of first publication, and audit it two ways.

- **A catalog audit** against Open Library matched 67% of works and proposed 1,452 corrections, 625 of which would move
  a work between eras. Because Open Library's "first publish year" often names a reprint, these were not applied
  automatically [src: `research/date_audit/report.md`].
- **A source-by-source review of early dates.** Every work catalogued before 1850, and every work catalogued
  1847–1853 (630 works), was checked against first-edition bibliographies by an agent working from cited sources. 566
  book dates were resolved and 64 were not. Among resolved dates, the catalog year was wrong in 41% of cases and off by
  more than five years in **23.5%** (25.9% in Confirmation, 21.5% in Discovery). Eighty-one works changed era
  (37 Confirmation, 44 Discovery), in both directions [src: `research/date_audit/verify/report.md`].

The primary set uses the verified year where one exists, excludes unresolved early dates, works outside 1800–1929, and
359 works whose catalog year is a bare "1900" placeholder [src: `docs/canon_measure.md` §3.1]. The agent review is
not yet human-signed; the pre-registration requires a human sign-off before unsealing (**TODO(verify)**: record the
sign-off).

### 3.4 Canon measure

The literary review of an earlier draft (§8) showed that our "historical trend" might be a canon-composition effect.
We therefore defined a canonicity measure **from metadata only, before the audit draw, without reading any labels**.
An author group is *canonical* if its author has a Wikipedia article in at least K = 30 language editions (Wikidata
sitelinks) and is not a publisher's house name. K = 30 sits near the 95th percentile of author groups. It was chosen
knowing where a sanity list falls (Austen 145, Eliot 92, Hardy 92, Collins 52, Trollope 41 are canonical; Alger 28,
Henty 11, Le Queux 8 are not), so K is not blind, and we register K ∈ {20, 25, 40, 50} and a downloads-based variant as
sensitivity analyses [src: `docs/canon_measure.md` §2].

The measure captures *lasting cultural visibility*, closer to Bourdieu's consecration than to a syllabus. It counts
Woodrow Wilson and Zane Grey as canonical and Braddon and Yonge as popular. Against ELTeC-eng's reprint-count
categories it agrees on 80% of 50 matched authors. Its main use is the strongest pattern in the archive. The
canonical share of works falls from about one-third to one-half before 1850 to about one-tenth after 1885, in both
halves (Figure 1). In the registered Confirmation primary set (4,048 works: E 87, M 538, L 3,423), 37% / 19% / 9% are
canonical by era.

---

## 4 Measurement

### 4.1 Task and codebook

The unit is a 350-word passage with ≈900 characters of context before it and ≈600 after, marked as
orientation-only. The model answers one question: *is something standing in the way of what a character wants, in a
way that matters for what happens next?* A "yes" needs three things inside the passage: a character with a goal, an
impediment, and a narrative consequence. The codebook (v0.9, Appendix A, given to the model verbatim) lists the
non-obstacles that a first QA pass found the model over-calling: mild shyness the character goes ahead despite,
banter, procedural description, and obstacles that appear only in the context [src: `docs/codebook.md`].

For each obstacle the model gives:
- one or two **domains**, from DISTANCE_TRAVEL, COMMUNICATION_INFORMATION, DARKNESS_VISIBILITY, ILLNESS_BODY_DEATH,
  MONEY_PROPERTY_LAW, SOCIAL_RANK_CONVENTION, INTERPERSONAL_CONFLICT, INNER_STATE, NATURE_WEATHER and OTHER;
- a **locus**: *material/external* (the physical world, the body, infrastructure), *social/institutional* (other
  people, rules, money, rank), or *internal/psychological* (the blocked character's own feeling, will or judgment).
  Locus is the *proximate source*, the thing that, if removed, would let the character proceed. It is judged before
  the domain, with a six-word reason;
- an `evidence_quote` of 6–20 consecutive words from inside the passage;
- sub-fields for communication failures, named technology and night scenes, used only descriptively.

The locus triad is the classroom conflict typology made operational, and we say so. It is not Greimas's actantial
opponent or Ryan's clash of private worlds, both of which live at the level of the whole story. Our unit is the
**scene-level obstacle**, and 72% of random windows contain one. Claims about "plot" in this paper always mean that.

### 4.2 Verified evidence quotes

Every positive label must point to its evidence. A deterministic checker classifies each quote as *exact*,
*normalized* (matching after whitespace, quote-mark and hyphenation normalization), *trimmed* (at least 6 words verify
inside the passage when the quote straddles its boundary), *context* (copied from the orientation text) or
*hallucinated*. On Discovery, 91–93% of positive rows verify exactly or after normalization, in every era
[src: methods review appendix]. That is below our own gate of 0.97 (`docs/model_selection.md`), and we report it as a
shortfall. A failed quote does not recode the label to "no". The row keeps its label and the failure flag enters the
DSL calibration model as its own category, so the correction absorbs any link between quote failure and error
(§5.1). The quotes also do humanistic work: every number in §6 comes with passages a reader can check.

### 4.3 Model selection and the cascade

All labeling runs on local open-weight models, served by Ollama on volunteers' consumer GPUs through a small
distributed client and coordinator. Each stage has one pinned model, quantization, prompt and decoding setting
(temperature 0, seed 0, JSON-schema-constrained output); any change creates a new pin.

**Selection.** We compared candidates on 60 frozen passages (51 fiction) against a provisional reference written by
a blind Claude reader applying the same codebook. That reference is *not* human gold, and the human audit replaces it
(§4.5). Gemma 4 12B (Q4_K_M) reached accuracy 0.86 on has_obstacle (precision 0.86, recall 1.00) and 0.88 locus
agreement, at 3,900 passages/h on an RTX 4070 Ti SUPER. Qwen 3.5 9B reached 0.78 (precision 0.94, recall 0.79). A
"grounded" prompt that first asks for goal, impediment and consequence fields was 7× slower for +0.02 accuracy and
was dropped. A cheap screening stage was also dropped. It passed 56% of passages, so screening plus labeling cost
about as much as labeling everything [src: `docs/model_selection.md`].

**What the cascade became.** In practice the label stage is a single Gemma 4 12B pass. A 4B model runs the
work-level fiction check and the name-cloze memorization probes (Chang et al., 2023). Qwen 3.5 9B relabels a
subsample as the alternate-family robustness check.

**Hand QA.** One reviewer read 90 production passages (40 oversampled for risk) under the v0.5 codebook. The model
over-called obstacles by about 15 points in every era (design-weighted yes-precision 0.77, recall 0.98; true obstacle
rate ≈ 0.71). SOCIAL_RANK_CONVENTION was inflated about 2×, and the late popular-fiction errors had a pattern: a steer
blocking the road coded as interpersonal, a massacre coded as illness. Locus was right for 90% (weighted) of true
obstacles [src: `docs/qa/label_pass_2.md`]. Codebook v0.9 added six targeted edits (the three-part test, a context-only
exclusion, a narrower SOCIAL_RANK rule, and others), plus the proximate-source locus rule. On the same 90 passages
it raised yes-precision from 0.73 to 0.80 and lowered recall from 0.97 to 0.88 [src: `docs/perf_label_ab.md` §3]. We
froze v0.9 as the registered predictor and **did not** relabel with a later version: DSL is valid for any predictor,
and in simulation better model accuracy was a weak lever on power (§5.3).

### 4.4 Efficiency

Making 600k passages affordable on volunteer hardware mattered more than any prompt change. On an RTX 3060 (12 GB),
the label stage ran at ≈1,035 passages/h with the original settings [src: `docs/perf_label_ab.md`]. Profiling showed
that **prefill, not decoding, dominates**: the prompt is ≈2,400 tokens and the output ≈150. Gemma's sliding-window
attention meant that at an 8k context the shared system-prompt prefix was never reused, so every request re-processed
the codebook. At a 4k context the server places a checkpoint at the system/user boundary, and the mean prefill per
request falls from ≈2,400 to ≈840 tokens. Combined with an 8-bit KV cache (which halves KV memory and allows four
parallel slots on 12 GB) and a lean output schema (no fields on "no" rows), v0.9 runs at **1,793–2,015 passages/h on
the 3060, 1.8–1.9× the original**, with no loss of accuracy against either reference. A 16 GB RTX 4070 Ti SUPER
reached up to ≈4,700 passages/h in a bench sweep [src: `docs/perf_report.md`; **TODO(verify)** which pin that sweep
used]. Two operational lessons cost us days. A second resident model forces partial CPU offload and cuts throughput
about 8×, and serving one model at two context sizes reloads it on every switch. `[CUT?]` Table 4 in Appendix B gives
the full A/B.

Even so, the full queue is far beyond what a handful of volunteer GPUs can finish by the deadline. We prioritized the
12-per-work random backbone of the Confirmation primary set (≈48k passages), early-era top-ups, and a Discovery
subsample (**TODO(unseal):** final labeled counts per split).

### 4.5 Human and expert audit

**Who labels.**
- *Peers*: the student first author and about three student volunteers, roughly 500 labels each, ≈2,000 labels in
  total with 10% overlap. Peers must first be **certified**: κ ≥ 0.60 on locus against the expert's key on a 20-item
  Discovery pre-test.
- *The expert*: an anonymous graduate student in English, about 8 hours, ≈900 labels. The expert has seen only the
  codebook and the annotator guide: no hypotheses, pilot results, reviews or project pages. Before labeling they
  sign a **blindness attestation**, deposited with the registration.
- *A high-school English teacher* labels about 8 items. Teacher–expert agreement is reported descriptively, and these
  labels never enter an estimate.

**What is labeled.** The human schema is shorter than the model's: has_obstacle, one main domain, locus, and the
communication-failure cause. Annotators see the passage and its context, with no title, author or date.

**How items are drawn.** About 1,820 Confirmation passages, drawn before registration with seed 20261105 by a
procedure that reads **metadata only**: strata are era × genre × canonical (41 non-empty cells). The budget is split
equally across the six era × canonical cells and then proportionally within them, and the inclusion probability π is
stored for every passage in the pool. The expert's ≈900 items are a 50% random subsample *within* audit cells, so
P(expert | audit) is known, and every expert item is also peer-labeled. An earlier design stratified the audit on
*predicted* labels. An adversarial methods review pointed out that this would have shown us the naive Confirmation
answer before registration, so we replaced it (§8.1) [src: `docs/prereg.md` §3.2].

**TODO(audit):** certification results; peer–expert κ overall and by era; model–expert κ by era; skip rates; the
attestation status. If peer–expert κ on locus falls below 0.6, the peers serve only as a variance-reduction phase.
If model–expert κ falls below 0.4 in any era, the paper flags weak model information (registered construct gate).

---

## 5 Inference

### 5.1 Expert-anchored DSL

Naive LLM labels are biased, and the bias need not be the same across eras or genres. Plugging them into a regression
gives tight intervals around the wrong answer. In our own simulations the naive H1 contrast was biased by about 12 pp
with 0% CI coverage [src: `docs/prereg.md` §7.1(b)]. We use design-based supervised learning (Egami et al., 2023),
which builds a doubly robust pseudo-outcome from model predictions plus a known-probability sample of gold labels. We
extend it to three levels because our gold labels are themselves nested:

Ỹ = g₁(model) + (R_a/π_a)·(g₂ − g₁) + (R_a R_e)/(π_a π_e|a)·(expert − g₂),

Here R_a and R_e indicate audit and expert membership. g₂ is a cross-fitted multinomial logit of the expert label on
the peers' mean soft label and the model label, and g₁ calibrates g₂ on the model label by era (five author folds).
Because E[Ỹ] equals the expert label for *any* g₁ and g₂, peer noise and peer bias cannot bias the estimate, and
neither can the fact that the first author, a peer, knows the hypotheses. They only change the variance. The remaining
assumption is the expert's own blindness and consistency. Work-level means of Ỹ then enter the outcome models, with
author-clustered (CR1) sandwich errors and the delta method. A stratified prediction-powered inference estimate
(Angelopoulos et al., 2023) agrees with DSL point estimates to machine precision under raw g. It ignores
within-work clustering and undercovers, so we report it only as a cross-check.

### 5.2 Sealing and pre-registration

Discovery labels have been read, analysed and reviewed, and the two-fictions hypothesis was **found** there. The
Confirmation half exists to test it. Confirmation results are stored only as ciphertext: workers encrypt them
(age/X25519) to the owner's pinned public key, and the private key is held offline. Unsealing is a one-way operation,
logged in an append-only audit log, and the unseal tool refuses to run unless the pre-registration file contains the
OSF registration hash and the unseal time is after registration (**TODO(unseal):** OSF hash and dates). One seal
incident is disclosed in §9.

**Hypotheses.** Eras are E 1800–1849, M 1850–1884, L 1885–1929.
- **TF (primary, α = 0.05).** Canonical and non-canonical works differ in their locus mix. The estimand is the pair of
  standardized differences (Δ_material, Δ_internal), canonical minus non-canonical, by g-computation over a fixed
  standard population at each work's own year. The test is a two-sided 2-df Wald test. Genre is deliberately *not*
  adjusted, because genre mix is part of what separates the two fields; a genre-adjusted TF is descriptive.
- **H1 (secondary; Holm with H1|canonical and H1|non-canonical).** The locus mix of scene-level obstacles shifts from E
  to L, standardized for genre. H1 is *motivated by* the inward-turn literature. It does not test Kahler, whose
  argument concerns narrative up to about 1800.
- **H2a–c and H3** (communication causes, travel, darkness; keyword mention vs. plot function) are estimation-only:
  effects and CIs, no verdicts.

When a Wald test rejects, the direction is classified symmetrically from Bonferroni-adjusted component CIs as
*inward*, *outward*, *socialisation*, *de-socialisation* or *indeterminate*. For TF, "inward" means that canonical
fiction locates resistance more in people and minds than the mass market does.

### 5.3 Power

We simulated the registered design with inputs calibrated to Discovery (obstacle prevalence 0.70, non-canonical
locus shares ≈0.21/0.69/0.10, author ICC 0.10, the QA error profile, peers at κ ≈ 0.6). Against a 10 pp canon gap in
the material share, **TF has power 0.70 at α = 0.05 (MDE ≈ 9 pp)** with size 0.05 under the null and CI coverage
0.98–1.00. Against a 6–7 pp gap, power is 0.37. H1 is **underpowered**: MDE ≈ 15 pp and power 0.02–0.10 against the
effects Discovery suggests [src: `docs/prereg.md` §7.7]. That is why TF, not H1, is primary.

Expert hours were the decisive lever. Going from about 450 to about 900 expert labels moved the TF MDE from 12.3 to
9.0 pp; balancing the audit on canonicity was essential (without canon strata the MDE is 22.6 pp); and better model
accuracy helped little. A peers-only estimator was biased toward zero (−6.3 vs −9.6 pp truth) with 0.84 coverage
(Table 1). For an NLP audience this is the practical message: **under DSL, the money is in the gold labels, not the
model**.

**Table 1.** TF power by design lever (tf_full truth, Δ_material = −9.6 pp; 60 replicates per row; MC SE ≈ ±0.06).

| Design | TF MDE (pp) | Power α = .05 |
|---|---|---|
| **Registered: ≈900 expert labels, canon strata** | **9.0** | **0.70** |
| ≈450 expert labels | 12.3 | 0.59 |
| ≈226 expert labels | 17.9 | 0.32 |
| No canon strata | 22.6 | 0.23 |
| Expert-only estimator | 13.5 | 0.50 |
| Peers-only estimator (biased; coverage 0.84) | 9.3 | 0.35 |

### 5.4 Verdict rule

A hypothesis is **supported** if its test rejects, it passes at least ⌈7/9 × applicable⌉ battery checks (§7), and
it has the same sign in replication when replication is available. It is **unstable** if it rejects but fails the
battery, and **null** if it does not reject. Nulls are reported with their registered MDE.

---

## 6 Results

### 6.1 Confirmatory results (Confirmation half, human-corrected)

> **TODO(unseal).** Fill Table 2 and the paragraph from `analysis/stats/out/confirmatory/` only. Do not round in a
> direction. Report every registered row, including nulls.

**Table 2.** Registered tests. Expert-construct DSL estimates; 95% CIs (Bonferroni-adjusted for components); author-
clustered.

| Test | Δ_material (pp) | Δ_internal (pp) | Wald p | Class | Battery (pass/applicable) | Verdict |
|---|---|---|---|---|---|---|
| **TF** canonical − non-canonical | TODO | TODO | TODO | TODO | TODO | TODO |
| H1 L − E (Holm) | TODO | TODO | TODO | TODO | TODO | TODO |
| H1 \| canonical (Holm) | TODO | TODO | TODO | — | — | TODO |
| H1 \| non-canonical (Holm) | TODO | TODO | TODO | — | — | TODO |
| TF, genre-adjusted (descriptive) | TODO | TODO | TODO | — | — | — |
| Composition share of E→L material change (descriptive) | TODO | — | — | — | — | — |

*Template sentence (choose by verdict):* "Canonical fiction put the material world in a character's way
[X] pp less often than non-canonical fiction (95% CI [a, b]; p = …), passing k of n robustness checks: supported:
[class]." / "We find no canon difference in locus (Δ_material = X pp, CI [a, b]; registered MDE 9 pp)."

H2a–c and H3 are reported as effects and CIs in Appendix C (**TODO(unseal)**).

### 6.2 Exploratory results (Discovery half, raw model labels)

Everything in this subsection uses **uncorrected v0.9 model labels** on the Discovery half: 15,583 passages from
6,824 works, recomputed on 2026-11-04 [src: handoff §5]. These results produced the hypotheses; they do not test
them. Model yes-precision is about 0.77, so treat them as directions.

**Obstacles are common, and mostly social.** 72.3% of passages contain an obstacle. Among obstacles, 68.2% are
social/institutional, 21.6% material and 10.2% internal.

**No inward turn.** By era, the locus shares are E .76/.13/.11, M .68/.20/.12, L .68/.22/.10 (social / material /
internal). The internal share is flat or slightly falling. Even in domestic/realist fiction and romance, the genres
most likely to show interiority, internal stays at 0.17–0.20 across eras [src: literary review P3]. This is the
functional counterpart of the lexical null of Radak et al. (2024).

**Two fictions.** Table 3 splits obstacles by our canon measure. In every era, canonical works put the material world
in the way less often than non-canonical ones, by 6–11 pp. The canonical share of obstacle passages falls from 36%
to 9%, so part of the aggregate "material rise" comes from composition. Not all of it does: the non-canonical
material share also rises from E to M, which is softer than an earlier ad-hoc author list suggested.

**Table 3.** Exploratory locus shares among obstacle passages, Discovery, raw v0.9 labels (canonical = sitelinks ≥ 30).

| Era | Canonical share of obstacle passages | Material: canon / non-canon | Internal: canon / non-canon |
|---|---|---|---|
| E 1800–1849 | 36% (112/314) | .09 / .15 | .11 / .11 |
| M 1850–1884 | 22% (317/1,445) | .11 / .22 | .17 / .11 |
| L 1885–1929 | 9% (887/9,501) | .16 / .23 | .13 / .10 |

**The machine is rarely the obstacle.** Only 2.0% of obstacles (226 of 11,260) name a technology. The most frequent are
telegram (53), telephone (41), carriage (35), letter (20) and steamship (18), and a literary reviewer found many of
those wrong. In a random page of this fiction, a machine is almost never what blocks anyone. When the mail works,
people become the obstacle: "She wrote to him; he did not reply" (Hardy, *The Mayor of Casterbridge*, 1886).

**Where the canon blurs society and self.** Canonical "internal" obstacles are often social rules the character has
absorbed. Brontë's Lucy Snowe asks "why did nobody undertake to make me clever while I was young enough to learn"
(*Villette*, 1853). The model codes it as internal; it is education denied to a woman. The boundary also leaks in the
other direction. The mass-market best-seller *Dora Thorne* (Brame, 1884) is non-canonical by our measure, but its
obstacle is pure class: "You are not my son's equal in refinement or education". We treat the social/internal line as
the construct's weakest point (§8.2).

**Figure 2** shows passage cards: paired canonical and mass-market quotes for each locus, all with exact or normalized
quote verification.

---

## 7 Robustness and validity

### 7.1 The battery

Each registered test goes through nine deterministic checks, all reported whether they pass or fail
[src: `analysis/stats/battery.py`]:

1. leave-one-author-out (20 author groups);
2. leave-one-decade-out;
3. drop each major genre;
4. high-confidence dates only;
5. drop the top decile of works by name-cloze memorization score;
6. alternate model family (Qwen 3.5 9B labels on a subsample);
7. alternate segmentation (250/500-word passages);
8. a permutation null. For TF, author-level canonical flags are permuted among authors within era; for H1, author
   date profiles are permuted within genre. (Permuting within author × genre blocks, as first planned, leaves
   chronology intact and is not a null);
9. replication on an external corpus (ELTeC-eng). This check is optional: it is excluded from the denominator when
   unavailable, never counted as a failure.

Registered sensitivity analyses add TF and H1 with every cross-half canonical author removed, standardization to the
early-era mix, canon thresholds K ∈ {20, 25, 40, 50}, the downloads-based canon flag, and peers-only and expert-only
estimators. **TODO(unseal):** Table 5 (per-check results).

### 7.2 A multiverse over instruments

The most serious threat to any LLM-labeled trend is that the trend belongs to the instrument. We have direct evidence
that it can.

- **Model.** On the same 600 Discovery passages with the same v0.9 codebook, Gemma 4 12B says "yes" on 72.3% and Qwen 3.5
  9B on 32.2%. Cohen's κ is 0.24 for has_obstacle and 0.25 for four-way locus, and the first domain agrees on only 48%
  of the passages both call obstacles [src: methods review P1].
- **Codebook.** Under v0.5 the pilot showed a +8.1 pp M→L material step "in the 1880s". Under v0.9, on 8,718 Discovery
  passages, the same contrast is +2.4 pp (author-bootstrap 95% CI [−3.1, +7.0]), and the step is gone.
- **Locus is mostly domain.** Under v0.9 the model's locus equals the default mapping of its first domain in 94.6% of
  obstacles, despite a required locus reason. The hand QA reference departs from that mapping 17% of the time.

We therefore report a specification curve on Discovery (exploratory) of the TF and H1 estimates across: model (Gemma
vs. Qwen vs. a Claude reference reader), codebook version, date source (catalog vs. verified), genre standard, canon
threshold, and clustering unit (Figure 3). DSL makes the *corrected* estimate valid for any predictor, so the multiverse
is a statement about how much the naive picture depends on the instrument, and how much work the human labels do.

> **TODO(claude-ref):** fill from `docs/claude_reference_analysis.md`: Claude-reference vs Gemma vs Qwen agreement (κ for
> has_obstacle and locus), naive TF and H1 estimates under each, and whether the canon gap keeps its sign across all
> three. Keep it framed as a reference reader, not gold.

---

## 8 What went wrong, and what it teaches

### 8.1 Three reviews that changed the design

Before registration we commissioned three adversarial reviews: methods, literary and feasibility. Three changes
follow from them.
- The **literary review** found the composition artifact behind the "outward turn" and proposed the two-fictions
  hypothesis.
- The **methods review** found that our audit draw would have read sealed labels. It also showed the instrument
  instability above, and that H1 as first registered had power of 15–55%.
- The **feasibility review** cut scope to what volunteer GPUs could finish.

We list these changes in the pre-registration's deviations log, including the ones made after viewing Discovery
data. We think this is the honest way to use a split-half design: look hard at one half, then register what you
learned before opening the other.

### 8.2 Agents narrate noise

One plan for this project was to let LLM research agents find the trends. A companion workshop paper (Anonymous, 2026)
builds a benchmark from our Discovery labels. Thirty corpora are made by resampling real labeled works: ten with a
real retained positive (a +3.7 pp rise in distance/travel obstacles, CI [+1.5, +5.7]), ten with an injected shift, and
ten **confounded nulls** with no within-genre change but a real archive artifact: genre-mix drift, reprint-date
contamination, duplicate editions or canon oversampling. Unlike synthetic-truth discovery benchmarks, the traps here
are the ones this paper had to avoid by hand. A structural leak audit finds the three arms indistinguishable
(random-forest accuracy 0.333, chance) [src: `bench/pilot_report.md`].

**TODO(AAAI):** headline false-claim rate on confounded nulls and detection rate on injected shifts once paid agent runs
exist. As of this draft, only a 30/30 dummy pilot has run, so no agent result may be quoted.

Our own history is the motivating case. A plausible, well-dated, within-genre "1880s step" appeared in a pilot,
inspired a redesign, and then disappeared when the codebook changed. A pipeline without a sealed half would have
published it.

---

## 9 Limitations

- **The archive.** Our population is fiction preserved in Project Gutenberg, which over-represents what volunteers
  were assigned in school (the early canon) and what they loved as children (late series fiction). Before 1850 the
  primary set has fewer than 100 works per half. Results do not describe "the nineteenth-century novel".
- **The canon proxy.** Wikipedia sitelinks measure present-day global fame. They reward Americana, pulp and
  non-literary celebrity, and K was set with knowledge of a sanity list. Canonicity is assigned per author, not per
  book. A historical-reception measure, such as periodical reviews (Underwood and Sellers, 2016), would be stronger.
- **Dates.** Even after review, early dates rest on an agent-conducted source review awaiting human sign-off, and
  late-era dates were not hand-verified.
- **LLM labels.** The model over-calls obstacles, inflates social rank, and mostly reads locus off the domain.
  Under DSL these errors cost precision, not validity, but only if the expert's labels define the construct well.
  Construct validity rests on one expert.
- **Annotators.** Peers are high-school students, and the first author is one of them and is not blind. The
  estimator is robust to peer bias by construction, but the expert anchor is a single graduate student (≈900 items).
- **Scale and construct.** A 350-word window sees the obstacle of a scene, not of a story (Casaubon's will is many
  chapters away). The instrument undercounts interiority: personified virtues, guilt coded as its occasion, and
  resolved deliberation all slip out. H1 tests what blocks characters, not how novels narrate minds.
- **Seal incident (disclosed).** On 2026-11-02, while a platform-migration export tool was being tested, an automated
  test exported 5 sealed Confirmation model-label blobs (≈2,000 passages; no human labels), encrypted them to a
  throwaway key and decrypted them to local disk. They were deleted within minutes. Nothing was read, displayed,
  analysed, uploaded or committed; only job IDs appeared in logs. Safeguards now restrict real sealed blobs to the
  owner's key and dry runs to synthetic data. We assess the impact as none, and we report it because a seal is only
  as credible as its incident log [src: `docs/prereg.md` §8.1].
- **Compute.** Not every planned passage was labeled. **TODO(unseal):** final coverage by era × canonical.

## 10 Ethics

All texts are public-domain in the United States and come from Project Gutenberg's official mirror. We do not
redistribute raw texts, and we follow PG's terms for automated access. pg-dates is licensed CC BY-NC, so we use it but
do not redistribute it. We release passage IDs, character offsets and hashes, labels, the codebook, prompts, model
pins and code. Volunteers ran the labeling client on their own machines and could pause or stop at any time
(**TODO(verify):** describe the consent/opt-in text the client shows); no personal data is collected beyond an anonymous worker ID. Student annotators and the expert took part
voluntarily, with an annotation guide and a time estimate, and annotators under 18 took part with parental
knowledge (**TODO(verify):** confirm consent procedure wording with the school/teacher). The corpus contains period
racism and imperialism. The codebook has no category for empire or race, and so folds those obstacles into
interpersonal conflict. We name this as a choice with consequences. LLM assistance: the first author used LLM coding
and writing assistants for pipeline code, simulations, literature search and draft editing, and all numbers come from
logged runs (**TODO:** match final SRW disclosure wording).

---

## References

Verified 2026-11-04 (see `research/lit/related_work_notes.md` and the `% verified` comments in
`research/lit/refs.bib`). Typeset from refs.bib with ACL natbib at submission.

- Angelopoulos, A. N., S. Bates, C. Fannjiang, M. I. Jordan, and T. Zrnic. 2023. Prediction-powered inference.
  *Science* 382(6671): 669–674. doi:10.1126/science.adi6000.
- Anonymous. 2026. Plausible stories from null corpora. Under review, AAAI 2027 workshop. *(anonymized self-citation)*
- Bamman, D., K. K. Chang, L. Lucy, and N. Zhou. 2024. On classification with large language models in cultural
  analytics. *Proc. CHR 2024*, CEUR-WS 3834: 494–527.
- Bode, K. 2018. *A World of Fiction: Digital Collections and the Future of Literary History*. University of Michigan
  Press. doi:10.3998/mpub.8784777.
- Bourdieu, P. 1993. *The Field of Cultural Production: Essays on Art and Literature*. Ed. R. Johnson. Columbia
  University Press.
- Chang, K. K., M. Cramer, S. Soni, and D. Bamman. 2023. Speak, memory: An archaeology of books known to
  ChatGPT/GPT-4. *Proc. EMNLP 2023*, 7312–7327. doi:10.18653/v1/2023.emnlp-main.453.
- Christou, D., and G. Tsoumakas. 2025. Relational arcs as narrative structure: Dynamics, distribution and diachronic
  change in fiction. *Computational Humanities Research* 2, e2. doi:10.1017/chr.2025.10021. (Online Dec 2025; volume
  dated 2026.)
- Egami, N., M. Hinck, B. Stewart, and H. Wei. 2023. Using imperfect surrogates for downstream inference:
  Design-based supervised learning for social science applications of large language models. *NeurIPS 36*.
- Gu, K., et al. 2024. BLADE: Benchmarking language model agents for data-driven science. *Findings of EMNLP 2024*,
  13936–13971. doi:10.18653/v1/2024.findings-emnlp.815.
- Häußler, J., and E. Gius. 2023. Operationalizing and measuring conflict in German novels. *Proc. CHR 2023*,
  CEUR-WS 3558: 426–440.
- Huang, K., Y. Jin, R. Li, M. Y. Li, E. Candès, and J. Leskovec. 2025. Automated hypothesis validation with agentic
  sequential falsifications. *Proc. ICML 2025*, PMLR 267: 25372–25437.
- Kahler, E. 1973. *The Inward Turn of Narrative*. Princeton University Press.
- Kim, A., C. Pethe, and S. Skiena. 2020. What time is it? Temporal analysis of novels. *Proc. EMNLP 2020*,
  9076–9086. doi:10.18653/v1/2020.emnlp-main.730.
- Liu, H., S. Huang, J. Hu, Y. Zhou, and C. Tan. 2025. HypoBench: Towards systematic and principled benchmarking for
  hypothesis generation. arXiv:2504.11524. *(preprint; peer-reviewed venue unverified)*
- Majumder, B. P., et al. 2025. DiscoveryBench: Towards data-driven discovery with large language models. *ICLR 2025*.
- Momen, O., M. Schaaf, and A. Mehler. 2025. Filling the temporal void: Recovering missing publication years in the
  Project Gutenberg corpus using LLMs. *Findings of ACL 2025*, 17318–17334. doi:10.18653/v1/2025.findings-acl.890.
- Moretti, F. 2000. The slaughterhouse of literature. *Modern Language Quarterly* 61(1): 207–227.
  doi:10.1215/00267929-61-1-207.
- Piper, A., R. J. So, and D. Bamman. 2021. Narrative theory for computational narrative understanding. *Proc. EMNLP
  2021*, 298–311. doi:10.18653/v1/2021.emnlp-main.26.
- Radak, T., et al. 2024. Towards a computational history of modernism in European literary history: Mapping the inner
  lives of characters in the European novel (1840–1920). *Open Research Europe* 3: 128 (v2).
  doi:10.12688/openreseurope.16290.2.
- Smeets, R., M. De Pourcq, and A. van den Bosch. 2021. Modeling conflict: Representations of social groups in
  present-day Dutch literature. *Journal of Cultural Analytics* 6(3). doi:10.22148/001c.24722. *(abstract only read)*
- Underwood, T., D. Bamman, and S. Lee. 2018. The transformation of gender in English-language fiction. *Journal of
  Cultural Analytics* 3(2). doi:10.22148/16.019.
- Underwood, T., and J. Sellers. 2016. The longue durée of literary prestige. *Modern Language Quarterly* 77(3):
  321–344. doi:10.1215/00267929-3570634.
- Woolf, V. 1925. Modern fiction. In *The Common Reader*. Harcourt, Brace. (Quotes checked against PG eBook #64457.)
- Youngman, P. A., and T. Carmichael. 2014. Big data, pattern recognition, and literary studies: N-gramming the
  railway in nineteenth-century German fiction. In *Distant Readings: Topologies of German Culture in the Long
  Nineteenth Century*, 285–300. Boydell & Brewer. *(paywalled; content not read; cited as topical precedent only)*
- Zhong, R., P. Zhang, S. Li, J. Ahn, D. Klein, and J. Steinhardt. 2023. Goal driven discovery of distributional
  differences via language descriptions. *NeurIPS 36*.

---

## Appendix A. Codebook v0.9 (verbatim)

*Insert the fenced block from `docs/codebook.md` and the prompt template.*

## Appendix B. Efficiency A/B (full table)

*From `docs/perf_label_ab.md` §2–3.*

## Appendix C. Estimation-only results (H2a–c, H3)

*TODO(unseal).*

## Appendix D. Deviations from pre-registration

*The table from `docs/prereg.md` §8, plus any post-registration deviation.*
