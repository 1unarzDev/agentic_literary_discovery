# Deploying the ALD coordinator

Run everything from `coordinator/`. Nothing here has been deployed yet.

## One-time setup

```sh
cd coordinator
npm install

# 1. Log in (opens a browser)
npx wrangler login

# 2. Create the D1 database. Copy the printed database_id into wrangler.toml
#    ([[d1_databases]] database_id = "...").
npx wrangler d1 create ald

# 3. Create the R2 bucket, then set bucket_name = "ald" in wrangler.toml
#    ([[r2_buckets]]).
npx wrangler r2 bucket create ald

# 4. Apply the schema to the remote database
npx wrangler d1 migrations apply ald --remote

# 5. Set the admin token (paste a long random value, e.g. from `openssl rand -base64 32`)
npx wrangler secret put ADMIN_TOKEN

# 6. Deploy (the deploy script regenerates src/annotate_html.ts first)
npm run deploy
```

Wrangler prints the URL, `https://ald-coordinator.<account>.workers.dev`. Check it with:

```sh
curl https://ald-coordinator.<account>.workers.dev/v1/ping
```

The Cron trigger (`*/5 * * * *`, which reclaims expired leases) is registered on deploy. `/v1/lease` also reclaims lazily.

## Later deploys

```sh
npm test                                          # local; no account needed
npx wrangler d1 migrations apply ald --remote     # only when migrations/ changed
npm run deploy
```

## Seeding (admin token in `$T`, URL in `$U`)

```sh
H="Authorization: Bearer $T"
curl -X PUT  -H "$H" --data-binary @registry/models.v1.json $U/v1/admin/registry
curl -X POST -H "$H" -H 'content-type: application/json' -d '{"n":5}' $U/v1/admin/invite
curl -X PUT  -H "$H" --data-binary @dist/ald-0.1.0-py3-none-any.whl $U/v1/admin/dist/ald-0.1.0-py3-none-any.whl
curl -X PUT  -H "$H" -H 'content-type: application/json' -d '{"version":"0.1.0","min_version":"0.1.0"}' $U/v1/admin/client_release
curl -X PUT  -H "$H" --data-binary @install.sh  $U/v1/admin/install/install.sh
curl -X PUT  -H "$H" --data-binary @install.ps1 $U/v1/admin/install/install.ps1
```

## Local development

```sh
cp .dev.vars.example .dev.vars
npx wrangler d1 migrations apply ald --local
npm run dev                                       # http://localhost:8787
```

## Free-tier notes

- The result index has one D1 row per uploaded shard result or partial, never one per passage.
- Bulk admin inserts (jobs, invites, annotation items) each run as a single `INSERT … SELECT FROM json_each(?)` statement, which keeps them within the per-invocation query limit.
- If D1 writes approach the daily free cap, the fix is the $5 Workers plan. No code changes are needed.

## Behaviour beyond `docs/api_contract.md` (for the `ald` client)

- **Statuses:**
  - A full `PUT /v1/result` returns `stored`, `duplicate`, or `late_duplicate` (when another worker already has a full result for the job). Late uploads are accepted from any worker that ever leased the job; anyone else gets 403.
  - `?partial=1` returns `{status: stored|duplicate, part_n, r2_key, n_ids}`.
- **`X-Passage-Ids`** (used with `?partial=1`): `base64(gzip(JSON array of passage_id strings))`. Plain `base64(JSON)` is also accepted. If the header is omitted, the server reads `passage_id` from each line of the blob.
- **`/v1/lease`:**
  - Each job also includes `attempt` and `skip_passage_ids`. `lease_expires` is an ISO-8601 UTC string.
  - The client version comes from the `X-Client-Version` header if present, otherwise from the version recorded at join.
  - A 426 response body includes `min_client_version`, `latest_client_version` and `wheel_url`.
- **Heartbeat:** a heartbeat sets the expiry to `max(current expiry, now + 10 min)`. `revoked` lists every requested job that was not extended: expired and reassigned, closed, done, or its pin deactivated. Jobs revoked because their pin was deactivated go back to the queue.
- **Release** and **revocation by pin deactivation** do not count as failed attempts. Only lease expiry counts toward the limit of 3 attempts, after which the job is `dead`.
- **`priority`:** lower numbers are served first. The default is 100.
- **`cell`:** jobs may carry an optional `cell` string, which `/v1/status` aggregates into `cells`.
- **Registry tiers:** if the registry JSON has `tiers: {"<tier>": {"stages": [...]}}` (or `{"<tier>": [...]}`), leases are limited to those stages. Without a tier table, the stages the worker requests are trusted.
- **R2 layout:**
  - Confirmation results go under `sealed/results/<job_id>/<worker_id>.jsonl.gz`, with partials at `….part<n>.jsonl.gz`.
  - Discovery results use the same paths without the `sealed/` prefix.
- **Endpoints:**
  - Admin-only: `PUT /v1/admin/dist/<file>`, `PUT /v1/admin/client_release`, `PUT /v1/admin/install/<install.sh|install.ps1>`.
  - Public (no auth): `/v1/ping`, `/v1/registry`, `/v1/bwtest`, `/dist/<file>`, `/install.sh`, `/install.ps1`.

## Human annotation (blind UI at `/annotate/<token>`, guide at `/annotate/guide`)

- Sets: `review` (expert reader adjudicates the practice/cert/retake key: the reference + rationale are shown before answering; never gates), `practice` (20 items, the reference + rationale are shown after each answer), `cert` (20, no feedback), `retake` (20, offered once if cert fails), `audit` (main set) and `teaching` (student only).
- Gate: an annotator with practice/cert items must finish practice, then pass cert (locus kappa >= 0.60 on none/material/social/internal, and obstacle yes vs not-yes agreement >= 0.75), before `audit`/`teaching` unlock. Annotators without gate items (the expert) are never gated. Override with `POST /v1/admin/ann_cert {name, decision: pass|revoke|clear}`.
- Admin: `POST /v1/admin/annotators`, `POST /v1/admin/ann_items` (<= 250 per call; `reference` is required on practice/cert/retake and refused elsewhere), `GET /v1/admin/ann_labels` (`practice: true` marks gate-set labels), `GET /v1/admin/ann_status` (per-queue progress + cert status and scores).
- The guide page is rendered from `docs/annotator_guide.md` by `scripts/build-html.mjs` (run by test/dev/deploy).
- Day-to-day use goes through `pipeline/annotators.py` (create / links / upload / export / progress) and `analysis/build_annotation_queues.py` (practice / build).
