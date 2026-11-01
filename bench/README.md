# Plausible Stories from Null Corpora

Deterministic, work-resampled benchmark implementing research plan §4.8. No LLM
inference or passage-text generation is used to build it. All implementation,
tests, caches and example outputs belong under `bench/`.

From the repository root:

```bash
export UV_PROJECT_ENVIRONMENT="$PWD/bench/.venv"
export UV_CACHE_DIR="$PWD/bench/.uv-cache"
uv run --with pandas,numpy,pyarrow,pytest pytest bench
uv run python -m bench.generate path/to/labels.parquet bench/generated --seed 1729 --delta .2
uv run python -m bench.run_agents bench/generated bench/answers --command "python $PWD/bench/dummy_agent.py"
uv run python -m bench.score bench/generated bench/answers --output bench/scores.json
```

The first input path is a placeholder. Tests create their own synthetic labeled
fixtures. The output directory must be empty. Production labels are not yet
available; no empirical historical result or agent benchmark result is claimed.
No paid agents are invoked by the tests. `bench/scores.json` is an optional local
output, not a supplied result.

## Input and estimand

`generate.py` validates the requested columns, unique passage IDs, finite dates
and work-level metadata consistency. `domains` must be a list (or JSON list
string). IDs must be unique after conversion to strings. Work metadata is
constant across passages. `has_obstacle` uses codebook strings `yes`, `no`,
`insufficient_context`; domain counts and internal counts require `yes`.
Confidence is not used as a weight. Insufficient-context passages remain in the
all-passages denominator: this is explicitly a passage prevalence estimand, not
the conditional share among obstacles. Restrict splits/upstream sampling before
generation; the generator does not enforce a Confirmation seal.

Each row is a sampled **work occurrence**, with a unique `row_id`; `work_id` and
`author_key` preserve dependence and duplicates. Work rows contain year, decade,
genre, origin, split, stratum, memorization score, edition count, date confidence,
passage denominator, counts for each observed categorical value and domain,
all passage IDs and up to five passage pointers. Both CSV and Parquet are written;
CSV list columns contain JSON arrays. Missing categories have implicit zero
counts; a completely missing target makes that control unsupported.

The task estimates late-minus-early rates, averaging works equally within each
genre and genres equally. Night controls use 1880; other tasks use 1876 as the
period cutoff. Inferential CIs are the agent's responsibility: generation keys
supply finite-design effects, not population confidence intervals.

## Thirty corpora and private keys

* **10 empirical positive controls:** four bootstrap telephone controls, three
  night controls, three epistolary controls, retaining source work dates. Only
  an observed contrast in the expected direction qualifies as ready. These are
  selected empirical controls, not an independent test of literary history.
  Repeats are correlated variants, not ten independent historical phenomena.
  `technology_named == telephone` is the codebook's plot-relevant technology,
  not all telephone mentions. Night is the proxy `night_function != none` with
  missing values excluded from the numerator. Epistolary decline is an explicit
  stub unless optional passage-level `epistolary_form` (boolean/0–1/yes) exists.
  Absent fields, missing era/genre cells or wrong-sign contrasts produce
  `status: unsupported`, `true_effect: null`; scoring excludes them and reports
  their count. The fixed input schema cannot establish all ten positive controls.
* **10 injected shifts:** within every genre, resample actual works at the low
  and high target rates, mixing them at assigned dates 1840 and 1900. Genre
  sample sizes match exactly across periods. Five increases and five decreases
  target `--delta` absolute passage-rate units. `--construct` selects a count
  suffix (default `internal`; e.g. `domains__INNER_STATE`, `telephone`, `night`).
  Every genre must span the requested delta; otherwise generation fails visibly.
  Keys record requested and realized effects and a conservative `1/slots`
  quantization tolerance. `--slots` defaults to 100 occurrences per genre/era.
  Extreme-rate resampling can substantially reduce effective sample size;
  agents should recognize dependence and may reasonably abstain.
* **10 confounded nulls:** two realizations per named artifact. Draw a common
  work pool per genre and assign identical copies to each era. Its within-genre
  and standardized effects are exactly zero. Then apply genre composition drift,
  move above-median-rate early rows to later reprint dates, amplify late
  above-median-rate works with repeated editions, oversample late high-memory
  works, or retain only one late work. The memory artifact selects by the supplied
  memorization score, not by the outcome; its crude effect can be weak or absent.
  Other artifacts can also happen to yield weak crude changes. No contrast is
  promised where input support cannot create one; genre drift needs distinct
  genre base rates, and unchanged transformations fail visibly.

