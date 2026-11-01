import { Hono } from "hono";
import { AppEnv, annotatorFromToken, requireAnnotator } from "./auth";
import { ANNOTATE_HTML } from "./annotate_html";
import { GUIDE_HTML } from "./guide_html";
import { HttpError, json, nowIso, readJson } from "./util";

export const annotateRoutes = new Hono<AppEnv>();

// ---------------------------------------------------------------- label schema (v2, simplified)
// One main domain (not up to two), a locus, and a failure cause only for COMMUNICATION.
export const HAS_OBSTACLE = ["yes", "no", "insufficient_context"] as const;
export const DOMAINS = [
  "DISTANCE_TRAVEL",
  "COMMUNICATION_INFORMATION",
  "DARKNESS_VISIBILITY",
  "ILLNESS_BODY_DEATH",
  "MONEY_PROPERTY_LAW",
  "SOCIAL_RANK_CONVENTION",
  "INTERPERSONAL_CONFLICT",
  "INNER_STATE",
  "NATURE_WEATHER",
  "OTHER",
] as const;
export const LOCI = ["material_external", "social_institutional", "internal_psychological"] as const;
export const FAILURE_CAUSES = [
  "infrastructure",
  "accidental_loss",
  "intentional_withholding",
  "misinterpretation",
  "success_resolution",
  "none",
] as const;
export const COMM = "COMMUNICATION_INFORMATION";

/** Queues (= item sets) an annotator can have, in the order the UI offers them. */
export const QUEUES = ["practice", "cert", "retake", "audit", "teaching"] as const;
export type Queue = (typeof QUEUES)[number];
/** Sets that carry a reference answer; their labels are training/certification, never data. */
export const GATE_SETS: readonly Queue[] = ["practice", "cert", "retake"];
const QUEUE_TITLE: Record<Queue, string> = {
  practice: "Practice",
  cert: "Check",
  retake: "Second check",
  audit: "Main set",
  teaching: "Teaching set",
};
/** Certification pass rule (statistician, prereg v0.3): both must hold on the 20 cert items. */
export const CERT_MIN_LOCUS_KAPPA = 0.6;
export const CERT_MIN_OBSTACLE_AGREEMENT = 0.75;

export interface HumanLabel {
  has_obstacle: (typeof HAS_OBSTACLE)[number];
  domain: string | null;
  locus: string | null;
  failure_cause: string | null;
  note: string;
}
export interface Reference extends Omit<HumanLabel, "note"> {
  rationale: string;
}

const inList = (list: readonly string[], v: unknown): v is string => typeof v === "string" && list.includes(v);

function asObject(raw: unknown, what: string): Record<string, unknown> {
  let v = raw;
  if (typeof v === "string") {
    try {
      v = JSON.parse(v);
    } catch {
      throw new HttpError(400, `${what} is not valid JSON`);
    }
  }
  if (!v || typeof v !== "object" || Array.isArray(v)) throw new HttpError(400, `${what} must be an object`);
  return v as Record<string, unknown>;
}

function checkCore(o: Record<string, unknown>): Omit<HumanLabel, "note"> {
  if (!inList(HAS_OBSTACLE, o.has_obstacle)) throw new HttpError(400, "has_obstacle must be yes|no|insufficient_context");
  const domain = o.domain ?? null;
  if (domain !== null && !inList(DOMAINS, domain)) throw new HttpError(400, "domain must be one of the listed domains (a single value)");
  const locus = o.locus ?? null;
  if (locus !== null && !inList(LOCI, locus)) throw new HttpError(400, "unknown locus");
  const fc = o.failure_cause ?? null;
  if (fc !== null && !inList(FAILURE_CAUSES, fc)) throw new HttpError(400, "unknown failure_cause");
  if (o.has_obstacle === "yes") {
    if (domain === null) throw new HttpError(400, "has_obstacle=yes needs a domain");
    if (locus === null) throw new HttpError(400, "has_obstacle=yes needs a locus");
    if (domain === COMM && fc === null) throw new HttpError(400, "COMMUNICATION_INFORMATION needs a failure_cause");
    if (domain !== COMM && fc !== null) throw new HttpError(400, "failure_cause only applies to COMMUNICATION_INFORMATION");
  } else if (domain !== null || locus !== null || fc !== null) {
    throw new HttpError(400, "domain/locus/failure_cause only apply when has_obstacle=yes");
  }
  return { has_obstacle: o.has_obstacle as HumanLabel["has_obstacle"], domain, locus, failure_cause: fc };
}

