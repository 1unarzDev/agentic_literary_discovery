"""Benchmark candidate Ollama models on real PG passages: throughput, schema validity, exact-quote rate.

usage: uv run python -I analysis/bench_models.py MODEL [--stage screen|label] [--n 48] [--par 4]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import random
import re
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
CODEBOOK = (ROOT / "docs/codebook_v0.5.md").read_text(encoding="utf-8")  # the 2026-10-31 pilot ran on v0.5
DOMAINS = ["DISTANCE_TRAVEL", "COMMUNICATION_INFORMATION", "DARKNESS_VISIBILITY", "ILLNESS_BODY_DEATH",
           "MONEY_PROPERTY_LAW", "SOCIAL_RANK_CONVENTION", "INTERPERSONAL_CONFLICT", "INNER_STATE",
           "NATURE_WEATHER", "OTHER", "NONE"]

SCREEN_SCHEMA = {"type": "object", "properties": {
    "has_obstacle": {"type": "string", "enum": ["yes", "no", "insufficient_context"]},
    "coarse_domain": {"type": "string", "enum": DOMAINS},
    "confidence": {"type": "number"}}, "required": ["has_obstacle", "coarse_domain", "confidence"]}

LABEL_SCHEMA = {"type": "object", "properties": {
    "character_goal": {"type": "string", "description": "who wants what, in <=12 words, or 'none'"},
    "impediment": {"type": "string", "description": "what stands in the way, in <=12 words, or 'none'"},
    "consequence_in_text": {"type": "string", "description": "how the passage shows it matters for action, <=12 words, or 'none'"},
    "has_obstacle": {"type": "string", "enum": ["yes", "no", "insufficient_context"]},
    "domains": {"type": "array", "items": {"type": "string", "enum": DOMAINS[:-1]}, "maxItems": 2},
    "locus": {"type": "string", "enum": ["material_external", "social_institutional", "internal_psychological", "none"]},
    "locus_reason": {"type": "string"},
    "failure_cause": {"type": "string", "enum": ["infrastructure", "accidental_loss", "intentional_withholding", "misinterpretation", "success_resolution", "none"]},
    "message_valence": {"type": "string", "enum": ["catastrophic", "romantic", "financial", "practical", "none"]},
    "technology_named": {"type": "string", "enum": ["letter", "note", "telegram", "telephone", "messenger", "railway", "coach", "steamship", "carriage", "horse", "foot", "gas", "electric", "candle", "lamp", "none"]},
    "night_function": {"type": "string", "enum": ["danger", "concealment", "intimacy", "labor", "leisure", "none"]},
    "resolution_hint": {"type": "string", "enum": ["by_technology", "by_person", "by_chance", "unresolved", "unknown"]},
    "obstacle_summary": {"type": "string"},
    "evidence_quote": {"type": "string"},
    "confidence": {"type": "number"}},
    "required": ["character_goal", "impediment", "consequence_in_text", "has_obstacle", "domains", "locus", "failure_cause", "message_valence", "technology_named",
                 "night_function", "resolution_hint", "obstacle_summary", "evidence_quote", "confidence"]}

SYSTEM_SCREEN = ("You are a careful literary annotator. Apply this codebook exactly.\n\n" + CODEBOOK.split("## Fields")[0]
                 + "\nAnswer only the JSON fields: has_obstacle, coarse_domain (NONE if no obstacle), confidence.")
SYSTEM_LABEL = ("You are a careful literary annotator. Apply this codebook exactly.\n\n" + CODEBOOK +
    "\n\nPROCEDURE: First fill character_goal, impediment and consequence_in_text using ONLY what the passage states. "
    "If any of the three is 'none' or requires guessing beyond the text, has_obstacle must be 'no' (or 'insufficient_context'). "
    "Many passages (often about half) are description, conversation, or exposition without a plot obstacle; do not invent one. "
    "Non-fiction prose (history, essays, travel description) never has a plot obstacle unless a character's goal is narrated. "
    "evidence_quote must be copied verbatim: 8-30 consecutive words from PASSAGE. Return only JSON.")


def sample_passages(n: int, seed: int = 7) -> list[dict]:
    frozen = ROOT / f"data/work/bench_sample_{n}_{seed}.jsonl"
    if frozen.exists():
        return [json.loads(l) for l in frozen.read_text(encoding="utf-8").splitlines()]
    out = _sample(n, seed)
    frozen.parent.mkdir(parents=True, exist_ok=True)
    frozen.write_text("\n".join(json.dumps(p) for p in out), encoding="utf-8")
    return out


def _sample(n: int, seed: int) -> list[dict]:
    files = sorted((ROOT / "data/raw/pg").glob("*/pg*.txt"))
    rng = random.Random(seed)
    rng.shuffle(files)
    out = []
    for f in files:
        t = f.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"\*\*\* START OF.*?\*\*\*", t)
        t = t[m.end():] if m else t
        words = t.split()
        if len(words) < 20000:
            continue
        for _ in range(2):
            s = rng.randrange(len(words) // 10, len(words) * 9 // 10)
            out.append({"id": f"{f.stem}_{s}", "text": " ".join(words[s:s + 350]),
                        "ctx": " ".join(words[max(0, s - 120):s])})
        if len(out) >= n:
            break
    return out[:n]


def norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip()


def call(model: str, stage: str, p: dict) -> dict:
    sysm = SYSTEM_SCREEN if stage == "screen" else SYSTEM_LABEL
    schema = SCREEN_SCHEMA if stage == "screen" else LABEL_SCHEMA
    user = f"CONTEXT BEFORE (for orientation only):\n{p['ctx']}\n\nPASSAGE:\n{p['text']}"
    t0 = time.time()
    r = httpx.post("http://localhost:11434/api/chat", timeout=600, json={
        "model": model, "stream": False, "think": False, "format": schema, "keep_alive": -1,
        "options": {"temperature": 0, "seed": 0, "num_ctx": 8192 if stage == "label" else 4096,
                    "num_predict": 64 if stage == "screen" else 400},
        "messages": [{"role": "system", "content": sysm}, {"role": "user", "content": user}]})
    j = r.json()
    dt = time.time() - t0
    try:
        out = json.loads(j["message"]["content"])
        ok = True
    except Exception:
        out, ok = {}, False
    q = out.get("evidence_quote", "")
    exact = bool(q) and norm(q) in norm(p["text"])
    return {"id": p["id"], "ok": ok, "out": out, "dt": dt, "exact": exact,
            "ptok": j.get("prompt_eval_count", 0), "gtok": j.get("eval_count", 0)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--stage", default="screen")
    ap.add_argument("--n", type=int, default=48)
    ap.add_argument("--par", type=int, default=4)
    a = ap.parse_args()
    ps = sample_passages(a.n)
    call(a.model, a.stage, ps[0])  # warm
    t0 = time.time()
    with cf.ThreadPoolExecutor(a.par) as ex:
        res = list(ex.map(lambda p: call(a.model, a.stage, p), ps))
    wall = time.time() - t0
    n = len(res)
    yes = sum(r["out"].get("has_obstacle") == "yes" for r in res)
    print(json.dumps({"model": a.model, "stage": a.stage, "n": n, "par": a.par,
                      "passages_per_hour": round(n / wall * 3600),
                      "schema_ok": sum(r["ok"] for r in res) / n,
                      "has_obstacle_yes": yes / n,
                      "exact_quote_rate_among_yes": (sum(r["exact"] for r in res if r["out"].get("has_obstacle") == "yes") / yes) if (a.stage == "label" and yes) else None,
                      "mean_prompt_tok": sum(r["ptok"] for r in res) / n,
                      "mean_gen_tok": sum(r["gtok"] for r in res) / n}))
    out = ROOT / f"data/work/bench_{a.model.replace(':', '_')}_{a.stage}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for r in res:
            f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main()
