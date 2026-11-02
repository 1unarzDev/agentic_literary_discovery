import { Hono } from "hono";
import { AppEnv, requireAdmin } from "./auth";
import { REF_SETS, certFor, validateReference } from "./annotate_routes";
import { CFG, getConfig, sealState, setConfigStmt } from "./db";
import { REGISTRY_KEY } from "./registry";
import {
  HttpError,
  SPLITS,
  STAGES,
  compareVersions,
  hash48,
  isStringArray,
  json,
  nowIso,
  randomId,
  randomToken,
  readJson,
  sha256Hex,
} from "./util";
import { wheelUrl } from "./worker_routes";

export const adminRoutes = new Hono<AppEnv>();
adminRoutes.use("/v1/admin/*", requireAdmin);

const SAFE_ID = /^[A-Za-z0-9._-]{1,128}$/;
const HEX64 = /^[0-9a-f]{64}$/;
const VERSION_RE = /^\d+(\.\d+){0,3}([A-Za-z0-9.+_]*)$/;
export const INSTALL_SCRIPTS = ["install.sh", "install.ps1"] as const;

function stableStringify(v: unknown): string {
  if (v === null || typeof v !== "object") return JSON.stringify(v);
  if (Array.isArray(v)) return `[${v.map(stableStringify).join(",")}]`;
  const o = v as Record<string, unknown>;
  return `{${Object.keys(o)
    .sort()
    .map((k) => `${JSON.stringify(k)}:${stableStringify(o[k])}`)
    .join(",")}}`;
}

function parseJsonField(s: string): unknown {
  try {
    return JSON.parse(s);
  } catch {
    return s;
  }
}

// ------------------------------------------------------------------ invites

adminRoutes.post("/v1/admin/invite", async (c) => {
  const b = await readJson<{ n?: unknown }>(c.req.raw);
  const n = b.n === undefined ? 1 : Number(b.n);
  if (!Number.isInteger(n) || n < 1 || n > 500) throw new HttpError(400, "n must be an integer in 1..500");
  const now = nowIso();
  const invites = Array.from({ length: n }, () => randomToken(16));
  const shas = await Promise.all(invites.map((code) => sha256Hex(code)));
  // One statement for the whole batch (stays within per-invocation query limits).
  await c.env.DB.prepare("INSERT INTO invites(code_sha256, created) SELECT value, ?2 FROM json_each(?1) WHERE true")
    .bind(JSON.stringify(shas), now)
    .run();
  return json({ invites });
});

// ------------------------------------------------------------------ viewer tokens (read-only fleet view)

adminRoutes.post("/v1/admin/viewer_token", async (c) => {
  const b = await readJson<{ name?: unknown }>(c.req.raw);
  const name = typeof b.name === "string" && b.name.trim() ? b.name.trim().slice(0, 64) : "viewer";
  const token = randomToken();
  await c.env.DB.prepare("INSERT INTO viewer_tokens(token_sha256, name, created) VALUES (?, ?, ?)")
    .bind(await sha256Hex(token), name, nowIso())
    .run();
  return json({ token, name, fleet_url: `${new URL(c.req.url).origin}/v1/fleet` });
});

// ------------------------------------------------------------------ pins

interface PinRow {
  pin_hash: string;
  stage: string;
  model_ref: string;
  model_digest: string;
  prompt_hash: string;
  schema_hash: string;
  options_json: string;
  active: number;
}

