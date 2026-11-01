import { Hono } from "hono";
import { adminRoutes, INSTALL_SCRIPTS } from "./admin_routes";
import { annotateRoutes } from "./annotate_routes";
import type { AppEnv } from "./auth";
import { reclaimExpired } from "./db";
import { statusRoutes } from "./status";
import { Env, HttpError, errorResponse, json } from "./util";
import { workerRoutes } from "./worker_routes";

const app = new Hono<AppEnv>();

app.onError((err, c) => {
  if (err instanceof HttpError) return errorResponse(err);
  console.error("unhandled", err);
  return json({ error: "internal error" }, 500);
});
app.notFound(() => json({ error: "not found" }, 404));

// ---- public, unauthenticated: installers and client wheels
for (const name of INSTALL_SCRIPTS) {
  app.get(`/${name}`, async (c) => {
    const obj = await c.env.BUCKET.get(`install/${name}`);
    if (!obj) throw new HttpError(404, `${name} not uploaded`);
    const origin = new URL(c.req.url).origin;
    const text = (await obj.text()).replaceAll("__COORDINATOR_URL__", origin);
    return new Response(text, {
      headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-cache" },
    });
  });
}

app.get("/dist/:file", async (c) => {
  const file = c.req.param("file");
  if (file.includes("/") || file.includes("..")) throw new HttpError(404, "not found");
  const obj = await c.env.BUCKET.get(`dist/${file}`);
  if (!obj) throw new HttpError(404, "not found");
  return new Response(obj.body, {
    headers: {
      "content-type": "application/octet-stream",
      "content-length": String(obj.size),
      "cache-control": "public, max-age=300",
      ...(obj.customMetadata?.content_sha256 ? { "x-content-sha256": obj.customMetadata.content_sha256 } : {}),
    },
  });
});

app.route("/", workerRoutes);
app.route("/", adminRoutes);
app.route("/", statusRoutes);
app.route("/", annotateRoutes);

export default {
  fetch: app.fetch,
  async scheduled(_controller: ScheduledController, env: Env, ctx: ExecutionContext) {
    ctx.waitUntil(
      reclaimExpired(env).then((r) => {
        if (r.requeued.length || r.dead.length) console.log("reclaimed", JSON.stringify(r));
      }),
    );
  },
} satisfies ExportedHandler<Env>;

export { app };
