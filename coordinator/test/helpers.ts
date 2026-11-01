import { createExecutionContext, env, waitOnExecutionContext, createScheduledController } from "cloudflare:test";
import worker from "../src/index";
import { gzipText, sha256Hex } from "../src/util";

export const ADMIN = "test-admin-token";
export const BASE = "https://coord.test";

let counter = 0;
export const uid = (p = "t") => `${p}${Date.now().toString(36)}${(counter++).toString(36)}${Math.random().toString(36).slice(2, 6)}`;

export interface CallOpts {
  token?: string;
  json?: unknown;
  body?: BodyInit | Uint8Array;
  headers?: Record<string, string>;
}

export async function call(method: string, path: string, o: CallOpts = {}): Promise<Response> {
  const headers: Record<string, string> = { ...(o.headers ?? {}) };
  if (o.token) headers.authorization = `Bearer ${o.token}`;
  let body: BodyInit | undefined;
  if (o.json !== undefined) {
    headers["content-type"] = "application/json";
    body = JSON.stringify(o.json);
  } else if (o.body !== undefined) body = o.body as BodyInit;
  const ctx = createExecutionContext();
  const res = await worker.fetch(new Request(BASE + path, { method, headers, body }), env, ctx);
  await waitOnExecutionContext(ctx);
  return res;
}

export async function callJson<T = any>(method: string, path: string, o: CallOpts = {}): Promise<{ status: number; body: T }> {
  const r = await call(method, path, o);
  const text = await r.text();
  let body: any = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  return { status: r.status, body };
}

export const admin = (method: string, path: string, json?: unknown) => callJson(method, path, { token: ADMIN, json });

export async function runCron(): Promise<void> {
  const ctx = createExecutionContext();
  await worker.scheduled(createScheduledController({ scheduledTime: Date.now(), cron: "*/5 * * * *" }), env, ctx);
  await waitOnExecutionContext(ctx);
}

export interface Pin {
  pin_hash: string;
  stage: string;
  model_ref: string;
  model_digest: string;
  prompt_hash: string;
  schema_hash: string;
  options: Record<string, unknown>;
}

export async function makePin(stage = "label"): Promise<Pin> {
  const pin: Pin = {
    pin_hash: uid("pin"),
    stage,
    model_ref: "qwen-test:8b-q4",
    model_digest: "sha256:" + (await sha256Hex(uid())),
    prompt_hash: "p1",
    schema_hash: "s1",
    options: { temperature: 0, seed: 0 },
  };
  const r = await admin("POST", "/v1/admin/pin", pin);
  if (r.status !== 200) throw new Error(`pin: ${r.status} ${JSON.stringify(r.body)}`);
  return pin;
}

export async function makeWorker(name = "w", extra: Record<string, unknown> = {}): Promise<{ worker_id: string; token: string }> {
  const inv = await admin("POST", "/v1/admin/invite", { n: 1 });
  const r = await callJson("POST", "/v1/join", {
    json: { invite: inv.body.invites[0], name, os: "linux", arch: "x86_64", gpu: "test", vram_gb: 16, ram_gb: 32, tier: "t16", client_version: "0.1.0", ...extra },
  });
  if (r.status !== 200) throw new Error(`join: ${r.status} ${JSON.stringify(r.body)}`);
  return r.body;
}

export interface JobSpec {
  job_id?: string;
  stage?: string;
  pin_hash: string;
  n_passages?: number;
  split?: "discovery" | "confirmation";
  dup_group?: string | null;
  priority?: number;
  cell?: string;
}

export async function addJobs(specs: JobSpec[]): Promise<string[]> {
  const jobs = specs.map((s) => ({
    job_id: s.job_id ?? uid("job"),
    stage: s.stage ?? "label",
    wave: "w1",
    shard_key: `w1/${uid("sh")}`,
    pin_hash: s.pin_hash,
    n_passages: s.n_passages ?? 3,
    split: s.split ?? "discovery",
    dup_group: s.dup_group ?? null,
    priority: s.priority ?? 100,
    ...(s.cell ? { cell: s.cell } : {}),
  }));
  const r = await admin("POST", "/v1/admin/jobs", { jobs });
  if (r.status !== 200) throw new Error(`jobs: ${r.status} ${JSON.stringify(r.body)}`);
  return jobs.map((j) => j.job_id);
}

export async function lease(token: string, stages = ["label"], max_jobs = 1, headers: Record<string, string> = {}) {
  return callJson("POST", "/v1/lease", { token, json: { tier: "t16", stages, max_jobs }, headers });
}

export async function resultBlob(passageIds: string[]): Promise<{ body: Uint8Array; sha: string }> {
  const lines = passageIds.map((p) => JSON.stringify({ passage_id: p, stage: "label", output: { has_obstacle: "no" }, valid_schema: true })).join("\n") + "\n";
  const body = await gzipText(lines);
  return { body, sha: await sha256Hex(body) };
}

export async function upload(
  token: string,
  jobId: string,
  pin: Pin,
  blob: { body: Uint8Array; sha: string },
  opts: { partial?: boolean; headers?: Record<string, string> } = {},
) {
  return callJson("PUT", `/v1/result/${jobId}${opts.partial ? "?partial=1" : ""}`, {
    token,
    body: blob.body,
    headers: {
      "x-content-sha256": blob.sha,
      "x-pin-hash": pin.pin_hash,
      "x-model-digest": pin.model_digest,
      "x-backend-version": "ollama-0.12",
      "x-stats": JSON.stringify({ n_ok: 3, n_flagged: 0, tok_s: 50, wall_s: 10, prompt_tokens: 100, gen_tokens: 50 }),
      ...(opts.headers ?? {}),
    },
  });
}

/** Clear queue state between tests (the seal table is irreversible by design and is not touched). */
export async function resetQueue(): Promise<void> {
  await env.DB.batch(
    ["job_partials", "results", "leases", "jobs"].map((t) => env.DB.prepare(`DELETE FROM ${t}`)),
  );
}
