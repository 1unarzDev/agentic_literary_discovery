import { Hono } from "hono";
import { AppEnv, annotatorFromToken, requireAnnotator } from "./auth";
import { ANNOTATE_HTML } from "./annotate_html";
import { HttpError, json, nowIso, readJson } from "./util";

export const annotateRoutes = new Hono<AppEnv>();

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
] as const;

export interface HumanLabel {
  has_obstacle: (typeof HAS_OBSTACLE)[number];
  domain: string[];
  locus: string | null;
  failure_cause: string | null;
  note: string;
}

const inList = (list: readonly string[], v: unknown): v is string => typeof v === "string" && list.includes(v);

/** Validate and canonicalize an annotator label. Throws HttpError(400) on anything malformed. */
export function validateLabel(raw: unknown): HumanLabel {
  let v = raw;
  if (typeof v === "string") {
    try {
      v = JSON.parse(v);
    } catch {
      throw new HttpError(400, "label_json is not valid JSON");
    }
  }
  if (!v || typeof v !== "object" || Array.isArray(v)) throw new HttpError(400, "label_json must be an object");
  const o = v as Record<string, unknown>;
  const allowed = new Set(["has_obstacle", "domain", "locus", "failure_cause", "note"]);
  const extra = Object.keys(o).filter((k) => !allowed.has(k));
  if (extra.length) throw new HttpError(400, `unknown label field(s): ${extra.join(",")}`);
  if (!inList(HAS_OBSTACLE, o.has_obstacle)) throw new HttpError(400, "has_obstacle must be yes|no|insufficient_context");
  const domain = o.domain === undefined || o.domain === null ? [] : o.domain;
  if (!Array.isArray(domain) || !domain.every((d) => inList(DOMAINS, d))) throw new HttpError(400, "domain must be a list of known domains");
  if (new Set(domain).size !== domain.length) throw new HttpError(400, "domain has duplicates");
  if (domain.length > 2) throw new HttpError(400, "at most 2 domains");
  const locus = o.locus ?? null;
  if (locus !== null && !inList(LOCI, locus)) throw new HttpError(400, "unknown locus");
  const fc = o.failure_cause ?? null;
  if (fc !== null && !inList(FAILURE_CAUSES, fc)) throw new HttpError(400, "unknown failure_cause");
  if (fc !== null && !domain.includes("COMMUNICATION_INFORMATION"))
    throw new HttpError(400, "failure_cause only applies when COMMUNICATION_INFORMATION is chosen");
  const note = o.note ?? "";
  if (typeof note !== "string" || note.length > 4000) throw new HttpError(400, "note must be a string (<=4000 chars)");
  if (o.has_obstacle === "yes") {
    if (domain.length === 0) throw new HttpError(400, "has_obstacle=yes needs at least one domain");
    if (locus === null) throw new HttpError(400, "has_obstacle=yes needs a locus");
  } else if (domain.length || locus !== null) {
    throw new HttpError(400, "domain/locus only apply when has_obstacle=yes");
  }
  return { has_obstacle: o.has_obstacle as HumanLabel["has_obstacle"], domain: domain as string[], locus: locus as string | null, failure_cause: fc as string | null, note };
}

const HTML_HEADERS = {
  "content-type": "text/html; charset=utf-8",
  "cache-control": "no-store",
  "referrer-policy": "no-referrer", // the token is in the URL
  "x-robots-tag": "noindex, nofollow",
  "x-frame-options": "DENY",
  "content-security-policy":
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
};

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

async function progress(c: { env: AppEnv["Bindings"] }, annotatorId: string) {
  const r = await c.env.DB.prepare(
    `SELECT COUNT(*) AS total,
            SUM(CASE WHEN EXISTS (SELECT 1 FROM ann_labels l WHERE l.annotator_id = s.annotator_id
                                   AND l.item_id = s.item_id AND l.undone = 0) THEN 1 ELSE 0 END) AS done
       FROM ann_assignments s WHERE s.annotator_id = ?`,
  )
    .bind(annotatorId)
    .first<{ total: number; done: number | null }>();
  return { done: r?.done ?? 0, total: r?.total ?? 0 };
}

// The annotator API returns ONLY item_id, text, ctx_before, ctx_after and
// progress (plus the annotator's own previous label on undo). Never passage_id,
// model output, other annotators' labels, title, author or date.
annotateRoutes.get("/annotate/:token/next", async (c) => {
  const a = c.get("annotator");
  const item = await c.env.DB.prepare(
    `SELECT i.item_id, i.text, i.ctx_before, i.ctx_after
       FROM ann_assignments s JOIN ann_items i ON i.item_id = s.item_id
      WHERE s.annotator_id = ?1
        AND NOT EXISTS (SELECT 1 FROM ann_labels l WHERE l.annotator_id = ?1 AND l.item_id = s.item_id AND l.undone = 0)
      -- an item whose label was just undone comes back first; otherwise the seeded order
      ORDER BY (SELECT MAX(l2.undone_at) FROM ann_labels l2 WHERE l2.annotator_id = ?1 AND l2.item_id = s.item_id AND l2.undone = 1) DESC NULLS LAST,
               s.ord, s.item_id
      LIMIT 1`,
  )
    .bind(a.id)
    .first<{ item_id: string; text: string; ctx_before: string; ctx_after: string }>();
  const p = await progress(c, a.id);
  if (!item) return json({ item_id: null, text: null, ctx_before: null, ctx_after: null, progress: p });
  return json({ item_id: item.item_id, text: item.text, ctx_before: item.ctx_before, ctx_after: item.ctx_after, progress: p });
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
  const assigned = await c.env.DB.prepare("SELECT 1 AS x FROM ann_assignments WHERE annotator_id = ? AND item_id = ?")
    .bind(a.id, b.item_id)
    .first();
  if (!assigned) throw new HttpError(404, "item not assigned to you");
  const ins = await c.env.DB.prepare(
    `INSERT INTO ann_labels(annotator_id, item_id, label_json, evidence_text, seconds_spent, created)
     VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING`,
  )
    .bind(a.id, b.item_id, JSON.stringify(label), evidence, secs === null ? null : Math.round(secs * 10) / 10, nowIso())
    .run();
  if (!ins.meta.changes) throw new HttpError(409, "item already labeled (use undo to change it)");
  return json({ status: "stored", progress: await progress(c, a.id) });
});

annotateRoutes.post("/annotate/:token/undo", async (c) => {
  const a = c.get("annotator");
  const row = await c.env.DB.prepare(
    `UPDATE ann_labels SET undone = 1, undone_at = ?2
      WHERE id = (SELECT id FROM ann_labels WHERE annotator_id = ?1 AND undone = 0 ORDER BY id DESC LIMIT 1)
      RETURNING item_id, label_json, evidence_text`,
  )
    .bind(a.id, nowIso())
    .first<{ item_id: string; label_json: string; evidence_text: string }>();
  const p = await progress(c, a.id);
  if (!row) return json({ undone: null, progress: p });
  return json({ undone: row.item_id, previous_label: JSON.parse(row.label_json), evidence_text: row.evidence_text, progress: p });
});
