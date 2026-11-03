# ALD migration: Cloudflare coordinator → research platform (`research.lunarz.dev/p/ald`)

Binding inputs: `~/.cache/research/platform/DECISIONS-ALD.md`; SPEC.md follows from the platform owner.
Invariants to preserve: `docs/api_contract.md`, `coordinator/DEPLOY.md`.

Status legend:
- [ ] to do
- [x] done (commit in git log)
- (P) platform-side work, owned by the platform owner `fast-boat-test-loop`

## 1. Endpoints

| today (Cloudflare) | platform | notes |
|---|---|---|
| `https://ald-coordinator.lunarzdev.workers.dev/v1/*` | `https://research.lunarz.dev/p/ald/v1/*` | Same paths, bodies and status codes; see below |
| `/install.sh`, `/install.ps1` | `/p/ald/install.sh`, `/p/ald/install.ps1` | `__COORDINATOR_URL__` → `https://research.lunarz.dev/p/ald` |
| `/dist/<wheel>` | `/p/ald/dist/<wheel>` | `wheel_url` in ping points here |
| `/annotate/<token>` | stays on Cloudflare for now | The offline annotation pipeline is unaffected. Moving it is a separate step |

Same semantics on `/p/ald/v1/*` (P):
- ping: latest/min version, `wheel_url`, registry version, **no queue summary**;
- lease: atomic; dup_group anti-affinity; `skip_passage_ids`; `attempt`; `retry_after` when empty; **new**: `split` per job, and the scheduler directive;
- heartbeat (extend/revoke, plus the directive);
- shard (holder only);
- result: 412 on pin/model_digest mismatch, `duplicate` / `late_duplicate`, 409 on a different sha; partials with `X-Passage-Ids`;
- release; registry with ETag; admin endpoints;
- one-way unseal recorded in an append-only audit log.

Worker tokens are migrated as their sha256 hashes, so existing volunteers keep working without re-joining.

## 2. Client changes (ald)

1. **Redirect.** If `/v1/ping` returns `"redirect": "<base URL>"`, the client:
   - checks that `<redirect>/v1/ping` answers `ok` and serves this project (`project: "ald"`);
   - flushes its outbox to the old coordinator first, since uploads for jobs leased there must finish there;
   - saves `coordinator_url = <redirect>` in its config and restarts its HTTP client;
   - logs `[migrate] coordinator moved to …`.

   To roll back, the platform ping redirects back the same way. A loop guard ignores a redirect to the URL we just left within 1 h.
2. **Scheduler directive.** Lease and heartbeat responses may carry `{"gpu": "run" | "yield" | "pause", "until": iso | null, "reason": "..."}`. The worker obeys:
   - `run`: normal operation.
   - `yield`: the worker uploads a partial if the current shard is less than 50% done, otherwise it finishes the shard. Then it unloads the model and stops leasing until `run`. A heartbeat `yield: [job ids]` naming a held job counts as `yield`.
   - `pause` (also drains): the worker starts nothing new, but the current shard runs to the end (no interruption). Then it unloads and idles.
   - Once `until` has passed, the directive counts as `run`.
   - These semantics apply from ald 0.1.26 on (0.1.23-0.1.25 interrupted on pause and finished on yield).

   `--gpu-lock` and the RAM guard stay until the directive is live.
3. **Sealed results are encrypted on the client.** For jobs with `split == "confirmation"`, the gzip JSONL result (full or partial) is encrypted with age (X25519, `pyrage`) to the project recipient before upload. Details:
   - The recipient comes from ping (`sealed_recipient`). It must equal the recipient pinned in the client release (`ald/src/ald/sealed.py`), so the server cannot swap in its own key. A mismatch means the worker refuses to upload confirmation results and logs it.
   - Headers: `X-Content-Sha256` = sha256 of the uploaded ciphertext; `X-Plain-Sha256` = sha256 of the plaintext gzip (used to verify after unseal); `X-Sealed: age-x25519`.
   - `X-Passage-Ids` (ids only, no labels) and `X-Stats` (counts only) stay readable, so the server can plan skips and throughput.
   - Discovery results are uploaded unencrypted, as today.
   - Until cutover, results keep going to the Cloudflare coordinator unchanged; encryption activates only when the ping offers `sealed_recipient`.
4. **Installers** take the base URL from the host they are served from (already the case), so `/p/ald/install.*` work unchanged.

## 3. Sealed crypto and key ceremony (owner)

**Algorithm.** age v1, X25519 recipient. It is interoperable with the `age` CLI (`age -d -i key.txt`) and with `pyrage`.

