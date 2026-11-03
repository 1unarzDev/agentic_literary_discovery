import { Hono } from "hono";
import { AppEnv, requireAdmin, requireViewer } from "./auth";
import { sealState } from "./db";
import { STAGES, intVar, json, nowIso } from "./util";

export const statusRoutes = new Hono<AppEnv>();
statusRoutes.use("/v1/status", requireAdmin);
statusRoutes.use("/v1/fleet", requireViewer);

const STATUSES = ["queued", "leased", "done", "dead", "closed"] as const;

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

// Responses are cached (isolate memory, then a D1 row) so monitors and `ald fleet --watch` cost ~1 row per call.
const memCache = new Map<string, { at: number; value: unknown }>();

async function fleetStatus(env: AppEnv["Bindings"], withIds: boolean) {
  const ttlMs = intVar((env as unknown as Record<string, string | undefined>).STATUS_CACHE_S, 120) * 1000;
  const key = `fleet:${withIds ? "admin" : "viewer"}`;
  const now = Date.now();
  if (ttlMs > 0) {
    const m = memCache.get(key);
    if (m && now - m.at < ttlMs) return m.value;
    const row = await env.DB.prepare("SELECT value, updated_ms FROM kv_cache WHERE key = ?").bind(key).first<{ value: string; updated_ms: number }>();
    if (row && now - row.updated_ms < ttlMs) {
      const value = JSON.parse(row.value);
      memCache.set(key, { at: row.updated_ms, value });
      return value;
    }
  }
  const value = await computeFleetStatus(env, withIds, now);
  if (ttlMs > 0) {
    memCache.set(key, { at: now, value });
    await env.DB.prepare(
      "INSERT INTO kv_cache(key, value, updated_ms) VALUES (?1, ?2, ?3) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_ms = excluded.updated_ms",
    ).bind(key, JSON.stringify(value), now).run();
  }
  return value;
}

async function computeFleetStatus(env: AppEnv["Bindings"], withIds: boolean, now: number) {
  const h1 = nowIso(now - 3600_000).slice(0, 13);
  const h24 = nowIso(now - 24 * 3600_000).slice(0, 13);
  const db = env.DB;
  // Everything below reads the trigger-maintained counters (job_counts, hourly): a few hundred rows in total.
  const [workers, counts, hourRows] = await db.batch([
    db.prepare(
      "SELECT id, name, tier, os, gpu, vram_gb, client_version, last_seen, tok_s, stats_json FROM workers WHERE disabled = 0 ORDER BY last_seen DESC",
    ),
    db.prepare("SELECT wave, stage, cell, status, n, p FROM job_counts WHERE n <> 0"),
    db.prepare(
      `SELECT hour, worker_id, stage, results, passages, n_ok, n_flagged, n_schema_invalid, n_evidence_unverified
         FROM hourly WHERE hour >= ?1`,
    ).bind(h24),
  ]);
  type H = { hour: string; worker_id: string; stage: string; results: number; passages: number; n_ok: number; n_flagged: number;
             n_schema_invalid: number; n_evidence_unverified: number };
  type C = { wave: string; stage: string; cell: string; status: string; n: number; p: number };
  const hrs = hourRows.results as H[];
  const agg = (by: "worker_id" | "stage") => {
    const m = new Map<string, { k: string; n_1h: number; n_24h: number }>();
    for (const r of hrs) {
      const e = m.get(r[by]) ?? { k: r[by], n_1h: 0, n_24h: 0 };
      e.n_24h += r.passages;
      if (r.hour >= h1) e.n_1h += r.passages;
      m.set(r[by], e);
    }
    return [...m.values()];
  };
  const perWorker = { results: agg("worker_id") };
  const perStage = { results: agg("stage") };
  const cnt = counts.results as C[];
  const sumBy = (keyf: (r: C) => string | null) => {
    const m = new Map<string, { n: number; p: number; r: C }>();
    for (const r of cnt) {
      const k = keyf(r);
      if (k === null) continue;
      const e = m.get(k) ?? { n: 0, p: 0, r };
      e.n += r.n;
      e.p += r.p;
      m.set(k, e);
    }
    return [...m.values()];
  };
  const queue = { results: sumBy((r) => `${r.stage}\u0000${r.status}`).map((e) => ({ stage: e.r.stage, status: e.r.status, n: e.n, p: e.p })) };
  const covered = { results: [] as { stage: string; n: number }[] }; // partial coverage of open jobs: not subtracted (approximation)
  const cells = { results: sumBy((r) => (r.cell ? `${r.cell}\u0000${r.stage}\u0000${r.status}` : null)).map((e) => ({ cell: e.r.cell, stage: e.r.stage, status: e.r.status, n: e.n, p: e.p })) };
  const waves = { results: sumBy((r) => `${r.wave}\u0000${r.stage}\u0000${r.status}`).map((e) => ({ wave: e.r.wave, stage: e.r.stage, status: e.r.status, n: e.n, p: e.p })) };
  const hourTotals = new Map<string, number>();
  for (const r of hrs) hourTotals.set(r.hour, (hourTotals.get(r.hour) ?? 0) + r.passages);
  const hourly = { results: [...hourTotals.entries()].map(([h, n]) => ({ h, n })) };
  const qm = new Map<string, Record<string, number | string>>();
  for (const r of hrs) {
    const e = (qm.get(r.stage) ?? { stage: r.stage, n_ok: 0, n_flagged: 0, n_schema_invalid: 0, n_evidence_unverified: 0, results: 0 }) as Record<string, number | string>;
    for (const k of ["n_ok", "n_flagged", "n_schema_invalid", "n_evidence_unverified", "results"] as const) e[k] = (e[k] as number) + (r[k] ?? 0);
    qm.set(r.stage, e);
  }
  const quality = { results: [...qm.values()] };

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
