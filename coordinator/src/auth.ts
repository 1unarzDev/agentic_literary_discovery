import type { MiddlewareHandler } from "hono";
import { Env, HttpError, bearer, sha256Hex } from "./util";

export interface WorkerRow {
  id: string;
  name: string;
  tier: string | null;
  os: string | null;
  client_version: string | null;
}

export interface AnnotatorRow {
  id: string;
  name: string;
  seed: string;
}

export type AppEnv = {
  Bindings: Env;
  Variables: { worker: WorkerRow; annotator: AnnotatorRow };
};

// Every auth failure, whatever the reason (missing header, unknown token, a
// valid token of another kind), produces this exact response, so callers can't
// learn which token types exist or whether a token is valid elsewhere.
export const UNAUTHORIZED = () => new HttpError(401, "unauthorized");

export const requireWorker: MiddlewareHandler<AppEnv> = async (c, next) => {
  const tok = bearer(c.req.raw);
  if (!tok) throw UNAUTHORIZED();
  const row = await c.env.DB.prepare(
    "SELECT id, name, tier, os, client_version FROM workers WHERE token_sha256 = ? AND disabled = 0",
  )
    .bind(await sha256Hex(tok))
    .first<WorkerRow>();
  if (!row) throw UNAUTHORIZED();
  c.set("worker", row);
  await next();
};

export const requireAdmin: MiddlewareHandler<AppEnv> = async (c, next) => {
  const tok = bearer(c.req.raw);
  const secret = c.env.ADMIN_TOKEN;
  // Compare digests rather than raw strings (also keeps the comparison length-independent).
  if (!tok || !secret || (await sha256Hex(tok)) !== (await sha256Hex(secret))) throw UNAUTHORIZED();
  await next();
};

export async function annotatorFromToken(env: Env, token: string): Promise<AnnotatorRow | null> {
  if (!token || token.length > 256) return null;
  return await env.DB.prepare("SELECT id, name, seed FROM annotators WHERE token_sha256 = ?")
    .bind(await sha256Hex(token))
    .first<AnnotatorRow>();
}

export const requireAnnotator: MiddlewareHandler<AppEnv> = async (c, next) => {
  const row = await annotatorFromToken(c.env, c.req.param("token") ?? "");
  if (!row) throw UNAUTHORIZED();
  c.set("annotator", row);
  await next();
};
