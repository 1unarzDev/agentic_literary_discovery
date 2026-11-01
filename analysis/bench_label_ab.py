"""A/B harness for label-stage compute efficiency (docs/perf_label_ab.md).

Three subcommands:
  build  (local)  write data/work/label_ab/{variants.json,passages.jsonl} from the production registry templates
                  + lean/compact variants, using the frozen 60-passage sample re-cut to production shape
                  (ctx_before = last 900 chars, ctx_after = next 600 chars, as in pipeline/build_corpus.py).
  run    (worker) run one variant at concurrency --par against a local Ollama; needs only httpx.
  score  (local)  score every run file against data/work/bench_ref_claude.jsonl (fiction only) with
                  ald.evidence.verify_quote.

usage:
  uv run python -I analysis/bench_label_ab.py build
  python bench_label_ab.py run --dir DIR --variant v0 --par 4 --tag np4
  uv run python -I analysis/bench_label_ab.py score DIR/runs
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOMAINS = ["DISTANCE_TRAVEL", "COMMUNICATION_INFORMATION", "DARKNESS_VISIBILITY", "ILLNESS_BODY_DEATH",
           "MONEY_PROPERTY_LAW", "SOCIAL_RANK_CONVENTION", "INTERPERSONAL_CONFLICT", "INNER_STATE",
           "NATURE_WEATHER", "OTHER"]


# --------------------------------------------------------------------------- build
def _passages() -> list[dict]:
    """Frozen bench sample, re-cut to the production passage shape."""
    out = []
    for line in (ROOT / "data/work/bench_sample_60_7.jsonl").read_text(encoding="utf-8").splitlines():
        p = json.loads(line)
        stem, s = p["id"].rsplit("_", 1)
        f = ROOT / "data/raw/pg" / stem[2:] / f"{stem}.txt"
        t = f.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"\*\*\* START OF.*?\*\*\*", t)
        words = (t[m.end():] if m else t).split()
        s = int(s)
        assert " ".join(words[s:s + 350]) == p["text"], p["id"]
        after = " ".join(words[s + 350:s + 470])[:600]
        out.append({"passage_id": p["id"], "text": p["text"], "ctx_before": p["ctx"][-900:], "ctx_after": after})
    return out


def build(outdir: Path) -> None:
    sys.path.insert(0, str(ROOT / "pipeline"))
    import make_registry as mr  # noqa: E402
    outdir.mkdir(parents=True, exist_ok=True)
    v0 = mr.V0_LABEL if hasattr(mr, "V0_LABEL") else dict(system=mr.LABEL_SYSTEM, schema=mr.LABEL_SCHEMA)
    lean = dict(system=mr.LEAN_SYSTEM_A, schema=mr.LEAN_SCHEMA)
    variants = {
        "v0": dict(system=v0["system"], schema=v0["schema"], user=mr.LABEL_USER, num_ctx=8192, num_predict=400),
        "v0_c4k": dict(system=v0["system"], schema=v0["schema"], user=mr.LABEL_USER, num_ctx=4096, num_predict=400),
        # v0 codebook, lean schema + lean output rules appended
        "leanout": dict(system=mr.LEANOUT_SYSTEM, schema=lean["schema"], user=mr.LABEL_USER, num_ctx=4096, num_predict=200),
        "leanout_anyof": dict(system=mr.LEANOUT_SYSTEM_ANYOF, schema=mr.LEAN_SCHEMA_ANYOF, user=mr.LABEL_USER,
                              num_ctx=4096, num_predict=200),
        # compact codebook + lean schema
        "compact": dict(system=lean["system"], schema=lean["schema"], user=mr.LABEL_USER, num_ctx=4096, num_predict=200),
        # compact codebook + anyOf (yes: full record; else: has_obstacle + confidence only)
        "compact_anyof": dict(system=mr.LEAN_SYSTEM_ANYOF_A, schema=mr.LEAN_SCHEMA_ANYOF, user=mr.LABEL_USER,
                              num_ctx=4096, num_predict=200),
        # compact2: same compact text in v0.5 section order (hard-case rules last)
        "compact2": dict(system=mr.LEAN_SYSTEM, schema=mr.LEAN_SCHEMA, user=mr.LABEL_USER, num_ctx=4096, num_predict=200),
        "compact2_anyof": dict(system=mr.LEAN_SYSTEM_ANYOF, schema=mr.LEAN_SCHEMA_ANYOF, user=mr.LABEL_USER,
                               num_ctx=4096, num_predict=200),
    }
    for k, ctx in ((3, 12288), (5, 12288), (8, 12288)):  # one load serves all K (num_ctx only sizes the 8 global layers)
        variants[f"batch{k}"] = dict(system=mr.BATCH_SYSTEM, schema=mr.batch_schema(k), user=mr.BATCH_USER_ITEM,
                                     num_ctx=ctx, num_predict=200 * k, batch_k=k)
    sys.path.insert(0, str(ROOT / "analysis"))
    import qa_ab  # noqa: E402  (QA pass-2 edits E1-E6 applied to the v0 prompt)
    variants["v09a_c4k"] = dict(system=qa_ab.v09a_system(v0["system"]), schema=v0["schema"], user=qa_ab.USER_NEW,
                                num_ctx=4096, num_predict=400)
    variants["v09lean"] = dict(system=mr.V09_SYSTEM_R1, schema=mr.V09_SCHEMA, user=mr.V09_USER, num_ctx=4096, num_predict=220)
    variants["v09lean_r2"] = dict(system=mr.V09_SYSTEM_R2, schema=mr.V09_SCHEMA, user=mr.V09_USER, num_ctx=4096, num_predict=220)
    variants["v09"] = dict(system=mr.V09_SYSTEM, schema=mr.V09_SCHEMA, user=mr.V09_USER, num_ctx=4096, num_predict=200)  # production
    variants["v09lean_b5"] = dict(system=mr.V09_BATCH_SYSTEM, schema=mr.batch_schema(5, mr.V09_SCHEMA),
                                  user=mr.V09_BATCH_USER_ITEM, num_ctx=12288, num_predict=1100, batch_k=5)
    (outdir / "variants.json").write_text(json.dumps(variants, indent=1, ensure_ascii=False), encoding="utf-8")
    qa_dir = ROOT / "data/work/label_ab_qa2"  # same variants on the QA pass-2 sample (passages from qa_ab.py build)
    if (qa_dir / "passages.jsonl").exists():
        (qa_dir / "variants.json").write_text(json.dumps(variants, indent=1, ensure_ascii=False), encoding="utf-8")
    ps = _passages()
    (outdir / "passages.jsonl").write_text("\n".join(json.dumps(p, ensure_ascii=False) for p in ps), encoding="utf-8")
    for k, v in variants.items():
        print(k, "system chars", len(v["system"]), "schema props", list(v["schema"].get("properties", {}))[:3])
    print("passages", len(ps), "->", outdir)


# --------------------------------------------------------------------------- run
def _call(url: str, model: str, v: dict, p: dict | list) -> dict:
    import httpx
    if isinstance(p, list):  # batch: K passages in one request
        user = "\n".join(v["user"].format(n=i + 1, **q) for i, q in enumerate(p))
        schema = json.loads(json.dumps(v["schema"]))
        lab = schema["properties"]["labels"]
        lab["minItems"] = lab["maxItems"] = len(p)  # only the trailing partial batch differs from K
        for it in lab["items"].get("anyOf", [lab["items"]]):
            it["properties"]["passage"]["enum"] = list(range(1, len(p) + 1))
        v = dict(v, schema=schema)
        pid = [q["passage_id"] for q in p]
    else:
        user = v["user"].format(**p)
        pid = p["passage_id"]
    t0 = time.time()
    r = httpx.post(url + "/api/chat", timeout=900, json={
        "model": model, "stream": False, "think": False, "format": v["schema"], "keep_alive": "30m",
        "options": {"temperature": 0, "seed": 0, "num_ctx": v["num_ctx"], "num_predict": v["num_predict"]},
        "messages": [{"role": "system", "content": v["system"]}, {"role": "user", "content": user}]})
    t1 = time.time()
    j = r.json()
    return {"id": pid, "t0": t0, "t1": t1, "content": j.get("message", {}).get("content", ""),
            "error": j.get("error"), "done_reason": j.get("done_reason"),
            "ptok": j.get("prompt_eval_count", 0), "pdur": j.get("prompt_eval_duration", 0),
            "gtok": j.get("eval_count", 0), "gdur": j.get("eval_duration", 0)}


def run(a: argparse.Namespace) -> None:
    d = Path(a.dir)
    v = json.loads((d / "variants.json").read_text(encoding="utf-8"))[a.variant]
    ps = [json.loads(l) for l in (d / "passages.jsonl").read_text(encoding="utf-8").splitlines()]
    ps = ps[: a.n] if a.n else ps
    k = v.get("batch_k")
    units = [ps[i:i + k] for i in range(0, len(ps), k)] if k else ps
    warm = [_call(a.url, a.model, v, units[-1 - i]) for i in range(2)]  # load + prefix-cache probe (2 sequential calls)
    t0 = time.time()
    with cf.ThreadPoolExecutor(a.par) as ex:
        res = list(ex.map(lambda p: _call(a.url, a.model, v, p), units))
    wall = time.time() - t0
    out = d / "runs" / f"{a.variant}__{a.tag}__c{a.par}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    meta = {"variant": a.variant, "tag": a.tag, "par": a.par, "n": len(ps), "batch_k": k, "wall_s": wall,
            "pph": round(len(ps) / wall * 3600), "warm": warm}
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps({"meta": meta}) + "\n")
        for r in res:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps({k: meta[k] for k in ("variant", "tag", "par", "n", "pph")}
                     | {"warm_ptok": [w["ptok"] for w in warm], "warm_pdur_ms": [round(w["pdur"] / 1e6) for w in warm],
                        "mean_gtok": sum(r["gtok"] for r in res) / len(res),
                        "max_ptok_plus_gtok": max(r["ptok"] + r["gtok"] for r in res),
                        "errors": sum(bool(r["error"]) for r in res)}), flush=True)


# --------------------------------------------------------------------------- score
def _expand(o: dict) -> dict:
    """anyOf minimal branch -> full record (the mapping production would apply)."""
    if o.get("has_obstacle") != "yes":
        o = {"domains": [], "locus": "none", "failure_cause": "none", "message_valence": "none",
             "technology_named": "none", "night_function": "none", "resolution_hint": "unknown",
             "obstacle_summary": "", "evidence_quote": ""} | o
    return o


def _batch_schema_for(schema: dict, n: int) -> dict:
    schema = json.loads(json.dumps(schema))
    lab = schema["properties"]["labels"]
    lab["minItems"] = lab["maxItems"] = n
    for it in lab["items"].get("anyOf", [lab["items"]]):
        it["properties"]["passage"]["enum"] = list(range(1, n + 1))
    return schema


def score_file(path: Path, ref: dict, texts: dict, schemas: dict) -> dict:
    import jsonschema
    sys.path.insert(0, str(ROOT / "ald/src"))
    from ald.evidence import verify_quote
    lines = path.read_text(encoding="utf-8").splitlines()
    meta = json.loads(lines[0])["meta"]
    res = [json.loads(l) for l in lines[1:]]
    schema = schemas.get(meta["variant"], {})  # unknown (e.g. synced production rows): no schema check
    ok = 0
    outs, pos, group = {}, {}, {}
    ptok = gtok = 0
    for r in res:
        ids = r["id"] if isinstance(r["id"], list) else [r["id"]]
        ptok += r.get("ptok", 0); gtok += r.get("gtok", 0)
        try:
            o = json.loads(r["content"])
        except Exception:
            o = None
        sch = _batch_schema_for(schema, len(ids)) if isinstance(r["id"], list) else schema
        if o is not None and not list(jsonschema.Draft202012Validator(sch).iter_errors(o)):
            ok += 1
        if isinstance(r["id"], list):
            labels = (o or {}).get("labels", []) if isinstance(o, dict) else []
            for j, pid in enumerate(ids):
                m = [x for x in labels if isinstance(x, dict) and x.get("passage") == j + 1]
                lab = m[0] if m else (labels[j] if j < len(labels) and isinstance(labels[j], dict) else {})
                outs[pid] = _expand(lab) if lab else {}
                pos[pid] = j + 1
                group[pid] = ids
        else:
            outs[ids[0]] = _expand(o) if isinstance(o, dict) else {}
            pos[ids[0]] = 1
            group[ids[0]] = ids
    tp = fp = fn = tn = 0
    dom = loc = 0
    both_yes = 0
    by_pos: dict[int, list[int]] = {}
    for pid, rf in ref.items():
        if not rf["is_fiction"]:
            continue
        o = outs.get(pid, {})
        my, ry = o.get("has_obstacle") == "yes", rf["has_obstacle"] == "yes"
        tp += my and ry; fp += my and not ry; fn += (not my) and ry; tn += (not my) and (not ry)
        by_pos.setdefault(pos.get(pid, 0), []).append(int(my == ry))
        if my and ry:
            both_yes += 1
            dom += bool(set(o.get("domains", [])) & set(rf["domains"]))
            loc += o.get("locus") == rf["locus"]
    n = tp + fp + fn + tn
    st, cross = [], 0
    for pid in outs:
        if outs[pid].get("has_obstacle") != "yes":
            continue
        q = outs[pid].get("evidence_quote", "")
        s0 = verify_quote(q, texts[pid]).status
        if s0 not in ("exact", "normalized"):  # pipeline/sync_results.check_quote's "trimmed": >=6 in-passage words
            w = q.split()
            if any(verify_quote(" ".join(w[:k]), texts[pid]).status in ("exact", "normalized")
                   or verify_quote(" ".join(w[-k:]), texts[pid]).status in ("exact", "normalized")
                   for k in range(len(w) - 1, 5, -1)):
                s0 = "trimmed"
        st.append(s0)
        if s0 not in ("exact", "normalized") and any(
                verify_quote(q, texts[o]).status in ("exact", "normalized") for o in group[pid] if o != pid):
            cross += 1
    nf_yes = sum(outs.get(pid, {}).get("has_obstacle") == "yes" for pid, rf in ref.items() if not rf["is_fiction"])
    dep = [_departs(o) for pid, o in outs.items() if pid in ref and ref[pid]["is_fiction"] and o.get("has_obstacle") == "yes"]
    dep = [d for d in dep if d is not None]
    lr = [bool((o.get("locus_reason") or "").strip()) for o in outs.values() if o.get("has_obstacle") == "yes"]
    qwords = [len(outs[pid].get("evidence_quote", "").split()) for pid in outs if outs[pid].get("has_obstacle") == "yes"]
    npass = len(outs)
    return {"variant": meta["variant"], "tag": meta["tag"], "c": meta["par"], "pph": meta["pph"],
            "schema_ok": round(ok / len(res), 3),
            "exact": round(sum(s == "exact" for s in st) / max(1, len(st)), 3),
            "exact_or_norm": round(sum(s in ("exact", "normalized") for s in st) / max(1, len(st)), 3),
            "quote_ok_trim": round(sum(s in ("exact", "normalized", "trimmed") for s in st) / max(1, len(st)), 3),
            "cross_quotes": cross,
            "acc": round((tp + tn) / n, 3), "P": round(tp / max(1, tp + fp), 3), "R": round(tp / max(1, tp + fn), 3),
            "dom": round(dom / max(1, both_yes), 3), "locus": round(loc / max(1, both_yes), 3),
            "nf_yes": f"{nf_yes}/{sum(not r['is_fiction'] for r in ref.values())}",
            "yes_rate": round(sum(outs.get(pid, {}).get("has_obstacle") == "yes" for pid, rf in ref.items() if rf["is_fiction"]) / n, 3),
            "locus_departs": round(sum(dep) / max(1, len(dep)), 3), "locus_reason_filled": round(sum(lr) / max(1, len(lr)), 3),
            "n_fiction": n,
            "ptok_per_passage": round(ptok / max(1, npass)), "gtok_per_passage": round(gtok / max(1, npass)),
            "max_ctx_used": max(r.get("ptok", 0) + r.get("gtok", 0) for r in res),
            "truncated": sum(r.get("done_reason") == "length" for r in res),
            "quote_words_med": sorted(qwords)[len(qwords) // 2] if qwords else None,
            "acc_by_pos": {k: round(sum(v) / len(v), 2) for k, v in sorted(by_pos.items())} if meta.get("batch_k") else None,
            "warm_ptok": [w["ptok"] for w in meta.get("warm", [])], "warm_pdur_ms": [round(w["pdur"] / 1e6) for w in meta.get("warm", [])]}


_DEFAULT_LOCUS = {"DISTANCE_TRAVEL": "material_external", "DARKNESS_VISIBILITY": "material_external",
                  "NATURE_WEATHER": "material_external", "ILLNESS_BODY_DEATH": "material_external",
                  "MONEY_PROPERTY_LAW": "social_institutional", "SOCIAL_RANK_CONVENTION": "social_institutional",
                  "INTERPERSONAL_CONFLICT": "social_institutional", "INNER_STATE": "internal_psychological"}


def _departs(o: dict) -> bool | None:
    """Locus differs from the codebook's default for the primary (first) domain; None when the default is
    undefined (COMMUNICATION depends on failure_cause, which the references lack; OTHER has none)."""
    d = (o.get("domains") or [None])[0]
    exp = _DEFAULT_LOCUS.get(d)
    return None if exp is None else o.get("locus") != exp


QA_FEWSHOT_IDS = {"pg8938_p00080", "pg72909_p00168"}  # v09a/v09lean few-shot sources: never scored


def load_ref(name: str) -> dict:
    if name == "bench":
        return {r["id"]: r for r in map(json.loads, (ROOT / "data/work/bench_ref_claude.jsonl").read_text(encoding="utf-8").splitlines())}
    import csv
    out = {}
    with open(ROOT / "docs/qa/label_pass_2_ref.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["passage_id"] in QA_FEWSHOT_IDS:
                continue
            out[r["passage_id"]] = {"is_fiction": r["truth"] != "nonfic", "has_obstacle": r["truth"],
                                    "domains": [d for d in r["ref_domains"].split(";") if d], "locus": r["ref_locus"]}
    return out


def ref_stats(ref: dict) -> dict:
    yes = [r for r in ref.values() if r["is_fiction"] and r["has_obstacle"] == "yes"]
    dep = [x for x in (_departs(r) for r in yes) if x is not None]
    return {"ref_yes_rate": round(len(yes) / sum(r["is_fiction"] for r in ref.values()), 3),
            "ref_locus_departs": round(sum(dep) / max(1, len(dep)), 3), "n_dep": len(dep)}


def score(a: argparse.Namespace) -> None:
    rd = Path(a.runs)
    ref = load_ref(a.ref)
    print(json.dumps({"ref": a.ref} | ref_stats(ref)))
    ps = [json.loads(l) for l in (rd.parent / "passages.jsonl").read_text(encoding="utf-8").splitlines()]
    texts = {p["passage_id"]: p["text"] for p in ps}
    schemas = {k: v["schema"] for k, v in json.loads((rd.parent / "variants.json").read_text(encoding="utf-8")).items()}
    rows = [score_file(f, ref, texts, schemas) for f in sorted(rd.glob("*.jsonl"))]
    for r in rows:
        print(json.dumps(r))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("--out", default=str(ROOT / "data/work/label_ab"))
    r = sub.add_parser("run")
    r.add_argument("--dir", required=True); r.add_argument("--variant", required=True)
    r.add_argument("--par", type=int, default=4); r.add_argument("--tag", default="")
    r.add_argument("--n", type=int, default=0); r.add_argument("--model", default="gemma4:12b-it-q4_K_M")
    r.add_argument("--url", default="http://127.0.0.1:11434")
    s = sub.add_parser("score"); s.add_argument("runs"); s.add_argument("--ref", choices=["bench", "qa"], default="bench")
    a = ap.parse_args()
    if a.cmd == "build":
        build(Path(a.out))
    elif a.cmd == "run":
        run(a)
    else:
        score(a)


if __name__ == "__main__":
    main()