/** Validate and canonicalize an annotator label. Throws HttpError(400) on anything malformed. */
export function validateLabel(raw: unknown): HumanLabel {
  const o = asObject(raw, "label_json");
  const allowed = new Set(["has_obstacle", "domain", "locus", "failure_cause", "note"]);
  const extra = Object.keys(o).filter((k) => !allowed.has(k));
  if (extra.length) throw new HttpError(400, `unknown label field(s): ${extra.join(",")}`);
  const core = checkCore(o);
  const note = o.note ?? "";
  if (typeof note !== "string" || note.length > 4000) throw new HttpError(400, "note must be a string (<=4000 chars)");
  return { ...core, note };
}

/** Reference answer for a practice item (admin-supplied; shown to the annotator only after they answer). */
export function validateReference(raw: unknown): Reference {
  const o = asObject(raw, "reference");
  const allowed = new Set(["has_obstacle", "domain", "locus", "failure_cause", "rationale"]);
  const extra = Object.keys(o).filter((k) => !allowed.has(k));
  if (extra.length) throw new HttpError(400, `unknown reference field(s): ${extra.join(",")}`);
  const core = checkCore(o);
  if (typeof o.rationale !== "string" || !o.rationale.trim() || o.rationale.length > 3000)
    throw new HttpError(400, "reference.rationale must be a non-empty string (<=3000 chars)");
  return { ...core, rationale: o.rationale };
}

// ---------------------------------------------------------------- pages

const HTML_HEADERS = {
  "content-type": "text/html; charset=utf-8",
  "cache-control": "no-store",
  "referrer-policy": "no-referrer", // the token is in the URL
  "x-robots-tag": "noindex, nofollow",
  "x-frame-options": "DENY",
  "content-security-policy":
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
};

// The guide holds no secrets (public-domain quotes from the Discovery half only), so it needs no token.
// Registered before /annotate/:token so "guide" is never looked up as a token.
annotateRoutes.get("/annotate/guide", () => new Response(GUIDE_HTML, { headers: HTML_HEADERS }));

annotateRoutes.get("/annotate/:token", async (c) => {
  const a = await annotatorFromToken(c.env, c.req.param("token"));
  if (!a) {
    return new Response("<!doctype html><meta charset=utf-8><title>Not found</title><p>This annotation link is not valid.</p>", {
      status: 404,
      headers: HTML_HEADERS,
    });
  }
  return new Response(ANNOTATE_HTML, { headers: HTML_HEADERS });
});

annotateRoutes.use("/annotate/:token/*", requireAnnotator);

// ---------------------------------------------------------------- scoring and gating

type Env = AppEnv["Bindings"];

/** Cohen's kappa of two equal-length label vectors (1 when both are constant and identical). */
export function cohenKappa(a: string[], b: string[]): number {
  const n = a.length;
  if (!n) return NaN;
  let agree = 0;
  const ca = new Map<string, number>();
  const cb = new Map<string, number>();
  for (let i = 0; i < n; i++) {
    if (a[i] === b[i]) agree++;
    ca.set(a[i], (ca.get(a[i]) ?? 0) + 1);
    cb.set(b[i], (cb.get(b[i]) ?? 0) + 1);
  }
  const po = agree / n;
  let pe = 0;
  for (const [k, v] of ca) pe += (v / n) * ((cb.get(k) ?? 0) / n);
  if (pe >= 1) return po === 1 ? 1 : 0;
  return (po - pe) / (1 - pe);
}

/** 4-category H1 construct: none (no obstacle / can't tell) or the locus. */
const locus4 = (l: { has_obstacle: string; locus: string | null }) => (l.has_obstacle === "yes" ? (l.locus ?? "none") : "none");
const obstacle2 = (l: { has_obstacle: string }) => (l.has_obstacle === "yes" ? "yes" : "no");

export interface RoundScore {
  round: Queue;
  n: number;
  done: number;
  obs_agree: number | null;
  locus_kappa: number | null;
  passed: boolean | null; // null until the round is complete
}

interface RoundRow {
  item_id: string;
  text: string;
  ref_json: string;
  label_json: string | null;
}

async function roundRows(env: Env, annotatorId: string, set: Queue): Promise<RoundRow[]> {
  const { results } = await env.DB.prepare(
    `SELECT i.item_id, i.text, i.ref_json,
            (SELECT l.label_json FROM ann_labels l WHERE l.annotator_id = s.annotator_id AND l.item_id = s.item_id AND l.undone = 0) AS label_json
       FROM ann_assignments s JOIN ann_items i ON i.item_id = s.item_id
      WHERE s.annotator_id = ? AND i.set_name = ? ORDER BY s.ord, s.item_id`,
  )
    .bind(annotatorId, set)
    .all<RoundRow>();
  return results;
}

