import { env } from "cloudflare:test";
import { beforeEach, describe, expect, it } from "vitest";
import { BWTEST_BYTES } from "../src/worker_routes";
import { ADMIN, addJobs, admin, call, callJson, lease, makePin, makeWorker, resetQueue, resultBlob, upload } from "./helpers";

beforeEach(resetQueue);

describe("ping, client releases, installers, bwtest", () => {
  it("ping reports versions, wheel url and registry version", async () => {
    const before = await callJson("GET", "/v1/ping");
    expect(before.status).toBe(200);
    expect(Object.keys(before.body).sort()).toEqual(["latest_client_version", "min_client_version", "ok", "queue", "registry_version", "wheel_url"]);
    expect(before.body.ok).toBe(true);

    // Release requires the wheel to exist first.
    expect((await admin("PUT", "/v1/admin/client_release", { version: "0.3.0", min_version: "0.2.0" })).status).toBe(400);
    const wheel = new Uint8Array([0x50, 0x4b, 3, 4, 9, 9]);
    const up = await callJson("PUT", "/v1/admin/dist/ald-0.3.0-py3-none-any.whl", { token: ADMIN, body: wheel });
    expect(up.status).toBe(200);
    const rel = await admin("PUT", "/v1/admin/client_release", { version: "0.3.0", min_version: "0.2.0" });
    expect(rel.status).toBe(200);
    const p = await callJson("GET", "/v1/ping");
    expect(p.body).toMatchObject({
      ok: true,
      min_client_version: "0.2.0",
      latest_client_version: "0.3.0",
      wheel_url: "https://coord.test/dist/ald-0.3.0-py3-none-any.whl",
    });
    // Wheel served publicly, byte-exact.
    const dl = await call("GET", "/dist/ald-0.3.0-py3-none-any.whl");
    expect(dl.status).toBe(200);
    expect(new Uint8Array(await dl.arrayBuffer())).toEqual(wheel);
    // min_version now enforced at lease, with upgrade info in the 426.
    const w = await makeWorker("oldie", { client_version: "0.1.5" });
    const l = await lease(w.token);
    expect(l.status).toBe(426);
    expect(l.body.wheel_url).toBe("https://coord.test/dist/ald-0.3.0-py3-none-any.whl");
    // Restore for other tests.
    await env.DB.prepare("DELETE FROM config WHERE key = 'min_client_version'").run();
  });

  it("registry: ETag / If-None-Match -> 304, version bumps per upload", async () => {
    const v0 = (await callJson("GET", "/v1/ping")).body.registry_version;
    const reg = { version: 1, tiers: { t16: { stages: ["screen", "label"] } } };
    const up = await callJson("PUT", "/v1/admin/registry", { token: ADMIN, body: JSON.stringify(reg) });
    expect(up.status).toBe(200);
    expect(up.body.registry_version).toBe(v0 + 1);
    const r1 = await call("GET", "/v1/registry");
    expect(r1.status).toBe(200);
    const etag = r1.headers.get("etag")!;
    expect(etag).toMatch(/^"[0-9a-f]{64}"$/);
    expect(await r1.json()).toEqual(reg);
    const r2 = await call("GET", "/v1/registry", { headers: { "if-none-match": etag } });
    expect(r2.status).toBe(304);
    expect(await r2.text()).toBe("");
    const reg2 = { ...reg, version: 2 };
    const up2 = await callJson("PUT", "/v1/admin/registry", { token: ADMIN, body: JSON.stringify(reg2) });
    expect(up2.body.registry_version).toBe(v0 + 2);
    const r3 = await call("GET", "/v1/registry", { headers: { "if-none-match": etag } });
    expect(r3.status).toBe(200);
    expect((await callJson("GET", "/v1/ping")).body.registry_version).toBe(v0 + 2);
    expect((await callJson("PUT", "/v1/admin/registry", { token: ADMIN, body: "not json" })).status).toBe(400);
  });

  it("registry tier table restricts leasable stages", async () => {
    await callJson("PUT", "/v1/admin/registry", { token: ADMIN, body: JSON.stringify({ tiers: { t8: { stages: ["screen"] }, t16: ["screen", "label"] } }) });
    const pin = await makePin("label");
    await addJobs([{ pin_hash: pin.pin_hash }]);
    const w = await makeWorker();
    const small = await callJson("POST", "/v1/lease", { token: w.token, json: { tier: "t8", stages: ["label"], max_jobs: 1 } });
    expect(small.body.jobs).toEqual([]);
    const big = await callJson("POST", "/v1/lease", { token: w.token, json: { tier: "t16", stages: ["label"], max_jobs: 1 } });
    expect(big.body.jobs.length).toBe(1);
    await callJson("PUT", "/v1/admin/registry", { token: ADMIN, body: JSON.stringify({ version: 3 }) });
  });

  it("installer scripts are templated with the coordinator origin", async () => {
    const script = "#!/bin/sh\nuv tool install __COORDINATOR_URL__/dist/x.whl\necho __COORDINATOR_URL__\n";
    expect((await callJson("PUT", "/v1/admin/install/install.sh", { token: ADMIN, body: script })).status).toBe(200);
    expect((await callJson("PUT", "/v1/admin/install/evil.sh", { token: ADMIN, body: script })).status).toBe(400);
    const r = await call("GET", "/install.sh");
    expect(r.status).toBe(200);
    expect(r.headers.get("content-type")).toContain("text/plain");
    expect(await r.text()).toBe("#!/bin/sh\nuv tool install https://coord.test/dist/x.whl\necho https://coord.test\n");
    expect((await call("GET", "/install.ps1")).status).toBe(404);
  });

  it("bwtest serves a 10 MiB object, generated on first request", async () => {
    const r = await call("GET", "/v1/bwtest");
    expect(r.status).toBe(200);
    expect((await r.arrayBuffer()).byteLength).toBe(BWTEST_BYTES);
    expect(await env.BUCKET.head("bwtest/10mb.bin")).not.toBeNull();
  });
});

