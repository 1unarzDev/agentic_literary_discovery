# Dummy pilot and real-agent budget

Validation: **14 tests passed** with the requested dependency set.

The repaired benchmark ran end to end on local v0.9 Discovery labels: **30/30
valid dummy answers, zero paid calls**. This establishes mechanics and the
specified structural leak checks; it does not measure research-agent performance.
Run date: 2026-11-01 (environment date; the task's background says Oct 31).

## Measured results

Reproduce from the repository root with an empty `bench/pilot/`:

```bash
export UV_PROJECT_ENVIRONMENT="$PWD/bench/.venv"
export UV_CACHE_DIR="$PWD/bench/.uv-cache"
uv run --with pandas,numpy,pyarrow,pytest,duckdb,scikit-learn pytest bench -q
uv run --with pandas,numpy,pyarrow,duckdb,scikit-learn python -m bench.pilot
```

The read-only adapter selected **8,667 valid passages from 5,257 Discovery works**
(stage `label`, pin prefix `41ca3c7d`), all from the random stratum. It samples one
passage per work for generation. Every corpus has 5,257 unique works/passages,
1,451 opaque author groups, and 122 distinct publication years spanning 1800–1925.
Real source-year multiplicities are identical across all 30 corpora; each work
has exactly one date. No Confirmation rows, raw text, source identities, or
identifying metadata enter public files.

| Component | Measured seconds |
|---|---:|
| Read-only adapter | 0.217 |
| Generation and control verification | 4.568 |
| Structural audit | 0.801 |
| All 30 dummy subprocesses, including staging | 0.662 |
| Total, including scoring | 7.006 |

All 16 audited corpus features, including public data-file byte sizes, were
identical across arms. Five-fold random-forest accuracy was **0.3333**, equal to
three-class chance. Tests also verify that deliberately restoring an arm-specific
size feature raises accuracy above 90%. This audit excludes intended outcome
trends and nuisance/year associations; it is not a claim of universal blindness.

The dummy abstains: 100% abstention, 0% detection, 0% null false claims, Brier
0.25, 0% CI coverage, no evidence citations, and **gate failed** as intended.
All 30 controls are eligible; no unsupported placeholders remain. Local machine
outputs are `bench/pilot/{summary,leak_audit,scores}.json`, plus public corpora,
private keys, and per-run logs. They are ignored by Git and can be regenerated.

## Which positive survived

Selection uses the one-passage-per-work panel actually exported, equal-genre
standardization, a ≥ 3 percentage-point absolute effect, and a 400-draw
**author-cluster** bootstrap interval excluding zero. Candidate screening is
exploratory; intervals do not adjust for selection.

| Candidate | Late-minus-early effect (pp) | Decision |
|---|---:|---|
| Distance/travel obstacles | **+3.687**; 95% interval **[+1.456, +5.729]** | Retain |
| Social rank/convention obstacles | −2.339 | Drop: below size threshold |
| Communication/information obstacles | +2.006 | Drop: below size threshold |
| Internal obstacles | −2.501 | Drop: below size threshold |
| Plot-relevant telephone technology | +0.258 | Drop: below size threshold |
| Non-`none` night function | +0.185 | Drop: below size threshold |

Telephone/telegram **mention rates are not provided by these labels**;
`technology_named` measures the codebook field, not exhaustive mentions. There
are no labelled enrichment strata in this adapter snapshot, so a darkness versus
enrichment positive cannot be verified. Epistolary has no measured proxy and
was removed. Nothing is inferred about those unavailable measurements.

The selected travel contrast is larger than the review's 0.2–0.7 pp controls,
but it remains a **selected empirical pattern**, not established historical
truth or evidence for H2b. Its ten replays use the same dated panel with fresh
opaque IDs and ordering; they are correlated and must not be counted as ten
independent discoveries. All injected and null arms use the same travel target,
so task metadata cannot identify positives. Injected shifts target ±5 pp;
realized effects and rounding tolerances are recorded in private keys.

Nulls use measured nuisance metadata rather than repeated works or an unmeasured
memorization score. Their finite random baselines are not exactly zero; the
randomization **expectation** is zero. The current pilot's observed standardized
null contrasts range approximately −1.39 to +2.30 pp. These are weaker traps than
the review's duplicated-edition examples. Before a paid study, assess difficulty
and crude as well as adjusted effects; this pilot is not evidence of a suitably
challenging false-claim benchmark. Stronger artifacts must preserve the leak
invariants, and should be designed before reading paid-agent outcomes.

## Planning 30 real-agent runs — estimates, not measurements

No `claude -p` or `codex exec` calls were made. CLI/model compatibility, actual
usage, inference speed, and dollar spend are **UNVERIFIED** by this pilot. The
following is a planning envelope for **one backend × one seed × 30 corpora**:

| Resource | Per corpus assumption | 30-corpus estimate |
|---|---:|---:|
| Billed input, including repeated context/tool results | 10,000–30,000 tokens | 300,000–900,000 tokens |
| Generated reasoning/output allowance | 4,000–8,000 tokens | 120,000–240,000 tokens |
| Combined input + generated | 14,000–38,000 tokens | **420,000–1,140,000 tokens** |
| Serial agent time | 2–5 minutes | **60–150 minutes** |

These are explicit assumptions, not extrapolations from the dummy's runtime.
The prompt contains 2,054 UTF-8 bytes (~514 tokens at a rough 4 bytes/token);
the dummy's 30 stdout responses total 5,550 bytes. These are byte counts, not
backend-tokenizer measurements. Each public corpus contains ~2.47 MB of work
Parquet, ~0.60 MB of passage Parquet, and ~0.95 MB of work CSV. Agents should
analyze tables locally and return compact aggregates; printing whole tables can
exceed the input envelope. The runner does not enforce this behavior.

The existing runner is serial. Its default 300-second subprocess timeout limits
30 model processes to about 150 minutes plus staging overhead, but terminated
runs may be incomplete and still bill usage. Four externally managed workers
could ideally reduce 60–150 minutes to ~15–40 minutes plus overhead; that is an
assumption, not a measured concurrency result. Two backends multiply token/time
estimates by two; three independent seeds multiply them by three again.

The 8,000-token setting is **prompt-only** and covers requested reasoning/output,
not cumulative input billing. A real study needs backend-native limits where
available, usage-event capture, fixed model/version, and actual token/cost logs.
Use a three-corpus instrumented paid pilot before committing to all 30. No paid
execution was performed or authorized by this report.

## Sources checked on the web

A web search located the primary [Smithsonian telephone record](https://americanhistory.si.edu/collections/object/nmah_689864),
whose search-index excerpt dates the relevant patent to 7 March 1876. Direct
page retrieval failed, so verification here is limited to that indexed excerpt.
That dates a technology; it does
**not** validate a large fictional-mention effect. Weak telephone controls were
therefore dropped despite the historically grounded cutoff.

Anthropic's [Claude Code usage and limits documentation](https://support.claude.com/en/articles/14552983-models-usage-and-limits-in-claude-code)
distinguishes API-token billing from subscription use and describes `/cost` for
API-key sessions. Its [explanation of Claude Code context billing](https://claude.com/de/resources/articles/maximizing-the-value-of-your-claude-code-sessions)
explains why file/tool content and repeated conversation context contribute
input tokens. These sources motivate measuring actual backend usage; they do
not support the numerical planning assumptions above. No dollar price or
unverified model-specific throughput is asserted.
