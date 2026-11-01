import { describe, expect, it } from "vitest";
import { admin, call, callJson, uid } from "./helpers";

const label = (over: Record<string, unknown> = {}) => ({
  has_obstacle: "yes",
  domain: "COMMUNICATION_INFORMATION",
  locus: "material_external",
  failure_cause: "accidental_loss",
  note: "",
  ...over,
});
const NO = { has_obstacle: "no", domain: null, locus: null, failure_cause: null, note: "" };

// Values that would only appear if model labels, bibliographic metadata or practice references leaked.
const SECRET_MARKERS = ["MODEL_LABEL_SECRET", "Jane Austen", "Pride and Prejudice", "1813", "pg1342", "REF_RATIONALE_SECRET"];
const LEAK_KEYS = ["passage_id", "model", "pin_hash", "title", "author", "date", "decade", "annotator", "reference", "rationale", "ref_json", "set_name"];

function expectBlind(raw: string, opts: { allowFeedback?: boolean } = {}) {
  for (const m of SECRET_MARKERS) if (!(opts.allowFeedback && m === "REF_RATIONALE_SECRET")) expect(raw).not.toContain(m);
  for (const k of LEAK_KEYS) if (!(opts.allowFeedback && (k === "rationale"))) expect(raw).not.toContain(`"${k}"`);
}

const ref = (over: Record<string, unknown> = {}) => ({
  has_obstacle: "yes",
  domain: "INNER_STATE",
  locus: "internal_psychological",
  failure_cause: null,
  rationale: "REF_RATIONALE_SECRET: she cannot bring herself to speak.",
  ...over,
});

const mkItems = (n: number, set: string, assign: string[], extra: (i: number) => Record<string, unknown> = () => ({})) =>
  Array.from({ length: n }, (_, i) => ({
    item_id: uid("it"),
    passage_id: `pg1342_p${set}${String(i).padStart(4, "0")}`,
    text: `Passage ${i}. The letter had not come.\n\nShe waited by the window until dark.`,
    ctx_before: "Earlier that week.",
    ctx_after: "Later.",
    set,
    assign,
    ...extra(i),
  }));

async function mkAnnotators(n: number) {
  const names: string[] = [];
  const tokens: string[] = [];
  for (let i = 0; i < n; i++) {
    const name = uid("ann");
    const r = await admin("POST", "/v1/admin/annotators", { name });
    expect(r.status).toBe(200);
    names.push(name);
    tokens.push(r.body.token);
  }
  return { names, tokens };
}

async function post(items: unknown[]) {
  const r = await admin("POST", "/v1/admin/ann_items", { items });
  expect(r.status, JSON.stringify(r.body)).toBe(200);
  return r.body;
}

const next = (t: string, q?: string) => callJson("GET", `/annotate/${t}/next${q ? `?queue=${q}` : ""}`);
const submit = (t: string, item_id: string, l: unknown = label()) =>
  callJson("POST", `/annotate/${t}/label`, { json: { item_id, label_json: l, evidence_text: "", seconds_spent: 3 } });

