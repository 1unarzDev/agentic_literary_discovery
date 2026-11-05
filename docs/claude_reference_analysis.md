# Claude reference labels: where Gemma v0.9 errs, and whether it biases TWO FICTIONS (Discovery, 2026-11-04)

**Status: exploratory, Discovery only.** No Confirmation passage, label or sealed file was read. The Claude labels are
an **LLM reference, not human gold**. They come from a stronger reader applying the same codebook, and they carry
their own errors (see §1.3). The registered correction for model error is still the human/expert audit (prereg §3,
DSL). This document does not replace that audit or change it. It tells us where to expect the audit to move the
estimates.

Code: `analysis/claude_ref.py` (sample, verify, analyze, tables, overlap, reliability, exemplars) and
`analysis/claude_ref_check.py` (quote/enum self-check used by the labelling agents). Data, not committed:
`data/work/claude_ref/` (`sample.parquet`, `sample_meta.json`, `batch_*.jsonl`, `overlap*.{parquet,jsonl}`,
`stats_{g,q}.csv`, `tables.md`, `analysis.pkl`).

```
uv run --with pandas,duckdb,pyarrow python -I analysis/claude_ref.py sample            # seed 20261104
uv run --with pandas,duckdb,pyarrow,rapidfuzz python -I analysis/claude_ref.py verify
uv run --with pandas,duckdb,pyarrow,tabulate python -I analysis/claude_ref.py analyze --B 1000
uv run --with pandas,duckdb,pyarrow,tabulate python -I analysis/claude_ref.py tables
uv run --with pandas,duckdb,pyarrow python -I analysis/claude_ref.py reliability
```

## 0. Headline

1. **Gemma over-labels obstacles, and it does so more in canonical works.**
   - Design-weighted obstacle rate: Gemma 58.9%, Claude 46.3%.
   - Precision of a Gemma "yes": 71% overall, 64% in canonical works, 72% in popular works. Recall is high (≈ 90%).
   - Locus accuracy on passages both readers call obstacles: 81% overall, 73% canonical, 82% popular.
2. **Gemma's locus mix is off in the same direction in both fields.**
   - Material share: Gemma 26%, Claude 32%. Gemma under-calls material.
   - Internal share: Gemma 14.5%, Claude 5.9%. Gemma over-calls internal about 2.5×.
   - Material-share error (Gemma − Claude): canonical −7.3 pp [−15.8, +0.8], popular −5.6 pp [−15.7, +3.0].
3. **TF gap: the error is not strongly differential, and the gap is about the same under both readers.**
   - The TF material gap (canonical − popular, era-standardised) is **−5.8 pp [−19.2, +6.8] under Gemma** and **−4.1 pp [−19.9, +11.3] under Claude**.
   - Bias in the gap: −1.7 pp [−15.2, +12.2].
   - The internal gap: +3.4 pp under Gemma, +8.2 pp [−0.7, +16.2] under Claude. If anything, Gemma *attenuates* the internal component of TF.
   - The full-Discovery Gemma pilot (`analysis/pilot_analysis_2_two_fictions.py`, work-level) gives a standardised material gap of −3.9 pp, which is consistent.
   - **The direction of the TF gap (canonical: less material, more internal) survives the stronger reader.** Neither reader puts it outside noise at n = 1,200.
4. **Era-dependent error exists, and it biases H1 toward the null, not away from it.**
   - Gemma over-calls material in E (20% vs Claude 16%) and under-calls it in L (27% vs 33%).
   - The L − E material rise is +17.7 pp [+3.9, +31.5] under Claude and +7.0 pp [−4.9, +20.1] under Gemma.
   - Bias: −10.7 pp [−22.1, −0.8].
   - Most of it is in the early era. The per-era TF material gap is −12.8 pp under Gemma vs −0.9 pp under Claude in E, mainly because Gemma inflates material in **E popular** (24% vs 16%).
5. **Qwen 9B is a much weaker instrument.**
   - Precision is 90%, but recall is only 50%: it misses half the obstacles.
   - It distorts TF badly. On the Qwen sub-sample, the material gap is +20.1 pp under Qwen against +5.7 pp under Claude, and the internal-gap bias is −15.7 pp [−29.4, −1.9].
   - Qwen should not be used as a TF robustness reader without correction.
