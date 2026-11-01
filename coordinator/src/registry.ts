import { CFG } from "./db";
import { Env } from "./util";

export const REGISTRY_KEY = "registry/models.v1.json";

let cache: { etag: string; at: number; data: Record<string, unknown> | null } | null = null;

async function loadRegistry(env: Env): Promise<Record<string, unknown> | null> {
  const row = await env.DB.prepare("SELECT value FROM config WHERE key = ?")
    .bind(CFG.registryEtag)
    .first<{ value: string }>();
  if (!row) return null;
  if (cache && cache.etag === row.value && Date.now() - cache.at < 60_000) return cache.data;
  const obj = await env.BUCKET.get(REGISTRY_KEY);
  let data: Record<string, unknown> | null = null;
  if (obj) {
    try {
      data = (await obj.json()) as Record<string, unknown>;
    } catch {
      data = null;
    }
  }
  cache = { etag: row.value, at: Date.now(), data };
  return data;
}

/**
 * Stages a tier may run, if the registry declares them. Accepted shapes:
 *   {"tiers": {"<tier>": {"stages": [...]}}}  or  {"tiers": {"<tier>": [...]}}
 * Returns null when the registry declares no tier table (then the stages the
 * worker requested are trusted); [] for a tier the table doesn't know.
 */
export async function stagesForTier(env: Env, tier: string | null | undefined): Promise<string[] | null> {
  const reg = await loadRegistry(env);
  const tiers = reg?.tiers;
  if (!tiers || typeof tiers !== "object" || Array.isArray(tiers)) return null;
  if (!tier) return [];
  const t = (tiers as Record<string, unknown>)[tier];
  const stages = Array.isArray(t) ? t : (t as { stages?: unknown } | undefined)?.stages;
  return Array.isArray(stages) ? stages.filter((s): s is string => typeof s === "string") : [];
}
