import { describe, expect, it } from "vitest";
import { admin, call, callJson, uid } from "./helpers";

const label = (over: Record<string, unknown> = {}) => ({
  has_obstacle: "yes",
  domain: ["COMMUNICATION_INFORMATION"],
  locus: "material_external",
  failure_cause: "accidental_loss",
  note: "",
  ...over,
});

// Values that would only appear if model labels or bibliographic metadata leaked.
const SECRET_MARKERS = ["MODEL_LABEL_SECRET", "Jane Austen", "Pride and Prejudice", "1813", "pg1342"];

async function setupAnnotation() {
  const names = [uid("ann"), uid("ann")];
  const tokens: string[] = [];
  for (const n of names) {
    const r = await admin("POST", "/v1/admin/annotators", { name: n });
    expect(r.status).toBe(200);
    tokens.push(r.body.token);
  }
  const items = Array.from({ length: 8 }, (_, i) => ({
    item_id: uid("it"),
    passage_id: `pg1342_p${String(i).padStart(4, "0")}`,
    text: `Passage ${i}. The letter had not come.\n\nShe waited by the window until dark.`,
    ctx_before: "Earlier that week.",
    ctx_after: "Later.",
    set: i % 2 ? "audit" : "teaching",
    assign: names,
  }));
  const r = await admin("POST", "/v1/admin/ann_items", { items });
  expect(r.status).toBe(200);
  expect(r.body.inserted).toBe(8);
  return { names, tokens, items };
}

describe("annotation admin", () => {
  it("rejects items carrying model labels, title, author or date", async () => {
    const name = uid("ann");
    await admin("POST", "/v1/admin/annotators", { name });
    for (const extra of [{ model_label: "x" }, { title: "Pride and Prejudice" }, { author: "Austen" }, { date: 1813 }, { output: {} }]) {
      const r = await admin("POST", "/v1/admin/ann_items", {
        items: [{ item_id: uid("it"), passage_id: "pgX_p1", text: "t", set: "audit", assign: [name], ...extra }],
      });
      expect(r.status).toBe(400);
    }
    const leaky = await admin("POST", "/v1/admin/ann_items", {
      items: [{ item_id: "pg9_p1", passage_id: "pg9_p1", text: "t", set: "audit", assign: [name] }],
    });
    expect(leaky.status).toBe(400); // item_id must not reveal the passage id
    expect((await admin("POST", "/v1/admin/annotators", { name })).status).toBe(409);
    expect((await admin("POST", "/v1/admin/annotators", { name, rotate: true })).status).toBe(200);
  });
});

