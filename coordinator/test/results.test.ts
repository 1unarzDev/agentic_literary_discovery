import { env } from "cloudflare:test";
import { beforeEach, describe, expect, it } from "vitest";
import { bytesToBase64, gzipText } from "../src/util";
import { addJobs, admin, callJson, lease, makePin, makeWorker, resetQueue, resultBlob, upload } from "./helpers";

beforeEach(resetQueue);

async function setup(n = 1) {
  const pin = await makePin();
  const jobIds = await addJobs(Array.from({ length: n }, () => ({ pin_hash: pin.pin_hash, n_passages: 3 })));
  const w = await makeWorker();
  return { pin, jobIds, w };
}

const statusOf = async (jobId: string) =>
  (await env.DB.prepare("SELECT status FROM jobs WHERE job_id = ?").bind(jobId).first<{ status: string }>())!.status;

describe("PUT /v1/result (idempotent)", () => {
  it("same sha -> duplicate, different sha -> 409, and the job is done", async () => {
    const { pin, jobIds, w } = await setup();
    await lease(w.token);
    const blob = await resultBlob(["p1", "p2", "p3"]);
    const r1 = await upload(w.token, jobIds[0], pin, blob);
    expect(r1.status).toBe(200);
    expect(r1.body.status).toBe("stored");
    expect(r1.body.r2_key).toBe(`results/${jobIds[0]}/${w.worker_id}.jsonl.gz`);
    expect(await statusOf(jobIds[0])).toBe("done");
    const stored = await env.BUCKET.get(r1.body.r2_key);
    expect(new Uint8Array(await stored!.arrayBuffer())).toEqual(blob.body);

    const r2 = await upload(w.token, jobIds[0], pin, blob);
    expect(r2.status).toBe(200);
    expect(r2.body.status).toBe("duplicate");

    const r3 = await upload(w.token, jobIds[0], pin, await resultBlob(["p1", "p2", "other"]));
    expect(r3.status).toBe(409);
    // Exactly one index row, per shard (not per passage).
    const n = await env.DB.prepare("SELECT COUNT(*) AS n FROM results WHERE job_id = ?").bind(jobIds[0]).first<{ n: number }>();
    expect(n!.n).toBe(1);
  });

  it("412 on pin or model digest mismatch; digest prefix 'sha256:' is normalised", async () => {
    const { pin, jobIds, w } = await setup();
    await lease(w.token);
    const blob = await resultBlob(["p1"]);
    const badPin = await upload(w.token, jobIds[0], pin, blob, { headers: { "x-pin-hash": "someotherpin" } });
    expect(badPin.status).toBe(412);
    expect(badPin.body.expected_pin_hash).toBe(pin.pin_hash);
    const badDigest = await upload(w.token, jobIds[0], pin, blob, { headers: { "x-model-digest": "sha256:deadbeef" } });
    expect(badDigest.status).toBe(412);
    expect(await statusOf(jobIds[0])).toBe("leased");
    const bare = await upload(w.token, jobIds[0], pin, blob, { headers: { "x-model-digest": pin.model_digest.replace("sha256:", "") } });
    expect(bare.body.status).toBe("stored");
  });

  it("400 when body does not match X-Content-Sha256; 403 for a worker that never leased the job", async () => {
    const { pin, jobIds, w } = await setup();
    await lease(w.token);
    const blob = await resultBlob(["p1"]);
    const bad = await upload(w.token, jobIds[0], pin, { body: blob.body, sha: "0".repeat(64) });
    expect(bad.status).toBe(400);
    const stranger = await makeWorker("stranger");
    expect((await upload(stranger.token, jobIds[0], pin, blob)).status).toBe(403);
    expect((await upload(w.token, "no-such-job", pin, blob)).status).toBe(404);
  });

  it("accepts late uploads after expiry/reassignment; a second full result is late_duplicate", async () => {
    const { pin, jobIds, w } = await setup();
    const w2 = await makeWorker("w2");
    await lease(w.token);
    await env.DB.prepare("UPDATE jobs SET lease_expires = 0 WHERE job_id = ?").bind(jobIds[0]).run();
    const r2 = await lease(w2.token); // lazily reclaims, then reassigns
    expect(r2.body.jobs[0].job_id).toBe(jobIds[0]);
    // Original worker's late upload is accepted.
    const late = await upload(w.token, jobIds[0], pin, await resultBlob(["p1", "p2", "p3"]));
    expect(late.body.status).toBe("stored");
    expect(await statusOf(jobIds[0])).toBe("done");
    // The new holder's heartbeat now revokes it, and its upload is a late duplicate.
    const hb = await callJson("POST", "/v1/heartbeat", { token: w2.token, json: { job_ids: [jobIds[0]] } });
    expect(hb.body.revoked).toEqual([jobIds[0]]);
    const dup = await upload(w2.token, jobIds[0], pin, await resultBlob(["p1", "p2", "p3", "x"]));
    expect(dup.status).toBe(200);
    expect(dup.body.status).toBe("late_duplicate");
    const rows = await env.DB.prepare("SELECT worker_id, late FROM results WHERE job_id = ? ORDER BY late").bind(jobIds[0]).all<any>();
    expect(rows.results).toEqual([
      { worker_id: w.worker_id, late: 0 },
      { worker_id: w2.worker_id, late: 1 },
    ]);
  });
});

