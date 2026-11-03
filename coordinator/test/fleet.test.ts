import { describe, expect, it } from "vitest";
import { addJobs, admin, callJson, makePin, makeWorker } from "./helpers";

describe("fleet view", () => {
  it("viewer token reads /v1/fleet only; no worker ids; heartbeat stats are whitelisted", async () => {
    const pin = await makePin();
    await addJobs([{ pin_hash: pin.pin_hash }]);
    const w = await makeWorker("fleet-w");
    const hb = await callJson("POST", "/v1/heartbeat", {
      token: w.token,
      json: { job_ids: [], stats: { tok_s: 50, state: "idle", keep_awake: true, battery_percent: 80, secret: "x", nested: { a: 1 } } },
    });
    expect(hb.status).toBe(200);
    const vt = await admin("POST", "/v1/admin/viewer_token", { name: "user" });
    expect(vt.status).toBe(200);
    const t = vt.body.token as string;
    const f = await callJson("GET", "/v1/fleet", { token: t });
    expect(f.status).toBe(200);
    const me = f.body.workers.find((x: { name: string }) => x.name === "fleet-w");
    expect(me.id).toBeUndefined();
    expect(me.report).toEqual({ tok_s: 50, state: "idle", keep_awake: true, battery_percent: 80 });
    expect(f.body.hourly_passages).toHaveLength(24);
    expect(f.body.waves.some((x: { wave: string }) => x.wave === "w1")).toBe(true);
    expect((await callJson("GET", `/v1/fleet?t=${t}`)).status).toBe(200);
    // viewer token is not an admin token, nor a worker token
    expect((await callJson("GET", "/v1/status", { token: t })).status).toBe(401);
    expect((await callJson("POST", "/v1/admin/invite", { token: t, json: { n: 1 } })).status).toBe(401);
    expect((await callJson("POST", "/v1/lease", { token: t, json: { stages: ["label"] } })).status).toBe(401);
    expect((await callJson("GET", "/v1/fleet", { token: "nope" })).status).toBe(401);
    expect((await admin("GET", "/v1/fleet")).status).toBe(200);
  });
});

describe("presence", () => {
  it("online / sleeping until window / overdue / silent", async () => {
    const { presence } = await import("../src/status");
    const now = Date.parse("2026-11-02T03:00:00Z");
    const iso = (ms: number) => new Date(now + ms).toISOString();
    expect(presence(iso(-60_000), null, now).presence).toBe("online");
    const window = (now + 3600_000) / 1000; // starts in 1 h
    expect(presence(iso(-3 * 3600_000), { next_window: window }, now)).toEqual({ presence: "sleeping", until: new Date(window * 1000).toISOString() });
    const past = (now - 20 * 60_000) / 1000; // started 20 min ago, not back
    expect(presence(iso(-3 * 3600_000), { next_window: past }, now).presence).toBe("overdue");
    expect(presence(iso(-3 * 3600_000), { next_window: (now - 5 * 60_000) / 1000 }, now).presence).toBe("sleeping"); // grace
    expect(presence(iso(-3 * 3600_000), {}, now).presence).toBe("silent");
  });
});

describe("trigger-maintained counters", () => {
  it("job_counts always equals a GROUP BY over jobs", async () => {
    const { env } = await import("cloudflare:test");
    const { addJobs, lease, makeWorker, upload, resultBlob, runCron, resetQueue } = await import("./helpers");
    await resetQueue(); // jobs left by other tests (exercises the DELETE trigger too)
    const pin = await makePin();
    const ids = await addJobs(Array.from({ length: 6 }, () => ({ pin_hash: pin.pin_hash })));
    const w = await makeWorker("counter-w");
    const l = await lease(w.token, ["label"], 3);
    const [a, b, c2] = l.body.jobs.map((j: { job_id: string }) => j.job_id);
    const blob = await resultBlob(["p1", "p2", "p3"]);
    const up = await upload(w.token, a, pin, blob);
    expect(up.status, JSON.stringify(up.body)).toBe(200);
    await callJson("POST", "/v1/release", { token: w.token, json: { job_ids: [b] } });
    const notLeased = ids.find((id) => ![a, b, c2].includes(id))!;
    await admin("POST", "/v1/admin/close_jobs", { job_ids: [notLeased] });
    await env.DB.prepare("UPDATE jobs SET lease_expires = 1, attempt = 3 WHERE job_id = ?").bind(c2).run();
    await runCron(); // expired + max attempts -> dead
    const real = await env.DB.prepare(
      "SELECT wave, stage, COALESCE(cell,'') AS cell, status, COUNT(*) AS n, SUM(n_passages) AS p FROM jobs GROUP BY 1,2,3,4",
    ).all<Record<string, unknown>>();
    const counted = await env.DB.prepare("SELECT wave, stage, cell, status, n, p FROM job_counts WHERE n <> 0").all<Record<string, unknown>>();
    const key = (r: Record<string, unknown>) => `${r.wave}|${r.stage}|${r.cell}|${r.status}|${r.n}|${r.p}`;
    expect(counted.results.map(key).sort()).toEqual(real.results.map(key).sort());
    const statuses = new Set(real.results.map((r) => r.status));
    expect([...statuses].sort()).toEqual(["closed", "dead", "done", "queued"]);
    const hourly = await env.DB.prepare("SELECT SUM(passages) AS p, SUM(results) AS r FROM hourly WHERE worker_id = ?").bind(w.worker_id).first<{ p: number; r: number }>();
    expect(hourly?.r).toBe(1);
  });
});

describe("sealed split never exposes quality", () => {
  it("confirmation results store only counts/timing; fleet quality is discovery-only", async () => {
    const { env } = await import("cloudflare:test");
    const { addJobs, lease, makeWorker, upload, resultBlob, resetQueue } = await import("./helpers");
    await resetQueue();
    await env.DB.prepare("DELETE FROM hourly").run();
    const pin = await makePin();
    await addJobs([{ job_id: "conf-q", pin_hash: pin.pin_hash, split: "confirmation" }]);
    const w = await makeWorker("sealed-w");
    const l = await lease(w.token, ["label"], 1);
    expect(l.body.jobs[0].job_id).toBe("conf-q");
    const blob = await resultBlob(["p1", "p2", "p3"]);
    const leaky = { n_ok: 1, n_flagged: 2, n_schema_invalid: 1, n_evidence_unverified: 1, n_retried: 2, gen_tokens: 99,
                    schema_error_sample: "x", tok_s: 5, wall_s: 10, prompt_tokens: 1 };
    const up = await upload(w.token, "conf-q", pin, blob, { headers: { "x-stats": JSON.stringify(leaky) } });
    expect(up.status).toBe(200);
    const row = await env.DB.prepare("SELECT stats_json, n_passages FROM results WHERE job_id = 'conf-q'").first<{ stats_json: string; n_passages: number }>();
    expect(JSON.parse(row!.stats_json)).toEqual({ n_lines: 3, wall_s: 10 });
    expect(row!.n_passages).toBe(3);
    const h = await env.DB.prepare("SELECT SUM(n_ok) a, SUM(n_flagged) b, SUM(n_schema_invalid) c, SUM(n_evidence_unverified) d, SUM(passages) p FROM hourly").first<Record<string, number>>();
    expect(h).toEqual({ a: 0, b: 0, c: 0, d: 0, p: 3 }); // throughput counted, quality not
    const f = await admin("GET", "/v1/fleet");
    for (const q of f.body.quality_24h) expect(q.n_flagged ?? 0).toBe(0);
    const s = await admin("GET", "/v1/status");
    expect(JSON.stringify(s.body)).not.toContain("schema_error_sample");
  });
});
