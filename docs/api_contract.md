# Coordinator API contract (v1)

Base URL: `https://ald-coordinator.<account>.workers.dev`. Every request body and response is JSON unless noted. Auth uses `Authorization: Bearer <token>`. There are three token kinds:

- **worker**: issued by `/v1/join`.
- **admin**: stored as the Worker secret `ADMIN_TOKEN`.
- **annotator**: created by an admin, used only under `/annotate/*`.

Only the sha256 of each token is stored in D1.

## Concepts
- **stage**: `screen` | `label` | `adjudicate` | `cloze` | `embed`.
- **pin**: `{pin_hash, stage, model_ref, model_digest, prompt_hash, schema_hash, options}`. Registered by an admin. A job references one `pin_hash`.
- **job**: one shard (≈500 passages) for one pin. Shards live in R2 at `shards/<wave>/<shard_id>.jsonl.gz`. If `dup_group` is non-null, the job has a twin that must go to a different worker.
- **result**: a JSONL.gz blob at R2 `results/<job_id>/<worker_id>.jsonl.gz`.
- **split**: every shard is `discovery` or `confirmation`. Confirmation result blobs are stored under `sealed/` and are listed/downloadable only after `POST /v1/admin/unseal` with `{prereg_hash}`.

## Worker endpoints
| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/v1/join` | `{invite, name, os, arch, gpu, vram_gb, ram_gb, tier, client_version}` | `{worker_id, token}` |
| POST | `/v1/lease` | `{tier, stages:[...], max_jobs}` | `{jobs:[{job_id, stage, pin_hash, shard_url, n_passages, lease_expires}]}`. The lease is atomic. It skips jobs whose `dup_group` sibling is held or completed by the same worker, and requires `client_version >= MIN_CLIENT_VERSION` (else 426). |
| POST | `/v1/heartbeat` | `{job_ids:[...], stats:{tok_s, passages_done}}` | `{extended:[job_id], revoked:[job_id]}`. Each extension adds 10 min. |
| GET | `/v1/shard/<job_id>` | (none) | Streams the gzip shard, but only to the lease holder; anyone else gets 403. |
| PUT | `/v1/result/<job_id>` | Raw gzip body. Headers: `X-Content-Sha256`, `X-Pin-Hash`, `X-Model-Digest`, `X-Backend-Version`, `X-Stats` (JSON: `n_ok, n_flagged, tok_s, wall_s, prompt_tokens, gen_tokens`) | 200 `{status:"stored"}`, 200 `{status:"duplicate"}` if the same sha was already stored, 409 if this worker already uploaded a different sha, 412 if the pin or digest mismatches. On success the job is marked `done`. |
| POST | `/v1/release` | `{job_ids:[...]}` | Returns the jobs to the queue (used on Ctrl-C). |
| GET | `/v1/registry` | (none) | The current `models.v1.json` (stored in R2 at `registry/models.v1.json`). |
| GET | `/v1/ping` | (none) | `{ok:true, min_client_version}`. Doctor also uses `GET /v1/bwtest` (a 10 MB R2 object) for the bandwidth test. |

## Admin endpoints (admin token)
| Method | Path | Body / notes |
|---|---|---|
| POST | `/v1/admin/invite` | `{n}` → `{invites:[...]}` (single use) |
| POST | `/v1/admin/pin` | The pin object above. Idempotent. |
| PUT | `/v1/admin/shard/<wave>/<shard_id>` | Raw gzip upload. Headers: `X-Split`, `X-N-Passages`, `X-Decades` (CSV). |
| POST | `/v1/admin/jobs` | `{jobs:[{job_id, stage, wave, shard_key, pin_hash, n_passages, split, dup_group, priority}]}`. Batch insert, at most 500 per call. |
| POST | `/v1/admin/close_jobs` | `{job_ids}`: cancels queued jobs (adaptive stopping). |
| GET | `/v1/admin/results?since=<iso>&split=discovery` | `{results:[{job_id, worker_id, r2_key, content_sha256, stats, created}]}` |
| GET | `/v1/admin/blob?key=<r2_key>` | Raw blob. Keys under `sealed/` are refused until unsealed. |
| POST | `/v1/admin/unseal` | `{prereg_hash}`. Recorded once and never reversible. |
| GET | `/v1/status` | `{workers:[{id,name,tier,os,last_seen,passages_1h,passages_24h,tok_s}], queue:{<stage>:{queued,leased,done,dead}}, eta_hours:{<stage>}, cells:[...]}` |
| PUT | `/v1/admin/registry` | Upload `models.v1.json`. |

## Annotation endpoints
Admin endpoints:
- `POST /v1/admin/annotators` with `{name}` → `{token}`.
- `POST /v1/admin/ann_items` with `{items:[{item_id, passage_id, text, ctx_before, ctx_after, set:"teaching|audit", assign:[annotator names]}]}`. Items **never carry model labels, title, author or date**.
- `GET /v1/admin/ann_labels` → every label row.

Annotator endpoints:
- `GET /annotate/<token>`: the HTML UI.
- `GET /annotate/<token>/next` → the next unlabeled assigned item, in a per-annotator seeded order: `{item_id, text, ctx_before, ctx_after, progress:{done,total}}`.
- `POST /annotate/<token>/label` with `{item_id, label_json, evidence_text, seconds_spent}`.
- `POST /annotate/<token>/undo`.

## Result line schema (one JSON object per passage)
```json
{"passage_id":"pg1342_p0017","stage":"label","pin_hash":"...","model_digest":"...","backend_version":"0.x",
 "output":{...stage schema...},"valid_schema":true,
 "evidence":[{"quote":"...","start":123,"end":180,"status":"exact|normalized|fuzzy_flag|hallucinated"}],
 "latency_ms":812,"prompt_tokens":905,"gen_tokens":120}
```

## Shard line schema
```json
{"passage_id":"pg1342_p0017","work_id":"pg1342","decade":1810,"stratum":"random|enrich_comm|enrich_mob|enrich_dark",
 "text":"...","ctx_before":"...","ctx_after":"...","text_sha256":"..."}
```
