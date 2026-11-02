import { Hono } from "hono";
import { AppEnv, requireWorker } from "./auth";
import { CFG, getConfig, leaseJobs, leaseTtlMs, minClientVersion, reclaimExpired } from "./db";
import { REGISTRY_KEY, stagesForTier } from "./registry";
import {
  HttpError,
  STAGES,
  base64ToBytes,
  compareVersions,
  gunzipToText,
  intVar,
  isStringArray,
  json,
  nowIso,
  randomId,
  randomToken,
  readJson,
  sha256Hex,
} from "./util";

export const workerRoutes = new Hono<AppEnv>();

export const BWTEST_KEY = "bwtest/10mb.bin";
export const BWTEST_BYTES = 10 * 1024 * 1024;

export function wheelUrl(origin: string, file: string | undefined): string | null {
  return file ? `${origin}/dist/${file}` : null;
}

/** Strip an optional "sha256:" prefix and lowercase, so Ollama-style and bare digests compare equal. */
export function normDigest(d: string | null | undefined): string {
  return (d ?? "").trim().toLowerCase().replace(/^sha256:/, "");
}

// ------------------------------------------------------------------ public

workerRoutes.get("/v1/ping", async (c) => {
  const cfg = await getConfig(c.env);
  return json({
    ok: true,
    min_client_version: cfg[CFG.minClientVersion] ?? c.env.MIN_CLIENT_VERSION ?? "0.0.0",
    latest_client_version: cfg[CFG.latestClientVersion] ?? null,
    wheel_url: wheelUrl(new URL(c.req.url).origin, cfg[CFG.wheelFile]),
    registry_version: parseInt(cfg[CFG.registryVersion] ?? "0", 10),
    queue: await queueSummary(c.env),
  });
});

// Worker-visible queue summary (no per-worker detail): remaining passages per stage, used for client ETA.
async function queueSummary(env: { DB: D1Database }) {
  const rs = await env.DB.prepare(
    "SELECT stage, status, COUNT(*) AS n, COALESCE(SUM(n_passages),0) AS p FROM jobs GROUP BY stage, status",
  ).all<{ stage: string; status: string; n: number; p: number }>();
  const out: Record<string, Record<string, { jobs: number; passages: number }>> = {};
  for (const r of rs.results ?? []) {
    (out[r.stage] ??= {})[r.status] = { jobs: r.n, passages: r.p };
  }
  return out;
}