export function scoreRound(round: Queue, rows: RoundRow[]): RoundScore {
  const done = rows.filter((r) => r.label_json !== null);
  const out: RoundScore = { round, n: rows.length, done: done.length, obs_agree: null, locus_kappa: null, passed: null };
  if (!done.length) return out;
  const L = done.map((r) => JSON.parse(r.label_json!) as HumanLabel);
  const R = done.map((r) => JSON.parse(r.ref_json) as Reference);
  out.obs_agree = L.filter((l, i) => obstacle2(l) === obstacle2(R[i])).length / L.length;
  out.locus_kappa = cohenKappa(L.map(locus4), R.map(locus4));
  if (done.length === rows.length)
    out.passed = out.locus_kappa >= CERT_MIN_LOCUS_KAPPA && out.obs_agree >= CERT_MIN_OBSTACLE_AGREEMENT;
  out.obs_agree = Math.round(out.obs_agree * 1000) / 1000;
  out.locus_kappa = Math.round(out.locus_kappa * 1000) / 1000;
  return out;
}

export type CertStatus =
  | "none" // no certification items: never gated (the expert reference annotator)
  | "not_started" // practice still open
  | "in_progress"
  | "passed"
  | "failed_retake_available"
  | "in_retake"
  | "failed"
  | "override" // admin passed them
  | "revoked"; // admin locked them out

export interface Gate {
  status: CertStatus;
  rounds: RoundScore[];
  practiceDone: boolean;
  mainOpen: boolean;
  retakeOpen: boolean;
}

interface Counts {
  queue: Queue;
  total: number;
  done: number | null;
}

async function gateFor(env: Env, annotatorId: string, by: Map<Queue, Counts>): Promise<Gate> {
  const pr = by.get("practice");
  const practiceDone = !pr || (pr.done ?? 0) >= pr.total;
  const rounds: RoundScore[] = [];
  for (const r of ["cert", "retake"] as const) if (by.has(r)) rounds.push(scoreRound(r, await roundRows(env, annotatorId, r)));
  const ov = await env.DB.prepare("SELECT decision FROM ann_cert_override WHERE annotator_id = ?")
    .bind(annotatorId)
    .first<{ decision: string }>();
  const cert = rounds.find((r) => r.round === "cert");
  const retake = rounds.find((r) => r.round === "retake");
  let status: CertStatus;
  if (ov?.decision === "pass") status = "override";
  else if (ov?.decision === "revoke") status = "revoked";
  else if (!cert) status = pr ? (practiceDone ? "none" : "not_started") : "none";
  else if (!practiceDone) status = "not_started";
  else if (cert.passed === null) status = "in_progress";
  else if (cert.passed) status = "passed";
  else if (!retake) status = "failed";
  else if (retake.passed === null) status = retake.done > 0 ? "in_retake" : "failed_retake_available";
  else status = retake.passed ? "passed" : "failed";
  return {
    status,
    rounds,
    practiceDone,
    mainOpen: status === "none" || status === "passed" || status === "override",
    retakeOpen: status === "failed_retake_available" || status === "in_retake",
  };
}

interface QueueState {
  queue: Queue;
  display: string;
  done: number;
  total: number;
  locked: boolean;
}

async function queueStates(env: Env, annotatorId: string): Promise<{ queues: QueueState[]; gate: Gate }> {
  const { results } = await env.DB.prepare(
    `SELECT i.set_name AS queue, COUNT(*) AS total,
            SUM(CASE WHEN EXISTS (SELECT 1 FROM ann_labels l WHERE l.annotator_id = s.annotator_id
                                   AND l.item_id = s.item_id AND l.undone = 0) THEN 1 ELSE 0 END) AS done
       FROM ann_assignments s JOIN ann_items i ON i.item_id = s.item_id
      WHERE s.annotator_id = ? GROUP BY i.set_name`,
  )
    .bind(annotatorId)
    .all<Counts>();
  const by = new Map(results.map((r) => [r.queue, r]));
  const gate = await gateFor(env, annotatorId, by);
  const locked = (q: Queue) =>
    q === "practice" ? false : q === "cert" ? !gate.practiceDone || gate.status === "revoked" : q === "retake" ? !gate.retakeOpen : !gate.mainOpen;
  // The retake set is only shown once it is relevant (the first check was failed).
  const visible = (q: Queue) => q !== "retake" || gate.rounds.find((r) => r.round === "cert")?.passed === false;
  const queues = QUEUES.filter((q) => by.has(q) && visible(q)).map((q) => {
    const r = by.get(q)!;
    return { queue: q, display: QUEUE_TITLE[q], done: r.done ?? 0, total: r.total, locked: locked(q) };
  });
  return { queues, gate };
}

