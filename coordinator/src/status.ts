import { Hono } from "hono";
import { AppEnv, requireAdmin, requireViewer } from "./auth";
import { sealState } from "./db";
import { STAGES, json, nowIso } from "./util";

export const statusRoutes = new Hono<AppEnv>();
statusRoutes.use("/v1/status", requireAdmin);
statusRoutes.use("/v1/fleet", requireViewer);

const STATUSES = ["queued", "leased", "done", "dead", "closed"] as const;

/**
 * Throughput counts passages from the per-shard result index: a full result
 * counts its n_passages (stats n_ok + n_flagged, else the job's n_passages);
 * a partial counts its passage ids, but only while that worker has not yet
 * uploaded a full result for the job (so checkpoints are not double counted).
 */
const THROUGHPUT_SQL = (groupBy: "worker_id" | "stage") => `
SELECT ${groupBy} AS k,
       SUM(CASE WHEN created >= ?1 THEN n ELSE 0 END) AS n_1h,
       SUM(n) AS n_24h
  FROM (
    SELECT worker_id, stage, n_passages AS n, created FROM results WHERE created >= ?2
    UNION ALL
    SELECT p.worker_id, p.stage, p.n_ids AS n, p.created FROM job_partials p
     WHERE p.created >= ?2
       AND NOT EXISTS (SELECT 1 FROM results r WHERE r.job_id = p.job_id AND r.worker_id = p.worker_id)
  )
 GROUP BY ${groupBy}`;

statusRoutes.get("/v1/status", async (c) => json(await fleetStatus(c.env, true)));

/** Read-only fleet view (viewer or admin token): /v1/status without worker ids. */
statusRoutes.get("/v1/fleet", async (c) => json(await fleetStatus(c.env, false)));

const ONLINE_MS = 15 * 60_000; // seen within this: online
const OVERDUE_GRACE_MS = 15 * 60_000; // not back this long after its window started: overdue

/**
 * online | sleeping (absence expected: its last report said "may sleep until next_window") |
 * overdue (next_window passed by more than 15 min and it has not been seen since) | silent (no schedule info).
 */
export function presence(lastSeen: unknown, report: Record<string, unknown> | null, now: number) {
  const seen = typeof lastSeen === "string" ? Date.parse(lastSeen) : NaN;
  if (!isNaN(seen) && now - seen < ONLINE_MS) return { presence: "online" as const, until: null };
  const nw = report && typeof report.next_window === "number" ? report.next_window * 1000 : null;
  if (nw !== null && (isNaN(seen) || seen < nw)) {
    if (now < nw + OVERDUE_GRACE_MS) return { presence: "sleeping" as const, until: new Date(nw).toISOString() };
    return { presence: "overdue" as const, until: new Date(nw).toISOString() };
  }
  return { presence: "silent" as const, until: null };
}

function parseStats(s: unknown): Record<string, unknown> | null {
  if (typeof s !== "string") return null;
  try {
    return JSON.parse(s);
  } catch {
    return null;
  }
}