describe("annotation admin", () => {
  it("rejects items carrying model labels, title, author or date", async () => {
    const name = uid("ann");
    await admin("POST", "/v1/admin/annotators", { name });
    for (const extra of [{ model_label: "x" }, { title: "Pride and Prejudice" }, { author: "Austen" }, { date: 1813 }, { output: {} }, { decade: 1810 }]) {
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

  it("references: required and valid on practice items, refused elsewhere", async () => {
    const name = uid("ann");
    await admin("POST", "/v1/admin/annotators", { name });
    const one = (o: Record<string, unknown>) =>
      admin("POST", "/v1/admin/ann_items", { items: [{ item_id: uid("it"), passage_id: "pgP_p1", text: "t", assign: [name], ...o }] });
    expect((await one({ set: "practice" })).status).toBe(400); // no reference
    expect((await one({ set: "practice", reference: ref({ rationale: "" }) })).status).toBe(400);
    expect((await one({ set: "practice", reference: ref({ domain: ["INNER_STATE"] }) })).status).toBe(400);
    expect((await one({ set: "practice", reference: ref({ model_label: "x" }) })).status).toBe(400);
    expect((await one({ set: "audit", reference: ref() })).status).toBe(400);
    expect((await one({ set: "teaching", reference: ref() })).status).toBe(400);
    expect((await one({ set: "expert" })).status).toBe(400);
    expect((await one({ set: "practice", reference: ref() })).status).toBe(200);
  });
});

describe("annotator API", () => {
  it("serves the UI and the guide, and returns only blind fields", async () => {
    const { names, tokens } = await mkAnnotators(1);
    await post(mkItems(3, "audit", names));
    const page = await call("GET", `/annotate/${tokens[0]}`);
    expect(page.status).toBe(200);
    expect(page.headers.get("content-type")).toContain("text/html");
    expect(page.headers.get("referrer-policy")).toBe("no-referrer");
    const html = await page.text();
    expect(html).toContain("COMMUNICATION_INFORMATION");
    expect(html).toContain("/annotate/guide");
    expect((await call("GET", "/annotate/not-a-token")).status).toBe(404);
    expect((await call("GET", "/annotate/not-a-token/next")).status).toBe(401);

    const g = await call("GET", "/annotate/guide");
    expect(g.status).toBe(200);
    expect(g.headers.get("content-type")).toContain("text/html");
    const guide = await g.text();
    expect(guide).toContain("<h1");
    expect(guide.toLowerCase()).toContain("can");
    expect(guide).not.toMatch(/pg\d+_p\d+/); // no passage ids in the guide

    const n = await next(tokens[0]);
    expect(n.status).toBe(200);
    expect(Object.keys(n.body).sort()).toEqual(["cert", "ctx_after", "ctx_before", "item_id", "progress", "queue", "queues", "text"]);
    expect(n.body.cert).toEqual({ status: "none", rounds: [] });
    expect(n.body.queue).toBe("audit");
    expect(n.body.progress).toEqual({ done: 0, total: 3 });
    expect(n.body.queues).toEqual([{ queue: "audit", display: "Main set", done: 0, total: 3, locked: false }]);
    expectBlind(JSON.stringify(n.body));
  });

  it("label / progress / undo / per-annotator order, and never leaks model fields", async () => {
    const { names, tokens } = await mkAnnotators(2);
    const items = mkItems(8, "audit", names);
    await post(items);
    const [t0, t1] = tokens;
    const seen: string[] = [];
    const responses: string[] = [];
    for (let i = 0; i < 8; i++) {
      const n = await next(t0);
      responses.push(JSON.stringify(n.body));
      seen.push(n.body.item_id);
      const r = await callJson("POST", `/annotate/${t0}/label`, {
        json: { item_id: n.body.item_id, label_json: label(), evidence_text: "The letter had not come.", seconds_spent: 12.3 },
      });
      expect(r.status).toBe(200);
      expect(r.body.progress).toEqual({ done: i + 1, total: 8 });
      expect(r.body.feedback).toBeUndefined();
      responses.push(JSON.stringify(r.body));
    }
    expect(new Set(seen)).toEqual(new Set(items.map((i) => i.item_id)));
    const end = await next(t0);
    expect(end.body.item_id).toBeNull();
    expect(end.body.progress).toEqual({ done: 8, total: 8 });

    const u = await callJson("POST", `/annotate/${t0}/undo`, { json: { queue: "audit" } });
    expect(u.body.undone).toBe(seen[7]);
    expect(u.body.previous_label).toEqual(label());
    const back = await next(t0, "audit");
    expect(back.body.item_id).toBe(seen[7]);
    expect(back.body.progress).toEqual({ done: 7, total: 8 });
    responses.push(JSON.stringify(u.body), JSON.stringify(back.body));
    const relabel = await submit(t0, seen[7], label({ failure_cause: "misinterpretation", locus: "social_institutional" }));
    expect(relabel.body.progress).toEqual({ done: 8, total: 8 });

    const other: string[] = [];
    for (let i = 0; i < 8; i++) {
      const n = await next(t1);
      other.push(n.body.item_id);
      responses.push(JSON.stringify(n.body));
      await submit(t1, n.body.item_id, NO);
    }
    expect(other).not.toEqual(seen);
    for (const r of responses) expectBlind(r);

    const all = await admin("GET", "/v1/admin/ann_labels");
    const mine = all.body.labels.filter((l: any) => items.some((i) => i.item_id === l.item_id));
    expect(mine.length).toBe(17);
    expect(mine.filter((l: any) => l.undone).length).toBe(1);
    expect(mine[0].passage_id).toMatch(/^pg1342_p/);
    expect(mine[0].seconds_spent).toBe(12.3);
    expect(mine.every((l: any) => l.practice === false)).toBe(true);
  });

  it("validates the simplified label schema", async () => {
    const { names, tokens } = await mkAnnotators(1);
    await post(mkItems(1, "audit", names));
    const n = await next(tokens[0]);
    const p = (l: unknown) => submit(tokens[0], n.body.item_id, l);
    expect((await p(label({ domain: ["COMMUNICATION_INFORMATION"] }))).status).toBe(400); // one domain, not a list
    expect((await p(label({ domain: "A" }))).status).toBe(400);
    expect((await p(label({ failure_cause: null }))).status).toBe(400); // COMMUNICATION needs a cause
    expect((await p(label({ domain: "DISTANCE_TRAVEL" }))).status).toBe(400); // cause only for COMMUNICATION
    expect((await p(label({ has_obstacle: "maybe" }))).status).toBe(400);
    expect((await p(label({ locus: null }))).status).toBe(400);
    expect((await p(label({ locus: "inner" }))).status).toBe(400);
    expect((await p(label({ has_obstacle: "no" }))).status).toBe(400); // no obstacle but domain set
    expect((await p({ ...NO, failure_cause: "none" })).status).toBe(400);
    expect((await p(label({ model_label: "x" }))).status).toBe(400);
    expect((await p(label({ evidence: "x" }))).status).toBe(400);
    expect((await p(label({ failure_cause: "none" }))).status).toBe(200);
    expect((await p(label())).status).toBe(409);
    const notMine = await callJson("POST", `/annotate/${tokens[0]}/label`, { json: { item_id: "nope", label_json: label() } });
    expect(notMine.status).toBe(404);
  });

  it("accepts every valid shape", async () => {
    const { names, tokens } = await mkAnnotators(1);
    const shapes = [
      NO,
      { ...NO, has_obstacle: "insufficient_context" },
      label({ domain: "INNER_STATE", locus: "internal_psychological", failure_cause: null }),
      label({ domain: "OTHER", locus: "material_external", failure_cause: null, note: "a curse" }),
      label({ failure_cause: "intentional_withholding", locus: "social_institutional" }),
    ];
    await post(mkItems(shapes.length, "audit", names));
    for (const s of shapes) {
      const n = await next(tokens[0]);
      expect((await submit(tokens[0], n.body.item_id, s)).status).toBe(200);
    }
  });
});

describe("practice mode", () => {
  it("gates the main set until practice is done; feedback only after answering", async () => {
    const { names, tokens } = await mkAnnotators(2); // [0] peer with practice, [1] expert without
    const [peer, expert] = names;
    const [tp, te] = tokens;
    const practice = mkItems(3, "practice", [peer], (i) => ({ reference: ref(i === 1 ? { has_obstacle: "no", domain: null, locus: null } : {}) }));
    const audit = mkItems(4, "audit", [peer, expert]);
    await post([...practice, ...audit]);

    // State and first item: practice first, main set locked. No reference anywhere.
    const st = await callJson("GET", `/annotate/${tp}/state`);
    expect(st.body.queues).toEqual([
      { queue: "practice", display: "Practice", done: 0, total: 3, locked: false },
      { queue: "audit", display: "Main set", done: 0, total: 4, locked: true },
    ]);
    const n0 = await next(tp);
    expect(n0.body.queue).toBe("practice");
    expectBlind(JSON.stringify(n0.body));
    expectBlind(JSON.stringify(st.body));
    expect((await next(tp, "audit")).status).toBe(423);
    expect((await next(tp, "teaching")).status).toBe(404);
    expect((await next(tp, "bogus")).status).toBe(400);
    expect((await submit(tp, audit[0].item_id)).status).toBe(423); // cannot label a locked item directly
    expect((await callJson("GET", `/annotate/${tp}/practice_review`)).body.items).toEqual([]);

    // Answer practice: the response carries the reference + rationale; nothing else does.
    const seen = new Set<string>();
    for (let i = 0; i < 3; i++) {
      const n = await next(tp);
      expect(n.body.queue).toBe("practice");
      expect(n.body.ctx_before).toBe("Earlier that week.");
      expectBlind(JSON.stringify(n.body));
      seen.add(n.body.item_id);
      const r = await submit(tp, n.body.item_id, NO);
      expect(r.status).toBe(200);
      expect(r.body.queue).toBe("practice");
      expect(r.body.feedback.rationale).toContain("REF_RATIONALE_SECRET");
      expect(Object.keys(r.body.feedback).sort()).toEqual(["domain", "failure_cause", "has_obstacle", "locus", "rationale"]);
      expectBlind(JSON.stringify({ ...r.body, feedback: undefined }));
      if (i < 2) expect(r.body.queues[1].locked).toBe(true);
    }
    expect(seen.size).toBe(3);
    expect((await callJson("POST", `/annotate/${tp}/undo`, { json: { queue: "practice" } })).status).toBe(409);
    const rev = await callJson("GET", `/annotate/${tp}/practice_review`);
    expect(rev.body.items.length).toBe(3);
    expect(rev.body.items.filter((x: any) => x.reference.has_obstacle === "no").length).toBe(1);

    // Unlocked: default queue is now the main set, and its items never carry feedback.
    const st2 = await callJson("GET", `/annotate/${tp}/state`);
    expect(st2.body.queues.map((q: any) => q.locked)).toEqual([false, false]);
    const n1 = await next(tp);
    expect(n1.body.queue).toBe("audit");
    const r1 = await submit(tp, n1.body.item_id);
    expect(r1.body.feedback).toBeUndefined();
    expectBlind(JSON.stringify(r1.body));
    const pr = await next(tp, "practice");
    expect(pr.body.item_id).toBeNull(); // finished practice

    // Undo is per set: undoing the main set does not touch practice.
    const u = await callJson("POST", `/annotate/${tp}/undo`, { json: { queue: "audit" } });
    expect(u.body.undone).toBe(n1.body.item_id);

    // An annotator without practice items is never gated.
    const e0 = await next(te);
    expect(e0.body.queue).toBe("audit");
    expect(e0.body.queues).toEqual([{ queue: "audit", display: "Main set", done: 0, total: 4, locked: false }]);
    expect((await callJson("GET", `/annotate/${te}/practice_review`)).body.items).toEqual([]);

    // Admin export flags practice labels; status reports per-queue progress.
    const all = await admin("GET", "/v1/admin/ann_labels");
    const mine = all.body.labels.filter((l: any) => l.annotator === peer);
    expect(mine.filter((l: any) => l.practice).length).toBe(3);
    expect(mine.filter((l: any) => l.practice).every((l: any) => l.set === "practice")).toBe(true);
    const s = await admin("GET", "/v1/admin/ann_status");
    const ps = s.body.annotators.find((a: any) => a.name === peer);
    expect(ps.practice_complete).toBe(true);
    expect(ps.queues).toContainEqual({ queue: "practice", done: 3, total: 3 });
    expect(ps.queues).toContainEqual({ queue: "audit", done: 0, total: 4 });
    const es = s.body.annotators.find((a: any) => a.name === expert);
    expect(es.practice_complete).toBe(true);
    expect((await call("GET", "/v1/admin/ann_status")).status).toBe(401);
  });

  it("keeps the teaching set separate from the main set", async () => {
    const { names, tokens } = await mkAnnotators(1);
    await post([...mkItems(2, "teaching", names), ...mkItems(3, "audit", names)]);
    const st = await callJson("GET", `/annotate/${tokens[0]}/state`);
    expect(st.body.queues.map((q: any) => [q.queue, q.total])).toEqual([["audit", 3], ["teaching", 2]]);
    const t = await next(tokens[0], "teaching");
    expect(t.body.queue).toBe("teaching");
    await submit(tokens[0], t.body.item_id, NO);
    const a = await next(tokens[0], "audit");
    expect(a.body.queue).toBe("audit");
    expect(a.body.progress).toEqual({ done: 0, total: 3 });
    // undo in the main set finds nothing; the teaching label stays
    expect((await callJson("POST", `/annotate/${tokens[0]}/undo`, { json: { queue: "audit" } })).body.undone).toBeNull();
    expect((await callJson("POST", `/annotate/${tokens[0]}/undo`, { json: { queue: "teaching" } })).body.undone).toBe(t.body.item_id);
  });
});

describe("certification", () => {
  // 20 cert items: 8 material, 6 social, 2 internal, 4 no obstacle (reference).
  const certRef = (i: number) =>
    i < 8
      ? ref({ domain: "NATURE_WEATHER", locus: "material_external" })
      : i < 14
        ? ref({ domain: "MONEY_PROPERTY_LAW", locus: "social_institutional" })
        : i < 16
          ? ref({ domain: "INNER_STATE", locus: "internal_psychological" })
          : ref({ has_obstacle: "no", domain: null, locus: null });
  const asLabel = (r: Record<string, unknown>) => {
    const { rationale: _r, ...core } = r;
    return { ...core, failure_cause: null, note: "" };
  };

  async function setup(withRetake = true) {
    const { names, tokens } = await mkAnnotators(1);
    const practice = mkItems(2, "practice", names, () => ({ reference: ref() }));
    const cert = mkItems(20, "cert", names, (i) => ({ reference: certRef(i) }));
    const retake = withRetake ? mkItems(20, "retake", names, (i) => ({ reference: certRef(i) })) : [];
    const audit = mkItems(3, "audit", names);
    await post([...practice, ...cert, ...retake, ...audit]);
    const refOf = new Map<string, any>([...cert, ...retake].map((it: any) => [it.item_id, it.reference]));
    return { name: names[0], t: tokens[0], refOf };
  }

  async function doPractice(t: string) {
    for (let i = 0; i < 2; i++) {
      const n = await next(t, "practice");
      expect((await submit(t, n.body.item_id, NO)).status).toBe(200);
    }
  }

  /** Answer a whole round; `wrong(i)` decides which answers deviate from the reference. */
  async function doRound(t: string, round: string, refOf: Map<string, any>, wrong: (i: number) => boolean) {
    const out: any[] = [];
    for (let i = 0; i < 20; i++) {
      const n = await next(t, round);
      expect(n.body.queue).toBe(round);
      expectBlind(JSON.stringify(n.body));
      const r = refOf.get(n.body.item_id);
      const l = wrong(i)
        ? r.has_obstacle === "yes"
          ? NO
          : asLabel(ref({ domain: "DISTANCE_TRAVEL", locus: "material_external" }))
        : asLabel(r);
      const res = await submit(t, n.body.item_id, l);
      expect(res.status).toBe(200);
      expect(res.body.feedback).toBeUndefined(); // no feedback during a check
      expectBlind(JSON.stringify(res.body));
      out.push(res.body);
    }
    return out;
  }

  it("unlocks the main set only after passing the check", async () => {
    const { name, t, refOf } = await setup();
    let st = await callJson("GET", `/annotate/${t}/state`);
    expect(st.body.cert.status).toBe("not_started");
    expect(st.body.queues.map((q: any) => [q.queue, q.locked])).toEqual([["practice", false], ["cert", true], ["audit", true]]); // retake hidden
    expect((await next(t, "cert")).status).toBe(423);
    await doPractice(t);
    st = await callJson("GET", `/annotate/${t}/state`);
    expect(st.body.cert.status).toBe("in_progress");
    expect((await next(t)).body.queue).toBe("cert");
    expect((await next(t, "audit")).status).toBe(423);
    expect((await callJson("GET", `/annotate/${t}/cert_review?round=cert`)).status).toBe(409); // not finished: nothing revealed
    expect((await callJson("POST", `/annotate/${t}/undo`, { json: { queue: "cert" } })).status).toBe(409);

    const res = await doRound(t, "cert", refOf, (i) => i === 0 || i === 19); // 2 wrong of 20
    for (const r of res.slice(0, 19)) expect(r.cert.rounds[0]).toEqual({ round: "cert", n: 20, done: expect.any(Number) }); // no running score
    const last = res[19].cert;
    expect(last.status).toBe("passed");
    expect(last.rounds[0].passed).toBe(true);
    expect(last.rounds[0].obs_agree).toBe(0.9);
    const n = await next(t);
    expect(n.body.queue).toBe("audit");
    expect(n.body.queues.map((q: any) => q.queue)).toEqual(["practice", "cert", "audit"]);
    const rev = await callJson("GET", `/annotate/${t}/cert_review?round=cert`);
    expect(rev.body.passed).toBe(true);
    expect(rev.body.misses.length).toBe(2);
    expect(rev.body.misses[0].reference.rationale).toContain("REF_RATIONALE_SECRET");

    const s = await admin("GET", "/v1/admin/ann_status");
    const me = s.body.annotators.find((a: any) => a.name === name);
    expect(me.cert.status).toBe("passed");
    expect(me.cert.rounds[0]).toMatchObject({ round: "cert", n: 20, done: 20, obs_agree: 0.9, passed: true });
    const all = await admin("GET", "/v1/admin/ann_labels");
    const mine = all.body.labels.filter((l: any) => l.annotator === name);
    expect(mine.filter((l: any) => l.set === "cert").every((l: any) => l.practice)).toBe(true);
  });

  it("fails on low locus agreement, shows misses, allows one retake", async () => {
    const { name, t, refOf } = await setup();
    await doPractice(t);
    // 6 wrong of 20: obstacle agreement 0.70 < 0.75 -> fail
    const res = await doRound(t, "cert", refOf, (i) => i < 6);
    expect(res[19].cert.status).toBe("failed_retake_available");
    expect(res[19].cert.rounds[0].passed).toBe(false);
    const st = await callJson("GET", `/annotate/${t}/state`);
    expect(st.body.queues.map((q: any) => [q.queue, q.locked])).toEqual([["practice", false], ["cert", false], ["retake", false], ["audit", true]]);
    expect((await next(t, "audit")).status).toBe(423);
    const rev = await callJson("GET", `/annotate/${t}/cert_review?round=cert`);
    expect(rev.body.passed).toBe(false);
    expect(rev.body.misses.length).toBe(6);
    expect(Object.keys(rev.body.misses[0]).sort()).toEqual(["excerpt", "item_id", "label", "reference"]);
    expect(JSON.stringify(rev.body)).not.toContain("passage_id");
    expect((await callJson("GET", `/annotate/${t}/cert_review?round=retake`)).status).toBe(409);

    expect((await next(t)).body.queue).toBe("retake");
    const r2 = await doRound(t, "retake", refOf, (i) => i < 6);
    expect(r2[0].cert.status).toBe("in_retake");
    expect(r2[19].cert.status).toBe("failed");
    expect((await next(t, "audit")).status).toBe(423);
    expect((await next(t, "retake")).status).toBe(423); // only one retake

    // Admin override passes them; revoke locks again; clear returns to the computed result.
    expect((await admin("POST", "/v1/admin/ann_cert", { name, decision: "pass", note: "reviewed" })).body.cert.status).toBe("override");
    expect((await next(t, "audit")).body.queue).toBe("audit");
    expect((await admin("POST", "/v1/admin/ann_cert", { name, decision: "revoke" })).body.cert.status).toBe("revoked");
    expect((await next(t, "audit")).status).toBe(423);
    expect((await admin("POST", "/v1/admin/ann_cert", { name, decision: "clear" })).body.cert.status).toBe("failed");
    expect((await admin("POST", "/v1/admin/ann_cert", { name: "nobody-xyz", decision: "pass" })).status).toBe(404);
    expect((await call("POST", "/v1/admin/ann_cert", { json: { name, decision: "pass" } })).status).toBe(401);
  });

  it("kappa gate: right obstacle calls but wrong loci still fails; no retake set means failed", async () => {
    const { t, refOf } = await setup(false);
    await doPractice(t);
    // every obstacle call right, but all social items answered as material -> kappa well below 0.6
    for (let i = 0; i < 20; i++) {
      const n = await next(t, "cert");
      const r = refOf.get(n.body.item_id);
      const l = asLabel(r.locus === "social_institutional" || r.locus === "internal_psychological" ? { ...r, domain: "NATURE_WEATHER", locus: "material_external" } : r);
      await submit(t, n.body.item_id, l);
    }
    const st = await callJson("GET", `/annotate/${t}/state`);
    expect(st.body.cert.status).toBe("failed");
    expect(st.body.cert.rounds[0].obs_agree).toBe(1);
    expect(st.body.cert.rounds[0].locus_kappa).toBeLessThan(0.6);
    expect(st.body.queues.find((q: any) => q.queue === "audit").locked).toBe(true);
  });
});
