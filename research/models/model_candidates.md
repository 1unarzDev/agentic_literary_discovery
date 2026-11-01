# Local Ollama models for the literary-obstacle cascade

**Checked 2026-10-31. Decision: pilot Qwen3.5-4B → Gemma 4 12B → Qwen3.8-27B, with Gemma 4 26B as an independent adjudicator.** These are deployment candidates, not validated annotators. No verified evaluation establishes their accuracy on nineteenth-century plot obstacles, material/social/internal distinctions, intentional withholding, or exact literary quotations. Those task-specific quality and reliability claims are **UNVERIFIED for every candidate**.

Web checks covered official Ollama library/tag pages, model cards, runtime documentation/source, and experimenters' own benchmark reports. No models were downloaded or benchmarked locally. Catalog pages are mutable; the checks establish availability today, not an archived release history.

## Hardware and tag policy

Use the explicit **GGUF quantization tags** below across Windows NVIDIA, Linux NVIDIA, and native macOS Ollama. Avoid `latest`, size-only aliases, `-cloud`, and initially `-mlx`/MTP variants: current size aliases can select different artifacts by platform. For example, the Qwen3.5 catalog gives ranges for aliases but separate GGUF and MLX tags. Identical weights still do not guarantee identical outputs across backends. Record the resolved digest, Ollama version, prompt/schema hashes, options, OS, and GPU with every run. [Qwen3.5 tags](https://ollama.com/library/qwen3.5/tags), [Gemma 4 tags](https://ollama.com/library/gemma4/tags).

Sizes below are **rounded download sizes in decimal GB**, not runtime VRAM requirements. Advertised context is the **library tag's ceiling**, not an allocation suitable for these cards. Start at `num_ctx=4096`, parallelism 1; move to 8192 only if annotation rules, examples, passage, and answer require it. Weights, KV/state buffers, compute buffers, the display, and the OS all need memory. The fit assessments are engineering estimates; exact peaks on the specified volunteer machines are **UNVERIFIED**.

Ollama supports the RTX 4070 Ti SUPER and Apple GPU acceleration. Use native macOS Ollama; Docker Desktop on macOS lacks GPU passthrough. Check `ollama ps` for GPU placement before accepting speed measurements. Apple unified memory includes the OS and applications: 16 GB unified memory is not 16 GB of spare VRAM. [Hardware support](https://docs.ollama.com/gpu), [FAQ](https://docs.ollama.com/faq).

## Candidates and verified artifacts

All generator tags listed here use **Q4_K_M**. License **A** means Apache-2.0: commercial and research use permitted, subject to its terms. This is verified in the relevant first-party cards: [Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B), [Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B), [Qwen3.5-27B](https://huggingface.co/Qwen/Qwen3.5-27B), [Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507), [Qwen2.5-14B-Instruct](https://huggingface.co/Qwen/Qwen2.5-14B-Instruct), [Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B), and the [Gemma 4 family card](https://huggingface.co/google/gemma-4-12B-it). **Gemma 4 uses Apache-2.0; do not apply Gemma 3's license to it.**

| Stage / candidate | Exact Ollama tag, verified on linked library page | File | Advertised context | License | Fit / thinking policy |
|---|---|---:|---:|---|---|
| SCREEN: Qwen3.5 4B | [`qwen3.5:4b-q4_K_M`](https://ollama.com/library/qwen3.5:4b-q4_K_M) | 3.3 GB | 256K | A | Good margin on 8 GB GPU / 16 GB Mac; set `think:false` for speed. |
| SCREEN: Qwen3 4B Instruct 2507 | [`qwen3:4b-instruct-2507-q4_K_M`](https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M) | 2.5 GB | 256K | A | Smallest fallback; **nonthinking-only**, no disabling needed. Do not substitute the thinking `qwen3:4b` alias. |
| SCREEN: Gemma 4 E2B | [`gemma4:e2b-it-q4_K_M`](https://ollama.com/library/gemma4:e2b-it-q4_K_M) | 4.6 GB | 128K | A | Likely fits at short context; E2B is effective parameter count, not total memory size. Set `think:false`. |
| LABEL: Gemma 4 12B | [`gemma4:12b-it-q4_K_M`](https://ollama.com/library/gemma4:12b-it-q4_K_M) | 8.0 GB | 256K | A | Comfortable starting candidate for 16 GB GPU / 24–32 GB Mac; set `think:false`. |
| LABEL: Qwen3.5 9B | [`qwen3.5:9b-q4_K_M`](https://ollama.com/library/qwen3.5:9b-q4_K_M) | 6.6 GB | 256K | A | More memory margin; set `think:false`. Avoid assuming it comfortably fits every 8 GB GPU. |
| LABEL: Qwen2.5 14B Instruct | [`qwen2.5:14b-instruct-q4_K_M`](https://ollama.com/library/qwen2.5:14b-instruct-q4_K_M) | 9.0 GB | 32K | A | Older JSON-oriented baseline with reasonable 16 GB headroom; no thinking mode. |
| ADJUDICATE: Qwen3.8 27B | [`qwen3.8:27b-q4_K_M`](https://ollama.com/library/qwen3.8:27b-q4_K_M) | 18 GB | 256K | A | Candidate for 24 GB GPU / preferably 32 GB+ Mac. Thinking defaults on; disable for throughput, separately pilot thinking on difficult cases. |
| ADJUDICATE: Gemma 4 26B-A4B | [`gemma4:26b-a4b-it-q4_K_M`](https://ollama.com/library/gemma4:26b-a4b-it-q4_K_M) | 18 GB | 256K | A | MoE with 4B active, but all expert weights still need storage/residency. Same memory tier; set `think:false` for speed. |
| ADJUDICATE: Qwen3.5 27B | [`qwen3.5:27b-q4_K_M`](https://ollama.com/library/qwen3.5:27b-q4_K_M) | 17 GB | 256K | A | Dense alternative, short-context 24 GB candidate; set `think:false` for speed. |

Tag/size/context cross-checks: [Qwen3.5](https://ollama.com/library/qwen3.5/tags), [Qwen3](https://ollama.com/library/qwen3/tags), [Qwen2.5](https://ollama.com/library/qwen2.5/tags), [Qwen3.8](https://ollama.com/library/qwen3.8/tags), [Gemma 4](https://ollama.com/library/gemma4/tags). The explicit Qwen3.8 Q4 tag currently differs from the default alias, which can include a draft model.

Thinking is a throughput choice, not a correctness requirement. Discover each installed artifact's supported controls with `/api/show`; request `think:false` through Ollama's native API where supported. Hiding a thinking field in a UI does not disable generation. The Qwen3 Instruct 2507 card explicitly specifies nonthinking-only operation; Gemma 4 and Qwen3.5 cards document configurable thinking, and Qwen3.8's library page documents on-by-default, disable-per-request behavior. [Ollama thinking controls](https://docs.ollama.com/capabilities/thinking), [Qwen3 Instruct card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507), [Gemma 4 card](https://huggingface.co/google/gemma-4-12B-it), [Qwen3.8 library](https://ollama.com/library/qwen3.8).

## Reading quality, JSON reliability, and speed evidence

**No verified model-specific Ollama schema pass rate was found for this annotation task.** General instruction-following, retrieval, writing, and tool-use benchmarks are proxies; none establishes faithful narrative interpretation. English literary assessments below are selection judgments, explicitly **UNVERIFIED** until a human-labeled pilot. Generic benchmark percentages must not be reported as annotation accuracy.

| Candidate | Structured-output evidence / English literary assessment | Reported speed and limits |
|---|---|---|
| Qwen3.5 4B | First-party instruction-following and long-context evaluations; plausible economical screener, but implicit goals and irony need testing. Schema/evidence accuracy **UNVERIFIED**. [Card](https://huggingface.co/Qwen/Qwen3.5-4B) | Experimenter's Jetson Orin Q4_K_M llama.cpp run: **36.7 generation / 473 prompt tok/s**, thinking disabled. Different runtime/hardware; not a cluster forecast. [Experiment](https://github.com/ArmanJR/PrismML-Bonsai-vs-Qwen3.5-Benchmark) |
| Qwen3 4B Instruct 2507 | Card reports IFEval **83.7**, which is instruction following, not JSON-schema success. Useful direct-answer baseline; historical prose quality **UNVERIFIED**. [Card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) | Community oMLX run on **M4 10-core GPU, 24 GB, 4-bit, 4K context**: **30.3 generation / 378.2 prompt tok/s**. MLX, not Ollama GGUF. [Run](https://omlx.ai/benchmarks/performance/3zrmdutw) |
| Gemma 4 E2B | Independent family for screening audit. Small known-answer/tool tests include JSON, but cannot establish schema reliability or literary competence. Both **UNVERIFIED** for this task. | Own-measurement report: **6.2–6.5 generation / 137–143 prompt tok/s** on CPU-only Ryzen 5 5600 VM, 6 vCPU, Ollama 0.40.12, Q4_K_M, 4K context. GPU speed **UNVERIFIED**. [Report](https://www.bigiron.cc/guides/gemma-4-on-a-cpu-only-box-measured) |
| Gemma 4 12B | Native system-role support and first-party reasoning/long-context evaluations make it a plausible full labeler. Ollama's schema documentation demonstrates Gemma 4; no quantified annotation guarantee. Literary reading **UNVERIFIED**. [Card](https://huggingface.co/google/gemma-4-12B-it), [Schema demo](https://docs.ollama.com/capabilities/structured-outputs) | Scribe's own Windows **RTX 5080 16 GB** dictation benchmark reports **431 ms median**, Q4_K_M **plus MTP**, 32K allocation. Different workload and draft configuration; no verified speed for the pinned plain tag on a 4070 Ti SUPER. [Benchmark](https://github.com/ChrisMcKee1/scribe/blob/main/docs/local-model-benchmark.md) |
| Qwen3.5 9B | Same first-party evaluation family as 4B; plausible accuracy upgrade with ample LABEL memory margin. Exact evidence and literary advantage over Gemma **UNVERIFIED**. [Card](https://huggingface.co/Qwen/Qwen3.5-9B) | Same Jetson experiment: **27.0 generation / 320 prompt tok/s**, Q4_K_M, thinking disabled. [Experiment](https://github.com/ArmanJR/PrismML-Bonsai-vs-Qwen3.5-Benchmark) |
| Qwen2.5 14B | Developer explicitly reports improved JSON generation and structured-data understanding; this is a qualitative claim, not a measured Ollama schema pass rate. Useful nonreasoning baseline; literary quality **UNVERIFIED**. [Card](https://huggingface.co/Qwen/Qwen2.5-14B-Instruct) | Matched, sufficiently documented speed on the requested hardware/tag **UNVERIFIED**; benchmark locally rather than assign a generic 14B tok/s estimate. |
| Qwen3.8 27B | First-party instruction-following/reasoning evaluations justify inclusion, not presumed superiority on literature. Best-quality adjudicator is a pilot hypothesis, **UNVERIFIED**. [Card](https://huggingface.co/Qwen/Qwen3.8-27B) | Experimenter's **128 GB Strix Halo**, Ollama 0.32.15 matched control: **12.89 tok/s without drafting / 22.71 with default MTP**. AMD/backend-specific; not the pinned plain tag on NVIDIA. [Evidence](https://strixhaloguide.com/evidence/) |
| Gemma 4 26B-A4B | Independent family reduces reliance on one model lineage; MoE makes it a throughput contender. First-party evaluations do not establish exact-span copying or historical reading. **UNVERIFIED** for both. [Family card](https://huggingface.co/google/gemma-4-12B-it) | Own benchmark on **Ryzen AI MAX+ 395 / Radeon 8060S / 128 GB UMA**, llama.cpp: **52.9 generation / 1196 prompt tok/s**, listed 16 GiB artifact. Different quant/artifact details from the Ollama tag; transfer **UNVERIFIED**. [Benchmark](https://slb350.github.io/strix-benchmarks/) |
| Qwen3.5 27B | Larger dense alternative with first-party instruction-following/long-context results. No verified literary-obstacle or schema/evidence advantage. [Card](https://huggingface.co/Qwen/Qwen3.5-27B) | Same Jetson Q4 experiment: **9.5 generation / 107 prompt tok/s**, thinking disabled. [Experiment](https://github.com/ArmanJR/PrismML-Bonsai-vs-Qwen3.5-Benchmark) |

Speed reports above verify what their authors reported, not independent reproductions. Their workloads, quantization, draft models, contexts, and devices differ. Compare **accepted passages/second**, including prompt processing, evidence validation, retries, and routing—not decode tok/s alone. No verified apples-to-apples cross-platform ranking is available here.

## Small embedding model

Use [`embeddinggemma:300m-bf16`](https://ollama.com/library/embeddinggemma:300m-bf16): **622 MB, BF16, 2K context, 768 dimensions**. A ~350-word passage will usually fit, but check tokenizer length and reject truncation. For a smaller pilot option, [`embeddinggemma:300m-qat-q8_0`](https://ollama.com/library/embeddinggemma:300m-qat-q8_0) is **338 MB**; quantized retrieval parity is **UNVERIFIED**. [Verified tags](https://ollama.com/library/embeddinggemma/tags), [Google model card](https://ai.google.dev/gemma/docs/embeddinggemma/model_card).

License: **Gemma Terms**, permitting research and commercial use subject to restrictions and redistribution requirements; unlike Gemma 4, this older embedding model is not Apache-2.0. Use `/api/embed`; JSON generation and thinking do not apply. Retrieval/clustering is its stated purpose; obstacle-sensitive literary retrieval quality and Ollama throughput on these machines are **UNVERIFIED**. Use one fixed embedding artifact for an index; changing it requires re-embedding. Follow the model's retrieval prompt conventions and verify what the installed Ollama template adds. [Terms](https://ai.google.dev/gemma/terms), [EmbeddingGemma library](https://ollama.com/library/embeddinggemma), [Prompt conventions](https://ai.google.dev/gemma/docs/embeddinggemma/model_card).

## Ollama runtime: version, schema, concurrency, and reuse

**Current stable: v0.40.13**, released **2026-10-28**, marked Latest at verification. Pin a common pilot version and record actual server versions; do not infer the server version from the Python package version. [Release](https://github.com/ollama/ollama/releases/tag/v0.40.13), [Latest release](https://github.com/ollama/ollama/releases/latest).

For native local `POST /api/chat`, pass the **schema object** as `format`; `format:"json"` alone requests JSON without the task's field constraints. Also include the schema/rules in the prompt, set temperature 0, and validate the returned `message.content` against the application schema. Ollama documents schema-constrained output, including vision models. This constrains form, not correct labels or truthful evidence. [Structured outputs](https://docs.ollama.com/capabilities/structured-outputs).

Recommended initial request shape (SCREEN; replace the schema for LABEL):

```json
{
  "model": "qwen3.5:4b-q4_K_M",
  "messages": [
    {"role": "system", "content": "Apply the obstacle rubric. Return only the requested schema. Copy evidence verbatim from the supplied passage."},
    {"role": "user", "content": "<rubric, examples, and schema first; passage last>"}
  ],
  "format": {
    "type": "object",
    "properties": {
      "has_obstacle": {"type": "boolean"},
      "evidence": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["has_obstacle", "evidence"],
    "additionalProperties": false
  },
  "think": false,
  "stream": false,
  "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 256},
  "keep_alive": "10m"
}
```

Application checks must require every evidence string to be an **exact substring of the original passage**, then compute offsets in code. Do not silently normalize punctuation or accept paraphrases as quotes. Also check field consistency, permitted enums, completion/truncation, and unsupported spans. An exact quote can still be irrelevant evidence; that requires human or adjudicator review. Use a larger output budget for LABEL, measured against the full schema. [Chat API](https://docs.ollama.com/api/chat).

**`OLLAMA_NUM_PARALLEL` currently defaults to 1.** Memory grows with parallelism × allocated context. Start with `OLLAMA_NUM_PARALLEL=1` and `OLLAMA_MAX_LOADED_MODELS=1` on small workers; benchmark 2 only after measuring headroom. Keep embedding work separate in time or on another worker. Q8 KV can reduce cache memory, with quality/backend tradeoffs; it is separate from Q4 weight quantization. [FAQ](https://docs.ollama.com/faq), [v0.40.13 defaults](https://github.com/ollama/ollama/blob/v0.40.13/envconfig/config.go).

**KV prefix reuse exists, but is local and backend-dependent.** The pinned llama wrapper sends `cache_prompt:true`; the MLX backend maintains a token-prefix trie with cached snapshots and eviction. Keep instructions, examples, and schema identical at the start, place the varying passage last, and keep the model resident. This can save repeated prefill; it does not cache new labels or guarantee hits in every parallel slot. `NUM_PARALLEL` is not a cache-enabling switch. Cache persistence across unload/restart and identical behavior for every model/backend are **UNVERIFIED**. [Pinned llama implementation](https://github.com/ollama/ollama/blob/v0.40.13/llm/llama_server.go), [Pinned MLX cache](https://github.com/ollama/ollama/blob/v0.40.13/mlxrunner/prefix_cache.go).

Current API responses expose `prompt_eval_cached_count`; measure it alongside prompt/evaluation durations and end-to-end latency. Record warm and cold runs, avoid mistakenly counting cached tokens as fresh prefill throughput, and distinguish repeated-prefix savings from output generation speed. [Chat response metrics](https://docs.ollama.com/api/chat).

## Final recommendation

| Role / memory tier | First pilot choice | Alternative / escalation | Initial settings and acceptance criterion |
|---|---|---|---|
| SCREEN: 8 GB GPU / 16 GB Mac | `qwen3.5:4b-q4_K_M` | `qwen3:4b-instruct-2507-q4_K_M`; Gemma E2B for family audit | 4K context, parallel 1, thinking off; choose for high obstacle recall, audit screen negatives. |
| LABEL: 16 GB GPU / 24–32 GB Mac | `gemma4:12b-it-q4_K_M` | `qwen3.5:9b-q4_K_M`; Qwen2.5 14B JSON baseline | 4K–8K, parallel 1, thinking off; select by human agreement and exact-evidence acceptance. |
| ADJUDICATE: ≥24 GB GPU / preferably ≥32 GB Mac | `qwen3.8:27b-q4_K_M` | `gemma4:26b-a4b-it-q4_K_M`; `qwen3.5:27b-q4_K_M` | Short context, parallel 1; compare thinking off/on on hard cases before fixing policy. |
| Embeddings: CPU or any GPU tier | `embeddinggemma:300m-bf16` | `embeddinggemma:300m-qat-q8_0` after retrieval check | 2K limit; fixed artifact; validate held-out retrieval/clustering utility. |

Before corpus-scale use, run a blinded human-labeled pilot stratified by period and obstacle domain, including mention-without-function negatives and ambiguous prose. Track schema validity, exact-span validity, field-level agreement, screen false negatives, and accepted passages/second separately. Sample negatives for LABEL to estimate cascade omissions. Keep research hypotheses and publication dates out of annotation prompts; evaluate temporal error drift and the confounded-null benchmark separately. A larger adjudicator is not ground truth, and same-family agreement is not independent validation.