6. **The Claude reference is reasonably self-consistent.**
   - 100 items were relabelled blind by different agents under fresh ids.
   - has_obstacle: agreement 0.89, κ 0.78. Locus, where both said yes: agreement 0.92, κ 0.85 (n = 50).

## 1. Design

### 1.1 Sample
- **Frame:** Discovery only (`works_v2.split_v2 == 'discovery'`), with every one of these conditions:
  - registered primary set (`primary_v2_capv2`);
  - `passages.stratum == 'random'` and `passages.split == 'discovery'`;
  - a valid Gemma v0.9 label (`results`, stage `label`, pin `41ca3c7d…`, `valid_schema`).
- **Era:** from `year_v2`, else `year`. Cuts: E < 1850, M < 1885, L ≤ 1929. **Canonical:** from works_v2/canon.parquet (K = 30).
- **Exclusions:** the two codebook few-shot passages.
- **Frame size:** 46,684 passages, snapshot 2026-11-04 ~23:00 UTC; labels were still syncing.
- **Cells:** era × canonical, 200 passages each, so n = 1,200.
  - Within each cell, passages that also have a Qwen alt label (`ca0c1188…`) form a sub-stratum. It gets up to half the cell budget, or all of its passages if there are fewer.
  - Each item carries N_h, n_h and π = n_h/N_h, and every estimate is weighted by 1/π. Preferring Qwen items therefore does not bias any cell estimate.
- **Seed:** 20261104. Item ids are opaque random hex, and the batch order is shuffled across cells.

| era | canonical | N cell | N with Qwen | n | n Qwen | works in frame |
|---|---|---|---|---|---|---|
| E | popular | 675 | 50 | 200 | 50 | 61 |
| E | canonical | 288 | 18 | 200 | 18 | 27 |
| M | popular | 4,519 | 329 | 200 | 100 | 414 |
| M | canonical | 1,091 | 78 | 200 | 78 | 99 |
| L | popular | 36,391 | 2,667 | 200 | 100 | 3,303 |
| L | canonical | 3,720 | 317 | 200 | 100 | 336 |

- **E is thin.** E canonical has 288 passages from 27 works and 11 author groups in the frame, so E-canonical estimates rest on few authors. The author-cluster bootstrap reflects this.
- **"All" estimates are design-weighted to the frame population,** which is dominated by L popular (78% of passages).