describe("partial uploads", () => {
  const idsHeader = async (ids: string[]) => bytesToBase64(await gzipText(JSON.stringify(ids)));

  it("stores parts, keeps the job leased, and the next lease skips covered passages", async () => {
    const { pin, jobIds, w } = await setup();
    const jobId = jobIds[0];
    await lease(w.token);
    const p1 = await resultBlob(["p1"]);
    const r1 = await upload(w.token, jobId, pin, p1, { partial: true, headers: { "x-passage-ids": await idsHeader(["p1"]) } });
    expect(r1.body).toMatchObject({ status: "stored", partial: true, part_n: 1, n_ids: 1 });
    expect(r1.body.r2_key).toBe(`results/${jobId}/${w.worker_id}.part1.jsonl.gz`);
    // Same part again: duplicate, no new part number.
    const again = await upload(w.token, jobId, pin, p1, { partial: true, headers: { "x-passage-ids": await idsHeader(["p1"]) } });
    expect(again.body).toMatchObject({ status: "duplicate", part_n: 1 });
    // Without the header the server reads ids from the blob.
    const r2 = await upload(w.token, jobId, pin, await resultBlob(["p2"]), { partial: true });
    expect(r2.body).toMatchObject({ status: "stored", part_n: 2, n_ids: 1 });
    expect(await statusOf(jobId)).toBe("leased");
    const rows = await env.DB.prepare("SELECT part_n, passage_ids_json FROM job_partials WHERE job_id = ? ORDER BY part_n").bind(jobId).all<any>();
    expect(rows.results).toEqual([
      { part_n: 1, passage_ids_json: '["p1"]' },
      { part_n: 2, passage_ids_json: '["p2"]' },
    ]);

    // Worker dies; the lease expires; another worker gets skip_passage_ids.
    await env.DB.prepare("UPDATE jobs SET lease_expires = 0 WHERE job_id = ?").bind(jobId).run();
    const w2 = await makeWorker("w2");
    const l2 = await lease(w2.token);
    expect(l2.body.jobs[0].job_id).toBe(jobId);
    expect(l2.body.jobs[0].skip_passage_ids.sort()).toEqual(["p1", "p2"]);

    // Admin listing includes partials, flagged.
    const list = await admin("GET", "/v1/admin/results");
    const mine = list.body.results.filter((r: any) => r.job_id === jobId);
    expect(mine.length).toBe(2);
    expect(mine.every((r: any) => r.partial === true)).toBe(true);
    expect(mine.map((r: any) => r.part_n)).toEqual([1, 2]);
  });

  it("a job fully covered by partials is marked done instead of being leased", async () => {
    const { pin, jobIds, w } = await setup(2);
    const covered = jobIds[0];
    // Lease both, upload partials covering all 3 passages of `covered`.
    await lease(w.token, ["label"], 2);
    await upload(w.token, covered, pin, await resultBlob(["a", "b"]), { partial: true });
    await upload(w.token, covered, pin, await resultBlob(["c"]), { partial: true });
    expect(await statusOf(covered)).toBe("leased");
    await env.DB.prepare("UPDATE jobs SET lease_expires = 0").run();
    const w2 = await makeWorker("w2");
    const l = await lease(w2.token, ["label"], 2);
    expect(l.body.jobs.map((j: any) => j.job_id)).toEqual([jobIds[1]]);
    expect(await statusOf(covered)).toBe("done");
    const row = await env.DB.prepare("SELECT done_by FROM jobs WHERE job_id = ?").bind(covered).first<any>();
    expect(row.done_by).toBe("partials");
  });

  it("late partial uploads from an expired lease are accepted", async () => {
    const { pin, jobIds, w } = await setup();
    await lease(w.token);
    await env.DB.prepare("UPDATE jobs SET lease_expires = 0 WHERE job_id = ?").bind(jobIds[0]).run();
    const w2 = await makeWorker("w2");
    await lease(w2.token);
    const r = await upload(w.token, jobIds[0], pin, await resultBlob(["p1"]), { partial: true });
    expect(r.body.status).toBe("stored");
    expect(await statusOf(jobIds[0])).toBe("leased");
  });
});