adminRoutes.post("/v1/admin/pin", async (c) => {
  const b = await readJson<Record<string, unknown>>(c.req.raw);
  const pinHash = b.pin_hash;
  if (typeof pinHash !== "string" || !pinHash) throw new HttpError(400, "pin_hash required");
  if (b.active !== undefined && typeof b.active !== "boolean") throw new HttpError(400, "active must be a boolean");
  const existing = await c.env.DB.prepare("SELECT * FROM pins WHERE pin_hash = ?").bind(pinHash).first<PinRow>();
  const fields = ["stage", "model_ref", "model_digest", "prompt_hash", "schema_hash"] as const;
  const onlyActive = Object.keys(b).every((k) => k === "pin_hash" || k === "active");

  if (existing) {
    if (!onlyActive) {
      const same =
        fields.every((f) => b[f] === undefined || b[f] === existing[f]) &&
        (b.options === undefined || stableStringify(b.options) === existing.options_json);
      if (!same) throw new HttpError(409, "pin_hash already registered with different fields");
    }
    if (typeof b.active === "boolean" && Number(b.active) !== existing.active) {
      await c.env.DB.prepare("UPDATE pins SET active = ? WHERE pin_hash = ?").bind(b.active ? 1 : 0, pinHash).run();
    }
    return json({ status: "exists", pin_hash: pinHash, active: typeof b.active === "boolean" ? b.active : !!existing.active });
  }
  for (const f of fields) {
    if (typeof b[f] !== "string" || !b[f]) throw new HttpError(400, `${f} required`);
  }
  if (!(STAGES as readonly string[]).includes(b.stage as string)) throw new HttpError(400, "unknown stage");
  const options = b.options ?? {};
  if (typeof options !== "object" || options === null || Array.isArray(options)) throw new HttpError(400, "options must be an object");
  const active = b.active === undefined ? true : (b.active as boolean);
  await c.env.DB.prepare(
    `INSERT INTO pins(pin_hash, stage, model_ref, model_digest, prompt_hash, schema_hash, options_json, active, created)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(pin_hash) DO NOTHING`,
  )
    .bind(pinHash, b.stage, b.model_ref, b.model_digest, b.prompt_hash, b.schema_hash, stableStringify(options), active ? 1 : 0, nowIso())
    .run();
  return json({ status: "created", pin_hash: pinHash, active });
});

// ------------------------------------------------------------------ shards & jobs

export function normalizeShardKey(k: string): string {
  let key = k.replace(/^\/+/, "");
  if (!key.startsWith("shards/")) key = `shards/${key}`;
  if (!key.endsWith(".jsonl.gz")) key = `${key}.jsonl.gz`;
  return key;
}

adminRoutes.put("/v1/admin/shard/:wave/:shard_id", async (c) => {
  const wave = c.req.param("wave");
  const shardId = c.req.param("shard_id").replace(/\.jsonl\.gz$/, "");
  if (!SAFE_ID.test(wave) || !SAFE_ID.test(shardId) || wave.includes("..") || shardId.includes(".."))
    throw new HttpError(400, "wave/shard_id must match [A-Za-z0-9._-]");
  const split = c.req.header("x-split") ?? "";
  if (!(SPLITS as readonly string[]).includes(split)) throw new HttpError(400, "X-Split must be discovery|confirmation");
  const nPassages = Number(c.req.header("x-n-passages"));
  if (!Number.isInteger(nPassages) || nPassages < 1) throw new HttpError(400, "X-N-Passages must be a positive integer");
  const decades = c.req.header("x-decades") ?? null;
  const body = await c.req.arrayBuffer();
  if (body.byteLength === 0) throw new HttpError(400, "empty body");
  const sha = await sha256Hex(body);
  const key = `shards/${wave}/${shardId}.jsonl.gz`;
  const existing = await c.env.DB.prepare("SELECT content_sha256, split FROM shards WHERE shard_key = ?")
    .bind(key)
    .first<{ content_sha256: string; split: string }>();
  if (existing) {
    if (existing.content_sha256 === sha && existing.split === split) return json({ status: "duplicate", shard_key: key, content_sha256: sha });
    throw new HttpError(409, "shard already uploaded with different content or split");
  }
  await c.env.BUCKET.put(key, body, {
    httpMetadata: { contentType: "application/gzip" },
    customMetadata: { content_sha256: sha, split, n_passages: String(nPassages), decades: decades ?? "" },
  });
  await c.env.DB.prepare(
    `INSERT INTO shards(shard_key, wave, shard_id, split, n_passages, decades, content_sha256, size, created)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(shard_key) DO NOTHING`,
  )
    .bind(key, wave, shardId, split, nPassages, decades, sha, body.byteLength, nowIso())
    .run();
  return json({ status: "stored", shard_key: key, content_sha256: sha });
});

