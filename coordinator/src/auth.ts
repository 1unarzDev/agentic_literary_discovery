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

/** Read-only fleet view: a viewer token (POST /v1/admin/viewer_token) or the admin token. */
export const requireViewer: MiddlewareHandler<AppEnv> = async (c, next) => {
  const tok = bearer(c.req.raw) ?? c.req.query("t") ?? null;
  if (!tok || tok.length > 256) throw UNAUTHORIZED();
  const sha = await sha256Hex(tok);
  const secret = c.env.ADMIN_TOKEN;
  if (secret && sha === (await sha256Hex(secret))) return next();
  const row = await c.env.DB.prepare("SELECT name FROM viewer_tokens WHERE token_sha256 = ?").bind(sha).first();
  if (!row) throw UNAUTHORIZED();
  await next();
};