/** Certification status and per-round scores for the admin view. */
export async function certFor(env: Env, annotatorId: string): Promise<{ status: CertStatus; rounds: RoundScore[] }> {
  const { gate } = await queueStates(env, annotatorId);
  return { status: gate.status, rounds: gate.rounds };
}

/** The queue to serve: the requested one, else the first unlocked queue with work left. */
function pickQueue(states: QueueState[], requested: string | undefined): QueueState | null {
  if (requested !== undefined && requested !== "") {
    if (!inList(QUEUES, requested)) throw new HttpError(400, "unknown queue");
    const s = states.find((x) => x.queue === requested);
    if (!s) throw new HttpError(404, "no such queue for you");
    if (s.locked) throw new HttpError(423, "this set is locked");
    return s;
  }
  return states.find((s) => !s.locked && s.done < s.total) ?? states.find((s) => !s.locked) ?? null;
}

const progressOf = (s: QueueState | undefined) => (s ? { done: s.done, total: s.total } : { done: 0, total: 0 });

/** What the annotator may see about their own certification: status, and scores once a round is complete. */
function publicCert(g: Gate) {
  return {
    status: g.status,
    rounds: g.rounds.map((r) => (r.passed === null ? { round: r.round, n: r.n, done: r.done } : r)),
  };
}

annotateRoutes.get("/annotate/:token/state", async (c) => {
  const a = c.get("annotator");
  const { queues, gate } = await queueStates(c.env, a.id);
  return json({ queues, cert: publicCert(gate) });
});

// The annotator API returns ONLY item_id, text, ctx_before, ctx_after, the queue name and
// progress (plus the annotator's own previous label on undo, the practice reference after a
// practice answer, and missed cert items after a completed round). Never passage_id, model
// output, other annotators' labels, title, author or date.
annotateRoutes.get("/annotate/:token/next", async (c) => {
  const a = c.get("annotator");
  const { queues: states, gate } = await queueStates(c.env, a.id);
  const s = pickQueue(states, c.req.query("queue"));
  const empty = { item_id: null, text: null, ctx_before: null, ctx_after: null };
  const cert = publicCert(gate);
  if (!s) return json({ ...empty, queue: null, progress: { done: 0, total: 0 }, queues: states, cert });
  const item = await c.env.DB.prepare(
    `SELECT i.item_id, i.text, i.ctx_before, i.ctx_after
       FROM ann_assignments s JOIN ann_items i ON i.item_id = s.item_id
      WHERE s.annotator_id = ?1 AND i.set_name = ?2
        AND NOT EXISTS (SELECT 1 FROM ann_labels l WHERE l.annotator_id = ?1 AND l.item_id = s.item_id AND l.undone = 0)
      -- an item whose label was just undone comes back first; otherwise the seeded order
      ORDER BY (SELECT MAX(l2.undone_at) FROM ann_labels l2 WHERE l2.annotator_id = ?1 AND l2.item_id = s.item_id AND l2.undone = 1) DESC NULLS LAST,
               s.ord, s.item_id
      LIMIT 1`,
  )
    .bind(a.id, s.queue)
    .first<{ item_id: string; text: string; ctx_before: string; ctx_after: string }>();
  const base = { queue: s.queue, progress: progressOf(s), queues: states, cert };
  if (!item) return json({ ...empty, ...base });
  return json({ item_id: item.item_id, text: item.text, ctx_before: item.ctx_before, ctx_after: item.ctx_after, ...base });
});

