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
// The UPDATE only touches the chosen job ids (primary key) and re-checks status, so concurrent leases never
// double-assign; a lost race just returns fewer rows and the caller picks again.
const LEASE_SQL = `
UPDATE jobs
   SET status = 'leased', lease_worker = ?1, lease_expires = ?2, leased_at_ms = ?3,
       attempt = attempt + 1
 WHERE job_id IN (SELECT value FROM json_each(?4)) AND +status = 'queued' -- "+": look up by primary key, not the status index (measured 1,600 rows/lease)
RETURNING job_id, stage, pin_hash, n_passages, lease_expires, attempt`;

const CANDIDATES_PER_PIN = 32;

/**
 * Lease candidates with bounded reads (D1 bills rows read): one index range scan per (stage, active pin) on
 * jobs_lease2_idx(status, stage, pin_hash, priority) with LIMIT, instead of a window function over every queued
 * job (~10k rows per lease). Lowest priority first, random within a priority, at most one job per dup_group,
 * and no job whose dup_group sibling this worker holds, held or completed.
 */
async function pickCandidates(env: Env, workerId: string, stages: string[], want: number): Promise<string[]> {
  const { results: pins } = await env.DB.prepare(
    "SELECT pin_hash, stage FROM pins WHERE active = 1 AND stage IN (SELECT value FROM json_each(?1))",
  )
    .bind(JSON.stringify(stages))
    .all<{ pin_hash: string; stage: string }>();
  if (pins.length === 0) return [];
  const res = await env.DB.batch(
    pins.map((p) =>
      env.DB.prepare(
        `SELECT job_id, priority, dup_group FROM jobs INDEXED BY jobs_lease2_idx
          WHERE status = 'queued' AND stage = ?1 AND pin_hash = ?2 ORDER BY priority LIMIT ?3`,
      ).bind(p.stage, p.pin_hash, CANDIDATES_PER_PIN),
    ),
  );
  type Cand = { job_id: string; priority: number; dup_group: string | null };
  let cands = res.flatMap((r) => r.results as Cand[]);
  const groups = [...new Set(cands.map((c) => c.dup_group).filter((g): g is string => !!g))];
  if (groups.length) {
    const { results: held } = await env.DB.prepare(
      `SELECT s.dup_group AS g, s.job_id AS id FROM jobs s
        WHERE s.dup_group IN (SELECT value FROM json_each(?1))
          AND (   (s.status = 'leased' AND s.lease_worker = ?2)
               OR EXISTS (SELECT 1 FROM leases l  WHERE l.job_id = s.job_id AND l.worker_id = ?2)
               OR EXISTS (SELECT 1 FROM results r WHERE r.job_id = s.job_id AND r.worker_id = ?2))`,
    )
      .bind(JSON.stringify(groups), workerId)
      .all<{ g: string; id: string }>();
    cands = cands.filter((c) => !c.dup_group || !held.some((h) => h.g === c.dup_group && h.id !== c.job_id));
  }
  // Random order within each priority level, lowest priority value first.
  const shuffled = cands.map((c) => ({ c, r: Math.random() })).sort((a, b) => a.c.priority - b.c.priority || a.r - b.r);
  const out: string[] = [];
  const usedGroups = new Set<string>();
  for (const { c } of shuffled) {
    if (out.length >= want) break;
    if (c.dup_group) {
      if (usedGroups.has(c.dup_group)) continue;
      usedGroups.add(c.dup_group);
    }
    out.push(c.job_id);
  }
  return out;
}

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
  for (let round = 0; round < 8 && out.length < maxJobs; round++) {
    const pick = await pickCandidates(env, workerId, stages, maxJobs - out.length);
    if (pick.length === 0) break;
    const { results } = await env.DB.prepare(LEASE_SQL)
      .bind(workerId, expires, nowMs, JSON.stringify(pick))
      .all<LeasedRow>();
    if (results.length === 0) continue; // lost every race this round: pick again from fresh candidates
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