adminRoutes.post("/v1/admin/jobs", async (c) => {
  const b = await readJson<{ jobs?: unknown }>(c.req.raw);
  const jobs = b.jobs;
  if (!Array.isArray(jobs) || jobs.length === 0) throw new HttpError(400, "jobs must be a non-empty array");
  if (jobs.length > 500) throw new HttpError(413, "at most 500 jobs per call");
  const pinHashes = [...new Set(jobs.map((j) => (j as { pin_hash?: unknown })?.pin_hash).filter((x) => typeof x === "string"))];
  const { results: pins } = await c.env.DB.prepare("SELECT pin_hash, stage FROM pins WHERE pin_hash IN (SELECT value FROM json_each(?))")
    .bind(JSON.stringify(pinHashes))
    .all<{ pin_hash: string; stage: string }>();
  const pinStage = new Map(pins.map((p) => [p.pin_hash, p.stage]));
  const shardKeys = jobs.map((j) => normalizeShardKey(String((j as { shard_key?: unknown })?.shard_key ?? "")));
  const { results: shards } = await c.env.DB.prepare("SELECT shard_key, split FROM shards WHERE shard_key IN (SELECT value FROM json_each(?))")
    .bind(JSON.stringify([...new Set(shardKeys)]))
    .all<{ shard_key: string; split: string }>();
  const shardSplit = new Map(shards.map((s) => [s.shard_key, s.split]));
  const now = nowIso();
  const errors: string[] = [];
  const rows: unknown[] = [];
  jobs.forEach((raw, i) => {
    const j = (raw ?? {}) as Record<string, unknown>;
    const err = (m: string) => errors.push(`jobs[${i}]: ${m}`);
    if (typeof j.job_id !== "string" || !SAFE_ID.test(j.job_id)) return err("job_id must match [A-Za-z0-9._-]{1,128}");
    if (!(STAGES as readonly string[]).includes(j.stage as string)) return err("unknown stage");
    if (typeof j.wave !== "string" || !j.wave) return err("wave required");
    if (typeof j.shard_key !== "string" || !j.shard_key) return err("shard_key required");
    if (typeof j.pin_hash !== "string" || !pinStage.has(j.pin_hash)) return err("unknown pin_hash (register it first)");
    if (pinStage.get(j.pin_hash) !== j.stage) return err("pin stage does not match job stage");
    if (!Number.isInteger(j.n_passages) || (j.n_passages as number) < 1) return err("n_passages must be a positive integer");
    if (!(SPLITS as readonly string[]).includes(j.split as string)) return err("split must be discovery|confirmation");
    const ss = shardSplit.get(shardKeys[i]);
    if (ss && ss !== j.split) return err(`split ${String(j.split)} contradicts shard split ${ss}`);
    if (j.dup_group !== undefined && j.dup_group !== null && typeof j.dup_group !== "string") return err("dup_group must be string|null");
    const priority = j.priority === undefined || j.priority === null ? 100 : j.priority;
    if (!Number.isInteger(priority)) return err("priority must be an integer");
    if (j.cell !== undefined && j.cell !== null && typeof j.cell !== "string") return err("cell must be string|null");
    rows.push({
      job_id: j.job_id, stage: j.stage, wave: j.wave, shard_key: shardKeys[i], pin_hash: j.pin_hash,
      n_passages: j.n_passages, split: j.split, dup_group: j.dup_group ?? null, priority, cell: j.cell ?? null,
    });
  });
  if (errors.length) throw new HttpError(400, "invalid jobs", { details: errors.slice(0, 50) });
  // Single INSERT ... SELECT over json_each: atomic, and one query regardless of batch size.
  const res = await c.env.DB.prepare(
    `INSERT INTO jobs(job_id, stage, wave, shard_key, pin_hash, n_passages, split, dup_group, priority, cell, created)
     SELECT json_extract(value, '$.job_id'), json_extract(value, '$.stage'), json_extract(value, '$.wave'),
            json_extract(value, '$.shard_key'), json_extract(value, '$.pin_hash'), json_extract(value, '$.n_passages'),
            json_extract(value, '$.split'), json_extract(value, '$.dup_group'), json_extract(value, '$.priority'),
            json_extract(value, '$.cell'), ?2
       FROM json_each(?1) WHERE true
     ON CONFLICT(job_id) DO NOTHING`,
  )
    .bind(JSON.stringify(rows), now)
    .run();
  const inserted = res.meta.changes ?? 0;
  return json({ inserted, skipped_existing: rows.length - inserted });
});

