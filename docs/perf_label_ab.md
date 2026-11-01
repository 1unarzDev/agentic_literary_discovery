# Label stage: compute-efficiency A/B (2026-11-01)

Goal: more label throughput on 12 GB / 16 GB cards without losing accuracy. All runs were on **COLLIN** (RTX 3060 12 GB,
Windows 11, Ollama 0.40.13, `gemma4:12b-it-q4_K_M`, flash attention on) with the ald worker paused and its task disabled.
The Linux GPU was not used.

Harness: `analysis/bench_label_ab.py` (build / run / score). Inputs:
- **bench set.** The frozen 60 passages of `data/work/bench_sample_60_7.jsonl`, re-cut to the production shape: 350 words,
  `ctx_before` = 900 chars, `ctx_after` = next 600 chars, production `LABEL_USER` template. That gives ~2,400 prompt
  tokens with v0, versus 2,527 in production. Scored on the 51 fiction passages against `data/work/bench_ref_claude.jsonl`.
- **QA set.** The 90 production passages of QA pass 2 (`data/work/label_ab_qa2`, built by `analysis/qa_ab.py`). Scored
  against `docs/qa/label_pass_2_ref.csv`: 84 fiction passages, after excluding the 2 few-shot source passages and 4
  non-fiction passages.

Each run: 2 sequential warm-up calls, then all passages at concurrency `c`, temperature 0, seed 0.
- pass/h = passages / wall time.
- Quote verified = `ald.evidence.verify_quote` status exact or normalized, among yes rows.
- Domain = share with any domain overlap; locus = exact agreement. Both are among passages where model and reference both say yes.
- "locus ≠ default" = share of yes rows whose locus departs from the codebook's default for the primary domain
  (COMMUNICATION and OTHER are excluded, since their default is undefined without failure_cause). The bench reference
  departs 0.00, the QA reference 0.17.

Every server configuration was a fresh `ollama serve`, so no run inherited another run's prompt cache. Runs tagged `_r2`/`_r3`
are repeats on the same server; they may see cached prefixes of the same passages, so their throughput is an upper
bound. Use them for accuracy noise only.

## 1. What limits throughput (findings)

1. **Prefill, not decode, dominates.** The prompt is ~2,400 tokens and the output ~155. In v0 at c=4, each slot prefills at
   ~325 tok/s while other slots decode. Per passage that is ~7.8 s of prefill against ~11.6 s of decode for 171 tokens.
2. **At num_ctx 8192 the system-prompt prefix is never reused.** Gemma 4 uses sliding-window attention (n_swa = 1024), so
   llama.cpp can reuse a cached prefix only from a context checkpoint inside the shared prefix. At 8192 every request logs
   `forcing full prompt re-processing due to lack of cache data (likely due to SWA ...)`: 672/672 requests in the first
   server log, 119/124 in the clean v0 run.
3. **At num_ctx 4096 the prefix is reused.** llama.cpp places a checkpoint at the system/user boundary (`created context
   checkpoint ... n_tokens = 1204`, then `restored context checkpoint ... n_past = 1204`). Mean prefill falls from ~2,400 to
   **~840 tokens per request**. This holds for the 1.7k-token v0 codebook too (`leanout` and `v0_c4k`), so the gain comes
   from the context size, not from prompt length.
   `LLAMA_ARG_CHECKPOINT_MIN_SPACING_NT=512` (more checkpoints) added nothing.
4. **VRAM is the limit on 12 GB.** At NP=4 and num_ctx 8192, 11.3 of 12.0 GB is in use. The KV cache is mostly the fixed
   SWA part: 1,920 MiB SWA plus 512 MiB global; num_ctx scales only the 8 global layers. Ollama also loads the MTP draft
   model (430 MB, speculative decoding is on) and the vision projector (350 MB). **`OLLAMA_KV_CACHE_TYPE=q8_0`** halves
   the KV, and with it 4 slots run at 10.6 GB. That alone gives +10–20%, and NP=6 becomes viable: NP=6 with f16 KV is the
   paging trap (998/h).
5. **Per-request num_ctx is applied by reloading the model.** On an idle server, a request with a different num_ctx
   reloaded the model in 11 s (probe: loaded at 12288, request at 4096). With two num_ctx values in flight at once
   (the auto-updated ald worker at 8192 and the bench at 4096, see §6), requests stalled for up to the 900 s client
   timeout. So: **one num_ctx per model on a machine at any time.** See §5 for ald.
