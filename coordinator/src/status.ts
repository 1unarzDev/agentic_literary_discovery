import { Hono } from "hono";
import { AppEnv, requireAdmin } from "./auth";
import { sealState } from "./db";
import { STAGES, json, nowIso } from "./util";

export const statusRoutes = new Hono<AppEnv>();
statusRoutes.use("/v1/status", requireAdmin);

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

statusRoutes.get("/v1/status", async (c) => {
  const now = Date.now();
  const h1 = nowIso(now - 3600_000);
  const h24 = nowIso(now - 24 * 3600_000);
  const db = c.env.DB;
  const [workers, perWorker, perStage, queue, covered, cells] = await db.batch([
    db.prepare("SELECT id, name, tier, os, last_seen, tok_s FROM workers WHERE disabled = 0 ORDER BY last_seen DESC"),
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

  return json({
    generated: nowIso(now),
    workers: (workers.results as Record<string, unknown>[]).map((w) => ({
      id: w.id,
      name: w.name,
      tier: w.tier,
      os: w.os,
      last_seen: w.last_seen,
      passages_1h: tp.get(w.id as string)?.n_1h ?? 0,
      passages_24h: tp.get(w.id as string)?.n_24h ?? 0,
      tok_s: w.tok_s,
    })),
    queue: queueOut,
    remaining_passages: remaining,
    fleet_passages_per_hour: pph,
    eta_hours: eta,
    cells: cellsOut,
    sealed: (await sealState(c.env)).sealed,
  });
});
