# Plausible Stories from Null Corpora

A blinded, work-level benchmark built from **Discovery-only** labels. Generation
and the dummy pilot require no model inference. Everything produced by these
commands, including caches, belongs under `bench/`. Run from the repository root:

```bash
export UV_PROJECT_ENVIRONMENT="$PWD/bench/.venv"
export UV_CACHE_DIR="$PWD/bench/.uv-cache"
uv run --with pandas,numpy,pyarrow,pytest,duckdb,scikit-learn pytest bench -q
uv run --with pandas,numpy,pyarrow,duckdb,scikit-learn python -m bench.pilot
```

`bench.pilot` runs the read-only adapter, generates 30 corpora, audits structural
leaks, runs the dummy on all 30, and scores its answers. Its output directory
(`bench/pilot/`, ignored by Git) must be empty. See [pilot_report.md](pilot_report.md)
for actual measurements, retained/dropped controls, and paid-run planning.
No paid agents have been run. Do not redistribute source dates without checking
their licence; generated pilot data and identity mappings are local artifacts.

## Input and sampling

`prepare.py` attaches `data/work/ald.duckdb` **READ_ONLY** to an in-memory DuckDB
connection. It selects valid, non-twin, error-free `stage='label'` results whose
pin starts `41ca3c7d`, retaining the latest valid result per passage. It joins
`works.parquet`, `genre.parquet`, and `passages.parquet` for identifiers and
sampling metadata, requiring Discovery on both works and passages. The earliest
PG identifier breaks work-edition ties deterministically. No source is modified.
No quotes, summaries, titles, or raw text enter the adapter output.

`generate.py` validates the adapter schema (the `REQUIRED` constant), finite
metadata, unique passage IDs, within-work metadata consistency, Discovery split,
and integer dates in 1800–1925. Domains must be lists or JSON lists. Source
passages may have different strata. It samples **one real labelled passage per
work without replacement**, then uses that same fixed panel in every arm.
Consequently, every corpus contains exactly the same number of unique works,
authors, passages, and labels, with the same dependence structure and missingness.
This changes the earlier all-passages-per-work design: the estimand is now the
prevalence in the sampled one-passage-per-work panel, standardized across genres.
Confidence does not weight observations. `insufficient_context` stays in the
passage denominator; domain/internal counts require `has_obstacle='yes'`.

Every public year is a real source publication year. Empirical controls retain
source dates; synthetic corpora **permute the panel's complete empirical year
multiset**. All arms therefore share an exactly matched, many-year distribution,
including the naturally small early-era sample. Each work appears exactly once,
with one date. There are no 1840/1900 placeholders or repeated work occurrences.
`--slots` was removed: size is determined by the fixed source panel, not the arm.

## Controls and finite-design truth

* **10 empirical positive replays.** Candidates are fixed in `CANDIDATES`:
  social-rank, communication, travel, telephone, night-function, and internal
  obstacle rates. A candidate must have an absolute standardized contrast
  **≥ 3 percentage points**, both eras in every genre, and a 400-draw
  author-cluster bootstrap 95% interval excluding zero. Weak/missing candidates
  are dropped; generation fails if none qualify. `--construct` can require a
  particular candidate; `--minimum-effect` sets the size threshold. The largest
  qualifying absolute effect is selected. Both directions qualify: these are
  **exploratory empirical contrasts**, not verified causal claims or confirmation
  of an expected literary trend. Screening intervals are descriptive and do not
  correct for candidate selection. Ten replays of the same dated panel receive
  independent opaque IDs/orderings; they are **not independent phenomena** and
  must not be pooled as ten independent sensitivity trials.
* **10 injected shifts.** Five increases and five decreases in the selected
  target (`--delta .05` by default). Disjoint binary-outcome quotas within each
  genre approximate the requested shift, while preserving that genre's actual
  early/late sample sizes and years. Each key records the realized finite-panel
  effect and a bound on rounding error. Infeasible shifts fail before writing
  output. Passage text and labels are never invented or relabelled.
