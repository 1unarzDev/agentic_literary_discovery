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
   - `yield` / `pause`: finish the current shard, or upload a partial if `until` is near, then unload the model, stop leasing, idle until `until` or a later `run`, and say so in `ald status`.

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

**Unseal (around Nov 9-11, one command):**
1. Register the preregistration on OSF and put its sha256 into `docs/prereg.md`, as today.
2. Call the platform's one-way unseal endpoint with that hash; it is recorded in the append-only audit log. (P) The old Cloudflare `POST /v1/admin/unseal` works the same way for anything still there.
3. Run:
   ```sh
   uv run --project ald --with pyrage python -I pipeline/unseal.py --key /media/usb/ald-sealed.agekey
   ```
   It:
   - reads the prereg hash in `docs/prereg.md`, fetches the unseal record from the platform audit log, and **refuses unless both match** and the unseal time is after the registration;
   - lists every sealed (confirmation) result and partial, downloads the ciphertext, and verifies each `X-Content-Sha256` against the manifest;
   - decrypts with the key and verifies `X-Plain-Sha256`;
   - writes plaintext **only** into `data/work/results_sealed_unsealed/<job_id>/<worker_id>[.part<n>].jsonl.gz`, plus `MANIFEST.json` (counts and hashes);
   - is idempotent: re-running skips files that already verify.
4. `pipeline/sync_results.py --sealed` ingests `data/work/results_sealed_unsealed/` the same way as discovery results.
5. Put the key back offline.

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