6. **Production flags (22% of label rows `evidence_unverified`) are mostly an artefact.**
   - In a COLLIN job checkpoint, 41 of the 43 unverified quotes were `hallucinated`, and **26 of those were the literal
     `"none"`** on has_obstacle = no rows: the v0 tail says "other sub-fields 'none'".
   - Most of the rest were copied from CONTEXT BEFORE/AFTER.
   - There were no schema retries and no truncation (max 199 generated tokens against num_predict 400).
   - The lean schemas emit `""` or nothing on no-rows, so these flags go away.
7. **The worker ran at c=2** for its first job after each restart (tuner start). Production 790/h is c=2 at num_ctx 8192
   with no prefix reuse, which is consistent with the bench numbers below.

## 2. Throughput and accuracy: bench set (60 passages, 51 fiction)

× v0 = pass/h ÷ 1,044 (mean of the clean v0 runs). qwen rows are baseline_small (single-stream), not comparable.

| variant | server | c | pass/h | × v0 | quote ok (exact/norm) | quote ok (+trimmed) | acc | P | R | domain | locus | locus ≠ default | yes rate | non-fic yes | prompt tok/passage | gen tok/passage |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v0 | NP4 f16 ctx8192 | 4 | 1035 | 0.99 | 0.90 | 0.92 | 0.863 | 0.860 | 1.000 | 0.907 | 0.837 | 0.00 | 0.98 | 2/9 | 2403 | 154 |
| v0 | NP4 f16 ctx8192 | 6 | 1052 | 1.01 | 0.90 | 0.92 | 0.863 | 0.860 | 1.000 | 0.907 | 0.860 | 0.00 | 0.98 | 2/9 | 2403 | 155 |
| v0 | NP4 f16 ctx8192 (repeat) | 4 | 1048 | 1.00 | 0.90 | 0.94 | 0.863 | 0.860 | 1.000 | 0.884 | 0.837 | 0.02 | 0.98 | 2/9 | 2403 | 154 |
| v0 | NP4 f16 ctx8192 (repeat) | 4 | 1048 | 1.00 | 0.90 | 0.94 | 0.863 | 0.860 | 1.000 | 0.907 | 0.860 | 0.02 | 0.98 | 2/9 | 2403 | 154 |
| v0_c4k | NP3 q8_0 ctx4096 | 3 | 1659 | 1.59 | 0.90 | 0.96 | 0.882 | 0.878 | 1.000 | 0.884 | 0.884 | 0.04 | 0.96 | 2/9 | 2403 | 153 |
| v0_c4k | NP4 f16 ctx4096 | 4 | 1578 | 1.51 | 0.86 | 0.90 | 0.863 | 0.860 | 1.000 | 0.884 | 0.884 | 0.02 | 0.98 | 2/9 | 2403 | 154 |
| v0_c4k | NP4 q8_0 ctx4096 | 4 | 1728 | 1.66 | 0.90 | 0.94 | 0.863 | 0.860 | 1.000 | 0.860 | 0.884 | 0.02 | 0.98 | 2/9 | 2403 | 153 |
| v0_c4k | NP4 q8_0 ctx4096 (repeat) | 4 | 1813 | 1.74 | 0.94 | 0.96 | 0.863 | 0.860 | 1.000 | 0.884 | 0.907 | 0.04 | 0.98 | 2/9 | 2403 | 154 |
| v0_c4k | NP4 f16 ctx4096 (repeat) | 4 | 1478 | 1.42 | 0.90 | 0.94 | 0.863 | 0.860 | 1.000 | 0.907 | 0.837 | 0.00 | 0.98 | 2/9 | 2403 | 154 |
| v0_c4k | NP6 q8_0 ctx4096 | 6 | 1844 | 1.77 | 0.89 | 0.94 | 0.843 | 0.843 | 1.000 | 0.884 | 0.884 | 0.02 | 1.00 | 2/9 | 2403 | 155 |
| v0_c4k | NP1 f16 ctx4096 qwen3.5:4b | 1 | 1305 | — | 0.85 | 0.90 | 0.804 | 0.923 | 0.837 | 0.583 | 0.639 | 0.08 | 0.77 | 1/9 | 2411 | 152 |
| leanout | NP4 f16 ctx4096 | 4 | 1532 | 1.47 | 0.94 | 0.96 | 0.882 | 0.878 | 1.000 | 0.860 | 0.884 | 0.00 | 0.96 | 2/9 | 2442 | 143 |
| leanout | NP4 q8_0 ctx4096 | 4 | 1830 | 1.75 | 0.90 | 0.92 | 0.863 | 0.860 | 1.000 | 0.837 | 0.860 | 0.00 | 0.98 | 2/9 | 2442 | 145 |
| leanout_anyof *(rule winner)* | NP4 q8_0 ctx4096 | 4 | 2006 | 1.92 | 0.92 | 0.92 | 0.922 | 0.933 | 0.977 | 0.905 | 0.857 | 0.02 | 0.88 | 2/9 | 2413 | 118 |
| leanout_anyof *(rule winner)* | NP4 q8_0 ctx4096 (repeat) | 4 | 1915 | 1.83 | 0.94 | 0.94 | 0.902 | 0.896 | 1.000 | 0.884 | 0.884 | 0.02 | 0.94 | 2/9 | 2413 | 124 |
| leanout_anyof | NP1 q8_0 ctx4096 qwen3.5:4b | 1 | 1572 | — | 0.90 | 0.93 | 0.804 | 0.923 | 0.837 | 0.639 | 0.583 | 0.04 | 0.77 | 1/9 | 2420 | 113 |
| compact | NP1 f16 ctx4096 | 1 | 972 | 0.93 | 0.92 | 0.96 | 0.882 | 0.894 | 0.977 | 0.762 | 0.857 | 0.05 | 0.92 | 2/9 | 1966 | 138 |
| compact | NP2 f16 ctx4096 | 2 | 1523 | 1.46 | 0.94 | 0.94 | 0.863 | 0.891 | 0.953 | 0.878 | 0.878 | 0.05 | 0.90 | 2/9 | 1966 | 137 |
| compact | NP3 f16 ctx4096 | 3 | 1860 | 1.78 | 0.94 | 0.94 | 0.863 | 0.891 | 0.953 | 0.878 | 0.878 | 0.05 | 0.90 | 2/9 | 1966 | 137 |
| compact | NP4 f16 ctx4096 | 4 | 1583 | 1.52 | 0.92 | 0.96 | 0.863 | 0.891 | 0.953 | 0.854 | 0.878 | 0.05 | 0.90 | 2/9 | 1966 | 138 |
| compact | NP4 f16 ctx4096 ckpt512 | 4 | 1554 | 1.49 | 0.96 | 0.96 | 0.843 | 0.872 | 0.953 | 0.854 | 0.878 | 0.05 | 0.92 | 2/9 | 1966 | 138 |
| compact | NP4 q8_0 ctx4096 | 4 | 1928 | 1.85 | 0.92 | 0.96 | 0.882 | 0.894 | 0.977 | 0.833 | 0.881 | 0.05 | 0.92 | 2/9 | 1966 | 139 |
| compact | NP4 q8_0 ctx4096 (repeat) | 4 | 1939 | 1.86 | 0.94 | 0.96 | 0.882 | 0.894 | 0.977 | 0.810 | 0.881 | 0.05 | 0.92 | 2/9 | 1966 | 139 |
| compact | NP6 f16 ctx4096 | 6 | 998 | 0.96 | 0.96 | 0.96 | 0.863 | 0.891 | 0.953 | 0.878 | 0.902 | 0.02 | 0.90 | 2/9 | 1966 | 137 |
| compact2 | NP4 q8_0 ctx4096 | 4 | 1916 | 1.84 | 0.94 | 0.96 | 0.863 | 0.891 | 0.953 | 0.829 | 0.902 | 0.00 | 0.90 | 2/9 | 1970 | 138 |
| compact2 | NP1 f16 ctx4096 qwen3.5:4b | 1 | 1464 | — | 0.77 | 0.81 | 0.902 | 0.913 | 0.977 | 0.667 | 0.571 | 0.05 | 0.90 | 1/9 | 1971 | 142 |
| compact_anyof | NP4 f16 ctx4096 | 4 | 1744 | 1.67 | 0.96 | 0.96 | 0.882 | 0.894 | 0.977 | 0.929 | 0.857 | 0.09 | 0.92 | 1/9 | 1937 | 118 |
| compact_anyof | NP4 q8_0 ctx4096 | 4 | 1960 | 1.88 | 0.94 | 0.96 | 0.843 | 0.872 | 0.953 | 0.951 | 0.854 | 0.09 | 0.92 | 2/9 | 1937 | 120 |
| compact_anyof | NP4 q8_0 ctx4096 (repeat) | 4 | 2110 | 2.02 | 1.00 | 1.00 | 0.863 | 0.891 | 0.953 | 0.951 | 0.878 | 0.07 | 0.90 | 1/9 | 1937 | 118 |
| compact_anyof | NP6 q8_0 ctx4096 | 6 | 1999 | 1.91 | 0.94 | 0.94 | 0.882 | 0.911 | 0.953 | 0.927 | 0.854 | 0.09 | 0.88 | 1/9 | 1937 | 115 |
| compact2_anyof | NP3 q8_0 ctx4096 | 3 | 1945 | 1.86 | 0.96 | 0.96 | 0.843 | 0.889 | 0.930 | 0.875 | 0.925 | 0.05 | 0.88 | 1/9 | 1941 | 117 |
| compact2_anyof | NP4 q8_0 ctx4096 | 4 | 2035 | 1.95 | 0.96 | 0.96 | 0.863 | 0.909 | 0.930 | 0.875 | 0.875 | 0.05 | 0.86 | 1/9 | 1941 | 115 |
| compact2_anyof | NP4 q8_0 ctx4096 (repeat) | 4 | 2032 | 1.95 | 0.98 | 0.98 | 0.843 | 0.889 | 0.930 | 0.875 | 0.925 | 0.05 | 0.88 | 2/9 | 1941 | 120 |
| v09lean | NP4 q8_0 ctx4096 | 4 | 2015 | 1.93 | 0.93 | 0.95 | 0.882 | 0.974 | 0.884 | 0.895 | 0.816 | 0.11 | 0.77 | 1/9 | 2446 | 113 |
| v09lean_r2 **(adopted: v0.9)** | NP4 q8_0 ctx4096 | 4 | 1917 | 1.84 | 0.95 | 0.97 | 0.863 | 0.974 | 0.860 | 0.946 | 0.838 | 0.06 | 0.74 | 1/9 | 2498 | 118 |
| v09a_c4k | NP4 q8_0 ctx4096 | 4 | 1739 | 1.67 | 1.00 | 1.00 | 0.843 | 0.889 | 0.930 | 0.875 | 0.925 | 0.02 | 0.88 | 1/9 | 3046 | 148 |
| batch3 | NP4 q8_0 ctx12288 | 4 | 1778 | 1.70 | 0.82 | 0.82 | 0.824 | 0.947 | 0.837 | 0.806 | 0.917 | 0.00 | 0.74 | 1/9 | 1197 | 140 |
| batch5 | NP2 q8_0 ctx12288 | 2 | 1503 | 1.44 | 0.83 | 0.83 | 0.824 | 0.972 | 0.814 | 0.829 | 0.857 | 0.00 | 0.71 | 0/9 | 1026 | 141 |
| batch5 | NP4 q8_0 ctx12288 | 4 | 2120 | 2.03 | 0.80 | 0.83 | 0.804 | 0.971 | 0.791 | 0.794 | 0.824 | 0.03 | 0.69 | 0/9 | 1026 | 140 |
| batch8 | NP2 q8_0 ctx12288 | 2 | 1699 | 1.63 | 0.84 | 0.84 | 0.745 | 0.969 | 0.721 | 0.774 | 0.839 | 0.00 | 0.63 | 0/9 | 941 | 133 |
| batch8 | NP4 q8_0 ctx12288 | 4 | 2174 | 2.08 | 0.82 | 0.88 | 0.804 | 1.000 | 0.767 | 0.848 | 0.879 | 0.03 | 0.65 | 0/9 | 941 | 133 |
| v09lean_b5 | NP4 q8_0 ctx12288 | 4 | 1980 | 1.90 | 0.88 | 0.96 | 0.627 | 1.000 | 0.558 | 0.958 | 0.750 | 0.14 | 0.47 | 1/9 | 1139 | 86 |