**Key generation (once, offline, before cutover):**
1. On a machine you trust, not the platform server, run either `uv run --with pyrage python pipeline/seal_keygen.py --out ~/ald-sealed.agekey` or `age-keygen -o ~/ald-sealed.agekey`.
2. The command prints the **public** recipient `age1…`. Send only that line to the platform and to ald; it is not secret.
3. The **private** key file contains a line `AGE-SECRET-KEY-1…`. Store it:
   - **primary:** an encrypted USB stick (or your password manager's secure file), kept off any server;
   - **backup 1:** a paper copy of the `AGE-SECRET-KEY-1…` line in a sealed envelope, stored somewhere physically separate;
   - **backup 2 (optional):** a second password-manager entry, or a Shamir split (e.g. `ssss-split -t 2 -n 3`) between you and two trusted people.
   - Never put it in the repo, Google Drive, the platform, the archive node or a chat.
4. Delete any copy on the generating machine once the backups are verified (`seal_keygen.py --check` decrypts a test ciphertext).
5. Write the public recipient into `ald/src/ald/sealed.py` (`PINNED_RECIPIENT`) and release a client. The platform serves the same value as `sealed_recipient`.

**Unseal timeline (target Nov 9-11).** On the platform, unseal takes two steps.
- The seal is created with `prereg: {required: true, min_lodge_hours: 24}`. The value is ours to choose when the seal is created; SPEC §4.4 uses 24.
- So the prereg hash must be **lodged at least 24 h before** the unseal: for an unseal on Nov 9 / 10 / 11, lodge by Nov 8 / 9 / 10 at the same hour.

| when | who | step |
|---|---|---|
| before any confirmation work on the platform | owner | key ceremony (above); send the `age1…` line |
| same day | ald | pin the key in `ald.sealed.PINNED_RECIPIENT`, release the client, then `POST /v1/projects/ald/seals {seal_id: "ald-confirmation-v09", recipient, custodian: "owner", prereg: {required: true, min_lodge_hours: 24}}` |
| ≤ Nov 8-10 | owner / PI | register the preregistration on OSF; put the sha256 into `docs/prereg.md`; `uv run --project ald python -I pipeline/unseal.py --lodge --prereg-ref <OSF URL>` (records it in the hash-chained audit log) |
| ≥ 24 h later | owner | `POST /v1/projects/ald/seals/ald-confirmation-v09/unseal {prereg_hash, confirm: "UNSEAL ald ald-confirmation-v09 <hash>"}` (or the one-step `/p/ald/v1/admin/unseal`) |
| right after | owner | `uv run --project ald --with pyrage python -I pipeline/unseal.py --key /media/usb/ald-sealed.agekey` (below) |
| right after | owner | the Cloudflare part (blobs sealed before cutover): `uv run --project ald python -I pipeline/unseal.py --source cloudflare --cloudflare-unseal`. This performs the old coordinator's one-way unseal with the same hash, and needs no key: those blobs were sealed server-side, not encrypted. |

**`pipeline/unseal.py` (one command per source):**
- It reads the prereg hash in `docs/prereg.md` and **refuses unless the seal is `unsealed` with exactly that hash**: `GET /v1/projects/ald/seals/<id>`. For Cloudflare it checks the hash returned by its one-way unseal.
- It downloads every sealed object. Platform: `…/seals/<id>/objects[/<key>]`, which carries cipher and plain sha256. Cloudflare: `/v1/admin/blob`, checked against `content_sha256`.
- It decrypts platform objects with the key file and verifies both hashes.
- It writes plaintext **only** into `data/work/results_sealed_unsealed/<job_id>/<worker_id>[.part<n>].jsonl.gz`, plus `MANIFEST.json`.
- It is idempotent.

Then:
- `pipeline/sync_results.py --sealed` ingests that directory the same way as discovery results.
- The key goes back offline.

Dry runs, tests only:
- `--from-export <synthetic export> --dry-run --out <dir outside data/>`.
- It refuses real sealed data and refuses to write under `data/`.

## 4. Data migration, with manifests

Tools (built): `pipeline/export_for_platform.py` (export + manifests), `pipeline/seal_keygen.py` (key ceremony), `pipeline/unseal.py` (one-command unseal). Staging target (platform decision): `creation:/home/conception/research-import/ald/<stamp>/`, then `research-server import ald <dir>`.

| data | how | verification |
|---|---|---|
| D1 tables `pins, shards, jobs, leases, results, job_partials, workers, invites, seal, config, viewer_tokens` | `wrangler d1 export --remote` → SQL dump + per-table JSON | per-table row counts; jobs per (wave, stage, status) equal before and after |
| R2 `shards/`, `results/` (discovery), `registry/`, `dist/`, `install/` | `wrangler r2 object get` → platform storage | sha256 of every object = D1 `content_sha256` where recorded; `manifest_r2.jsonl` lists key, size and sha256 |
| R2 `sealed/` (confirmation results + partials) | **streamed**: `wrangler r2 object get --pipe` → in-memory age encryption to the project recipient → ciphertext uploaded; plaintext never written to disk (this box or the platform) | plaintext sha256 = D1 `content_sha256`, computed while streaming; the ciphertext sha256 is recorded too; `manifest_sealed.jsonl` holds key, plain_sha256, cipher_sha256, size |
| annotation tables | stay on Cloudflare | n/a |

**Rule: real sealed data is encrypted only to the owner's key.**
- `export_for_platform.py` refuses to encrypt real `sealed/` blobs to anything but `ald.sealed.PINNED_RECIPIENT`, the owner's key, pinned at the key ceremony.
- Dry runs use `--synthetic-sealed`: synthetic stand-ins under the same keys, marked `synthetic`.
- `unseal.py --dry-run` refuses any export that is not synthetic, and refuses to write under `data/`.

These guards exist because a first local test on 2026-11-02 exported 5 real sealed blobs to a throwaway key and decrypted them into `data/work/results_sealed_unsealed/`. The plaintext was deleted unread within minutes. It was never uploaded or committed, and only job and worker ids were seen. The incident is recorded for the preregistration's deviations log.

The R2 originals stay **untouched and readable only by the admin token** until the owner confirms the import. Then: R2 bucket read-only, D1 kept 30 days as a fallback, then retired.

Write freeze: during the export the Cloudflare coordinator is set to `redirect` = platform. Workers flush and move; nothing new is written to D1 after the last worker has moved (check `/v1/fleet`).

## 5. Cutover and rollback

1. (P) The platform serves `/p/ald/v1/*` with imported state. Import the D1 export and R2 objects.
2. Dry run with a **test worker** (`ALD_COORDINATOR=https://research.lunarz.dev/p/ald`) against a `wtest` wave. Check:
   - lease, shard, partial, 412 pin rejection, release;
   - a confirmation job uploads as ciphertext (the server holds only `X-Sealed`);
   - unseal on a throwaway key.
3. Release an ald client with redirect + directive + sealed support. Wait until `/v1/fleet` shows every worker on it.
4. Set the Cloudflare ping `redirect` to `https://research.lunarz.dev/p/ald`.
5. Within ≤ 10 min each worker flushes to Cloudflare, switches, and appears in the platform dashboard. Verify **both** workers (innovation, COLLIN/"harmony") lease and upload there.
6. Freeze Cloudflare: `close_jobs` is not needed, since jobs were imported. Make D1 writes refuse new leases (min_client_version far ahead, or remove the lease route).

**Rollback:** remove the redirect on Cloudflare and set the platform ping `redirect` back to Cloudflare. Clients follow within 10 min. Results uploaded to the platform in between are exported back with the same tool, in reverse.

## 6. Verification checklist

- [ ] D1 → platform row counts per table; jobs per (wave, stage, status) identical.
- [ ] Every R2 object's sha256 = manifest; sealed: plain sha256 = D1 `content_sha256` for every row; ciphertext stored, no plaintext on platform disk.
- [ ] Test worker: lease → shard → full + partial upload → skip_ids on re-lease → late duplicate → 412 on a wrong pin → dup twins never to the same worker.
- [ ] Confirmation upload is ciphertext; platform admin and dashboard cannot read it; `unseal.py` with a throwaway key recovers it bit-exact.
- [ ] Redirect: both real workers move, keep their tokens, keep auto-update (wheel from `/p/ald/dist/`).
- [ ] Directive: `yield` makes a worker finish or partial-upload, unload and idle; `run` resumes.
- [ ] Installers from `/p/ald/install.*` work on a clean container.
- [ ] Annotation UI still works on Cloudflare.
- [ ] Owner confirms; R2 read-only; D1 retired after 30 days.

## 7. Status (2026-11-03) and cutover checklist

**Done:**
- [x] Platform live (`research-cluster e56a6df` on creation): ALD compat API at `https://research.lunarz.dev/p/ald/v1`, per HANDOFF-ALD.md.
- [x] **Compat API verified** with throwaway in-memory test workers (`pipeline/platform_compat_check.py`; discovery-only test campaign `wtest`, throwaway pin). **18/18:**
  - ping (`project: ald`); input, pin and job submit; join via `admin/invite`;
  - stage-filtered lease with `split` and the directive; holder-only shard (sha matches; non-holder 403);
  - **412 on a wrong pin**; partial upload, then **`skip_passage_ids` on re-lease**; full upload, then **`duplicate`**; **403 for a non-leaser**;
  - **dup twins never to the same worker** (`anti_affinity` scope worker); heartbeat extends and carries the directive.
  - The test jobs stay in campaign `wtest` until the platform's campaign close/hide is live.
- [x] **Sealed-stats leak closed** on Cloudflare (migration 0007):
  - Confirmation results store only `{n_lines, wall_s}`; quality counters and fleet quality cover discovery only; per-worker quality rates are not stored.
  - Clients ≥ 0.1.25 never send more for confirmation jobs.
  - The platform applies the same rule server-side, which fast-boat-test-loop has confirmed.
- [x] **Synthetic staging fixture** for the importer at `creation:/home/conception/research-import/ald/synthetic-20261102T230633/`, mode 700. Contents:
  - real D1 export: 5,153 jobs, 66 results, 19 partials, 2 workers;
  - 63 plain objects: 20 shards, 20 results, 20 dist, 2 install, 1 registry;
  - 20 synthetic sealed `.age` stand-ins;
  - manifests (83 entries) verified on creation, 0 mismatches.

**Platform rules relevant to ALD** (live since 2026-11-03 05:23 UTC, crane-server:760f315, migration 0013_blind):
- Sealed (confirmation) results store only `{n_lines, wall_s}`. `n_lines` comes from the `X-Passage-Ids` count, else `n_lines`. Everything else is dropped server-side, and earlier rows were scrubbed after a snapshot.
- Heartbeats on confirmation jobs store no worker stats, and clear existing ones.
- Confirmation jobs show no `attempt`, `last_error` or `stats` on `/v1/projects/ald/jobs`, `/v1/jobs` or the feed.
- `spec.split=confirmation` without `outputs.class=sealed` gets **400**.
  - We build every submitted job with `pipeline/platform_jobs.py` (`rc_job()` → sealed + `seal_id` for confirmation, summary for discovery; `check_jobs()` guards a batch).
  - The ald client never submits jobs; it only uploads results.
- Panel sections pushed with `PUT /v1/projects/ald/panel` that mention confirmation or the seal may only be **progress**, **workers** or **milestone**, otherwise 400. `pipeline/platform_jobs.panel_section(concerns_sealed=True)` enforces that, and also rejects outcome-related terms.

**Privacy:**
- `GET /v1/projects/ald/panel` needs an ald viewer or admin token, or the owner's PIN cookie; anonymous callers get **401**.
- The public `/v1/feed` and its SSE stream exclude ald.
- `/v1/feed/private` includes it for authorized callers.
- Our viewer token is `~/.config/research-cluster/ald-viewer.token`, mode 600.

**Campaign routes (ald submitter/admin):**
- `POST /v1/projects/ald/campaigns/<c>/cancel` and `.../close`.
- `POST .../hide` returns 409 while any job is queued or leased; `.../unhide` reverses it.
- Done: the platform closed and hid campaign `wtest` (2 jobs) and disabled test workers `w_d63a93bcb6fefeae` and `w_2ed0063753b31e53`.

**Cutover checklist:**
1. [ ] (P) Importer `research-server import ald <dir>` passes on the synthetic fixture, with a report.
2. [ ] Owner key ceremony → `PINNED_RECIPIENT` → client release → seal `ald-confirmation-v09` created with `min_lodge_hours: 24`.
3. [ ] Wheel + release + installers + registry uploaded to `/p/ald` (`PUT /v1/projects/ald/dist|releases|install`, `/p/ald/v1/admin/registry`).
4. [ ] Pins registered; shard inputs uploaded; the unfinished queue re-submitted as rc-job/1 with the same ids:
   - `dup_group` → `anti_affinity.keys`, scope host;
   - discovery jobs get `outputs.class=summary`;
   - confirmation jobs get `class=sealed, seal_id`.
5. [ ] Workers imported: `POST /p/ald/v1/admin/workers` with the D1 rows (`token_sha256` unchanged).
6. [ ] Freeze leasing on Cloudflare (all workers on a client with redirect support, ≥ 0.1.23); then set Cloudflare's ping `redirect` to `https://research.lunarz.dev/p/ald`.
7. [ ] Verify both workers (innovation, COLLIN/"harmony") lease and upload on the platform. Keep Cloudflare up for late uploads.
8. [ ] Real export (owner key) → importer → owner confirms → R2 read-only → D1 retired after 30 days.

**Rollback:** clear the Cloudflare redirect, and set `/p/ald/v1/admin/redirect` back to Cloudflare. Clients follow within 10 min.

