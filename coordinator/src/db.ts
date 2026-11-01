import { Env, intVar, nowIso } from "./util";

// ---------------------------------------------------------------- config

export const CFG = {
  latestClientVersion: "latest_client_version",
  minClientVersion: "min_client_version",
  wheelFile: "wheel_file",
  registryVersion: "registry_version",
  registryEtag: "registry_etag",
} as const;

export async function getConfig(env: Env): Promise<Record<string, string>> {
  const { results } = await env.DB.prepare("SELECT key, value FROM config").all<{ key: string; value: string }>();
  const out: Record<string, string> = {};
  for (const r of results) out[r.key] = r.value;
  return out;
}

export function setConfigStmt(env: Env, key: string, value: string): D1PreparedStatement {
  return env.DB.prepare(
    "INSERT INTO config(key, value, updated_at) VALUES (?1, ?2, ?3) " +
      "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
  ).bind(key, value, nowIso());
}

export async function minClientVersion(env: Env): Promise<string> {
  const row = await env.DB.prepare("SELECT value FROM config WHERE key = ?")
    .bind(CFG.minClientVersion)
    .first<{ value: string }>();
  return row?.value ?? env.MIN_CLIENT_VERSION ?? "0.0.0";
}

// ---------------------------------------------------------------- seal

export interface SealState {
  sealed: boolean;
  prereg_hash?: string;
  unsealed_at?: string;
}

export async function sealState(env: Env): Promise<SealState> {
  const row = await env.DB.prepare("SELECT prereg_hash, unsealed_at FROM seal WHERE id = 1").first<{
    prereg_hash: string;
    unsealed_at: string;
  }>();
  return row ? { sealed: false, ...row } : { sealed: true };
}

// ---------------------------------------------------------------- leases

export function leaseTtlMs(env: Env): number {
  return intVar(env.LEASE_TTL_SECONDS, 600) * 1000;
}

export interface ReclaimResult {
  requeued: string[];
  dead: string[];
}

/** Return expired leases to the queue; attempt >= MAX_ATTEMPTS goes to 'dead'. */
export async function reclaimExpired(env: Env, nowMs = Date.now()): Promise<ReclaimResult> {
  const maxAttempts = intVar(env.MAX_ATTEMPTS, 3);
  const { results } = await env.DB.prepare(
    `UPDATE jobs
        SET status = CASE WHEN attempt >= ?2 THEN 'dead' ELSE 'queued' END,
            lease_worker = NULL, lease_expires = NULL
      WHERE status = 'leased' AND lease_expires < ?1
      RETURNING job_id, status`,
  )
    .bind(nowMs, maxAttempts)
    .all<{ job_id: string; status: string }>();
  const out: ReclaimResult = { requeued: [], dead: [] };
  for (const r of results) (r.status === "dead" ? out.dead : out.requeued).push(r.job_id);
  return out;
}

export interface LeasedRow {
  job_id: string;
  stage: string;
  pin_hash: string;
  n_passages: number;
  lease_expires: number;
  attempt: number;
}

/**
 * Single atomic statement: picks up to `limit` queued jobs (allowed stages,
 * active pin), at most one per dup_group, never a job whose dup_group sibling
 * this worker has ever leased or has completed, ordered by priority (ascending)
 * then random, and marks them leased. The `jobs_lease_log` trigger records the
 * lease history row inside the same statement.
 */
const LEASE_SQL = `
UPDATE jobs
   SET status = 'leased', lease_worker = ?1, lease_expires = ?2, leased_at_ms = ?3,
       attempt = attempt + 1
 WHERE status = 'queued' AND job_id IN (
   SELECT job_id FROM (
     SELECT j.job_id, j.priority,
            ROW_NUMBER() OVER (PARTITION BY COALESCE(j.dup_group, 'job:' || j.job_id)
                               ORDER BY j.priority, random()) AS rn
       FROM jobs j
       JOIN pins p ON p.pin_hash = j.pin_hash AND p.active = 1
      WHERE j.status = 'queued'
        AND j.stage IN (SELECT value FROM json_each(?4))
        AND (j.dup_group IS NULL OR NOT EXISTS (
              SELECT 1 FROM jobs s
               WHERE s.dup_group = j.dup_group AND s.job_id <> j.job_id
                 AND (   (s.status = 'leased' AND s.lease_worker = ?1)
                      OR EXISTS (SELECT 1 FROM leases l  WHERE l.job_id = s.job_id AND l.worker_id = ?1)
                      OR EXISTS (SELECT 1 FROM results r WHERE r.job_id = s.job_id AND r.worker_id = ?1))))
   ) WHERE rn = 1
   ORDER BY priority, random()
   LIMIT ?5
 )
RETURNING job_id, stage, pin_hash, n_passages, lease_expires, attempt`;

/** Union of passage ids covered by partial uploads, per job. */
export async function partialCoverage(env: Env, jobIds: string[]): Promise<Map<string, string[]>> {
  const out = new Map<string, string[]>();
  if (jobIds.length === 0) return out;
  const { results } = await env.DB.prepare(
    `SELECT DISTINCT jp.job_id AS job_id, je.value AS pid
       FROM job_partials jp, json_each(jp.passage_ids_json) je
      WHERE jp.job_id IN (SELECT value FROM json_each(?1))`,
  )
    .bind(JSON.stringify(jobIds))
    .all<{ job_id: string; pid: string }>();
  for (const r of results) {
    let a = out.get(r.job_id);
    if (!a) out.set(r.job_id, (a = []));
    a.push(String(r.pid));
  }
  return out;
}

export interface LeasedJob extends LeasedRow {
  skip_passage_ids: string[];
}

export async function leaseJobs(
  env: Env,
  workerId: string,
  stages: string[],
  maxJobs: number,
  nowMs = Date.now(),
): Promise<LeasedJob[]> {
  const out: LeasedJob[] = [];
  const expires = nowMs + leaseTtlMs(env);
  // A few rounds: jobs fully covered by partial uploads are marked done
  // instead of being handed out, and the slot is refilled.
  for (let round = 0; round < 3 && out.length < maxJobs; round++) {
    const { results } = await env.DB.prepare(LEASE_SQL)
      .bind(workerId, expires, nowMs, JSON.stringify(stages), maxJobs - out.length)
      .all<LeasedRow>();
    if (results.length === 0) break;
    const cov = await partialCoverage(env, results.map((r) => r.job_id));
    const complete: string[] = [];
    for (const r of results) {
      const skip = cov.get(r.job_id) ?? [];
      if (skip.length >= r.n_passages && r.n_passages > 0) complete.push(r.job_id);
      else out.push({ ...r, skip_passage_ids: skip });
    }
    if (complete.length === 0) break;
    await env.DB.prepare(
      `UPDATE jobs SET status = 'done', done_by = 'partials', done_at = ?3,
                       lease_worker = NULL, lease_expires = NULL
        WHERE status = 'leased' AND lease_worker = ?2
          AND job_id IN (SELECT value FROM json_each(?1))`,
    )
      .bind(JSON.stringify(complete), workerId, nowIso(nowMs))
      .run();
  }
  return out;
}
