# Model selection log

## 2026-10-31: pilot benchmark (60 frozen passages, RTX 4070 Ti Super, Ollama 0.40.13)
The provisional reference is a blind Claude reader applying codebook v0.5 (`data/work/bench_ref_claude.jsonl`). It is **not** human gold; we re-check against the human audit set on Nov 6–8.

Scores are on the 51 fiction passages.

| Model / prompt | Pass./h | Acc | P | R | Domain overlap | Locus | Non-fiction marked "yes" |
|---|---|---|---|---|---|---|---|
| gemma4:12b-it-q4_K_M, v0 prompt | 3,900 | 0.86 | 0.86 | 1.00 | 0.91 | 0.88 | 3/9 |
| gemma4:12b-it-q4_K_M, grounded prompt (goal/impediment/consequence fields) | 511 | 0.88 | 0.89 | 0.98 | 0.86 | 0.88 | 2/9 |
| qwen3.5:9b-q4_K_M, v0 prompt | 1,530 | 0.78 | 0.94 | 0.79 | 0.76 | 0.79 | 0/9 |
| qwen3.5:4b-q4_K_M (screen only) | 6,913 | — | — | — | — | — | — |

### Decisions
- **Drop the screen stage.** Its pass rate is 56%, so screening plus labeling costs about as much as labeling directly.
- **Label stage = Gemma 4 12B, v0 prompt.** The verbatim-quote instruction is kept. The grounded prompt was 7× slower for +0.02 accuracy.
- **8 GB tier = `workcheck` stage** (fiction / translation / juvenile / setting check per work) with qwen3.5:4b, plus name-cloze memorization probes and the alternate-family robustness subsample (Qwen 9B, 10%).
- Exact-quote rate is 0.89–0.94 with crude normalization; the `evidence.py` normalization should raise it. **Gate G1 needs ≥ 0.97 after normalization.** If it falls short, we add a verbatim-retry pass.
- **Ops finding:** a second resident model forced partial CPU offload, cutting throughput about 8×. Workers must unload non-pinned models and verify 100% GPU.