* **10 confounded nulls.** Two nuisance-associated date permutations for each of
  genre composition, uncertain dating/reprints, edition selection, prolific
  authors, and origin composition. The controlled pre-artifact process randomly
  permutes dates within genre, independently of outcomes, so its **expected**
  standardized effect is zero. Finite random baselines fluctuate; keys record
  their actual effects and the zero expectation separately. The artifact assigns
  sorted source years by a noisy nuisance rank, preserving every work once and
  the global year histogram. These are controlled analogues of contamination,
  not claims that the measured source metadata caused a historical effect.
  Apparent standardized/crude effects may be weak; generation does not promise
  a strong trap. Inspect private observed effects before choosing a full study.

Repeated-edition copies and memory/sparse-size artifacts were removed: repeated
copies violate the one-work-once design, memorization was unmeasured, and corpus
size/year coverage must not reveal the arm. Edition counts remain measured
source metadata; memorization placeholders are **never exported or used**.

**Every arm uses the same selected construct and cutoff (1876).** Task target,
numbering, and file layout cannot reveal which arm is being evaluated. Specs are
shuffled before anonymous corpus numbers are assigned. Positive replay truth is
the observed source-date contrast; injected truth is the realized quota effect;
null truth is zero under the pre-artifact randomization process. These are
finite-design/control targets, not population confidence intervals.

## Blinding and leak tests

Public files are `works.parquet`, `works.csv`, `passages.parquet`, and `task.json`.
Allowlisted work metadata are opaque work/author IDs, assigned year/decade,
genre, origin, edition count, date confidence, counts, and opaque evidence IDs.
Passages contain opaque passage/work IDs and categorical labels/confidence only.
Free text, titles, author names, source IDs, hashes, paths, offsets, original
dates, split, strata, and other identifying metadata are excluded. IDs are
re-keyed independently per corpus. Authors retain their grouping for inference.
Opaque IDs resolve **only within that corpus**; they are not external pointers.

`private/` contains keys, candidate validation, source hash, identity mappings,
and null baselines. It is created with mode 0700 and is never staged for agents.
`manifest.json` contains anonymous IDs only. Keep private artifacts and adapter
labels out of any agent-accessible mount. Public Parquet uses plain encodings;
passage order is stable before re-keying to avoid variable-size null/list
encodings becoming another side channel.

Tests assert uniqueness, source-label preservation through private mappings,
matching year histograms, opaque IDs, allowlisted schemas, strong-control
screening, injected effect tolerances, shuffled arms, and no prompt checklist.
The structural audit checks sizes, author counts, year summaries, missingness,
column counts, and actual file byte sizes. These features must be **identical**
across all 30 corpora. A five-fold random-forest classifier must score at chance
(1/3); a deliberately restored size leak must score above 90%.

This is an audit of marginal structure/storage features, **not proof that no
classifier can identify the arms**. Target trends and nuisance/year relationships
are intentional experimental differences. Cross-corpus matching is possible
because the source panel is shared: evaluate one isolated corpus per agent
session and do not give it other sessions' outputs.

## Real-agent study (2026-11-04)

Snapshot: 15,744 valid Discovery passages / 6,766 works / 1,669 authors. The travel
contrast fell to +2.53 pp (author-cluster interval lower bound −0.002 pp) and no
candidate passed the 3 pp screen, so generation used the pre-named target with
`--allow-unverified-positive`: the 10 empirical replays are generated but marked
`unsupported` (descriptive only); the 10 injected and 10 null corpora are scored.

