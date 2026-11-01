# Ollama runtime verification — 2026-10-31

Primary-source checks for the model-selection report. These are web/source checks, not local performance tests.

## Version

The official GitHub `releases/latest` endpoint redirects to **v0.40.13**; its release page is marked Latest and shows release on **28 October 2026**, 19:55 (page display; timezone UNVERIFIED). The release specifically adds LFM3 Linux/Windows support alongside Apple Silicon. Pin this version for the pilot, then record the actual client/server version on every volunteer. [Official release](https://github.com/ollama/ollama/releases/tag/v0.40.13), [latest endpoint](https://github.com/ollama/ollama/releases/latest).

## JSON schema and thinking

For native local `POST /api/chat`, send the schema object as `format`, rather than merely `"format":"json"` (which requests JSON without your field constraints). Ollama recommends also describing the schema in the prompt, temperature 0, and Pydantic/Zod validation. Its cloud service currently does not support structured outputs. [Structured outputs](https://docs.ollama.com/capabilities/structured-outputs).

The pinned llama backend passes schemas as `json_schema` and uses a grammar for JSON; thinking-aware formats can constrain the answer after reasoning. This establishes constrained generation, **not semantic accuracy or verbatim evidence fidelity**. Reject truncated/invalid output and require each evidence string to be an exact substring of the original passage. No model-specific correctness guarantee follows from API schema support. [v0.40.13 implementation](https://github.com/ollama/ollama/blob/v0.40.13/llm/llama_server.go).

Current API docs say `think:false` requests no thinking output, but supported values/defaults are model-specific and discoverable through `/api/show`; named thinking levels must match those reported by the model. Do not assume every reasoning model can disable reasoning. Responses include `prompt_eval_cached_count`, and `prompt_eval_duration` measures uncached prompt evaluation; use those alongside total latency and generated-token rate. [Chat API](https://docs.ollama.com/api/chat).

## Parallelism, cache, and memory

`OLLAMA_NUM_PARALLEL` currently defaults to **1**. The FAQ says memory scales with parallel requests × context length; e.g. four 2K requests allocate 8K of context. Begin at 1 on small volunteers, then benchmark 2/4 only with measured headroom. `OLLAMA_MAX_LOADED_MODELS` controls separate loaded models and is different from within-model parallelism. The FAQ reports default context 4096; set `options.num_ctx` explicitly. KV defaults to f16; q8_0 uses approximately half its memory with precision tradeoffs. Flash Attention is automatic where supported. These controls are backend-dependent. [FAQ](https://docs.ollama.com/faq), [pinned default source](https://github.com/ollama/ollama/blob/v0.40.13/envconfig/config.go).

Prefix reuse is **real but backend-dependent**, not a cluster-wide persistent cache. In v0.40.13, the llama-server wrapper enables `cache_prompt:true` for both internal generation/chat paths. Its timings distinguish cached from newly evaluated prompt tokens. [Pinned llama wrapper](https://github.com/ollama/ollama/blob/v0.40.13/llm/llama_server.go).

The MLX backend explicitly maintains a compressed token-prefix trie shared across conversations, restores matching snapshots, evaluates the remainder, and evicts snapshots above its memory budget. Generation retains at least one seed token to evaluate. [Pinned MLX prefix implementation](https://github.com/ollama/ollama/blob/v0.40.13/mlxrunner/prefix_cache.go).

Operational inference: keep instructions, annotation rules, examples, and schema stable at the beginning; append the changing passage last; keep the model resident and route repeat jobs consistently to a worker. Cache survival across unloads/restarts, identical behavior across all architectures/backends, and exact concurrent cache hit rates are **UNVERIFIED**. Increasing NUM_PARALLEL is not a prefix-reuse switch; verify actual cached-token counts and warm/cold latency.

## Platforms

Official hardware docs include RTX 4070 Ti SUPER under supported NVIDIA compute capability 8.9 GPUs and support Apple GPU acceleration through Metal. Current NVIDIA requirements are driver 550+ (570+ for older 5.0–6.2 devices). [Hardware support](https://docs.ollama.com/gpu).

Use native Ollama on macOS for GPU inference: the FAQ says Docker Desktop on macOS lacks GPU passthrough; Linux/Windows WSL2 Docker GPU inference needs the NVIDIA container toolkit. Confirm `ollama ps` shows full GPU placement before accepting timing results. [FAQ](https://docs.ollama.com/faq).