## 3. QA set (90 production passages, 84 fiction)

× v0 = pass/h ÷ 1,002 (v0 on this set). `v0_synced` = the production outputs for these passages, from the QA kit.

| variant | server | c | pass/h | × v0 | quote ok (exact/norm) | quote ok (+trimmed) | acc | P | R | domain | locus | locus ≠ default | yes rate | non-fic yes | prompt tok/passage | gen tok/passage |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v0 | NP4 f16 ctx8192 | 4 | 1002 | 1.00 | 0.65 | 0.78 | 0.726 | 0.731 | 0.966 | 0.860 | 0.895 | 0.07 | 0.93 | 3/4 | 2525 | 156 |
| v0_c4k | NP4 q8_0 ctx4096 | 4 | 1600 | 1.60 | 0.62 | 0.78 | 0.750 | 0.738 | 1.000 | 0.831 | 0.847 | 0.04 | 0.95 | 3/4 | 2525 | 156 |
| leanout | NP4 q8_0 ctx4096 | 4 | 1669 | 1.67 | 0.65 | 0.75 | 0.726 | 0.731 | 0.966 | 0.860 | 0.825 | 0.06 | 0.93 | 3/4 | 2564 | 148 |
| leanout_anyof *(rule winner)* | NP4 q8_0 ctx4096 | 4 | 1815 | 1.81 | 0.72 | 0.81 | 0.738 | 0.747 | 0.949 | 0.839 | 0.804 | 0.06 | 0.89 | 2/4 | 2535 | 125 |
| compact2_anyof | NP4 q8_0 ctx4096 | 4 | 1862 | 1.86 | 0.72 | 0.80 | 0.762 | 0.775 | 0.932 | 0.764 | 0.818 | 0.06 | 0.84 | 2/4 | 2063 | 112 |
| v09lean | NP4 q8_0 ctx4096 | 4 | 1925 | 1.92 | 0.82 | 0.93 | 0.774 | 0.812 | 0.881 | 0.788 | 0.827 | 0.03 | 0.76 | 2/4 | 2568 | 117 |
| v09lean_r2 **(adopted: v0.9)** | NP4 q8_0 ctx4096 | 4 | 1793 | 1.79 | 0.75 | 0.91 | 0.762 | 0.800 | 0.881 | 0.769 | 0.827 | 0.03 | 0.77 | 2/4 | 2620 | 132 |
| v09a_c4k | NP4 q8_0 ctx4096 | 4 | 1699 | 1.70 | 0.80 | 0.91 | 0.786 | 0.806 | 0.915 | 0.778 | 0.815 | 0.06 | 0.80 | 2/4 | 3168 | 147 |
| v09lean_b5 | NP4 q8_0 ctx12288 | 4 | 1929 | 1.93 | 0.72 | 0.87 | 0.655 | 0.917 | 0.559 | 0.848 | 0.879 | 0.03 | 0.43 | 1/4 | 1261 | 83 |
| v0_synced | production rows | — | — | — | 0.51 | 0.73 | 0.738 | 0.734 | 0.983 | 0.862 | 0.845 | 0.06 | 0.94 | 3/4 | — | — |