adminRoutes.post("/v1/admin/close_jobs", async (c) => {
  const b = await readJson<{ job_ids?: unknown; wave?: unknown }>(c.req.raw);
  const byWave = typeof b.wave === "string" && b.wave.length > 0;
  if (b.job_ids !== undefined && !isStringArray(b.job_ids)) throw new HttpError(400, "job_ids must be an array of strings");
  if (!byWave && !isStringArray(b.job_ids)) throw new HttpError(400, "job_ids (array of strings) or wave (string) required");
  // Queued jobs are cancelled; leased jobs are closed too and their holder sees
  // them in heartbeat `revoked`. Done/dead jobs are untouched. `wave` closes
  // every open job of that wave (e.g. a test wave).
  const { results } = await c.env.DB.prepare(
    `UPDATE jobs SET status = 'closed', lease_worker = NULL, lease_expires = NULL
      WHERE status IN ('queued', 'leased')
        AND (job_id IN (SELECT value FROM json_each(?1)) OR (?2 IS NOT NULL AND wave = ?2))
      RETURNING job_id`,
  )
    .bind(JSON.stringify(isStringArray(b.job_ids) ? b.job_ids : []), byWave ? (b.wave as string) : null)
    .all<{ job_id: string }>();
  return json({ closed: results.map((r) => r.job_id) });
});

// ------------------------------------------------------------------ results & blobs (sealed)

adminRoutes.get("/v1/admin/results", async (c) => {
  const sinceQ = c.req.query("since");
  let since = "";
  if (sinceQ) {
    const d = new Date(sinceQ);
    if (isNaN(d.getTime())) throw new HttpError(400, "since must be an ISO timestamp");
    since = d.toISOString();
  }
  const split = c.req.query("split");
  if (split && !(SPLITS as readonly string[]).includes(split)) throw new HttpError(400, "split must be discovery|confirmation");
  const seal = await sealState(c.env);
  if (seal.sealed && split === "confirmation") throw new HttpError(403, "sealed: confirmation results are unavailable until POST /v1/admin/unseal");
  const includePartials = c.req.query("partials") !== "0";
  const limit = Math.min(Math.max(parseInt(c.req.query("limit") ?? "10000", 10) || 10000, 1), 50000);
  // While sealed, confirmation rows are always excluded.
  const splitFilter = split ?? (seal.sealed ? "discovery" : null);
  const parts = [
    `SELECT job_id, worker_id, r2_key, content_sha256, stats_json, created, stage, split, pin_hash, model_digest,
            backend_version, late, 0 AS partial, NULL AS part_n, NULL AS n_ids
       FROM results WHERE created >= ?1 AND (?2 IS NULL OR split = ?2)`,
  ];
  if (includePartials)
    parts.push(
      `SELECT job_id, worker_id, r2_key, content_sha256, stats_json, created, stage, split, pin_hash, model_digest,
              backend_version, 0 AS late, 1 AS partial, part_n, n_ids
         FROM job_partials WHERE created >= ?1 AND (?2 IS NULL OR split = ?2)`,
    );
  const { results } = await c.env.DB.prepare(`${parts.join(" UNION ALL ")} ORDER BY created, job_id, worker_id, part_n LIMIT ?3`)
    .bind(since, splitFilter, limit)
    .all<Record<string, unknown>>();
  return json({
    sealed: seal.sealed,
    results: results.map((r) => {
      const { stats_json, partial, part_n, n_ids, late, ...rest } = r;
      return {
        ...rest,
        stats: parseJsonField(String(stats_json)),
        partial: partial === 1,
        late: late === 1,
        ...(partial === 1 ? { part_n, n_ids } : {}),
      };
    }),
  });
});

