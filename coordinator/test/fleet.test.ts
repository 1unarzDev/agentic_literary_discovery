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