## 4. Decision

**Adopted for production: codebook v0.9 = `v09lean_r2`.** It applies to `label`, `alt_label` and `baseline_small`, and
`cloze` moves to num_ctx 4096. This is the coordinator's decision on 2026-11-01, recorded below. It is implemented in
`pipeline/make_registry.py` and `docs/codebook.md`; the registry was not rebuilt or uploaded.
- **Text.** The model codebook is the fenced block in `docs/codebook.md`, read verbatim by `make_registry.py`. It is the
  measured `v09lean_r2` text; only the version line changed, from "v0.9-lean" to "v0.9", and an assertion checks this.
- **Rules.** v0.5's rules, plus QA pass-2 edits E1–E6, condensed:
  - the three-part test and the extra "not obstacles";
  - quotes only from inside the PASSAGE START/END markers;
  - SOCIAL_RANK as a rule that would stop anyone in that position;
  - failure_cause consistency;
  - DARKNESS / night_function.
- **Locus.** Locus is the proximate source and is judged first. The domain table is a "typical pattern only". The body
  is not the mind: this r2 fix removed r1's "her own sleep → internal" errors.
- **Schema.** `anyOf`. The yes branch, in order: `has_obstacle, locus, locus_reason (required, non-empty, ≤6 words),
  domains (1–2), failure_cause, message_valence, technology_named, night_function, resolution_hint,
  obstacle_summary (≤10 words), evidence_quote (6–20 words), confidence`. The no / insufficient_context branch is
  `{has_obstacle, confidence}`. Ollama 0.40's grammar enforces `anyOf`: schema validity was 1.00 in every gemma4 run,
  and in the qwen3.5:4b run with the `leanout_anyof` schema. v0.9 itself was not run on qwen; check its first
  alt_label / baseline_small shard for schema failures.
