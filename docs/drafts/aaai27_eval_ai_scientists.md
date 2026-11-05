# Plausible Stories from Null Corpora: Do AI Research Agents Overclaim Literary-Historical Trends?

*AAAI-27 Workshop on Effective and Efficient Evaluation for AI Scientists. Resource/artifact track (2–4 pages).
Anonymous submission. DRAFT v0.2 (2026-11-05). Markdown source; convert to the AAAI-27 two-column kit.*

> **Drafting notes (delete before submission).** Every number comes from `bench/runs/2026-11-04/metrics.json`
> (also `metrics_table.md`, `rows.csv`), produced by `python -m bench.analyze`. Figures: `bench/figs/*.pdf`.
> Body ≈ 2,590 words incl. captions (trim ~100 if the two-column layout overflows 4 pages). Still to do before submission: (1) blind human adjudication of confound naming on the
> 60 null-corpus rationales; (2) move references into the AAAI BibTeX style; (3) prepare an anonymized artifact
> mirror without paths or usernames (run logs contain local paths).

## Abstract

AI "scientist" agents are increasingly asked to analyze data and report findings. Archives of digitized
literature are a hard test: almost any trend can be told as a plausible story, and archive composition changes
with date. We release a blinded benchmark of 30 corpora built from real LLM passage labels for 6,766 nineteenth-
and early-twentieth-century novels. Ten corpora contain injected ±5 percentage-point (pp) shifts. Ten are
*confounded nulls*, in which dates are assigned through archive artifacts (genre drift, reprint dating,
edition/canon selection, prolific authors, origin drift) but are independent of the outcome by design. Ten replay
the real dates. We ran a frontier coding agent (180 sessions: 30 corpora × 3 repeats × 2 prompts) and a 30-line
deterministic estimator. The agent detected 100% of injected shifts and falsely claimed a shift on 10% [0, 27] of
null runs. These are exactly the estimator's numbers, at $0.115 per corpus. Its stated probabilities were well
calibrated (Brier 0.059 vs. 0.199). However, its "alternative explanations" were boilerplate: it named each
artifact as often in corpora without it as with it. An explicit confound-check instruction made naming specific
for one artifact (prolific authors: 100% vs. 10%) and eliminated shift claims on the real-date replays (63% → 0%),
but did not change the false-claim rate. We argue that evaluations of AI scientists should score claims against
design-based truth, report a non-agentic floor, score diagnostics rather than prose, and treat the harness as part
of the measurement.

## 1 Problem: AI scientists and data-driven historical claims

AI-scientist systems are now evaluated on end-to-end, data-driven discovery. Benchmarks check whether an agent
recovers a reference hypothesis or answer (Majumder et al. 2025; Gu et al. 2024; Liu et al. 2025), and some
systems add sequential falsification (Huang et al. 2025). Cultural analytics is a demanding domain for this
workflow. Claims like "fiction turned toward X after 1876" are cheap to compute from labeled corpora (Underwood,
Bamman, and Lee 2018), LLM labels are increasingly used as the measurements (Bamman et al. 2024), and a fluent
literary-historical narrative is almost always available. But digitized archives are not samples of what was
written or read. Which genres, editions and authors survive changes with date, so a trend in the archive can be a
trend *of* the archive.

We ask a narrow, measurable question: **given a corpus whose generating process is known, does an agent claim a
historical shift that the design says is absent, and does it detect the artifact that could produce one?** We
contribute (i) a blinded, leak-audited benchmark of 30 corpora built from real labels, with design-based truth;
(ii) scoring for claims, calibration, abstention, confound naming and evidence, plus process logs; (iii) 180 real
agent sessions under two prompts, a deterministic reference, and measured token and dollar costs; and (iv) four
requirements for evaluating AI scientists on observational data.

## 2 Benchmark design

**Source labels.** We use 15,744 passage labels from the discovery split of a corpus of English-language novels
(1800–1925) in a public-domain archive. A pinned open-weight LLM labeled each passage for whether it contains a plot
obstacle and, if so, the obstacle's domains (e.g., distance/travel, social rank). A sealed confirmation split is
never read. We sample one labeled passage per work, which gives a fixed panel of 6,766 works by 1,669 authors in 8
genres, with 123 distinct years. **Every corpus contains exactly this panel. Only the assignment of real
publication years to works differs.** All corpora share one target, the rate of distance/travel obstacles, and one
estimand: the late-minus-early (cutoff 1876) rate, with equal weight per genre and per work within genre.