describe("auth", () => {
  it("every kind of bad credential gets the identical 401", async () => {
    const w = await makeWorker();
    const ann = await admin("POST", "/v1/admin/annotators", { name: `auth-${Date.now()}` });
    const probes = [
      await call("POST", "/v1/lease", { json: { stages: ["label"] } }),
      await call("POST", "/v1/lease", { token: "garbage", json: { stages: ["label"] } }),
      await call("POST", "/v1/lease", { token: ADMIN, json: { stages: ["label"] } }),
      await call("POST", "/v1/lease", { token: ann.body.token, json: { stages: ["label"] } }),
      await call("GET", "/v1/status", { token: w.token }),
      await call("GET", "/v1/status", { token: ann.body.token }),
      await call("POST", "/v1/admin/invite", { token: "garbage", json: { n: 1 } }),
    ];
    const bodies = await Promise.all(probes.map(async (r) => [r.status, await r.text()]));
    for (const b of bodies) expect(b).toEqual([401, '{"error":"unauthorized"}']);
  });

  it("invites are single use", async () => {
    const inv = await admin("POST", "/v1/admin/invite", { n: 1 });
    const code = inv.body.invites[0];
    const [a, b] = await Promise.all([
      callJson("POST", "/v1/join", { json: { invite: code, name: "a" } }),
      callJson("POST", "/v1/join", { json: { invite: code, name: "b" } }),
    ]);
    expect([a.status, b.status].sort()).toEqual([200, 403]);
    const n = await env.DB.prepare("SELECT COUNT(*) AS n FROM workers WHERE name IN ('a','b')").first<{ n: number }>();
    expect(n!.n).toBe(1);
    // Only hashes are stored.
    const raw = await env.DB.prepare("SELECT COUNT(*) AS n FROM invites WHERE code_sha256 = ?").bind(code).first<{ n: number }>();
    expect(raw!.n).toBe(0);
  });
});

describe("status", () => {
  it("aggregates per-worker throughput, queue counts and ETA", async () => {
    const pin = await makePin();
    const ids = await addJobs(Array.from({ length: 4 }, (_, i) => ({ pin_hash: pin.pin_hash, n_passages: 3, cell: i < 2 ? "1820s|random" : "1900s|random" })));
    const w = await makeWorker("statusw");
    await lease(w.token, ["label"], 2);
    const leased = (await env.DB.prepare("SELECT job_id FROM jobs WHERE status = 'leased'").all<{ job_id: string }>()).results.map((r) => r.job_id);
    await upload(w.token, leased[0], pin, await resultBlob(["a", "b", "c"]));
    await callJson("POST", "/v1/heartbeat", { token: w.token, json: { job_ids: [leased[1]], stats: { tok_s: 42, passages_done: 3 } } });
    const s = await admin("GET", "/v1/status");
    expect(s.status).toBe(200);
    const me = s.body.workers.find((x: any) => x.id === w.worker_id);
    expect(me).toMatchObject({ name: "statusw", tier: "t16", os: "linux", passages_1h: 3, passages_24h: 3, tok_s: 42 });
    expect(s.body.queue.label).toEqual({ queued: 2, leased: 1, done: 1, dead: 0, closed: 0 });
    expect(s.body.remaining_passages.label).toBe(9);
    expect(s.body.eta_hours.label).toBe(3); // 9 remaining / 3 per hour
    expect(s.body.eta_hours.embed).toBe(0);
    expect(s.body.cells.length).toBe(2);
    expect(s.body.cells.every((c: any) => c.open)).toBe(true);
    expect(ids.length).toBe(4);
  });
});