- **Options and server.** num_ctx 4096 and num_predict 200; max prompt + output seen was 3,032 tokens, with no
  truncation. Tiers get `kv_cache_type_hint: q8_0`, with NP=4 on t12 and NP=6 on t16. NP=6 with q8_0 fits on 12 GB but
  sits at 11.3 of 12.0 GB for +0–7%, so t12 stays at 4.
- **Throughput.** v0.9 runs at 1,793–2,015 passages/h on the 3060, **1.8–1.9× v0**.
- **Why v0.9 rather than the rule winner below** (coordinator):
  - Both references were labelled under v0.5, which follows the default locus mapping, so they penalise v0.9's
    intended locus independence.
  - With n = 84, the misses against the v0.9 bar are within noise.
  - E1–E6 fix construct-validity problems.
  - Human gold (Nov 6–8) decides v1.0.
  - **Watch locus agreement and the yes rate** in the first audit and dup-twin comparisons after the switch.

**Winner under the original adoption rule:** `leanout_anyof`, i.e. the v0.5 codebook verbatim + lean anyOf output at
num_ctx 4096 + q8_0. It is the fallback if v0.9 is rejected (`LEANOUT_SYSTEM_ANYOF` / `LEAN_SCHEMA_ANYOF` in make_registry).
Rule check on the bench set, means over the two fresh-server runs vs the four clean v0 runs:

| | pass/h | acc | P | R | domain | locus | quote ok |
|---|---|---|---|---|---|---|---|
| v0 (prod config) | 1,035–1,052 | 0.863 | 0.860 | 1.000 | 0.901 | 0.849 | 0.904 |
| **leanout_anyof** | **2,006** (repeat 1,915) | **0.912** | **0.915** | 0.988 | 0.895 | 0.871 | 0.928 |
| Δ (rule: ≥ 1.5×, each ≥ −0.02) | **1.92×** ✓ | +0.049 ✓ | +0.055 ✓ | −0.012 ✓ | −0.006 ✓ | +0.022 ✓ | +0.024 ✓ |

On the QA set (one run each), leanout_anyof has acc 0.738 vs 0.726 and quotes 0.81 vs 0.78 (with `trimmed`), at 1.81×.
**Locus is 0.804 vs 0.895.** The same v0 prompt gives 0.845 in the synced production rows and 0.847 at num_ctx 4096,
so v0's own spread is about 0.05. Even so, locus is H1's outcome. This is one more reason to watch locus after any switch.

Where the 1.9× comes from (bench, fresh servers, NP=4):

| step | pass/h | × v0 |
|---|---|---|
| v0, num_ctx 8192, f16 KV (production) | 1,035 | 1.00 |
| + num_ctx 4096 (prefix reuse starts working) | 1,578 | 1.52 |
| + KV cache q8_0 | 1,728 | 1.67 |
| + lean anyOf output (118 instead of 154 generated tokens; no-rows ~10 tokens) | 2,006 | 1.94 |

The first two steps leave the prompt untouched; their has_obstacle decisions are identical to v0 in all 6 runs. If the
coordinator prefers not to change the prompt at all, `v0` with num_ctx 4096 + q8_0 alone gives 1.6–1.8×.

**Not adopted:**
- **Compact codebooks** (`compact`, `compact2`, ~1,200-token rendition of the same rules; `_anyof` versions):
  1,860–2,110/h, but recall falls to 0.93–0.98 in every run. Two true positives are lost consistently: a reported-past
  obstacle (missed in 9/9 runs) and a comic one (6/9). Moving the hard-case rules last (`compact2`) did not help.
  Once the system prefix is cached, a shorter codebook buys little: ~1,940 vs ~2,400 prompt tokens, but only ~840 of
  them are prefilled either way.
- **Multi-passage batching (K = 3, 5, 8).** The best was K=8: 2,174/h, 1.08× single-passage compact_anyof. Accuracy
  collapses: bench R 0.72–0.84 and quotes 0.80–0.84, and v0.9-lean at K=5 on the QA set has R 0.56. Position effects
  (acc by position, compact at K=8: 1.00 / 0.57 / 0.80 / 1.00 / 1.00 / 0.86 / 0.71 / 0.57) and a lower yes rate show
  the model under-attends to later and middle items. No quote was ever attributed to another passage in the batch (0
  cross-quotes), so the problem is attention, not contamination. With prefix reuse the per-passage prefill is already
  ~840 tokens; batching only lowers it to ~950–1,200 per passage *including* the item framing. Registry change it would
  have needed: a `batch_k` stage field, a `{"labels": [K items, each with "passage": n]}` schema, one result line per
  item in `run_passage`, and a K-passage user template. **Not recommended.**
- **`LLAMA_ARG_CHECKPOINT_MIN_SPACING_NT=512`** (more SWA checkpoints): no gain (1,554 vs 1,583/h).
- **NP=6 with f16 KV on 12 GB**: VRAM paging, 998/h. NP=1 / 2 / 3 with f16: 972 / 1,523 / 1,860.

**v0.9 candidates (QA pass-2 edits E1–E6) against the coordinator's bar** (the bar was later waived; see above).
`v09lean` is E1–E6 condensed onto the compact codebook, plus the pilot-analysis locus changes: locus before domains, a
required ≤6-word `locus_reason`, the "proximate source" rule, and the default mapping framed as "typical pattern only".

