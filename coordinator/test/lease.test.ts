import { env } from "cloudflare:test";
import { beforeEach, describe, expect, it } from "vitest";
import { addJobs, admin, call, callJson, lease, makePin, makeWorker, resetQueue, runCron } from "./helpers";

beforeEach(resetQueue);

describe("lease", () => {
  it("50 concurrent leases never double-assign a job", async () => {
    const pin = await makePin();
    const jobIds = await addJobs(Array.from({ length: 30 }, () => ({ pin_hash: pin.pin_hash })));
    const workers = await Promise.all(Array.from({ length: 50 }, (_, i) => makeWorker(`racer${i}`)));
    const res = await Promise.all(workers.map((w) => lease(w.token, ["label"], 2)));
    expect(res.every((r) => r.status === 200)).toBe(true);
    const got = res.flatMap((r) => r.body.jobs.map((j: { job_id: string }) => j.job_id));
    expect(new Set(got).size).toBe(got.length); // no job handed out twice
    expect(got.length).toBe(30); // all jobs leased, none lost
    expect(new Set(got)).toEqual(new Set(jobIds));
    // DB agrees: every job leased exactly once, one history row each
    const { results } = await env.DB.prepare("SELECT job_id, COUNT(*) AS n FROM leases GROUP BY job_id").all<{ n: number }>();
    expect(results.length).toBe(30);
    expect(results.every((r) => r.n === 1)).toBe(true);
  });

  it("returns contract fields and lets only the holder download the shard", async () => {
    const pin = await makePin();
    const shard = new Uint8Array([0x1f, 0x8b, 1, 2, 3]);
    const up = await call("PUT", "/v1/admin/shard/w1/s001", {
      token: "test-admin-token",
      body: shard,
      headers: { "x-split": "discovery", "x-n-passages": "3", "x-decades": "1820,1830" },
    });
    expect(up.status).toBe(200);
    await addJobs([{ job_id: "job-shard-1", pin_hash: pin.pin_hash }]);
    await env.DB.prepare("UPDATE jobs SET shard_key = 'shards/w1/s001.jsonl.gz' WHERE job_id = 'job-shard-1'").run();
    const a = await makeWorker("a");
    const b = await makeWorker("b");
    const r = await lease(a.token);
    const j = r.body.jobs[0];
    expect(Object.keys(j).sort()).toEqual(
      ["attempt", "job_id", "lease_expires", "n_passages", "pin_hash", "shard_url", "skip_passage_ids", "stage"].sort(),
    );
    expect(j.shard_url).toBe("https://coord.test/v1/shard/job-shard-1");
    expect(new Date(j.lease_expires).getTime()).toBeGreaterThan(Date.now() + 9 * 60_000);
    const ok = await call("GET", "/v1/shard/job-shard-1", { token: a.token });
    expect(ok.status).toBe(200);
    expect(new Uint8Array(await ok.arrayBuffer())).toEqual(shard);
    expect((await call("GET", "/v1/shard/job-shard-1", { token: b.token })).status).toBe(403);
    expect((await call("GET", "/v1/shard/job-shard-1")).status).toBe(401);
  });

  it("filters by stage and prefers lower priority values", async () => {
    const lp = await makePin("label");
    const sp = await makePin("screen");
    await addJobs([
      { job_id: "p-late", pin_hash: lp.pin_hash, priority: 50 },
      { job_id: "p-first", pin_hash: lp.pin_hash, priority: 1 },
      { job_id: "p-screen", stage: "screen", pin_hash: sp.pin_hash, priority: 0 },
    ]);
    const w = await makeWorker();
    const r1 = await lease(w.token, ["label"]);
    expect(r1.body.jobs.map((j: any) => j.job_id)).toEqual(["p-first"]);
    const r2 = await lease(w.token, ["label"]);
    expect(r2.body.jobs.map((j: any) => j.job_id)).toEqual(["p-late"]);
    const r3 = await lease(w.token, ["label"]);
    expect(r3.body.jobs).toEqual([]);
    expect((await lease(w.token, ["nope"])).status).toBe(400);
  });

  it("never gives one worker both twins of a dup_group (same call, later call, or after completing one)", async () => {
    const pin = await makePin();
    await addJobs([
      { job_id: "twin-a", pin_hash: pin.pin_hash, dup_group: "g1" },
      { job_id: "twin-b", pin_hash: pin.pin_hash, dup_group: "g1" },
    ]);
    const w1 = await makeWorker("w1");
    const w2 = await makeWorker("w2");
    const r1 = await lease(w1.token, ["label"], 5);
    expect(r1.body.jobs.length).toBe(1);
    expect((await lease(w1.token, ["label"], 5)).body.jobs).toEqual([]);
    const r2 = await lease(w2.token, ["label"], 5);
    expect(r2.body.jobs.length).toBe(1);
    expect(r2.body.jobs[0].job_id).not.toBe(r1.body.jobs[0].job_id);
  });

  it("refuses clients older than MIN_CLIENT_VERSION with 426", async () => {
    const w = await makeWorker("old", { client_version: "0.0.9" });
    const r = await lease(w.token);
    expect(r.status).toBe(426);
    expect(r.body.min_client_version).toBe("0.1.0");
    // A newer version reported in X-Client-Version is accepted and persisted.
    expect((await lease(w.token, ["label"], 1, { "x-client-version": "0.1.3" })).status).toBe(200);
    expect((await lease(w.token)).status).toBe(200);
  });
});