annotateRoutes.post("/annotate/:token/label", async (c) => {
  const a = c.get("annotator");
  const b = await readJson<Record<string, unknown>>(c.req.raw);
  if (typeof b.item_id !== "string") throw new HttpError(400, "item_id required");
  const label = validateLabel(b.label_json);
  const evidence = b.evidence_text ?? "";
  if (typeof evidence !== "string" || evidence.length > 10000) throw new HttpError(400, "evidence_text must be a string");
  const secs = b.seconds_spent ?? null;
  if (secs !== null && (typeof secs !== "number" || !Number.isFinite(secs) || secs < 0 || secs > 86400))
    throw new HttpError(400, "seconds_spent must be a number of seconds");
  const it = await c.env.DB.prepare(
    `SELECT i.set_name AS queue, i.ref_json FROM ann_assignments s JOIN ann_items i ON i.item_id = s.item_id
      WHERE s.annotator_id = ? AND s.item_id = ?`,
  )
    .bind(a.id, b.item_id)
    .first<{ queue: Queue; ref_json: string | null }>();
  if (!it) throw new HttpError(404, "item not assigned to you");
  const before = await queueStates(c.env, a.id);
  const qs = before.queues.find((s) => s.queue === it.queue);
  if (!qs || qs.locked) throw new HttpError(423, "this set is locked");
  const ins = await c.env.DB.prepare(
    `INSERT INTO ann_labels(annotator_id, item_id, label_json, evidence_text, seconds_spent, created)
     VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING`,
  )
    .bind(a.id, b.item_id, JSON.stringify(label), evidence, secs === null ? null : Math.round(secs * 10) / 10, nowIso())
    .run();
  if (!ins.meta.changes) throw new HttpError(409, "item already labeled (use undo to change it)");
  const { queues: states, gate } = await queueStates(c.env, a.id);
  const out: Record<string, unknown> = {
    status: "stored",
    queue: it.queue,
    progress: progressOf(states.find((s) => s.queue === it.queue)),
    queues: states,
    cert: publicCert(gate),
  };
  if (it.queue === "practice" && it.ref_json) out.feedback = JSON.parse(it.ref_json) as Reference;
  return json(out);
});

annotateRoutes.post("/annotate/:token/undo", async (c) => {
  const a = c.get("annotator");
  const b = await readJson<Record<string, unknown>>(c.req.raw);
  const q = b.queue ?? "audit";
  if (!inList(QUEUES, q)) throw new HttpError(400, "unknown queue");
  // Practice answers are final once the reference has been shown; check answers are a test.
  if (GATE_SETS.includes(q as Queue)) throw new HttpError(409, "practice and check answers cannot be undone");
  const row = await c.env.DB.prepare(
    `UPDATE ann_labels SET undone = 1, undone_at = ?3
      WHERE id = (SELECT l.id FROM ann_labels l JOIN ann_items i ON i.item_id = l.item_id
                   WHERE l.annotator_id = ?1 AND l.undone = 0 AND i.set_name = ?2 ORDER BY l.id DESC LIMIT 1)
      RETURNING item_id, label_json, evidence_text`,
  )
    .bind(a.id, q, nowIso())
    .first<{ item_id: string; label_json: string; evidence_text: string }>();
  const { queues: states } = await queueStates(c.env, a.id);
  const p = progressOf(states.find((s) => s.queue === q));
  if (!row) return json({ undone: null, queue: q, progress: p });
  return json({ undone: row.item_id, queue: q, previous_label: JSON.parse(row.label_json), evidence_text: row.evidence_text, progress: p });
});

/** The annotator's own answered practice items with their references (end-of-practice summary). */
annotateRoutes.get("/annotate/:token/practice_review", async (c) => {
  const a = c.get("annotator");
  const { results } = await c.env.DB.prepare(
    `SELECT l.item_id, l.label_json, i.ref_json FROM ann_labels l JOIN ann_items i ON i.item_id = l.item_id
      WHERE l.annotator_id = ? AND l.undone = 0 AND i.set_name = 'practice' ORDER BY l.id`,
  )
    .bind(a.id)
    .all<{ item_id: string; label_json: string; ref_json: string }>();
  return json({
    items: results.map((r) => ({ item_id: r.item_id, label: JSON.parse(r.label_json), reference: JSON.parse(r.ref_json) })),
  });
});

/**
 * Result of a COMPLETED check round: scores and, for items where the obstacle call or the
 * locus differs from the reference, the passage start, the annotator's answer, the reference
 * and the rationale. Nothing is revealed for a round that is still open.
 */
annotateRoutes.get("/annotate/:token/cert_review", async (c) => {
  const a = c.get("annotator");
  const round = c.req.query("round") ?? "cert";
  if (round !== "cert" && round !== "retake") throw new HttpError(400, "round must be cert|retake");
  const rows = await roundRows(c.env, a.id, round);
  if (!rows.length) throw new HttpError(404, "no such round for you");
  const score = scoreRound(round, rows);
  if (score.passed === null) throw new HttpError(409, "finish the round first");
  const { gate } = await queueStates(c.env, a.id);
  const misses = rows
    .map((r) => ({ r, l: JSON.parse(r.label_json!) as HumanLabel, ref: JSON.parse(r.ref_json) as Reference }))
    .filter(({ l, ref }) => obstacle2(l) !== obstacle2(ref) || locus4(l) !== locus4(ref))
    .map(({ r, l, ref }) => ({
      item_id: r.item_id,
      excerpt: r.text.length > 700 ? r.text.slice(0, 700).replace(/\s+\S*$/, "") + " …" : r.text,
      label: l,
      reference: ref,
    }));
  return json({ ...score, status: gate.status, misses });
});