**Three arms, 10 corpora each.**
*Real-date replays* keep the observed dates (+2.5 pp). This contrast failed our pre-set screen (|effect| ≥ 3 pp and
an author-cluster bootstrap interval excluding zero; lower bound −0.002 pp). On a snapshot with half as many labels
it had been +3.7 pp. The replays are therefore **reported descriptively, not scored**.
*Injected shifts* permute the real year multiset within genre and assign works to eras with disjoint
binary-outcome quotas. The realized standardized effects are +5.2 pp (5 corpora) and −5.0 pp (5). No text or label
is edited.
*Confounded nulls* (2 per artifact) assign the sorted real years by a noisy rank of a measured nuisance variable.
Dates are then associated with the nuisance but, by construction, not with the outcome, so the design-expected
effect is zero. The artifacts are controlled analogues of archive contamination. In **genre drift**, late periods
over-represent high-rate genres. In **reprint dating**, low date-confidence works are pushed late. In
**edition/canon selection**, many-edition works are pushed late. In **prolific authors**, works by prolific authors
are pushed late. In **origin drift**, national origin shifts across eras. Each artifact leaves a visible trace in
the public metadata. For example, the correlation between author productivity and year is 0.26 in the
prolific-author nulls against −0.11 in the real panel; the low-confidence share rises 18 pp across eras in the
reprint nulls; and genre drift moves the crude contrast to +4.3 pp. Duplicated editions and sparse decades were
excluded because both change corpus size or year coverage, which reveals the arm.

**Blinding and audit.** Public files hold opaque work, author and passage IDs (re-keyed per corpus), years,
genre, origin, edition count, date confidence, and categorical labels. There is no text, title, name or source ID.
A five-fold random forest on 16 structural and storage features (sizes, author counts, year summaries,
missingness, file bytes) classifies the arm at chance (0.333). A deliberately restored size leak is detected at
> 90%. Answer keys never enter an agent's directory.

**Scoring.** A run is *correct* on an injected corpus if it claims a shift in the true direction, and on a null
if it answers `no_shift`. A *false claim* is a `shift` answer on a null; abstention is neither. Agents report
P(robust shift) on every corpus, which we score with Brier loss. *Confound naming* is a documented keyword rule
over named confounds and rationale. We also compute its *specificity*: the naming rate in the artifact's own arm
versus all other corpora. *Evidence validity* is the share of cited passage IDs whose labels support the
construct. 95% CIs are two-stage bootstraps that resample corpora, then repeats within corpus (5,000 draws). The
artifact's gate requires ≥ 8/10 injected detections and ≤ 1/10 null claims.

## 3 Agents and runs

We ran a coding-agent CLI non-interactively (`claude -p`, CLI 2.1.318, its default model `claude-opus-5-5`).
Customizations, memory and MCP were disabled; shell and file tools were enabled and web tools disallowed. Each
session started in a fresh directory holding only the four public files and the prompt, with a Python environment
(pandas, numpy, statsmodels) on the path. We ran 3 independent sessions per corpus (the CLI exposes no sampling
seed), ≤ 6 concurrently, with a 20-minute timeout. The prompt asks for the estimand, a 95% CI, coverage,
alternative explanations, and abstention "when the data do not support" a claim. It names no confound. In the
**+confound check** condition one paragraph is appended. It tells the agent to test whether the assigned years
are associated with each metadata column, to check that the contrast survives adjustment and restriction to
well-dated works, and to claim a shift only if it does.

*Harness incidents.* The first base-prompt sessions shared the host's temporary directory. Some sessions wrote
scratch files to fixed shared paths, and some hit a temporary-file quota exhausted by unrelated jobs. By a rule
fixed before reading their answers, we reran all 11 affected sessions in a bubblewrap sandbox. The sandbox gives
each session a private `/tmp` and masks the repository (including the keys) and the other sessions. All
confound-check sessions ran sandboxed, and 8 that failed with gateway HTTP 503 errors were rerun. No session's tool
calls read outside its own directory. A second agent backend was planned, but its shared endpoint had no
capacity during the run window.

**Deterministic estimator.** As a non-agentic reference, a 30-line script computes the estimand and a 1,000-draw
author-cluster bootstrap interval. It claims a shift iff the interval excludes zero and performs no confound
checks. Its "P(shift)" is the two-sided bootstrap mass, 2·max(p, 1−p) − 1.

## 4 Results

**Table 1.** Mean [95% CI] over corpora; 20 scored corpora (10 injected, 10 null) × 3 repeats.