adminRoutes.get("/v1/admin/blob", async (c) => {
  const raw = c.req.query("key");
  if (!raw) throw new HttpError(400, "key required");
  const key = raw.replace(/^\/+/, "");
  if (key.startsWith("sealed/") && (await sealState(c.env)).sealed)
    throw new HttpError(403, "sealed: confirmation blobs are unavailable until POST /v1/admin/unseal");
  const obj = await c.env.BUCKET.get(key);
  if (!obj) throw new HttpError(404, "no such blob");
  return new Response(obj.body, {
    headers: {
      "content-type": obj.httpMetadata?.contentType ?? "application/octet-stream",
      "content-length": String(obj.size),
      ...(obj.customMetadata?.content_sha256 ? { "x-content-sha256": obj.customMetadata.content_sha256 } : {}),
    },
  });
});

adminRoutes.post("/v1/admin/unseal", async (c) => {
  const b = await readJson<{ prereg_hash?: unknown }>(c.req.raw);
  const h = typeof b.prereg_hash === "string" ? b.prereg_hash.trim().toLowerCase().replace(/^sha256:/, "") : "";
  if (!HEX64.test(h)) throw new HttpError(400, "prereg_hash must be a hex sha256 (64 chars)");
  const at = nowIso();
  const ins = await c.env.DB.prepare("INSERT INTO seal(id, prereg_hash, unsealed_at) VALUES (1, ?, ?) ON CONFLICT(id) DO NOTHING")
    .bind(h, at)
    .run();
  if (ins.meta.changes) return json({ status: "unsealed", prereg_hash: h, unsealed_at: at });
  const s = await sealState(c.env);
  if (s.prereg_hash === h) return json({ status: "already_unsealed", prereg_hash: h, unsealed_at: s.unsealed_at });
  throw new HttpError(409, "already unsealed with a different prereg_hash (irreversible)", {
    prereg_hash: s.prereg_hash,
    unsealed_at: s.unsealed_at,
  });
});

// ------------------------------------------------------------------ registry, client releases, installers

adminRoutes.put("/v1/admin/registry", async (c) => {
  const text = await c.req.text();
  let reg: Record<string, unknown>;
  try {
    reg = JSON.parse(text);
    if (!reg || typeof reg !== "object" || Array.isArray(reg)) throw new Error();
  } catch {
    throw new HttpError(400, "registry must be a JSON object");
  }
  let activePins: string[] | null = null;
  if (reg.active_pins !== undefined) {
    if (!isStringArray(reg.active_pins)) throw new HttpError(400, "active_pins must be an array of strings");
    activePins = reg.active_pins;
  }
  const etag = await sha256Hex(text);
  await c.env.BUCKET.put(REGISTRY_KEY, text, { httpMetadata: { contentType: "application/json" } });
  const cfg = await getConfig(c.env);
  const version = parseInt(cfg[CFG.registryVersion] ?? "0", 10) + 1;
  const stmts = [setConfigStmt(c.env, CFG.registryVersion, String(version)), setConfigStmt(c.env, CFG.registryEtag, etag)];
  if (activePins)
    stmts.push(
      c.env.DB.prepare("UPDATE pins SET active = CASE WHEN pin_hash IN (SELECT value FROM json_each(?)) THEN 1 ELSE 0 END").bind(
        JSON.stringify(activePins),
      ),
    );
  await c.env.DB.batch(stmts);
  let unknownPins: string[] = [];
  if (activePins?.length) {
    const { results } = await c.env.DB.prepare("SELECT pin_hash FROM pins WHERE pin_hash IN (SELECT value FROM json_each(?))")
      .bind(JSON.stringify(activePins))
      .all<{ pin_hash: string }>();
    const known = new Set(results.map((r) => r.pin_hash));
    unknownPins = activePins.filter((p) => !known.has(p));
  }
  return json({ registry_version: version, etag, active_pins_applied: activePins !== null, unknown_pins: unknownPins });
});

const DIST_FILE = /^[A-Za-z0-9][A-Za-z0-9._+-]*\.(whl|tar\.gz)$/;

adminRoutes.put("/v1/admin/dist/:file", async (c) => {
  const file = c.req.param("file");
  if (!DIST_FILE.test(file) || file.includes("..")) throw new HttpError(400, "file must be a wheel/sdist filename");
  const body = await c.req.arrayBuffer();
  if (body.byteLength === 0) throw new HttpError(400, "empty body");
  const sha = await sha256Hex(body);
  await c.env.BUCKET.put(`dist/${file}`, body, {
    httpMetadata: { contentType: "application/octet-stream" },
    customMetadata: { content_sha256: sha },
  });
  return json({ status: "stored", url: `${new URL(c.req.url).origin}/dist/${file}`, sha256: sha });
});