```bash
R=bench/runs/2026-11-04
uv run --with pandas,numpy,pyarrow,duckdb,scikit-learn python -m bench.pilot --output $R/pilot  # adapter (fails at generation)
uv run --with pandas,numpy,pyarrow python -m bench.generate $R/pilot/labels.parquet $R/pilot/generated \
    --construct domains__DISTANCE_TRAVEL --allow-unverified-positive
# Analysis venv for agents, outside the repo: pandas numpy statsmodels pyarrow
uv run --with pandas,numpy,pyarrow python -m bench.run_agents $R/pilot/generated $R/claude_base --backend claude \
    --timeout 1200 --seeds 3 --concurrency 6 --resume --isolate \
    --temp-root $PWD/bench/runs/tmp/stage --extra-path $HOME/.cache/bench-agent-venv/bin
#   ... same with --condition confound_check -> $R/claude_confound_check
uv run --with pandas,numpy,pyarrow python -m bench.run_agents $R/pilot/generated $R/baseline \
    --command "/tmp/bench-agent-venv/bin/python $PWD/bench/baseline.py"
uv run --with pandas,numpy,pyarrow,matplotlib python -m bench.analyze $R/pilot/generated $R/conditions \
    --output $R/metrics.json --rows $R/rows.csv --figs bench/figs
```

`--isolate` wraps each session in bubblewrap: private `/tmp`, and the repository,
other staging dirs and `~/.claude/projects` masked. `--resume` reruns only missing,
`error` or `infra_error` sessions (environment I/O failures, gateway 5xx); invalid
answers and timeouts are agent outcomes and are kept. In this study 11 early base
sessions (shared-`/tmp` writes or quota failures) were quarantined by rule
(`quarantine/`) and rerun isolated, and 8 confound-check sessions that hit gateway
503s were rerun. Results: `metrics.json`, `metrics_table.md`, `rows.csv`, `bench/figs/`.
Paper draft: `docs/drafts/aaai27_eval_ai_scientists.md`.

`run.json` files keep the CLI's final result event (model, usage, cost, turns) and a
truncated list of tool-call inputs for process-level checks; full transcripts are not
kept. `analyze.py` reports two-stage (corpus, then repeat) bootstrap CIs. Generated
corpora and private keys stay local (ignored by Git).

## Agents, scoring, and limits

```bash
uv run python -m bench.run_agents bench/pilot/generated bench/answers --command "python $PWD/bench/dummy_agent.py"
uv run python -m bench.score bench/pilot/generated bench/answers --output bench/scores.json
# Paid presets: invoke only for an explicitly authorized real study.
uv run python -m bench.run_agents bench/pilot/generated bench/answers --backend claude --timeout 300
uv run python -m bench.run_agents bench/pilot/generated bench/answers --backend codex --token-budget 8000
```

`agent_task.md` asks generically for uncertainty, coverage, and alternative
explanations. It names no particular confounds or canonical answer strings.
Analysis uses Python/pandas/numpy/statsmodels; no web, other models, external
files, or invented quotations. Return the JSON schema in that prompt.
`confidence` means P(robust historical shift), including on abstention.

The runner stages only public files in a fresh temporary directory. This is
working-directory isolation, **not an OS sandbox**: paid CLIs inherit filesystem,
network, and credentials. Use a separate restricted container for a real study.
The 8,000-token reasoning/output allowance is a **prompt instruction**, not a
metered ceiling; tool inputs and repeated context can add substantial input
usage. The 300-second timeout kills the process group. Logs record elapsed time,
exit status, stdout/stderr, and the lack of hard token enforcement. Token usage
and price are not measured by the dummy and require backend usage instrumentation
for a real run. Backend versions/flags are not verified by this free pilot.

Scoring covers detection/direction, false claims, abstention, Brier loss,
label-supported evidence IDs, and finite-key CI coverage. Free-form confound
identification uses documented keyword combinations as well as canonical names;
it needs human adjudication and is not a semantic guarantee. Missing answers
remain in denominators; no citations give null evidence precision. Gate: all 20
injected/null answers valid, ≥ 8/10 injected detected in the correct direction,
and ≤ 1/10 null shift claims. An always-abstaining dummy correctly fails.