workerRoutes.get("/v1/registry", async (c) => {
  const cfg = await getConfig(c.env);
  const etag = cfg[CFG.registryEtag];
  if (!etag) throw new HttpError(404, "no registry uploaded");
  const quoted = `"${etag}"`;
  const headers = {
    etag: quoted,
    "x-registry-version": cfg[CFG.registryVersion] ?? "0",
    "cache-control": "no-cache",
  };
  const inm = c.req.header("if-none-match");
  if (inm && inm.split(",").some((t) => t.trim().replace(/^W\//, "") === quoted || t.trim() === "*")) {
    return new Response(null, { status: 304, headers });
  }
  const obj = await c.env.BUCKET.get(REGISTRY_KEY);
  if (!obj) throw new HttpError(404, "no registry uploaded");
  return new Response(obj.body, { headers: { ...headers, "content-type": "application/json; charset=utf-8" } });
});

workerRoutes.get("/v1/bwtest", async (c) => {
  let obj = await c.env.BUCKET.get(BWTEST_KEY);
  if (!obj) {
    // 64 KiB of random bytes tiled to 10 MiB: cheap on CPU and, served as
    // application/octet-stream, not compressed in transit.
    const block = new Uint8Array(65536);
    crypto.getRandomValues(block);
    const buf = new Uint8Array(BWTEST_BYTES);
    for (let off = 0; off < BWTEST_BYTES; off += block.length) buf.set(block, off);
    await c.env.BUCKET.put(BWTEST_KEY, buf, { httpMetadata: { contentType: "application/octet-stream" } });
    obj = await c.env.BUCKET.get(BWTEST_KEY);
    if (!obj) throw new HttpError(500, "bwtest object unavailable");
  }
  return new Response(obj.body, {
    headers: {
      "content-type": "application/octet-stream",
      "content-length": String(obj.size),
      "cache-control": "no-store",
    },
  });
});

// ------------------------------------------------------------------ join

workerRoutes.post("/v1/join", async (c) => {
  const b = await readJson<Record<string, unknown>>(c.req.raw);
  const invite = b.invite;
  const name = b.name;
  if (typeof invite !== "string" || !invite) throw new HttpError(400, "invite required");
  if (typeof name !== "string" || !name.trim() || name.length > 100) throw new HttpError(400, "name required (<=100 chars)");
  const str = (v: unknown) => (typeof v === "string" ? v.slice(0, 200) : null);
  const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : null);
  const workerId = randomId("w_");
  const token = randomToken();
  const now = nowIso();
  const inviteSha = await sha256Hex(invite);
  // One transaction: the worker row is inserted only if the invite is unused,
  // and the invite is consumed only by that worker. Concurrent joins with the
  // same invite serialize; the second inserts nothing.
  const [ins] = await c.env.DB.batch([
    c.env.DB.prepare(
      `INSERT INTO workers(id, token_sha256, name, os, arch, gpu, vram_gb, ram_gb, tier, client_version, created, last_seen)
       SELECT ?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?11
        WHERE EXISTS (SELECT 1 FROM invites WHERE code_sha256 = ?12 AND used_by IS NULL)`,
    ).bind(
      workerId,
      await sha256Hex(token),
      name.trim(),
      str(b.os),
      str(b.arch),
      str(b.gpu),
      num(b.vram_gb),
      num(b.ram_gb),
      str(b.tier),
      str(b.client_version),
      now,
      inviteSha,
    ),
    c.env.DB.prepare(
      `UPDATE invites SET used_by = ?1, used_at = ?2
        WHERE code_sha256 = ?3 AND used_by IS NULL AND EXISTS (SELECT 1 FROM workers WHERE id = ?1)`,
    ).bind(workerId, now, inviteSha),
  ]);
  if (!ins.meta.changes) throw new HttpError(403, "invalid or used invite");
  return json({ worker_id: workerId, token });
});

// ------------------------------------------------------------------ authed

workerRoutes.use("/v1/lease", requireWorker);
workerRoutes.use("/v1/heartbeat", requireWorker);
workerRoutes.use("/v1/release", requireWorker);
workerRoutes.use("/v1/shard/*", requireWorker);
workerRoutes.use("/v1/result/*", requireWorker);

workerRoutes.post("/v1/lease", async (c) => {
  const w = c.get("worker");
  const b = await readJson<Record<string, unknown>>(c.req.raw);
  const stages = b.stages;
  if (!isStringArray(stages) || stages.length === 0) throw new HttpError(400, "stages must be a non-empty array");
  const bad = stages.filter((s) => !(STAGES as readonly string[]).includes(s));
  if (bad.length) throw new HttpError(400, `unknown stage(s): ${bad.join(",")}`);
  const cap = intVar(c.env.MAX_LEASE_JOBS, 16);
  const maxJobs = b.max_jobs === undefined ? 1 : Number(b.max_jobs);
  if (!Number.isInteger(maxJobs) || maxJobs < 1) throw new HttpError(400, "max_jobs must be a positive integer");

  // Client version: X-Client-Version header (or body.client_version) overrides
  // the version recorded at join, and is persisted when it changes.
  const reported = c.req.header("x-client-version") ?? (typeof b.client_version === "string" ? b.client_version : null);
  const clientVersion = reported ?? w.client_version ?? "0.0.0";
  const minV = await minClientVersion(c.env);
  if (compareVersions(clientVersion, minV) < 0) {
    const cfg = await getConfig(c.env);
    throw new HttpError(426, "client too old", {
      min_client_version: minV,
      latest_client_version: cfg[CFG.latestClientVersion] ?? null,
      wheel_url: wheelUrl(new URL(c.req.url).origin, cfg[CFG.wheelFile]),
    });
  }

  const tier = typeof b.tier === "string" ? b.tier : w.tier;
  const tierStages = await stagesForTier(c.env, tier);
  const allowed = tierStages === null ? stages : stages.filter((s) => tierStages.includes(s));

  const now = Date.now();
  await reclaimExpired(c.env, now); // cheap; cron does the same every 5 min
  const jobs = allowed.length ? await leaseJobs(c.env, w.id, allowed, Math.min(maxJobs, cap), now) : [];
  await c.env.DB.prepare(
    "UPDATE workers SET last_seen = ?2, client_version = COALESCE(?3, client_version), tier = COALESCE(?4, tier) WHERE id = ?1",
  )
    .bind(w.id, nowIso(now), reported, typeof b.tier === "string" ? b.tier : null)
    .run();
  const origin = new URL(c.req.url).origin;
  return json({
    jobs: jobs.map((j) => ({
      job_id: j.job_id,
      stage: j.stage,
      pin_hash: j.pin_hash,
      shard_url: `${origin}/v1/shard/${encodeURIComponent(j.job_id)}`,
      n_passages: j.n_passages,
      lease_expires: nowIso(j.lease_expires),
      attempt: j.attempt,
      skip_passage_ids: j.skip_passage_ids,
    })),
  });
});

workerRoutes.post("/v1/heartbeat", async (c) => {
  const w = c.get("worker");
  const b = await readJson<Record<string, unknown>>(c.req.raw);
  const ids = b.job_ids ?? [];
  if (!isStringArray(ids)) throw new HttpError(400, "job_ids must be an array of strings");
  const stats = (b.stats && typeof b.stats === "object" ? b.stats : {}) as Record<string, unknown>;
  const tokS = typeof stats.tok_s === "number" && Number.isFinite(stats.tok_s) ? stats.tok_s : null;
  const done = typeof stats.passages_done === "number" && Number.isFinite(stats.passages_done) ? Math.trunc(stats.passages_done) : null;
  const now = Date.now();
  const idsJson = JSON.stringify(ids);
  const report = sanitizeWorkerStats(stats);
  const [, ext] = await c.env.DB.batch([
    // Jobs whose pin was deactivated go straight back to the queue (not
    // counted as a failed attempt) and are reported as revoked.
    c.env.DB.prepare(
      `UPDATE jobs SET status = 'queued', lease_worker = NULL, lease_expires = NULL, attempt = MAX(attempt - 1, 0)
        WHERE status = 'leased' AND lease_worker = ?1 AND job_id IN (SELECT value FROM json_each(?2))
          AND pin_hash IN (SELECT pin_hash FROM pins WHERE active = 0)`,
    ).bind(w.id, idsJson),
    // Extension: expiry becomes max(current, now + TTL), i.e. a heartbeat
    // guarantees at least TTL (10 min) from now without unbounded growth.
    c.env.DB.prepare(
      `UPDATE jobs SET lease_expires = MAX(COALESCE(lease_expires, 0), ?3)
        WHERE status = 'leased' AND lease_worker = ?1 AND job_id IN (SELECT value FROM json_each(?2))
        RETURNING job_id`,
    ).bind(w.id, idsJson, now + leaseTtlMs(c.env)),
    c.env.DB.prepare(
      `UPDATE workers SET last_seen = ?2, tok_s = COALESCE(?3, tok_s), passages_done = COALESCE(?4, passages_done),
              stats_json = COALESCE(?5, stats_json) WHERE id = ?1`,
    ).bind(w.id, nowIso(now), tokS, done, report),
  ]);
  const extended = new Set((ext.results as { job_id: string }[]).map((r) => r.job_id));
  return json({
    extended: ids.filter((id) => extended.has(id)),
    revoked: [...new Set(ids.filter((id) => !extended.has(id)))],
  });
});

// Worker self-report shown in the fleet view. Only these keys, only scalars, short strings.
const STAT_KEYS = [
  "tok_s", "passages_done", "state", "stage", "job_id", "progress", "concurrency", "passages_per_hour",
  "keep_awake", "battery_percent", "power_plugged", "gpu_fraction", "gpu", "client_version", "service", "gpu_lock",
  "quality_stage", "schema_fail_rate", "evidence_fail_rate", "next_window", "may_sleep",
] as const;

export function sanitizeWorkerStats(stats: Record<string, unknown>): string | null {
  const out: Record<string, unknown> = {};
  for (const k of STAT_KEYS) {
    const v = stats[k];
    if (typeof v === "number" && Number.isFinite(v)) out[k] = v;
    else if (typeof v === "boolean" || v === null) out[k] = v;
    else if (typeof v === "string") out[k] = v.slice(0, 120);
  }
  return Object.keys(out).length ? JSON.stringify(out) : null;
}

workerRoutes.post("/v1/release", async (c) => {
  const w = c.get("worker");
  const b = await readJson<Record<string, unknown>>(c.req.raw);
  const ids = b.job_ids ?? [];
  if (!isStringArray(ids)) throw new HttpError(400, "job_ids must be an array of strings");
  // A voluntary release (Ctrl-C) does not count as a failed attempt.
  const { results } = await c.env.DB.prepare(
    `UPDATE jobs SET status = 'queued', lease_worker = NULL, lease_expires = NULL, attempt = MAX(attempt - 1, 0)
      WHERE status = 'leased' AND lease_worker = ?1 AND job_id IN (SELECT value FROM json_each(?2))
      RETURNING job_id`,
  )
    .bind(w.id, JSON.stringify(ids))
    .all<{ job_id: string }>();
  return json({ released: results.map((r) => r.job_id) });
});

workerRoutes.get("/v1/shard/:job_id", async (c) => {
  const w = c.get("worker");
  const job = await c.env.DB.prepare("SELECT shard_key, status, lease_worker FROM jobs WHERE job_id = ?")
    .bind(c.req.param("job_id"))
    .first<{ shard_key: string; status: string; lease_worker: string | null }>();
  if (!job || job.status !== "leased" || job.lease_worker !== w.id) throw new HttpError(403, "not the lease holder");
  const obj = await c.env.BUCKET.get(job.shard_key);
  if (!obj) throw new HttpError(404, "shard blob missing");
  const headers: Record<string, string> = {
    "content-type": "application/gzip",
    "content-length": String(obj.size),
  };
  const sha = obj.customMetadata?.content_sha256;
  if (sha) headers["x-content-sha256"] = sha;
  return new Response(obj.body, { headers });
});

// ------------------------------------------------------------------ results

interface JobForUpload {
  job_id: string;
  stage: string;
  pin_hash: string;
  split: string;
  status: string;
  n_passages: number;
  pin_digest: string;
}

/** X-Passage-Ids: base64 of gzip(JSON array of strings). Plain base64 JSON (no gzip) is also accepted. */
export async function decodePassageIdsHeader(h: string): Promise<string[]> {
  let ids: unknown;
  try {
    const bytes = base64ToBytes(h);
    const text = bytes[0] === 0x1f && bytes[1] === 0x8b ? await gunzipToText(bytes) : new TextDecoder().decode(bytes);
    ids = JSON.parse(text);
  } catch {
    throw new HttpError(400, "X-Passage-Ids must be base64(gzip(JSON array))");
  }
  if (!isStringArray(ids)) throw new HttpError(400, "X-Passage-Ids must decode to an array of strings");
  return ids;
}

async function passageIdsFromBlob(body: ArrayBuffer): Promise<string[]> {
  let text: string;
  try {
    text = await gunzipToText(body);
  } catch {
    throw new HttpError(400, "body is not valid gzip");
  }
  const ids: string[] = [];
  for (const line of text.split("\n")) {
    if (!line.trim()) continue;
    try {
      const o = JSON.parse(line) as { passage_id?: unknown };
      if (typeof o.passage_id === "string") ids.push(o.passage_id);
    } catch {
      throw new HttpError(400, "body contains a line that is not JSON");
    }
  }
  return ids;
}

workerRoutes.put("/v1/result/:job_id", async (c) => {
  const w = c.get("worker");
  const jobId = c.req.param("job_id");
  const partial = c.req.query("partial") === "1";
  const job = await c.env.DB.prepare(
    `SELECT j.job_id, j.stage, j.pin_hash, j.split, j.status, j.n_passages, p.model_digest AS pin_digest
       FROM jobs j JOIN pins p ON p.pin_hash = j.pin_hash WHERE j.job_id = ?`,
  )
    .bind(jobId)
    .first<JobForUpload>();
  if (!job) throw new HttpError(404, "unknown job");
  // Any worker that ever held a lease on this job may upload, including after
  // its lease expired or the job was reassigned (late uploads are accepted).
  const held = await c.env.DB.prepare("SELECT 1 AS x FROM leases WHERE job_id = ? AND worker_id = ? LIMIT 1")
    .bind(jobId, w.id)
    .first();
  if (!held) throw new HttpError(403, "this worker never leased the job");

  const sha = (c.req.header("x-content-sha256") ?? "").trim().toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(sha)) throw new HttpError(400, "X-Content-Sha256 must be a hex sha256");
  const pinHash = c.req.header("x-pin-hash");
  const digest = c.req.header("x-model-digest");
  if (!pinHash || !digest) throw new HttpError(400, "X-Pin-Hash and X-Model-Digest are required");
  if (pinHash !== job.pin_hash || normDigest(digest) !== normDigest(job.pin_digest)) {
    throw new HttpError(412, "pin or model digest mismatch", {
      expected_pin_hash: job.pin_hash,
      expected_model_digest: job.pin_digest,
    });
  }
  const backend = c.req.header("x-backend-version") ?? null;
  let stats: Record<string, unknown> = {};
  const statsHdr = c.req.header("x-stats");
  if (statsHdr) {
    try {
      const s = JSON.parse(statsHdr);
      if (!s || typeof s !== "object" || Array.isArray(s)) throw new Error();
      stats = s;
    } catch {
      throw new HttpError(400, "X-Stats must be a JSON object");
    }
  }
  const statsJson = JSON.stringify(stats);
  const prefix = job.split === "confirmation" ? "sealed/" : "";
  const now = nowIso();

  if (partial) {
    const dup = await c.env.DB.prepare(
      "SELECT part_n, r2_key FROM job_partials WHERE job_id = ? AND worker_id = ? AND content_sha256 = ?",
    )
      .bind(jobId, w.id, sha)
      .first<{ part_n: number; r2_key: string }>();
    if (dup) return json({ status: "duplicate", part_n: dup.part_n, r2_key: dup.r2_key });
    const body = await c.req.arrayBuffer();
    if (body.byteLength === 0) throw new HttpError(400, "empty body");
    if ((await sha256Hex(body)) !== sha) throw new HttpError(400, "body does not match X-Content-Sha256");
    const idsHdr = c.req.header("x-passage-ids");
    const ids = [...new Set(idsHdr ? await decodePassageIdsHeader(idsHdr) : await passageIdsFromBlob(body))];
    const last = await c.env.DB.prepare("SELECT MAX(part_n) AS n FROM job_partials WHERE job_id = ? AND worker_id = ?")
      .bind(jobId, w.id)
      .first<{ n: number | null }>();
    const partN = (last?.n ?? 0) + 1;
    const key = `${prefix}results/${jobId}/${w.id}.part${partN}.jsonl.gz`;
    await c.env.BUCKET.put(key, body, {
      httpMetadata: { contentType: "application/gzip" },
      customMetadata: { content_sha256: sha, job_id: jobId, worker_id: w.id, part_n: String(partN) },
    });
    const ins = await c.env.DB.prepare(
      `INSERT INTO job_partials(job_id, worker_id, part_n, r2_key, content_sha256, passage_ids_json, n_ids,
                                pin_hash, model_digest, backend_version, stats_json, stage, split, created)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14)
       ON CONFLICT DO NOTHING`,
    )
      .bind(jobId, w.id, partN, key, sha, JSON.stringify(ids), ids.length, pinHash, digest, backend, statsJson, job.stage, job.split, now)
      .run();
    if (!ins.meta.changes) throw new HttpError(409, "concurrent partial upload for this job; retry");
    await c.env.DB.prepare("UPDATE workers SET last_seen = ? WHERE id = ?").bind(now, w.id).run();
    // The job stays queued/leased; /v1/lease will skip these passages (or mark
    // the job done if partials cover all of it).
    return json({ status: "stored", partial: true, part_n: partN, r2_key: key, n_ids: ids.length });
  }

  const markDone = c.env.DB.prepare(
    `UPDATE jobs SET status = CASE WHEN status = 'closed' THEN 'closed' ELSE 'done' END,
                     done_at = COALESCE(done_at, ?2), done_by = COALESCE(done_by, ?3),
                     lease_worker = NULL, lease_expires = NULL
      WHERE job_id = ?1`,
  ).bind(jobId, now, w.id);

  const existing = await c.env.DB.prepare("SELECT content_sha256, r2_key, late FROM results WHERE job_id = ? AND worker_id = ?")
    .bind(jobId, w.id)
    .first<{ content_sha256: string; r2_key: string; late: number }>();
  if (existing) {
    if (existing.content_sha256 !== sha) throw new HttpError(409, "this worker already uploaded a different result");
    if (job.status !== "done" && job.status !== "closed") await markDone.run();
    return json({ status: "duplicate", r2_key: existing.r2_key });
  }
  const body = await c.req.arrayBuffer();
  if (body.byteLength === 0) throw new HttpError(400, "empty body");
  if ((await sha256Hex(body)) !== sha) throw new HttpError(400, "body does not match X-Content-Sha256");
  const key = `${prefix}results/${jobId}/${w.id}.jsonl.gz`;
  await c.env.BUCKET.put(key, body, {
    httpMetadata: { contentType: "application/gzip" },
    customMetadata: { content_sha256: sha, job_id: jobId, worker_id: w.id },
  });
  const other = await c.env.DB.prepare("SELECT 1 AS x FROM results WHERE job_id = ? AND worker_id <> ? LIMIT 1")
    .bind(jobId, w.id)
    .first();
  const late = other ? 1 : 0;
  const nOk = stats.n_ok;
  const nFlag = stats.n_flagged;
  const nPassages =
    typeof nOk === "number" && typeof nFlag === "number" && Number.isFinite(nOk + nFlag) ? Math.trunc(nOk + nFlag) : job.n_passages;
  const [ins] = await c.env.DB.batch([
    c.env.DB.prepare(
      `INSERT INTO results(job_id, worker_id, r2_key, content_sha256, pin_hash, model_digest, backend_version,
                           stats_json, n_passages, stage, split, late, created)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13)
       ON CONFLICT(job_id, worker_id) DO NOTHING`,
    ).bind(jobId, w.id, key, sha, pinHash, digest, backend, statsJson, nPassages, job.stage, job.split, late, now),
    markDone,
    c.env.DB.prepare("UPDATE workers SET last_seen = ? WHERE id = ?").bind(now, w.id),
  ]);
  if (!ins.meta.changes) {
    // Lost a race with a concurrent upload from this same worker.
    const row = await c.env.DB.prepare("SELECT content_sha256, r2_key FROM results WHERE job_id = ? AND worker_id = ?")
      .bind(jobId, w.id)
      .first<{ content_sha256: string; r2_key: string }>();
    if (row?.content_sha256 === sha) return json({ status: "duplicate", r2_key: row.r2_key });
    throw new HttpError(409, "this worker already uploaded a different result");
  }
  return json({ status: late ? "late_duplicate" : "stored", r2_key: key });
});
