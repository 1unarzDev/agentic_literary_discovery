export interface Env {
  DB: D1Database;
  BUCKET: R2Bucket;
  ADMIN_TOKEN: string;
  MIN_CLIENT_VERSION?: string;
  LEASE_TTL_SECONDS?: string;
  MAX_ATTEMPTS?: string;
  MAX_LEASE_JOBS?: string;
}

export const STAGES = ["screen", "label", "adjudicate", "cloze", "embed"] as const;
export type Stage = (typeof STAGES)[number];
export const SPLITS = ["discovery", "confirmation"] as const;

export class HttpError extends Error {
  constructor(
    public status: number,
    message: string,
    public extra: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

export function json(data: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", ...headers },
  });
}

export function errorResponse(e: HttpError): Response {
  return json({ error: e.message, ...e.extra }, e.status);
}

export async function readJson<T = Record<string, unknown>>(req: Request): Promise<T> {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    throw new HttpError(400, "invalid JSON body");
  }
  if (body === null || typeof body !== "object" || Array.isArray(body)) {
    throw new HttpError(400, "JSON body must be an object");
  }
  return body as T;
}

const HEX = "0123456789abcdef";
export function toHex(buf: ArrayBuffer | Uint8Array): string {
  const b = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
  let s = "";
  for (let i = 0; i < b.length; i++) s += HEX[b[i] >> 4] + HEX[b[i] & 15];
  return s;
}

export async function sha256Hex(data: string | ArrayBuffer | Uint8Array): Promise<string> {
  const bytes = typeof data === "string" ? new TextEncoder().encode(data) : data;
  return toHex(await crypto.subtle.digest("SHA-256", bytes));
}

export function randomToken(nBytes = 32): string {
  const b = new Uint8Array(nBytes);
  crypto.getRandomValues(b);
  let bin = "";
  for (const x of b) bin += String.fromCharCode(x);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function randomId(prefix: string, nBytes = 8): string {
  const b = new Uint8Array(nBytes);
  crypto.getRandomValues(b);
  return prefix + toHex(b);
}

export function nowIso(ms = Date.now()): string {
  return new Date(ms).toISOString();
}

export function intVar(v: string | undefined, dflt: number): number {
  const n = v === undefined ? NaN : parseInt(v, 10);
  return Number.isFinite(n) ? n : dflt;
}

/**
 * Compare dotted versions numerically ("0.10.0" > "0.9.3"). Only the leading
 * numeric components count; a pre-release/local suffix ("0.2.0rc1", "0.2.0+g1")
 * is ignored, so "0.2.0rc1" == "0.2.0". Returns -1/0/1.
 */
export function compareVersions(a: string, b: string): number {
  const parse = (v: string) =>
    (v.trim().replace(/^v/i, "").match(/^\d+(?:\.\d+)*/)?.[0] ?? "0").split(".").map(Number);
  const pa = parse(a);
  const pb = parse(b);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const x = pa[i] ?? 0;
    const y = pb[i] ?? 0;
    if (x !== y) return x < y ? -1 : 1;
  }
  return 0;
}

export function bearer(req: Request): string | null {
  const h = req.headers.get("authorization");
  if (!h) return null;
  const m = /^Bearer\s+(\S+)\s*$/i.exec(h);
  return m ? m[1] : null;
}

export function isStringArray(v: unknown): v is string[] {
  return Array.isArray(v) && v.every((x) => typeof x === "string");
}

export async function gunzipToText(data: ArrayBuffer | Uint8Array): Promise<string> {
  const stream = new Blob([data]).stream().pipeThrough(new DecompressionStream("gzip"));
  return await new Response(stream).text();
}

export async function gzipText(text: string): Promise<Uint8Array> {
  const stream = new Blob([text]).stream().pipeThrough(new CompressionStream("gzip"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

export function base64ToBytes(b64: string): Uint8Array {
  const norm = b64.replace(/-/g, "+").replace(/_/g, "/").replace(/\s+/g, "");
  const bin = atob(norm + "===".slice((norm.length + 3) % 4));
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export function bytesToBase64(b: Uint8Array): string {
  let bin = "";
  for (const x of b) bin += String.fromCharCode(x);
  return btoa(bin);
}

/** First 48 bits of sha256(s) as a non-negative integer (fits in a JS number / SQLite INTEGER). */
export async function hash48(s: string): Promise<number> {
  const d = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s)));
  let n = 0;
  for (let i = 0; i < 6; i++) n = n * 256 + d[i];
  return n;
}
