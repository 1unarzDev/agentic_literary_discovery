"""Build registry/models.v1.json from docs/codebook.md + stage schemas + local Ollama digests.

usage: uv run python -I pipeline/make_registry.py [--version 2026-11-01.1]
Every change to codebook/prompt/schema/model changes the stage prompt_hash -> new pin.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
from bench_models import LABEL_SCHEMA as _LS  # noqa: E402  (keeps bench and production schema identical)

CODEBOOK = (ROOT / "docs/codebook.md").read_text(encoding="utf-8")
CB_VERSION = CODEBOOK.split("\n", 1)[0].split("Codebook ")[1].split(":")[0].strip()

LABEL_SCHEMA = {k: v for k, v in _LS.items()}
LABEL_SCHEMA["properties"] = {k: v for k, v in _LS["properties"].items()
                              if k not in ("character_goal", "impediment", "consequence_in_text")}
LABEL_SCHEMA["required"] = [k for k in _LS["required"] if k in LABEL_SCHEMA["properties"]]

LABEL_SYSTEM = ("You are a careful literary annotator of nineteenth- and early-twentieth-century fiction. "
                "Apply this codebook exactly.\n\n" + CODEBOOK +
                "\n\nJudge ONLY from the PASSAGE (context is for orientation). Do not use outside knowledge of the book. "
                "evidence_quote must be copied verbatim: 8-30 consecutive words from PASSAGE, unchanged. "
                "If has_obstacle is not 'yes', set domains to [], locus 'none', and other sub-fields 'none'. Return only JSON.")
LABEL_USER = "CONTEXT BEFORE (orientation only):\n{ctx_before}\n\nPASSAGE:\n{text}\n\nCONTEXT AFTER (orientation only):\n{ctx_after}"

WORKCHECK_SCHEMA = {"type": "object", "properties": {
    "form": {"type": "string", "enum": ["novel_or_novella", "story_collection", "single_short_story", "drama", "verse",
                                        "essay_or_nonfiction", "history_or_biography", "travel", "religious", "other"]},
    "is_translation": {"type": "boolean"},
    "is_juvenile": {"type": "boolean"},
    "is_abridged_or_excerpt": {"type": "boolean"},
    "setting_period": {"type": "string", "enum": ["contemporary_to_writing", "historical_past", "future", "timeless_or_fantasy", "unknown"]},
    "setting_place": {"type": "string", "enum": ["britain_ireland", "north_america", "continental_europe", "colonial_or_overseas", "at_sea", "mixed", "unknown"]},
    "confidence": {"type": "number"}},
    "required": ["form", "is_translation", "is_juvenile", "is_abridged_or_excerpt", "setting_period", "setting_place", "confidence"]}
WORKCHECK_SYSTEM = ("You classify books from their opening pages and catalog subjects. Judge the WORK as a whole. "
                    "'novel_or_novella' requires sustained narrative fiction. Prefaces may precede the story; look past them. "
                    "setting_period: is the story set roughly when it was written (contemporary) or in an earlier era? "
                    "Return only JSON.")
WORKCHECK_USER = "CATALOG SUBJECTS: {subjects}\n\nOPENING TEXT:\n{text}"

CLOZE_SCHEMA = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
CLOZE_SYSTEM = ("You have seen many books. The passage below comes from a published novel. One proper name has been "
                "replaced with [MASK]. Reply with the exact name that was masked (one word). Return only JSON.")
CLOZE_USER = "{text}"

STAGES = {
    "workcheck": dict(model_ref="qwen3.5:4b-q4_K_M", schema=WORKCHECK_SCHEMA, system_template=WORKCHECK_SYSTEM,
                      user_template=WORKCHECK_USER, num_ctx=4096, num_predict=96, evidence_field=None,
                      vram_gb_required=4.5, model_size_gb=3.3, kv_gb_per_slot=0.15, priority=10),
    "label": dict(model_ref="gemma4:12b-it-q4_K_M", schema=LABEL_SCHEMA, system_template=LABEL_SYSTEM,
                  user_template=LABEL_USER, num_ctx=8192, num_predict=400, evidence_field="evidence_quote",
                  vram_gb_required=10.5, model_size_gb=8.0, kv_gb_per_slot=0.5, priority=20),
    "cloze": dict(model_ref="gemma4:12b-it-q4_K_M", schema=CLOZE_SCHEMA, system_template=CLOZE_SYSTEM,
                  user_template=CLOZE_USER, num_ctx=2048, num_predict=16, evidence_field=None,
                  vram_gb_required=10.0, model_size_gb=8.0, kv_gb_per_slot=0.12, priority=30),
    "alt_label": dict(model_ref="qwen3.5:9b-q4_K_M", schema=LABEL_SCHEMA, system_template=LABEL_SYSTEM,
                      user_template=LABEL_USER, num_ctx=8192, num_predict=400, evidence_field="evidence_quote",
                      vram_gb_required=8.5, model_size_gb=6.6, kv_gb_per_slot=0.5, priority=40),
    "baseline_small": dict(model_ref="qwen3.5:4b-q4_K_M", schema=LABEL_SCHEMA, system_template=LABEL_SYSTEM,
                           user_template=LABEL_USER, num_ctx=8192, num_predict=400, evidence_field="evidence_quote",
                           vram_gb_required=5.0, model_size_gb=3.3, kv_gb_per_slot=0.35, priority=45),
    "embed": dict(model_ref="embeddinggemma:300m-bf16", schema=None, system_template="", user_template="{text}",
                  num_ctx=2048, num_predict=0, evidence_field=None, api="embed",
                  vram_gb_required=0.0, model_size_gb=0.6, kv_gb_per_slot=0.0, priority=50),
}
TIERS = {
    "cpu": {"min_vram_gb": 0, "stages": ["embed"], "num_parallel_hint": 2},
    "t6": {"min_vram_gb": 5.5, "stages": ["workcheck", "baseline_small", "embed"], "num_parallel_hint": 2},
    "t8": {"min_vram_gb": 7.5, "stages": ["workcheck", "baseline_small", "embed"], "num_parallel_hint": 4},
    "t12": {"min_vram_gb": 11.5, "stages": ["label", "workcheck", "cloze", "alt_label", "embed"], "num_parallel_hint": 2},
    "t16": {"min_vram_gb": 15.5, "stages": ["label", "workcheck", "cloze", "alt_label", "embed"], "num_parallel_hint": 6},
    "t24": {"min_vram_gb": 23.5, "stages": ["label", "workcheck", "cloze", "alt_label", "embed"], "num_parallel_hint": 8},
}


def digest(model: str) -> str:
    r = httpx.get("http://localhost:11434/api/tags", timeout=10).json()
    for m in r["models"]:
        if m["name"] == model or m["model"] == model:
            return "sha256:" + m["digest"]
    raise SystemExit(f"model {model} not pulled locally; run: ollama pull {model}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default=dt.datetime.now().strftime("%Y-%m-%d.%H%M"))
    a = ap.parse_args()
    stages = {}
    for name, s in STAGES.items():
        s = dict(s)
        s.update(model_digest=digest(s["model_ref"]), ollama_version_range=">=0.40.0,<1.0.0",
                 codebook_version=CB_VERSION, temperature=0, seed=0, think=False, unload_others=True)
        stages[name] = s
    reg = {"registry_version": a.version, "codebook_version": CB_VERSION, "tiers": TIERS, "stages": stages}
    out = ROOT / "registry/models.v1.json"
    out.write_text(json.dumps(reg, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", out, "version", a.version, "codebook", CB_VERSION)


if __name__ == "__main__":
    main()