| QA set (84 fiction) | pass/h | × v0 | acc | P | R | yes rate (ref 0.70) | domain | locus | locus ≠ default (ref 0.17) | quote ok +trimmed |
|---|---|---|---|---|---|---|---|---|---|---|
| v0 (prod) | 1,002 | 1.00 | 0.726 | 0.731 | 0.966 | 0.93 | 0.860 | 0.895 | 0.07 | 0.78 |
| v09a (num_ctx 4096, q8) | 1,699 | 1.70 | 0.786 | 0.806 | 0.915 | 0.80 | 0.778 | 0.815 | 0.06 | 0.91 |
| v09lean | 1,925 | 1.92 | 0.774 | 0.812 | 0.881 | 0.76 | 0.788 | 0.827 | 0.03 | 0.93 |
| v09lean r2 | 1,793 | 1.79 | 0.762 | 0.800 | 0.881 | 0.77 | 0.769 | 0.827 | 0.03 | 0.91 |
| v09lean, K=5 batch | 1,929 | 1.93 | 0.655 | 0.917 | 0.559 | 0.43 | 0.848 | 0.879 | 0.03 | 0.87 |
| bar | ≥ 1.5× | | ≥ 0.776 | | | | | ≥ 0.895 | | ≥ 0.95 |

- **Both QA-edit prompts fix most of the over-labelling.** The yes rate falls from 0.93 to 0.76–0.80 (reference 0.70)
  and precision rises from 0.73 to 0.81. v09lean does it at 1.9× v0.
- **Neither meets the bar.** v09a passes accuracy (+0.06) but fails locus and quotes. v09lean misses accuracy by one
  passage (+0.048) and also fails locus (0.827) and quotes (0.93).
- **"Locus first + required locus_reason" did not make the model depart from the default mapping more.** On QA rows
  the departure rate is 0.03, against the reference's 0.17. On the bench set it is 0.11, where the reference departs 0.00.
- **The required locus_reason pulled bodily states toward internal_psychological** ("her own sleep", "his own sickness").
  r2 adds "the body is not the mind" and neutral examples; it fixed that wording but did not raise locus agreement.
- **The ≥ 0.95 quote bar looks unreachable by prompting on this sample.** 40/90 of its items were oversampled for bad
  quotes. The remaining v09lean failures are ellipsis or joined speakers (6), context quotes (3), boundary straddles (3)
  and fabrications (2).
- **On the bench set, v09lean** runs at 2,015/h with acc 0.882, P 0.974, R 0.884, domain 0.895, locus 0.816. Against a
  reference with 84% yes, the lower recall is the intended effect of E1.
