import { env } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { ADMIN, addJobs, admin, call, lease, makePin, makeWorker, resultBlob, upload } from "./helpers";

// One sequential story: the seal is irreversible, so ordering matters here.
describe("confirmation seal", () => {
  it("stores confirmation results under sealed/ and refuses them until unseal, irreversibly", async () => {
    const pin = await makePin();
    const [disc] = await addJobs([{ pin_hash: pin.pin_hash, split: "discovery", job_id: "seal-disc" }]);
    const [conf] = await addJobs([{ pin_hash: pin.pin_hash, split: "confirmation", job_id: "seal-conf" }]);
    const w = await makeWorker();
    await lease(w.token, ["label"], 2);
    const rd = await upload(w.token, disc, pin, await resultBlob(["d1"]));
    const rc = await upload(w.token, conf, pin, await resultBlob(["c1"]));
    const rp = await upload(w.token, conf, pin, await resultBlob(["c2"]), { partial: true });
    expect(rd.body.r2_key).toBe(`results/${disc}/${w.worker_id}.jsonl.gz`);
    expect(rc.body.r2_key).toBe(`sealed/results/${conf}/${w.worker_id}.jsonl.gz`);
    expect(rp.body.r2_key).toBe(`sealed/results/${conf}/${w.worker_id}.part1.jsonl.gz`);

    // Before unseal: explicit confirmation listing refused; default listing omits it; blobs refused.
    expect((await admin("GET", "/v1/admin/results?split=confirmation")).status).toBe(403);
    const all = await admin("GET", "/v1/admin/results");
    expect(all.body.sealed).toBe(true);
    expect(all.body.results.some((r: any) => r.split === "confirmation" || r.r2_key.startsWith("sealed/"))).toBe(false);
    expect(all.body.results.some((r: any) => r.job_id === disc)).toBe(true);
    const blobRes = await call("GET", `/v1/admin/blob?key=${encodeURIComponent(rc.body.r2_key)}`, { token: ADMIN });
    expect(blobRes.status).toBe(403);
    const slash = await call("GET", `/v1/admin/blob?key=${encodeURIComponent("/" + rc.body.r2_key)}`, { token: ADMIN });
    expect(slash.status).toBe(403);
    expect((await call("GET", `/v1/admin/blob?key=${encodeURIComponent(rd.body.r2_key)}`, { token: ADMIN })).status).toBe(200);
    // Non-admins can't unseal; malformed hash rejected.
    expect((await call("POST", "/v1/admin/unseal", { token: w.token, json: { prereg_hash: "a".repeat(64) } })).status).toBe(401);
    expect((await admin("POST", "/v1/admin/unseal", { prereg_hash: "not-a-hash" })).status).toBe(400);

    // Unseal.
    const h = "ab".repeat(32);
    const u = await admin("POST", "/v1/admin/unseal", { prereg_hash: h });
    expect(u.status).toBe(200);
    expect(u.body.status).toBe("unsealed");
    expect((await admin("POST", "/v1/admin/unseal", { prereg_hash: h })).body.status).toBe("already_unsealed");
    expect((await admin("POST", "/v1/admin/unseal", { prereg_hash: "cd".repeat(32) })).status).toBe(409);
    // The seal row cannot be deleted or changed, even directly in SQL.
    await expect(env.DB.prepare("DELETE FROM seal").run()).rejects.toThrow(/irreversible/);
    await expect(env.DB.prepare("UPDATE seal SET prereg_hash = 'x'").run()).rejects.toThrow(/irreversible/);

    // After unseal: available.
    const conf2 = await admin("GET", "/v1/admin/results?split=confirmation");
    expect(conf2.status).toBe(200);
    expect(conf2.body.results.map((r: any) => [r.job_id, r.partial])).toEqual([
      [conf, false],
      [conf, true],
    ]);
    const blob2 = await call("GET", `/v1/admin/blob?key=${encodeURIComponent(rc.body.r2_key)}`, { token: ADMIN });
    expect(blob2.status).toBe(200);
  });
});