adminRoutes.put("/v1/admin/client_release", async (c) => {
  const b = await readJson<{ version?: unknown; min_version?: unknown }>(c.req.raw);
  if (typeof b.version !== "string" || !VERSION_RE.test(b.version)) throw new HttpError(400, "version must look like 0.2.0");
  if (b.min_version !== undefined && (typeof b.min_version !== "string" || !VERSION_RE.test(b.min_version)))
    throw new HttpError(400, "min_version must look like 0.1.0");
  const file = `ald-${b.version}-py3-none-any.whl`;
  if (!(await c.env.BUCKET.head(`dist/${file}`)))
    throw new HttpError(400, `upload the wheel first: PUT /v1/admin/dist/${file}`);
  const stmts = [setConfigStmt(c.env, CFG.latestClientVersion, b.version), setConfigStmt(c.env, CFG.wheelFile, file)];
  if (typeof b.min_version === "string") {
    if (compareVersions(b.min_version, b.version) > 0) throw new HttpError(400, "min_version cannot exceed version");
    stmts.push(setConfigStmt(c.env, CFG.minClientVersion, b.min_version));
  }
  await c.env.DB.batch(stmts);
  const cfg = await getConfig(c.env);
  return json({
    latest_client_version: b.version,
    min_client_version: cfg[CFG.minClientVersion] ?? c.env.MIN_CLIENT_VERSION ?? "0.0.0",
    wheel_url: wheelUrl(new URL(c.req.url).origin, file),
  });
});

adminRoutes.put("/v1/admin/install/:name", async (c) => {
  const name = c.req.param("name");
  if (!(INSTALL_SCRIPTS as readonly string[]).includes(name)) throw new HttpError(400, "name must be install.sh or install.ps1");
  const text = await c.req.text();
  if (!text) throw new HttpError(400, "empty body");
  await c.env.BUCKET.put(`install/${name}`, text, { httpMetadata: { contentType: "text/plain; charset=utf-8" } });
  return json({ status: "stored", url: `${new URL(c.req.url).origin}/${name}` });
});

// ------------------------------------------------------------------ annotation admin

adminRoutes.post("/v1/admin/annotators", async (c) => {
  const b = await readJson<{ name?: unknown; rotate?: unknown }>(c.req.raw);
  if (typeof b.name !== "string" || !b.name.trim() || b.name.length > 64) throw new HttpError(400, "name required (<=64 chars)");
  const name = b.name.trim();
  const token = randomToken();
  const tokSha = await sha256Hex(token);
  const existing = await c.env.DB.prepare("SELECT id FROM annotators WHERE name = ?").bind(name).first<{ id: string }>();
  if (existing) {
    if (b.rotate !== true) throw new HttpError(409, "annotator exists; pass rotate:true to issue a new token (the old one stops working)");
    await c.env.DB.prepare("UPDATE annotators SET token_sha256 = ? WHERE id = ?").bind(tokSha, existing.id).run();
    return json({ token, annotator_id: existing.id, rotated: true });
  }
  const id = randomId("a_");
  await c.env.DB.prepare("INSERT INTO annotators(id, name, token_sha256, seed, created) VALUES (?, ?, ?, ?, ?)")
    .bind(id, name, tokSha, randomToken(12), nowIso())
    .run();
  return json({ token, annotator_id: id });
});

const ITEM_KEYS = new Set(["item_id", "passage_id", "text", "ctx_before", "ctx_after", "set", "assign", "reference"]);