describe("expiry, reclaim, heartbeat, release", () => {
  it("cron reclaims expired leases and dead-letters after 3 attempts", async () => {
    const pin = await makePin();
    const [jobId] = await addJobs([{ pin_hash: pin.pin_hash }]);
    const w = await makeWorker();
    for (let attempt = 1; attempt <= 3; attempt++) {
      const r = await lease(w.token);
      expect(r.body.jobs[0]?.job_id).toBe(jobId);
      expect(r.body.jobs[0].attempt).toBe(attempt);
      await env.DB.prepare("UPDATE jobs SET lease_expires = ? WHERE job_id = ?").bind(Date.now() - 1, jobId).run();
      await runCron();
      const row = await env.DB.prepare("SELECT status, lease_worker FROM jobs WHERE job_id = ?").bind(jobId).first<any>();
      expect(row.status).toBe(attempt < 3 ? "queued" : "dead");
      expect(row.lease_worker).toBeNull();
    }
    expect((await lease(w.token)).body.jobs).toEqual([]);
    const hb = await callJson("POST", "/v1/heartbeat", { token: w.token, json: { job_ids: [jobId], stats: {} } });
    expect(hb.body).toEqual({ extended: [], revoked: [jobId] });
  });

  it("does not reclaim live leases; heartbeat extends to >= now + 10 min", async () => {
    const pin = await makePin();
    const [jobId] = await addJobs([{ pin_hash: pin.pin_hash }]);
    const w = await makeWorker();
    const other = await makeWorker("other");
    await lease(w.token);
    await env.DB.prepare("UPDATE jobs SET lease_expires = ? WHERE job_id = ?").bind(Date.now() + 30_000, jobId).run();
    await runCron();
    expect((await env.DB.prepare("SELECT status FROM jobs WHERE job_id = ?").bind(jobId).first<any>()).status).toBe("leased");
    const hb = await callJson("POST", "/v1/heartbeat", { token: w.token, json: { job_ids: [jobId], stats: { tok_s: 123.4, passages_done: 7 } } });
    expect(hb.body).toEqual({ extended: [jobId], revoked: [] });
    const exp = (await env.DB.prepare("SELECT lease_expires FROM jobs WHERE job_id = ?").bind(jobId).first<any>()).lease_expires;
    expect(exp).toBeGreaterThan(Date.now() + 9.5 * 60_000);
    expect(exp).toBeLessThan(Date.now() + 10.5 * 60_000);
    // Someone else's heartbeat on the job is revoked, not extended.
    const hb2 = await callJson("POST", "/v1/heartbeat", { token: other.token, json: { job_ids: [jobId] } });
    expect(hb2.body).toEqual({ extended: [], revoked: [jobId] });
    const wr = await env.DB.prepare("SELECT tok_s, passages_done FROM workers WHERE id = ?").bind(w.worker_id).first<any>();
    expect(wr).toEqual({ tok_s: 123.4, passages_done: 7 });
  });

  it("release returns jobs to the queue without burning an attempt", async () => {
    const pin = await makePin();
    const [jobId] = await addJobs([{ pin_hash: pin.pin_hash }]);
    const w = await makeWorker();
    await lease(w.token);
    const r = await callJson("POST", "/v1/release", { token: w.token, json: { job_ids: [jobId, "not-mine"] } });
    expect(r.body).toEqual({ released: [jobId] });
    const row = await env.DB.prepare("SELECT status, attempt FROM jobs WHERE job_id = ?").bind(jobId).first<any>();
    expect(row).toEqual({ status: "queued", attempt: 0 });
  });
});