| Metric | Agent | Agent + check | Estimator |
|---|---:|---:|---:|
| Injected shifts detected, % | 100 [100, 100] | 100 [100, 100] | 100 [100, 100] |
| False shift claims on nulls, % | 10 [0, 27] | 10 [0, 30] | 10 [0, 30] |
| Abstention (scored corpora), % | 10 [0, 23] | 7 [0, 18] | 0 |
| Brier loss | 0.059 [0.030, 0.095] | 0.050 [0.024, 0.087] | 0.199 [0.078, 0.337] |
| Confound "identified" (keyword), % | 60 [30, 87] | 83 [60, 100] | 0 |
| Shift claims, real-date replays, % | 63 [40, 83] | 0 [0, 0] | 20 [0, 50] |
| Cited evidence IDs valid, % | 100 (n = 557) | 100 (n = 532) | — |
| USD / corpus | 0.115 [0.107, 0.123] | 0.114 [0.109, 0.120] | ≈ 0 |
| Tokens / corpus, input / output (k) | 58.6 / 3.3 | 55.2 / 3.3 | — |
| API minutes / corpus | 0.76 [0.62, 1.08] | 0.57 [0.54, 0.60] | 0.01 (wall) |

**The agent is a competent statistician, and no more.** All 180 sessions returned schema-valid answers. In both
conditions the agent detected every injected shift in the right direction. Its reported effects matched the
realized ones to within 0.1 pp, and every CI covered the truth. Its false-claim rate on nulls (10%) equals the
estimator's (Fig. 1). The false claims fall almost entirely on corpus 9, an edition-selection null whose realized
standardized effect (+2.6 pp) the estimator also calls significant. The only other false claim is one session on
the −2.6 pp prolific-author null. Neither prompt led the agent to reject corpus 9, even though its dates were
assigned by edition count. The confound-check sessions named edition count as an alternative in only 1 of 6 runs.
The false-claim rate is thus set by the finite-sample noise of the nulls, not by the artifacts. A gate of
≤ 1/10 null claims is passed by both the agent (2 of 3 repeats; 3 of 3 with the check) and the estimator.

**Stated probabilities were informative.** P(shift) tracks evidence (Fig. 2, left). It averaged 0.81 on injected
corpora and 0.23 on nulls, and rose to 0.4–0.6 only on the nulls whose realized effect neared ±2.6 pp. The agent's
Brier loss (0.059) is less than a third of the estimator's p-value proxy (0.199). The agent rarely abstained on
scored corpora (7–10%). Instead it hedged through P(shift), which is what a proper scoring rule rewards.

**Alternative explanations were boilerplate.** Every base-prompt answer listed 5–6 alternatives (5.9 on nulls,
6.3 on injected shifts). The keyword scorer credits the agent with identifying the confound in 60% of null runs,
but this is not identification. Genre composition and date uncertainty were named in 100% of *all* corpora, and
origin in 83% of its own arm against 82% elsewhere. Prolific authors were named in 17% of their own arm against
23% elsewhere, and edition selection never in its own arm. Naming had no specificity: the agent's caveats do not
depend on the corpus it is given.

**An explicit instruction changes process, not the headline.** With the confound-check paragraph, the agent
named "author productivity imbalance" in 100% of prolific-author runs against 10% elsewhere. That is the one
artifact with a strong metadata trace, and its single false claim there disappeared. Keyword "identification" rose
to 83%. Because genre, date and origin caveats remained universal, most of the rise is not specific. The
false-claim rate was unchanged (10%), and sensitivity stayed at 100% with no extra cost ($0.114 per corpus). The
largest effect fell on the unscored real-date replays. Shift claims there dropped from 63% to 0% (all abstentions;
mean P(shift) 0.55 → 0.37). The agent cited real date-confidence and edition-count imbalances across the cutoff,
and these are genuine features of the archive. The estimator claimed a shift on 2 of the 10 replays. So the
"real" +2.5 pp travel trend is exactly the case where a prompt flips an AI scientist's published conclusion.

**Cost.** One session cost $0.115 on average (58.6k input tokens, mostly cached context; 3.3k output tokens;
about 4.5 tool calls), or 0.6–0.8 API minutes. The whole study, including reruns and the smoke test, cost $22.25
for 192 sessions. The estimator gives the same detection and false-claim rates in about a second of CPU (Fig. 2,
right).

**Figure 1.** False shift claims on confounded nulls by artifact (2 corpora × 3 repeats each; whiskers are 95%
two-stage bootstrap CIs, which are wide with 2 corpora per type). Tick labels give each artifact's largest
realized |standardized effect|. False claims track the size of the random fluctuation, not the artifact.
[`bench/figs/false_claims_by_confound.pdf`]

**Figure 2.** Left: stated P(shift) per session against the corpus's realized standardized effect (hollow = null,
filled = injected or real-date replay at +2.5 pp). Right: balanced accuracy on the 20 scored corpora against API
cost per corpus. [`bench/figs/accuracy_vs_cost.pdf`]