- **An option for v1.0 if human gold shows lost recall:** E1–E6 on the verbatim v0.5 codebook (v09a's text) with the
  v0.9 lean output at num_ctx 4096. The full-codebook wording did better on recall than the compact renditions here.
  Not run.

## 5. Changes needed outside make_registry (for the coordinator / ald)

1. **KV cache type.** Read `tiers.<tier>.kv_cache_type_hint` (new, `q8_0` on t12/t16/t24) in `ollama_env.wanted_env` and
   set `OLLAMA_KV_CACHE_TYPE` next to `OLLAMA_FLASH_ATTENTION=1`. The registry schema already accepts the extra tier field.
   Until ald reads it, workers get the num_ctx 4096 and lean-output gains (~1.6–1.7×) but not the q8_0 gain.
2. **One num_ctx per model.** Before a job, compare `/api/ps` `context_length` for the stage's model with the pin's
   `num_ctx`. If they differ, `unload()` first. `unload_non_pinned(keep={model_ref})` currently keeps a mismatched model.
   Ollama reloads on its own in about 11 s when idle, but with two num_ctx values in flight at once (e.g. a stage switch
   while old requests drain, or a second client) requests stall for minutes. `cloze` is now pinned at 4096 as well (a new cloze pin), so label ↔ cloze switches need no reload.
3. **Missing fields on no-obstacle rows (anyOf).** The worker's evidence check already skips rows without
   `evidence_quote` (`evidence.collect_quotes` ignores absent keys), so these rows are no longer flagged `evidence_unverified`.
   Consumers must read missing fields on `has_obstacle ≠ yes` rows as `domains []`,
   `locus none`, sub-fields `none`, `resolution_hint unknown` and quote `n/a`. `pipeline/sync_results.check_quote` already
   returns `n/a` for them.
4. **Concurrency tuner start.** It starts at c=2 after every restart, and production stayed there for whole 400-passage
   jobs. Start at `min(num_parallel_hint, …)`. NP3–6 are within 10% of each other with q8_0, so c=4 on t12 is safe.
5. **Pause handling.** The auto-updater relaunched a worker that had been stopped with `schtasks /end` (0.1.6 → 0.1.7 at
   00:40). A manual pause should survive updates.
6. **Not reachable through Ollama env:** speculative MTP decoding (`--spec-type draft-mtp`) and the vision projector are
   on the llama-server command line, so they cannot be switched off with `LLAMA_ARG_*` variables. The projector costs
   ~350 MB of VRAM per load.

## 6. Fleet ETA for 100k label passages

Single-machine rate with v0.9, and wall time for 100k label passages on that machine alone. **Measured** only on
the RTX 3060; the rest are **estimates**. For the 3060 planning rate I take the measured v0.9 rate (bench 1,917–2,015/h; 1,793–1,925/h on
the QA set's production passages, whose prompts are ~120 tokens longer) and allow ~10% for ald overheads: lease,
upload, tuner ramp-up and stage switches.

| machine | stage, model | settings | passages/h | 100k passages | basis |
|---|---|---|---|---|---|
| RTX 3060 12 GB | label, gemma4 12B | NP4, q8_0, ctx 4096 | **~1,700** (measured 1,800–2,000) | **~59 h** | measured on COLLIN |
| RTX 4070 Ti SUPER 16 GB | label, gemma4 12B | NP6, q8_0, ctx 4096 | ~3,400–4,500 | ~22–30 h | **estimate**: 2.0–2.4× the 3060. The pilot (same frozen sample, v0) measured 3,900 vs 1,636/h = 2.4×; memory bandwidth 672 vs 360 GB/s = 1.9× |
| GTX 1660 SUPER 6 GB | baseline_small, qwen3.5:4b (np 1) | ctx 4096 | ~500–800 | ~125–200 h | **estimate**: on the 3060, qwen3.5:4b with the lean anyOf output (`leanout_anyof`) measured 1,572/h single-stream; v0.9 itself was not run on qwen. Decode is bandwidth-similar (336 vs 360 GB/s), but prefill is ~3–5× slower without tensor cores |
| Apple M-series 16 GB (base chip, 100–120 GB/s) | label, gemma4 12B | NP1–2, q8_0 | ~200–350 | ~290–500 h | **estimate** from public llama.cpp/Ollama Metal figures for 12B Q4 (~12–15 tok/s decode, ~150–250 tok/s prefill). The model fits only just inside macOS's default ~10.7 GB GPU budget |
| Apple M-series 24 GB (Pro chip, 150–270 GB/s) | label, gemma4 12B | NP2, q8_0 | ~450–750 | ~130–220 h | **estimate** (~20–28 tok/s decode, ~400–600 tok/s prefill). A 24 GB *base* chip (e.g. M4) is closer to the 16 GB row, ~300–400/h |

For comparison, the production v0 config on the 3060 measured 1,035/h, about 97 h per 100k. The fleet's observed
790/h (c=2) is about 127 h. One 3060 plus one 4070 Ti SUPER on v0.9 is ~5,100–6,200 passages/h, so ~16–20 h per
100k and ~5–6 days for the ~700k queue. The Mac and 1660 rows assume prefix reuse works the same way on Metal and for
qwen3.5's hybrid attention. That is not verified.

## 7. Method notes and caveats

- **Noise.** One passage is 0.020 of accuracy on the bench set (51) and 0.012 on the QA set (84). Domain and locus are
  computed on ~35–60 both-yes passages, so one passage is 0.02–0.03. Under parallel batching, the same prompt at
  temperature 0 does not give identical outputs: the four clean v0 runs range over 0.884–0.907 in domain and 0.837–0.860
  in locus. A 0.02 margin is therefore about one passage. The decision rule is applied to means over repeats where repeats exist.
- **The bench reference and the QA reference disagree about prevalence.** The bench reference (Claude, codebook v0.5) marks
  84% of fiction passages yes. The QA reviewer finds the true rate in production is ~70% and that the model over-labels by
  ~15 points. A prompt that fixes over-labelling (E1) must therefore lose "recall" against the bench reference.
- **The first 40 minutes of runs were discarded.** The ald 0.1.7 auto-update relaunched the paused worker at 00:40. It
  shared Ollama with the benchmark until 01:19, when I disabled the task. Those runs are kept apart in
  `data/work/label_ab/runs_phase1_contaminated`.
- The clock fell back from CDT to CST at 02:00 during the runs, so log timestamps repeat 01:00–02:00.
- Raw runs: `data/work/label_ab/runs/` and `data/work/label_ab_qa2/runs/` (not in git). Scores were regenerated with
  `uv run --with jsonschema --with rapidfuzz python -I analysis/bench_label_ab.py score <runs> --ref bench|qa`.