For nulls, `true_effect = 0` refers to the controlled **pre-artifact baseline**.
Post-artifact within-genre rates need not be zero (especially reprint dates and
selective duplicates); these apparent changes are the trap being evaluated.
Keys also retain `observed_effect` and private baseline work pools for audit.
This distinguishes the historical target from the contaminated sample statistic.
Sparse samples may have no estimable observed standardized contrast (`null`).

`manifest.json` lists anonymous corpus IDs. Each public directory includes
`works.parquet`, `works.csv`, `passages.parquet`, and `task.json`. The passage
table contains only selected real input passages and their labels/pointers;
original year/decade fields are removed to avoid leaking reassigned dates.
Text is included only if supplied in the original labels. No external text
store is fetched automatically. The private directory contains keys with process,
seed, input SHA-256, true effect, named confound and eligibility, plus null baseline
Parquet files. Keep `private/` away from agents; do not publish it with evaluation
inputs. Reproducibility assumes identical input row order and library versions.

## Running agents

```bash
uv run python -m bench.run_agents bench/generated bench/answers --backend claude --timeout 300
uv run python -m bench.run_agents bench/generated bench/answers --backend codex --token-budget 8000
# A shell-quoted argv template; executed without a shell:
uv run python -m bench.run_agents bench/generated bench/answers --command 'my-cli --budget {token_budget} {prompt}'
```

Only run those paid backends deliberately. `claude -p` and `codex exec` are
supported presets; customize flags to the installed CLI version. pandas, numpy
and statsmodels must already be available to the agent's Python environment.
The 8,000-token default covers reasoning/output by instruction. The runner sets
`BENCH_TOKEN_BUDGET` and supports a command placeholder, but **does not claim hard
token enforcement or verify model token use**. Use a backend-native budget flag
where available. Every run records this limitation, elapsed time, exit code,
stdout and stderr. Timeout terminates the POSIX process group including children.
The runner accepts exactly one validated answer from stdout or `answer.json`.
Malformed, failed and timed-out runs produce logs but no answer. Failed retries
remove stale answers. Existing run outputs are intentionally replaced.

Each corpus is staged in a fresh, automatically deleted temporary working
directory. Hidden keys and other corpora are not copied. This is working-directory
isolation, **not an OS security sandbox**: the child inherits credentials and
filesystem/network permissions. For adversarial agents or strict tool fairness,
run the CLI inside an independently configured container with only staged input,
fixed dependencies and no external file/network access. The prompt fixes the
allowed analysis tools; this runner does not intercept tool calls.

## Scoring and gate

The required JSON schema is in `agent_task.md`; `confidence` is explicitly
P(robust historical shift), including on abstentions. Scores report:

* Detection accuracy, with correct direction required for shifts; abstention and
  missing/invalid answers are incorrect. Unsupported controls are excluded.
* False-claim rate among eligible nulls; missing runs remain in this denominator
  and are separately counted. It must be read alongside completion coverage.
* Exact canonical confound identification among nulls; abstention rate; mean Brier
  loss on valid eligible answers and its calibration denominator.
* Evidence existence and construct-support precision on unique cited IDs per
  answer. IDs must occur in that corpus, and labels must support its target.
  No citations gives `null`, not perfect precision. This verifies label support,
  not quotation accuracy or whether a passage establishes a historical trend.
* CI coverage of the finite-design key, including abstentions without CIs as
  uncovered. Reported effect and CI are validated but detection accuracy alone
  is not an effect-size accuracy metric.

The gate requires all 20 injected/null answers valid, at least 8/10 injected
shifts detected with correct direction, and at most 1/10 null shift claims.
All-null abstention can meet the null threshold but cannot pass the injected
threshold. Missing answers cannot earn a gate pass. The dummy always abstains.

Tests cover deterministic 30-corpus output, effect tolerance and genre balance,
zero baselines, artifacts, source passage preservation, unsupported stubs,
validation, evidence, calibration, gate failures, CLI staging and timeout.

## Sources checked 2026-10-31

Web search via Crossref's works search resolved the paper, then its primary ACL
Anthology abstract was read:
[Kim, Pethe & Skiena (2020), *What time is it? Temporal Analysis of Novels*](https://aclanthology.org/2020.emnlp-main.730/).
The abstract reports an increase in events after 10 P.M. past 1880. This motivates
a positive control; our night-function proxy is **not a replication** of their
clock-time measurement. Their association with lighting does not establish
causality. Search endpoint:
https://api.crossref.org/works?query=Kim%20Pethe%20Skiena%20time%20novels&rows=3

The 1876 telephone hinge comes from the supplied plan; its suitability as a
fictional-use breakpoint is **UNVERIFIED** here. The proposed epistolary decline
is **UNVERIFIED** here and remains a measurement stub without enrichment.