async function fleetStatus(env: AppEnv["Bindings"], withIds: boolean) {
  const now = Date.now();
  const h1 = nowIso(now - 3600_000);
  const h24 = nowIso(now - 24 * 3600_000);
  const db = env.DB;
  const [workers, perWorker, perStage, queue, covered, cells, waves, hourly, quality] = await db.batch([
    db.prepare(
      "SELECT id, name, tier, os, gpu, vram_gb, client_version, last_seen, tok_s, stats_json FROM workers WHERE disabled = 0 ORDER BY last_seen DESC",
    ),
    db.prepare(THROUGHPUT_SQL("worker_id")).bind(h1, h24),
    db.prepare(THROUGHPUT_SQL("stage")).bind(h1, h24),
    db.prepare("SELECT stage, status, COUNT(*) AS n, SUM(n_passages) AS p FROM jobs GROUP BY stage, status"),
    // Passages of still-open jobs already covered by partial uploads.
    db.prepare(
      `SELECT stage, COUNT(*) AS n FROM (
         SELECT DISTINCT j.stage AS stage, jp.job_id, je.value
           FROM job_partials jp JOIN jobs j ON j.job_id = jp.job_id AND j.status IN ('queued', 'leased'),
                json_each(jp.passage_ids_json) je)
        GROUP BY stage`,
    ),
    db.prepare(
      `SELECT cell, stage, status, COUNT(*) AS n, SUM(n_passages) AS p
         FROM jobs WHERE cell IS NOT NULL GROUP BY cell, stage, status ORDER BY cell, stage`,
    ),
    db.prepare("SELECT wave, stage, status, COUNT(*) AS n, SUM(n_passages) AS p FROM jobs GROUP BY wave, stage, status ORDER BY wave"),
    // Fleet passages per hour over the last 24 h (full results only: partials would double count).
    db.prepare(
      `SELECT substr(created, 1, 13) AS h, SUM(n_passages) AS n FROM results WHERE created >= ?1 GROUP BY h ORDER BY h`,
    ).bind(h24),
    db.prepare(
      `SELECT stage, SUM(json_extract(stats_json, '$.n_ok')) AS n_ok, SUM(json_extract(stats_json, '$.n_flagged')) AS n_flagged,
              SUM(json_extract(stats_json, '$.n_schema_invalid')) AS n_schema_invalid,
              SUM(json_extract(stats_json, '$.n_evidence_unverified')) AS n_evidence_unverified,
              COUNT(*) AS results FROM results WHERE created >= ?1 GROUP BY stage`,
    ).bind(h24),
  ]);

  const tp = new Map((perWorker.results as { k: string; n_1h: number; n_24h: number }[]).map((r) => [r.k, r]));
  const queueOut: Record<string, Record<string, number>> = {};
  const remaining: Record<string, number> = {};
  for (const s of STAGES) {
    queueOut[s] = Object.fromEntries(STATUSES.map((st) => [st, 0]));
    remaining[s] = 0;
  }
  for (const r of queue.results as { stage: string; status: string; n: number; p: number }[]) {
    (queueOut[r.stage] ??= Object.fromEntries(STATUSES.map((st) => [st, 0])))[r.status] = r.n;
    if (r.status === "queued" || r.status === "leased") remaining[r.stage] = (remaining[r.stage] ?? 0) + (r.p ?? 0);
  }
  for (const r of covered.results as { stage: string; n: number }[]) remaining[r.stage] = Math.max(0, (remaining[r.stage] ?? 0) - r.n);

  // Fleet rate per stage: passages in the last hour; if none, the 24 h average.
  const rate: Record<string, number> = {};
  for (const r of perStage.results as { k: string; n_1h: number; n_24h: number }[]) rate[r.k] = r.n_1h > 0 ? r.n_1h : r.n_24h / 24;
  const eta: Record<string, number | null> = {};
  const pph: Record<string, number> = {};
  for (const s of Object.keys(remaining)) {
    pph[s] = Math.round((rate[s] ?? 0) * 10) / 10;
    eta[s] = remaining[s] === 0 ? 0 : rate[s] > 0 ? Math.round((remaining[s] / rate[s]) * 100) / 100 : null;
  }

  const cellMap = new Map<string, Record<string, unknown>>();
  for (const r of cells.results as { cell: string; stage: string; status: string; n: number; p: number }[]) {
    const key = `${r.cell}\u0000${r.stage}`;
    let e = cellMap.get(key);
    if (!e) {
      e = { cell: r.cell, stage: r.stage, ...Object.fromEntries(STATUSES.map((st) => [st, 0])), passages_total: 0, passages_done: 0 };
      cellMap.set(key, e);
    }
    e[r.status] = r.n;
    if (r.status !== "closed") e.passages_total = (e.passages_total as number) + (r.p ?? 0);
    if (r.status === "done") e.passages_done = (e.passages_done as number) + (r.p ?? 0);
  }
  const cellsOut = [...cellMap.values()].map((e) => ({ ...e, open: (e.queued as number) + (e.leased as number) > 0 }));

  const waveMap = new Map<string, Record<string, unknown>>();
  for (const r of waves.results as { wave: string; stage: string; status: string; n: number; p: number }[]) {
    const key = `${r.wave}\u0000${r.stage}`;
    let e = waveMap.get(key);
    if (!e) {
      e = { wave: r.wave, stage: r.stage, jobs: Object.fromEntries(STATUSES.map((st) => [st, 0])), passages: Object.fromEntries(STATUSES.map((st) => [st, 0])) };
      waveMap.set(key, e);
    }
    (e.jobs as Record<string, number>)[r.status] = r.n;
    (e.passages as Record<string, number>)[r.status] = r.p ?? 0;
  }
  const hourMap = new Map((hourly.results as { h: string; n: number }[]).map((r) => [r.h, r.n]));
  const hourlyOut = Array.from({ length: 24 }, (_, i) => {
    const h = nowIso(now - (23 - i) * 3600_000).slice(0, 13);
    return { hour: h, passages: hourMap.get(h) ?? 0 };
  });

  return {
    generated: nowIso(now),
    workers: (workers.results as Record<string, unknown>[]).map((w) => ({
      ...(withIds ? { id: w.id } : {}),
      name: w.name,
      tier: w.tier,
      os: w.os,
      gpu: w.gpu,
      vram_gb: w.vram_gb,
      client_version: w.client_version,
      last_seen: w.last_seen,
      passages_1h: tp.get(w.id as string)?.n_1h ?? 0,
      passages_24h: tp.get(w.id as string)?.n_24h ?? 0,
      tok_s: w.tok_s,
      report: parseStats(w.stats_json),
      ...(() => {
        const p = presence(w.last_seen, parseStats(w.stats_json), now);
        return { presence: p.presence, expected_back: p.until };
      })(),
    })),
    waves: [...waveMap.values()],
    hourly_passages: hourlyOut,
    quality_24h: quality.results,
    queue: queueOut,
    remaining_passages: remaining,
    fleet_passages_per_hour: pph,
    eta_hours: eta,
    cells: cellsOut,
    sealed: (await sealState(env)).sealed,
  };
}