describe("pin activation and close_jobs", () => {
  it("inactive pins are not leased; leased jobs of a deactivated pin are revoked on heartbeat", async () => {
    const pin = await makePin();
    const [j1, j2] = await addJobs([{ pin_hash: pin.pin_hash }, { pin_hash: pin.pin_hash }]);
    const w = await makeWorker();
    const r = await lease(w.token);
    const held = r.body.jobs[0].job_id;
    // Deactivate via the pin endpoint.
    expect((await admin("POST", "/v1/admin/pin", { pin_hash: pin.pin_hash, active: false })).body.active).toBe(false);
    expect((await lease(w.token, ["label"], 5)).body.jobs).toEqual([]);
    const hb = await callJson("POST", "/v1/heartbeat", { token: w.token, json: { job_ids: [held] } });
    expect(hb.body).toEqual({ extended: [], revoked: [held] });
    const row = await env.DB.prepare("SELECT status, lease_worker FROM jobs WHERE job_id = ?").bind(held).first<any>();
    expect(row).toEqual({ status: "queued", lease_worker: null });
    // Reactivate via the registry's active_pins.
    const reg = await callJson("PUT", "/v1/admin/registry", { token: "test-admin-token", body: JSON.stringify({ active_pins: [pin.pin_hash] }) });
    expect(reg.status).toBe(200);
    const again = await lease(w.token, ["label"], 5);
    expect(again.body.jobs.map((j: any) => j.job_id).sort()).toEqual([j1, j2].sort());
    // And deactivate through the registry (pin not listed).
    await callJson("PUT", "/v1/admin/registry", { token: "test-admin-token", body: JSON.stringify({ active_pins: [] }) });
    const hb2 = await callJson("POST", "/v1/heartbeat", { token: w.token, json: { job_ids: [j1, j2] } });
    expect(hb2.body.revoked.sort()).toEqual([j1, j2].sort());
    await admin("POST", "/v1/admin/pin", { pin_hash: pin.pin_hash, active: true });
  });

  it("close_jobs cancels queued and leased jobs; heartbeat reports them revoked", async () => {
    const pin = await makePin();
    const [a, b, c] = await addJobs([{ pin_hash: pin.pin_hash }, { pin_hash: pin.pin_hash }, { pin_hash: pin.pin_hash }]);
    const w = await makeWorker();
    const held = (await lease(w.token)).body.jobs[0].job_id;
    const closed = await admin("POST", "/v1/admin/close_jobs", { job_ids: [a, b] });
    expect(closed.body.closed.sort()).toEqual([a, b].sort());
    const hb = await callJson("POST", "/v1/heartbeat", { token: w.token, json: { job_ids: [held] } });
    if (held === c) expect(hb.body.extended).toEqual([c]);
    else expect(hb.body.revoked).toEqual([held]);
  });
});

describe("every stage in STAGES is storable", () => {
  it("accepts pins and jobs for workcheck and alt_label (D1 CHECK constraints match STAGES)", async () => {
    const { STAGES } = await import("../src/util");
    const w = await makeWorker("allstages");
    for (const stage of STAGES) {
      const pin = await makePin(stage);
      const [id] = await addJobs([{ pin_hash: pin.pin_hash, stage }]);
      const r = await lease(w.token, [stage]);
      expect(r.status).toBe(200);
      expect(r.body.jobs.map((j: { job_id: string }) => j.job_id)).toEqual([id]);
    }
  });
});

describe("close_jobs by wave", () => {
  it("closes every open job of a wave and nothing else", async () => {
    const pin = await makePin();
    const [keep] = await addJobs([{ pin_hash: pin.pin_hash }]); // wave w1
    await admin("POST", "/v1/admin/jobs", {
      jobs: ["t1", "t2"].map((id) => ({ job_id: `wt-${id}`, stage: "label", wave: "wtest", shard_key: `wtest/${id}`,
        pin_hash: pin.pin_hash, n_passages: 3, split: "discovery", priority: 1 })),
    });
    const r = await admin("POST", "/v1/admin/close_jobs", { wave: "wtest" });
    expect(r.status).toBe(200);
    expect(r.body.closed.sort()).toEqual(["wt-t1", "wt-t2"]);
    const w = await makeWorker("wavecheck");
    const l = await lease(w.token, ["label"], 4);
    expect(l.body.jobs.map((j: { job_id: string }) => j.job_id)).toEqual([keep]);
    expect((await admin("POST", "/v1/admin/close_jobs", {})).status).toBe(400);
  });
});