adminRoutes.post("/v1/admin/ann_items", async (c) => {
  const b = await readJson<{ items?: unknown }>(c.req.raw);
  const items = b.items;
  if (!Array.isArray(items) || items.length === 0) throw new HttpError(400, "items must be a non-empty array");
  if (items.length > 250) throw new HttpError(413, "at most 250 items per call");
  const { results: anns } = await c.env.DB.prepare("SELECT id, name, seed FROM annotators").all<{ id: string; name: string; seed: string }>();
  const byName = new Map(anns.map((a) => [a.name, a]));
  const errors: string[] = [];
  items.forEach((raw, i) => {
    const it = (raw ?? {}) as Record<string, unknown>;
    const err = (m: string) => errors.push(`items[${i}]: ${m}`);
    // Whitelist: anything else (model labels, title, author, date, ...) is refused.
    const extra = Object.keys(it).filter((k) => !ITEM_KEYS.has(k));
    if (extra.length) return err(`forbidden field(s): ${extra.join(",")} (items carry only ${[...ITEM_KEYS].join(",")})`);
    if (typeof it.item_id !== "string" || !SAFE_ID.test(it.item_id)) return err("item_id must match [A-Za-z0-9._-]{1,128}");
    if (typeof it.passage_id !== "string" || !it.passage_id) return err("passage_id required");
    if (it.item_id.includes(it.passage_id)) return err("item_id must be opaque (must not contain passage_id)");
    if (typeof it.text !== "string" || !it.text.trim()) return err("text required");
    for (const k of ["ctx_before", "ctx_after"]) if (it[k] !== undefined && typeof it[k] !== "string") return err(`${k} must be a string`);
    if (!["review", "practice", "cert", "retake", "teaching", "audit"].includes(it.set as string))
      return err("set must be review|practice|cert|retake|teaching|audit");
    // A reference answer exists only for practice and check items (never sent before the annotator answers).
    if ((REF_SETS as readonly unknown[]).includes(it.set)) {
      try {
        it.reference = validateReference(it.reference);
      } catch (e) {
        return err(`practice reference: ${e instanceof HttpError ? e.message : String(e)}`);
      }
    } else if (it.reference !== undefined) return err("reference is only allowed on review/practice/cert/retake items");
    if (!isStringArray(it.assign)) return err("assign must be an array of annotator names");
    const unknown = it.assign.filter((n) => !byName.has(n));
    if (unknown.length) return err(`unknown annotator(s): ${unknown.join(",")}`);
  });
  if (errors.length) throw new HttpError(400, "invalid items", { details: errors.slice(0, 50) });
  const now = nowIso();
  const itemRows: unknown[] = [];
  const assignRows: unknown[] = [];
  for (const raw of items) {
    const it = raw as { item_id: string; passage_id: string; text: string; ctx_before?: string; ctx_after?: string; set: string; assign: string[]; reference?: unknown };
    itemRows.push({
      item_id: it.item_id, passage_id: it.passage_id, text: it.text, ctx_before: it.ctx_before ?? "", ctx_after: it.ctx_after ?? "", set: it.set,
      ref_json: it.reference === undefined ? null : JSON.stringify(it.reference),
    });
    for (const name of new Set(it.assign)) {
      const a = byName.get(name)!;
      assignRows.push({ annotator_id: a.id, item_id: it.item_id, ord: await hash48(`${a.seed}:${it.item_id}`) });
    }
  }
  const [r1, r2] = await c.env.DB.batch([
    c.env.DB.prepare(
      `INSERT INTO ann_items(item_id, passage_id, text, ctx_before, ctx_after, set_name, ref_json, created)
       SELECT json_extract(value, '$.item_id'), json_extract(value, '$.passage_id'), json_extract(value, '$.text'),
              json_extract(value, '$.ctx_before'), json_extract(value, '$.ctx_after'), json_extract(value, '$.set'),
              json_extract(value, '$.ref_json'), ?2
         FROM json_each(?1) WHERE true
       ON CONFLICT(item_id) DO NOTHING`,
    ).bind(JSON.stringify(itemRows), now),
    c.env.DB.prepare(
      `INSERT OR IGNORE INTO ann_assignments(annotator_id, item_id, ord)
       SELECT json_extract(value, '$.annotator_id'), json_extract(value, '$.item_id'), json_extract(value, '$.ord')
         FROM json_each(?1)`,
    ).bind(JSON.stringify(assignRows)),
  ]);
  const inserted = r1.meta.changes ?? 0;
  return json({
    inserted,
    skipped_existing: items.length - inserted,
    assignments_added: r2.meta.changes ?? 0,
  });
});

