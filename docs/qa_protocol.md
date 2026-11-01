# Annotation QA protocol

This is the recurring check that local-LLM labels follow the codebook. It covers discovery data only. Confirmation data is never sampled, and the sampler filters on `split='discovery'` in both passages and works.

## When to run

| Trigger | Stage | Sample |
|---|---|---|
| First 200 or more workcheck rows synced, and again after any workcheck pin change | workcheck | all rows if ≤ 200, else n = 60 |
| 300 or more `label` rows from wave w01 synced (QA pass 1) | label | n = 80 |
| Each later wave (w03 enrichment, w05), once 300 or more new rows exist | label | n = 80 (per-wave sample) |
| Once alt_label (w08) or baseline_small (w09) share 200 or more passages with label | alt_label, baseline_small | n = 40, plus the cross-model tables |
| Before a codebook freeze (v0.9 on Nov 5, v1.0 on Nov 8) | label | A/B re-run on the frozen QA sample (below) |

Check the counts first:

```
SELECT stage, pin_hash, count(*) FROM results GROUP BY 1, 2
```

Run it read-only against `data/work/ald.duckdb`.

## Drawing the sample

```
uv run --with pandas,duckdb,pyarrow python -I analysis/qa_sample.py --stage label --n 80 --seed <pass#>
```

**Strata.** The sampler stratifies on three things:
- era: 1800–1849, 1850–1884 or 1885–1929, taken from the work's `year`;
- predicted class: the primary domain, or no / insufficient_context / SCHEMA_FAIL;
- risk.

**Risk** means any of these:
- confidence below 0.7;
- a yes-label whose `quote_status` is not exact or normalized;
- a schema failure;
- for workcheck only, the catalog and model disagree on form.

**Allocation.** Strata get a √N share of the sample, with at least 1 each. Risk sub-strata get 3× that share.

**Weighting.** Every row carries `N_h`, `n_h` and `design_weight`. Estimate error rates per stratum and re-weight by `N_h`. Never quote raw sample proportions as population rates, because the sample is oversampled.

**Outputs.** `data/work/qa/<stage>_<ts>.jsonl` and `<stage>_<ts>.md`. These are never committed.

For label-type stages, the packet also holds cross-model agreement tables: label vs alt_label and label vs baseline_small, by field and era, over all shared rows. Disagreement between Gemma and Qwen on a field points to an unclear codebook definition, even where no human has looked yet.

## Reviewing
- **Reviewers read as English-literature readers, against codebook vX in force for the pin.**
- **Workcheck:** judge `form` from the opening text and catalog metadata. Translation, juvenile and period are checked against the catalog.
- **Label:** decide whether each of these is right:
  - has_obstacle;
  - domains, using the proximate-cause rule;
  - locus, including whether an override was needed;
  - failure_cause and message_valence, if COMMUNICATION_INFORMATION;
  - night_function;
  - the evidence quote: does it show the obstacle, rather than merely appearing verbatim?
- **Record each error** under a pattern tag, using these as a starting list:
  - over_label_description
  - interpersonal_vs_rank
  - locus_default_misapplied
  - comm_cause_wrong
  - night_fn_wrong
  - era_misread (archaic, irony, epistolary)
  - nonfiction_leak
  - quote_nondiagnostic
  - under_label
- **Fill in** `review_ok`, `review_errors` and `review_ref` in the jsonl so the pass is machine-readable.
- **Write up** `docs/qa/label_pass_<n>.md`. It needs:
  - an error table (pattern | count/n | example passage_id + short quote | fix);
  - design-weighted accuracy per era;
  - proposed edits as minimal diffs.
- **Prioritise** fixes by their impact on the hypotheses:
  - H1: locus shares;
  - H2a: communication failure_cause;
  - H2b: DISTANCE_TRAVEL;
  - H2c: DARKNESS / night_function.
- **Exemplars:** add strong prototypes, and cross-era pairs, to `docs/qa/exemplar_candidates.md`.

## Change control
- **Do not edit `docs/codebook.md` or `registry/models.v1.json` in a QA pass.** QA only proposes changes. A prompt change creates a new pin, and every passage under the old pin must be relabelled.
- **All accepted proposals are batched into codebook v0.9, frozen on Nov 5.** v0.9 is the last version that can change labels at scale.
- **v1.0 is frozen on Nov 8** and pre-registered. After Nov 8, only typo or clarity edits are allowed, and only if they leave prompt hashes unchanged. Anything else waits for a declared v1.1, and every result is then reported per pin.
- **Each proposal must cite** its error count, its affected hypothesis, and the exact diff.
- **Few-shot examples come only from QA-reviewed discovery passages, with exact quotes.** Never use passages that are in the human audit or teaching set, or the A/B set; the passage is then contaminated for evaluation.

## Measuring improvement before adopting (A/B)
1. **Freeze the QA sample.** It is the `.jsonl` of the pass that motivated the change, and the reviewer's `review_ref` fields serve as the reference labels. Also add the 60-passage bench set (`data/work/bench_sample_60_7.jsonl`) and its Claude reference (`bench_ref_claude.jsonl`) as a second, untouched check.
2. **Run old and new prompts on the same items.** Use `analysis/bench_models.py`-style local runs: same model digest, temperature 0, seed 0, same num_ctx. Run the old prompt as a control, because a rerun can drift from the synced results with an Ollama version change.
   - For synced pins, compare like with like: `analysis/qa_sample.py --stage label --reuse <frozen.jsonl> --pin <new_pin>`.
3. **Score both arms against `review_ref`:**
   - has_obstacle accuracy, P and R;
   - domain overlap;
   - locus agreement;
   - failure_cause agreement on COMMUNICATION items;
   - night_function on DARKNESS items;
   - the share of exact or normalized quotes;
   - the share of quotes that are diagnostic;
   - non-fiction marked "yes";
   - throughput, in passages per hour.
4. **Adoption rule.** Adopt only if all of these hold:
   - the targeted error pattern drops by at least 50%, or by at least 3 items when n is small;
   - no other field loses more than 0.03 in agreement;
   - quote exact-or-normalized stays at 0.97 or above (gate G1);
   - throughput stays at 70% of the current pin's or better.
   
   Report both arms in `docs/model_selection.md`.
5. **Guard against overfitting.** Few-shot examples taken from the QA sample must be removed from the A/B scoring set. Prefer the bench set as the deciding comparison.
6. **After adoption:**
   - bump `codebook_version` and regenerate the pins (orchestrator);
   - relabel;
   - re-run the QA pass on a **fresh** seed, to confirm the gain holds outside the A/B set.