### 1.2 Labelling
- **Labellers:** 24 Claude sub-agents, one batch of 50 each, 6–8 running concurrently.
- **What each agent saw:** only the v0.9 codebook block, extracted byte for byte from `docs/codebook.md`, and a packet. The packet held the opaque item id, CONTEXT BEFORE, PASSAGE and CONTEXT AFTER, in the production template and markers.
- **What each agent did not see:** no title, author, date, passage id, model label or other metadata. Agents were told not to open any other file.
- **Fields:** has_obstacle, locus, locus_reason, domains, failure_cause, evidence_quote, rationale, confidence. Agents also gave a `clarity` rating (vivid / clear / borderline), used only for exemplar mining.
- **Quote check:** every quote for a "yes" had to be an exact substring of its PASSAGE, checked by `claude_ref_check.py` inside each agent and re-checked by `claude_ref.py verify`.
  - **Result: 595/595 yes-quotes exact, 0 failures.** (Gemma's quote failure rate in QA pass 2 was 10.9%.)
- **Claude yes rate:** 50.4% raw (605 no / 595 yes). There were no `insufficient_context` answers.

### 1.3 How reliable is the reference? (`reliability`)
- **Design:** 100 sample items, drawn at random with seed 99, were repacked under fresh ids (`r…`) and labelled by two further agents.

| | value |
|---|---|
| has_obstacle agreement / κ | 0.89 / 0.78 |
| yes rate, first / second pass | 0.55 / 0.56 |
| locus agreement / κ, both yes (n = 50) | 0.92 / 0.85 |
| joint 4-way (no / material / social / internal) κ | 0.77 |

- **Comparison with human targets:** this is near the κ ≈ 0.75 that prereg §7 names as the annotator target, and above the κ ≈ 0.6 assumed for peers.
- **What it does not show:** this is *self*-consistency of one model family. It does not show agreement with human readers. Claude's internal share (5.9%) is lower than the 11–12% in the QA pass-2 reviewer reference, so Claude may under-assign internal relative to a human reader. That is the main open question for the human audit.

### 1.4 Estimands and inference
- **Rates, precision and recall:** design-weighted (w = 1/π) means.
- **Locus shares:** shares among each reader's *own* obstacle set, i.e. what that reader would feed into TF. They are also computed on the both-yes set, which isolates pure locus error from prevalence error.
- **TF gap:** Σ_e π_e (share_canonical,e − share_popular,e), with π_e the frame's era mix (E 2.1%, M 12.0%, L 85.9%).
  - This is a passage-level, era-standardised analogue of the registered TF estimand.
  - The registered estimand is work-level, uses a g-computation with a year spline, and takes DSL soft outcomes. **The numbers here are not the TF estimate.** They compare two readers on identical passages under one fixed estimator.
- **H1-style contrast:** L − E share, pooled over canon at the frame's within-era canon mix.
- **CIs:** 95% percentile intervals from B = 1,000 replicates of an author-group cluster bootstrap within each design stratum (era × canon × Qwen).

## 2. Gemma v0.9 vs Claude

### 2.1 has_obstacle and locus accuracy (design-weighted %, 95% CI)

| subset | n | Claude obstacle rate | Gemma obstacle rate | precision | recall | locus acc. (both yes) |
|---|---|---|---|---|---|---|
| all | 1200 | 46.3 [38.3, 53.8] | 58.9 [50.8, 66.5] | 71.1 [62.1, 79.3] | 90.5 [83.4, 96.5] | 80.6 [71.5, 88.3] |
| era E | 400 | 48.1 [42.4, 54.8] | 67.2 [61.1, 73.4] | 67.5 [60.8, 74.5] | 94.5 [90.2, 97.9] | 83.4 [77.7, 88.8] |
| era M | 400 | 45.1 [36.9, 53.6] | 62.9 [55.4, 70.4] | 68.0 [58.7, 77.2] | 95.1 [91.0, 97.8] | 91.5 [86.2, 95.8] |
| era L | 400 | 46.4 [37.0, 54.8] | 58.1 [48.8, 66.9] | 71.7 [60.9, 81.6] | 89.7 [81.7, 96.7] | 79.0 [68.1, 88.1] |
| canonical | 600 | 47.3 [38.6, 55.9] | 67.0 [60.3, 74.1] | 64.2 [55.0, 73.0] | 90.8 [84.3, 95.9] | 72.7 [63.3, 82.0] |
| popular | 600 | 46.1 [37.0, 54.5] | 57.9 [48.9, 66.4] | 72.1 [61.9, 81.8] | 90.4 [82.8, 97.3] | 81.6 [71.3, 90.6] |
| E canonical | 200 | 47.1 [37.7, 58.9] | 72.7 [65.2, 82.3] | 61.9 [52.1, 73.1] | 95.6 [91.3, 99.0] | 83.2 [76.8, 89.4] |
| E popular | 200 | 48.5 [41.1, 56.6] | 64.9 [56.7, 72.9] | 70.2 [61.1, 79.3] | 94.0 [88.1, 98.7] | 83.5 [75.5, 90.5] |
| M canonical | 200 | 57.3 [45.4, 69.3] | 70.3 [61.6, 77.8] | 72.5 [62.8, 81.6] | 88.9 [83.1, 93.3] | 84.9 [78.1, 91.1] |
| M popular | 200 | 42.1 [32.8, 51.8] | 61.2 [51.7, 70.2] | 66.8 [55.1, 78.5] | 97.1 [92.1, 99.8] | 93.5 [86.9, 98.5] |
| L canonical | 200 | 44.4 [33.5, 55.0] | 65.6 [56.4, 74.4] | 61.8 [49.9, 72.8] | 91.2 [82.0, 97.9] | 67.3 [54.5, 80.2] |
| L popular | 200 | 46.6 [36.4, 56.1] | 57.3 [47.1, 67.1] | 72.8 [60.9, 83.7] | 89.6 [80.9, 97.3] | 80.1 [68.1, 90.2] |

- **The QA pass-2 finding holds on v0.9 with a stronger reader.** Gemma's errors are overwhelmingly false yeses: precision ≈ 0.7, recall ≈ 0.9. Pass 2 found precision 0.77 under v0.5.
- **The canonical/popular difference is real but modest.**
  - Gemma's false-yes excess is about 20 pp in canonical works and about 12 pp in popular works.
  - Its locus accuracy is about 9 pp lower in canonical works, worst in L canonical (67%).
  - Plausible mechanism: canonical prose has more narratorial reflection, social comedy and interiority, which Gemma reads as obstacles (most often social or internal; see §2.3).

### 2.2 Locus shares among obstacles (%; C = Claude, G = Gemma)

| subset | material C | material G | social C | social G | internal C | internal G |
|---|---|---|---|---|---|---|
| all | 32.0 [21.9, 42.6] | 26.1 [17.7, 34.8] | 62.1 [51.2, 72.0] | 59.4 [49.1, 69.3] | 5.9 [2.5, 11.2] | 14.5 [8.6, 21.4] |
| era E | 15.6 [9.6, 21.8] | 20.3 [13.4, 26.9] | 77.7 [71.2, 84.3] | 68.7 [62.2, 75.1] | 6.7 [3.0, 10.8] | 11.0 [7.2, 15.9] |
| era M | 25.0 [15.5, 35.7] | 19.3 [11.7, 28.8] | 66.8 [54.0, 77.8] | 65.9 [55.1, 75.8] | 8.2 [3.6, 14.2] | 14.8 [8.4, 22.9] |
| era L | 33.3 [21.8, 46.0] | 27.3 [17.1, 37.7] | 61.1 [48.3, 73.0] | 58.2 [46.3, 69.7] | 5.6 [1.5, 11.6] | 14.5 [7.8, 22.3] |
| canonical | 26.8 [18.6, 35.2] | 19.5 [12.3, 26.9] | 60.4 [52.1, 68.5] | 62.9 [52.8, 72.5] | 12.8 [7.4, 18.5] | 17.6 [11.2, 25.6] |
| popular | 32.6 [21.2, 44.8] | 27.0 [17.6, 36.9] | 62.3 [49.9, 73.6] | 59.0 [47.2, 70.4] | 5.0 [1.2, 11.0] | 14.0 [7.3, 22.0] |
| E canonical | 15.0 [6.1, 22.3] | 11.6 [4.9, 17.4] | 73.7 [67.3, 82.9] | 73.1 [64.1, 83.1] | 11.3 [4.1, 19.4] | 15.4 [6.9, 25.4] |
| E popular | 15.9 [8.7, 24.1] | 24.4 [14.7, 34.0] | 79.4 [70.2, 87.7] | 66.6 [57.3, 74.9] | 4.7 [1.1, 9.6] | 9.0 [4.8, 13.9] |
| M canonical | 22.5 [13.9, 31.5] | 11.0 [5.8, 16.9] | 66.9 [57.4, 75.0] | 69.4 [56.3, 78.3] | 10.6 [6.0, 15.5] | 19.6 [10.7, 31.6] |
| M popular | 25.8 [14.0, 39.7] | 21.6 [12.0, 33.4] | 66.7 [50.1, 81.3] | 65.0 [51.7, 77.1] | 7.5 [1.0, 15.3] | 13.4 [5.8, 23.4] |
| L canonical | 29.5 [18.0, 42.1] | 22.9 [12.9, 33.5] | 56.8 [45.1, 68.2] | 60.0 [46.7, 72.5] | 13.7 [5.7, 21.8] | 17.2 [8.7, 27.8] |
| L popular | 33.7 [21.3, 47.6] | 27.8 [16.9, 39.4] | 61.5 [46.8, 74.2] | 58.0 [44.4, 71.0] | 4.8 [0.5, 11.4] | 14.2 [6.6, 23.1] |

### 2.3 Locus confusion (rows Claude, columns Gemma; raw counts in the sample)

All passages:

| Claude \ Gemma | internal | material | no obstacle | social |
|---|---|---|---|---|
| internal | 37 | 5 | 1 | 17 |
| material | 7 | 83 | 7 | 30 |
| no obstacle | 50 | 47 | 336 | 172 |
| social | 30 | 22 | 34 | 322 |

| | canonical (raw) | popular (raw) |
|---|---|---|
| Claude no → Gemma social / internal / material | 99 / 27 / 16 | 73 / 23 / 31 |
| Claude material → Gemma social | 17 of 65 | 13 of 62 |
| Claude social → Gemma internal | 19 of 198 | 11 of 210 |
| Claude internal → Gemma social | 11 of 39 | 6 of 21 |

- **The largest error cell is Claude "no" → Gemma "social"** (172 raw). This is the QA pass-2 pattern: banter, etiquette, mild discomfort and description read as a social obstacle.
- **Next:** Claude "material" → Gemma "social" (30), and Claude "social" → Gemma "internal" (30).
- **Canonical false yeses lean social and internal; popular false yeses lean material** (adventure description). This is the differential component. It partly cancels in the TF gap, because Gemma's internal over-call is large in both fields.
- Weighted versions of every confusion matrix, by canon and by era, are in `data/work/claude_ref/tables.md`.

## 3. The key question: does Gemma's error bias the TF gap?

TF gap = canonical − popular, era-standardised (pp, 95% CI):

| share | Claude labels | Gemma labels | bias (G − C) | Claude, both-yes set | Gemma, both-yes set | locus-only bias |
|---|---|---|---|---|---|---|
| material | −4.1 [−19.9, +11.3] | −5.8 [−19.2, +6.8] | −1.7 [−15.2, +12.2] | −5.2 [−21.3, +10.9] | −0.6 [−16.4, +14.5] | +4.6 [−9.2, +17.5] |
| social | −4.1 [−19.2, +11.8] | +2.4 [−12.3, +19.1] | +6.5 [−11.1, +22.5] | −3.9 [−19.4, +12.1] | −3.1 [−20.6, +15.3] | +0.8 [−15.0, +18.5] |
| internal | +8.2 [−0.7, +16.2] | +3.4 [−7.3, +15.4] | −4.8 [−16.2, +7.7] | +9.1 [−0.6, +17.9] | +3.8 [−8.6, +16.5] | −5.4 [−18.7, +8.3] |

TF material gap by era:

| era | Claude | Gemma |
|---|---|---|
| E | −0.9 [−13.6, +9.3] | −12.8 [−26.4, −0.8] |
| M | −3.3 [−18.5, +12.1] | −10.6 [−23.5, +0.7] |
| L | −4.3 [−22.5, +13.6] | −4.9 [−20.5, +9.5] |

**Reading.**
- **The TF material gap survives the stronger reader.** It is the same sign and similar size (−4 to −6 pp) under both. The pooled bias is −1.7 pp, small next to its own CI and next to the registered MDE of ≈ 9 pp.
- **Gemma's errors split into two parts that partly cancel.**
  - *Locus-only error* (both-yes set): Gemma compresses the material gap by about 5 pp (−5.2 → −0.6).
  - *Prevalence error* (false yeses with field-specific loci): this pushes the gap back, because canonical false yeses are rarely material.
  - That the two parts cancel is a property of this codebook and model. It is not guaranteed under the DSL-corrected estimator, which corrects both.
- **The internal component is attenuated under Gemma** (+3.4 vs +8.2 pp). Claude's internal gap nearly excludes 0. On this evidence, the TWO FICTIONS "inward canon" signal is, if anything, stronger under a better reader. Gemma over-calls internal in popular fiction (14% vs 5%) and so narrows the contrast.
- **The era breakdown shows where differential error lives: the early and middle eras.**
  - Under Gemma, the E and M material gaps are −13 and −11 pp. Under Claude they are −1 and −3 pp.
  - In E, the cause is that Gemma inflates material in E popular: Gothic and adventure description becomes material obstacles.
  - In M, the cause is that Gemma deflates material in M canonical (11% vs 23%).
  - These eras carry only 14% of the standardisation weight, so the pooled effect is small. **Any era-stratified TF result (TF by era, or the H1|canon × era interaction) would be biased by raw Gemma labels toward a larger early canon gap.**

**Verdict on TF.** Raw Gemma labels do not manufacture the TF material gap, and they do not inflate it materially; the pooled bias is about −2 pp. The main risk is in the per-era breakdowns, not in the pooled primary estimand. The expert-anchored DSL correction in the Confirmation design addresses exactly this kind of differential error, and nothing here argues against it.

## 4. Era-dependent error and H1

L − E contrast (pp):

| share | Claude | Gemma | bias |
|---|---|---|---|
| material | +17.7 [+3.9, +31.5] | +7.0 [−4.9, +20.1] | −10.7 [−22.1, −0.8] |
| social | −16.6 [−31.4, −1.6] | −10.5 [−24.0, +2.9] | +6.1 [−5.6, +18.6] |
| internal | −1.1 [−7.0, +6.1] | +3.5 [−4.8, +12.6] | +4.6 [−4.8, +14.3] |

- **Gemma's error is era-dependent, and it attenuates H1.**
  - Gemma's material share is too high in E (+4.7 pp) and too low in L (−6.0 pp), so the material rise from E to L shrinks by about 11 pp.
  - It also adds an internal rise (+3.5 pp) that Claude does not see.
- **This is the opposite of the prereg §7 scenario ("naive labels exaggerate H1").** Naive Gemma labels here bias H1 toward a *smaller* outward (material) shift.
- **Consequences:**
  - (a) A raw-label H1 null on Discovery should not be read as evidence of no shift.
  - (b) The registered DSL correction matters for H1 as much as for TF.
  - (c) The E-era QA gap flagged in pass 2 (w01 had about 10 early items) is now partly filled. In E, Gemma's precision is 68% and its errors are mostly false social/material yeses on description.
- **Claude's own E → L material rise (+18 pp) is large.** It rests on 400 E passages from 38 popular and 11 canonical author groups, and it is a reference reading, not an estimate of the registered H1. Treat it as a hypothesis for the human audit.

## 5. Qwen 9B (alt_label) vs Claude

Computed on the Qwen sub-strata only (446 items with a Qwen label), weighted to the Qwen-covered part of each cell.

| subset | n | Claude rate | Qwen rate | precision | recall | locus acc. |
|---|---|---|---|---|---|---|
| all | 446 | 53.7 [45.9, 61.5] | 30.1 [23.4, 37.0] | 89.7 [80.6, 97.4] | 50.3 [39.8, 60.4] | 84.7 [73.9, 92.9] |
| canonical | 196 | 50.9 [41.9, 59.6] | 29.7 [23.1, 37.1] | 82.0 [69.9, 91.5] | 47.8 [38.1, 56.7] | 76.5 [64.9, 87.9] |
| popular | 250 | 54.1 [45.2, 62.9] | 30.2 [22.7, 37.7] | 90.7 [80.4, 99.5] | 50.6 [38.9, 62.3] | 85.7 [73.7, 94.8] |

| TF gap, pp | Claude | Qwen | bias |
|---|---|---|---|
| material | +5.7 [−8.9, +21.0] | +20.1 [+3.3, +36.9] | +14.4 [−1.4, +30.8] |
| internal | +5.5 [−5.5, +17.2] | −10.1 [−22.6, +2.0] | −15.7 [−29.4, −1.9] |

- **Qwen is the mirror image of Gemma.** It under-labels, recalling only half the obstacles.
- **Its misses are not random.** It drops material obstacles in popular works most of all: material-share error is −14.0 pp in popular works and −0.6 pp in canonical works. Its internal assignments run the other way.
- **Under Qwen labels, TF would flip sign on material (+20 pp) and on internal (−10 pp).**
- **The Qwen sub-sample is a different population from the full sample.** Claude's gap is +5.7 pp on it, against −4.1 pp on the full sample, and it rests on 446 items. The cross-reader comparison is what matters here.
- **Recommendation:** in the multiverse appendix (prereg §6), report Qwen as a *weak* reader. Do not present Gemma–Qwen agreement or disagreement on TF as evidence about the construct.

## 6. Caveats

- **Claude is an LLM reference.**
  - Its 0.78/0.85 κ is self-consistency. Agreement with humans is unmeasured.
  - It may share blind spots with Gemma: both are LLMs reading the same codebook.
  - Its internal share (≈ 6%) is below the earlier human-style reviewer reference (11–12%).
- **Not the registered estimator:** passage-level, era-standardised, no year spline, no genre, no DSL.
- **The sample is small for some cells.**
  - E canonical has 11 author groups. CIs on per-era-by-canon quantities are wide.
  - Pooled numbers are dominated by L popular through the design weights.
- **The frame was a snapshot while Gemma labels were still syncing (frame 46,684 passages).** Late-arriving shards are not represented. Inclusion probabilities are relative to the snapshot.
- **Blindness:** agents saw no metadata. Some passages are from famous works (Austen, Brontë), and an agent may recognise them; the codebook forbids using outside knowledge.
- **The human/expert audit remains the registered correction.** Use these numbers to anticipate it, not to adjust estimates.

## 7. Exemplars
- 20 passage-card exemplars (10 canonical, 10 popular; every era and locus covered) are in `docs/qa/tf_exemplars.md`. They are drawn from the passages Claude rated "vivid", with quotes verified verbatim.