adminRoutes.get("/v1/admin/ann_labels", async (c) => {
  const { results } = await c.env.DB.prepare(
    `SELECT l.id, l.item_id, i.passage_id, i.set_name AS "set", a.name AS annotator, l.label_json, l.evidence_text,
            l.seconds_spent, l.created, l.undone, l.undone_at
       FROM ann_labels l JOIN annotators a ON a.id = l.annotator_id JOIN ann_items i ON i.item_id = l.item_id
      ORDER BY l.id`,
  ).all<Record<string, unknown>>();
  return json({
    labels: results.map(({ label_json, undone, ...r }) => ({
      ...r,
      label: parseJsonField(String(label_json)),
      undone: undone === 1,
      practice: (REF_SETS as readonly unknown[]).includes(r.set), // key review / training / certification: never analysed as data
    })),
  });
});

/** Per-annotator, per-queue progress (done = active labels) and whether practice is complete. */
adminRoutes.get("/v1/admin/ann_status", async (c) => {
  const { results } = await c.env.DB.prepare(
    `SELECT a.id, a.name, i.set_name AS queue, COUNT(s.item_id) AS total,
            SUM(CASE WHEN EXISTS (SELECT 1 FROM ann_labels l WHERE l.annotator_id = s.annotator_id
                                   AND l.item_id = s.item_id AND l.undone = 0) THEN 1 ELSE 0 END) AS done,
            MAX((SELECT MAX(l.created) FROM ann_labels l WHERE l.annotator_id = s.annotator_id AND l.item_id = s.item_id)) AS last_label
       FROM annotators a LEFT JOIN ann_assignments s ON s.annotator_id = a.id LEFT JOIN ann_items i ON i.item_id = s.item_id
      GROUP BY a.id, a.name, i.set_name ORDER BY a.name`,
  ).all<{ id: string; name: string; queue: string | null; total: number; done: number | null; last_label: string | null }>();
  const by = new Map<string, { id: string; name: string; queues: { queue: string; done: number; total: number }[]; last_label: string | null }>();
  for (const r of results) {
    const e = by.get(r.name) ?? { id: r.id, name: r.name, queues: [], last_label: null };
    if (r.queue) e.queues.push({ queue: r.queue, done: r.done ?? 0, total: r.total });
    if (r.last_label && (!e.last_label || r.last_label > e.last_label)) e.last_label = r.last_label;
    by.set(r.name, e);
  }
  const annotators = [];
  for (const { id, ...e } of by.values()) {
    const p = e.queues.find((q) => q.queue === "practice");
    annotators.push({ ...e, practice_complete: !p || p.done >= p.total, cert: await certFor(c.env, id) });
  }
  return json({ annotators });
});

/** Override the computed certification: pass (after review), revoke (lock out), or clear. */
adminRoutes.post("/v1/admin/ann_cert", async (c) => {
  const b = await readJson<{ name?: unknown; decision?: unknown; note?: unknown }>(c.req.raw);
  if (typeof b.name !== "string") throw new HttpError(400, "name required");
  if (b.decision !== "pass" && b.decision !== "revoke" && b.decision !== "clear") throw new HttpError(400, "decision must be pass|revoke|clear");
  const note = typeof b.note === "string" ? b.note.slice(0, 1000) : "";
  const a = await c.env.DB.prepare("SELECT id FROM annotators WHERE name = ?").bind(b.name).first<{ id: string }>();
  if (!a) throw new HttpError(404, "unknown annotator");
  if (b.decision === "clear") await c.env.DB.prepare("DELETE FROM ann_cert_override WHERE annotator_id = ?").bind(a.id).run();
  else
    await c.env.DB.prepare(
      `INSERT INTO ann_cert_override(annotator_id, decision, note, created) VALUES (?, ?, ?, ?)
       ON CONFLICT(annotator_id) DO UPDATE SET decision = excluded.decision, note = excluded.note, created = excluded.created`,
    )
      .bind(a.id, b.decision, note, nowIso())
      .run();
  return json({ name: b.name, cert: await certFor(c.env, a.id) });
});