## 5 What an evaluation of AI scientists should require

**R1. Design-based truth, with sensitivity and false claims together.** Each corpus needs a known generating
process, and both rates must be reported jointly. Either alone is gameable: an always-abstaining dummy makes zero
false claims and fails our gate.

**R2. A non-agentic floor at matched budget.** Our 30-line estimator matched the agent's detection and false-claim
rates at almost no cost. Without it, the agent's 10% false-claim rate looks like an agent failure, when it is the
irreducible error of a calibrated test on finite nulls. An AI-scientist score is informative only relative to what
a competent script achieves on the same data.

**R3. Score diagnostics, not prose.** Lists of alternative explanations should be scored for *specificity*: is an
artifact named more often where it is present than where it is absent? Our keyword scorer reports 60–83%
"identification" that is mostly boilerplate. Benchmarks should require the diagnostic itself as structured output
(e.g., a nuisance-by-era table and an adjusted estimate) and check it against the generating process. The
confound-check prompt shows the agent *can* run such diagnostics, but it used them selectively. It never examined
edition counts closely enough to reject the one null it got wrong.

**R4. First-class abstention and calibration.** Ask for P(claim true) on every task, abstentions included, and
score it with a proper rule. Calibrated hedging, not refusal, is the target. Prompt-induced abstention on real,
messy data (63% → 0% claims on the replays) should be reported as a finding about the agent's decision rule, not
hidden in an accuracy number.

**R5. The harness is part of the measurement.** Concurrent sessions on one host interfered through shared scratch
paths and an exhausted temporary-file quota. One agent honestly abstained because "the execution environment
failed". Gateway outages produced invalid answers. Evaluations should isolate sessions at the OS level, log tool
calls, and report environment failures separately from agent errors, under a rerun rule fixed in advance.

## 6 Limitations

*Weak, mostly statistical traps.* Keeping the panel and year histogram identical across arms is what defeats
the structural classifier, but it also limits how far an artifact can move the standardized estimand.
Null-corpus "signal" is mostly permutation noise (|Δ| ≤ 2.6 pp), so even a calibrated test has a false-claim floor
near 1/10. Stronger artifacts that preserve these invariants, e.g., nuisance-sorted dates within genre, should be
designed before more agent outcomes are read.
*No verified positive.* The empirical contrast failed screening, so sensitivity rests on ±5 pp injected shifts,
which turned out to be easy. Smaller injected effects are needed to separate methods. The 10 replays share one
dated panel and are not independent.
*One agent, one model, few repeats.* We report one CLI with its default model, 3 sessions per corpus, and 2
corpora per artifact. Per-artifact CIs are therefore wide. The second backend was unavailable.
*Heuristic confound scoring.* Keyword rules need blind human adjudication, which is planned for the release.
*Model labels.* The construct is itself an LLM label. Labels are fixed across arms, so design-based truth is
unaffected, but the replays carry no substantive literary-historical claim.
*Isolation.* Early base sessions were not sandboxed. Affected sessions were rerun by rule, and no session read
outside its directory, but an OS sandbox should be used from the start.
*Licensing.* Source dates come from a non-commercially licensed catalogue. The release ships the generator,
opaque IDs, saved agent outputs and scores, and users regenerate corpora locally.

## AI-use disclosure

Passage labels were produced by an open-weight LLM. The evaluated agent is a commercial LLM agent. Benchmark code,
experiment orchestration and a first draft of this text were produced with LLM coding assistants under the
authors' direction. The authors checked all reported numbers against the released outputs and take responsibility
for the content.

## References (keys in `research/lit/refs.bib`)

Bamman, D.; Chang, K. K.; Lucy, L.; and Zhou, N. 2024. On Classification with Large Language Models in Cultural
Analytics. CHR 2024. `bamman2024classification`
Gu, K.; et al. 2024. BLADE: Benchmarking Language Model Agents for Data-Driven Science. Findings of EMNLP.
`gu2024blade`
Huang, K.; Jin, Y.; Li, R.; Li, M. Y.; Candès, E.; and Leskovec, J. 2025. Automated Hypothesis Validation with
Agentic Sequential Falsifications. ICML. `huang2025popper`
Liu, H.; Huang, S.; Hu, J.; Zhou, Y.; and Tan, C. 2025. HypoBench. arXiv:2504.11524. `liu2025hypobench`
Majumder, B. P.; et al. 2025. DiscoveryBench: Towards Data-Driven Discovery with Large Language Models. ICLR.
`majumder2025discoverybench`
Underwood, T.; Bamman, D.; and Lee, S. 2018. The Transformation of Gender in English-Language Fiction. Journal of
Cultural Analytics 3(2). `underwood2018gender`