describe("annotator API", () => {
  it("serves the UI and returns only blind fields", async () => {
    const { tokens } = await setupAnnotation();
    const page = await call("GET", `/annotate/${tokens[0]}`);
    expect(page.status).toBe(200);
    expect(page.headers.get("content-type")).toContain("text/html");
    expect(page.headers.get("referrer-policy")).toBe("no-referrer");
    const html = await page.text();
    expect(html).toContain("COMMUNICATION_INFORMATION");
    expect((await call("GET", "/annotate/not-a-token")).status).toBe(404);
    expect((await call("GET", "/annotate/not-a-token/next")).status).toBe(401);

    const n = await callJson("GET", `/annotate/${tokens[0]}/next`);
    expect(n.status).toBe(200);
    expect(Object.keys(n.body).sort()).toEqual(["ctx_after", "ctx_before", "item_id", "progress", "text"]);
    expect(n.body.progress).toEqual({ done: 0, total: 8 });
    const raw = JSON.stringify(n.body);
    for (const m of SECRET_MARKERS) expect(raw).not.toContain(m);
    expect(raw).not.toContain("passage_id");
  });

  it("label / progress / undo / per-annotator order, and never leaks model fields", async () => {
    const { tokens, items } = await setupAnnotation();
    const [t0, t1] = tokens;
    const seen: string[] = [];
    const responses: string[] = [];
    for (let i = 0; i < 8; i++) {
      const n = await callJson("GET", `/annotate/${t0}/next`);
      responses.push(JSON.stringify(n.body));
      seen.push(n.body.item_id);
      const r = await callJson("POST", `/annotate/${t0}/label`, {
        json: { item_id: n.body.item_id, label_json: label(), evidence_text: "The letter had not come.", seconds_spent: 12.3 },
      });
      expect(r.status).toBe(200);
      expect(r.body.progress).toEqual({ done: i + 1, total: 8 });
      responses.push(JSON.stringify(r.body));
    }
    expect(new Set(seen)).toEqual(new Set(items.map((i) => i.item_id)));
    const end = await callJson("GET", `/annotate/${t0}/next`);
    expect(end.body.item_id).toBeNull();
    expect(end.body.progress).toEqual({ done: 8, total: 8 });

    // Undo reopens the most recent item, with the annotator's own label.
    const u = await callJson("POST", `/annotate/${t0}/undo`, { json: {} });
    expect(u.body.undone).toBe(seen[7]);
    expect(u.body.previous_label).toEqual(label());
    const back = await callJson("GET", `/annotate/${t0}/next`);
    expect(back.body.item_id).toBe(seen[7]);
    expect(back.body.progress).toEqual({ done: 7, total: 8 });
    responses.push(JSON.stringify(u.body), JSON.stringify(back.body));
    const relabel = await callJson("POST", `/annotate/${t0}/label`, {
      json: { item_id: seen[7], label_json: label({ failure_cause: "misinterpretation" }), evidence_text: "", seconds_spent: 4 },
    });
    expect(relabel.body.progress).toEqual({ done: 8, total: 8 });

    // Another annotator: different seeded order, and cannot see annotator 0's labels.
    const other: string[] = [];
    for (let i = 0; i < 8; i++) {
      const n = await callJson("GET", `/annotate/${t1}/next`);
      other.push(n.body.item_id);
      responses.push(JSON.stringify(n.body));
      await callJson("POST", `/annotate/${t1}/label`, { json: { item_id: n.body.item_id, label_json: label({ has_obstacle: "no", domain: [], locus: null, failure_cause: null }), evidence_text: "", seconds_spent: 3 } });
    }
    expect(other).not.toEqual(seen);
    for (const r of responses) {
      for (const m of SECRET_MARKERS) expect(r).not.toContain(m);
      for (const k of ["passage_id", "model", "pin_hash", "title", "author", "date", "annotator"]) expect(r).not.toContain(`"${k}`);
    }

    // Admin sees every label row, including the undone one.
    const all = await admin("GET", "/v1/admin/ann_labels");
    const mine = all.body.labels.filter((l: any) => items.some((i) => i.item_id === l.item_id));
    expect(mine.length).toBe(17);
    expect(mine.filter((l: any) => l.undone).length).toBe(1);
    expect(mine[0].passage_id).toMatch(/^pg1342_p/);
    expect(mine[0].seconds_spent).toBe(12.3);
  });

  it("validates labels", async () => {
    const { tokens } = await setupAnnotation();
    const n = await callJson("GET", `/annotate/${tokens[0]}/next`);
    const post = (l: unknown) => callJson("POST", `/annotate/${tokens[0]}/label`, { json: { item_id: n.body.item_id, label_json: l, evidence_text: "", seconds_spent: 1 } });
    expect((await post(label({ domain: ["A", "B"] }))).status).toBe(400);
    expect((await post(label({ domain: ["DISTANCE_TRAVEL", "OTHER", "INNER_STATE"] }))).status).toBe(400);
    expect((await post(label({ domain: ["DISTANCE_TRAVEL"], failure_cause: "infrastructure" }))).status).toBe(400);
    expect((await post(label({ has_obstacle: "maybe" }))).status).toBe(400);
    expect((await post(label({ locus: null }))).status).toBe(400);
    expect((await post(label({ has_obstacle: "no" }))).status).toBe(400);
    expect((await post(label({ model_label: "x" }))).status).toBe(400);
    expect((await post(label())).status).toBe(200);
    expect((await post(label())).status).toBe(409);
    const notMine = await callJson("POST", `/annotate/${tokens[0]}/label`, { json: { item_id: "nope", label_json: label() } });
    expect(notMine.status).toBe(404);
  });
});
