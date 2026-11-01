"""Build registry/models.v1.json from docs/codebook.md + stage schemas + local Ollama digests.

The label-type stages use the fenced codebook block in docs/codebook.md verbatim (human and model codebook are the same
text). docs/codebook_v0.5.md is kept to rebuild the v0 baseline prompt for A/B runs.

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
MODEL_CODEBOOK = CODEBOOK.split("```text\n", 1)[1].split("\n```", 1)[0]  # the block the model receives
CODEBOOK_V05 = (ROOT / "docs/codebook_v0.5.md").read_text(encoding="utf-8")  # v0 baseline (A/B) only

LABEL_SCHEMA = {k: v for k, v in _LS.items()}
LABEL_SCHEMA["properties"] = {k: v for k, v in _LS["properties"].items()
                              if k not in ("character_goal", "impediment", "consequence_in_text")}
LABEL_SCHEMA["required"] = [k for k in _LS["required"] if k in LABEL_SCHEMA["properties"]]

LABEL_SYSTEM = ("You are a careful literary annotator of nineteenth- and early-twentieth-century fiction. "
                "Apply this codebook exactly.\n\n" + CODEBOOK_V05 +
                "\n\nJudge ONLY from the PASSAGE (context is for orientation). Do not use outside knowledge of the book. "
                "evidence_quote must be copied verbatim: 8-30 consecutive words from PASSAGE, unchanged. "
                "If has_obstacle is not 'yes', set domains to [], locus 'none', and other sub-fields 'none'. Return only JSON.")
LABEL_USER = "CONTEXT BEFORE (orientation only):\n{ctx_before}\n\nPASSAGE:\n{text}\n\nCONTEXT AFTER (orientation only):\n{ctx_after}"

LABEL_SYSTEM_V0, LABEL_SCHEMA_V0 = LABEL_SYSTEM, LABEL_SCHEMA  # the v0 (codebook v0.5) production prompt, A/B baseline

# ---------------------------------------------------------------- A/B variants (docs/perf_label_ab.md)
# Lean output: has_obstacle first, no locus_reason, obstacle_summary <=10 words, evidence_quote 6-20 words, and the
# "no obstacle" record reduced to empty values (flat) or to has_obstacle + confidence (anyOf). Compact = the v0.5 rules
# in a shorter rendition. All system prompts are constants, so Ollama's per-slot prompt cache can reuse them.
_ENUM = lambda *v: {"type": "string", "enum": list(v)}  # noqa: E731
_LP = _LS["properties"]
LEAN_PROPS = {
    "has_obstacle": _LP["has_obstacle"],
    "domains": _LP["domains"],
    "locus": _LP["locus"],
    "failure_cause": _LP["failure_cause"],
    "message_valence": _LP["message_valence"],
    "technology_named": _LP["technology_named"],
    "night_function": _LP["night_function"],
    "resolution_hint": _LP["resolution_hint"],
    "obstacle_summary": {"type": "string"},
    "evidence_quote": {"type": "string"},
    "confidence": {"type": "number"},
}
LEAN_SCHEMA = {"type": "object", "properties": LEAN_PROPS, "required": list(LEAN_PROPS)}
LEAN_SCHEMA_ANYOF = {"anyOf": [
    {"type": "object", "properties": {**LEAN_PROPS, "has_obstacle": _ENUM("yes")}, "required": list(LEAN_PROPS)},
    {"type": "object", "properties": {"has_obstacle": _ENUM("no", "insufficient_context"), "confidence": {"type": "number"}},
     "required": ["has_obstacle", "confidence"]},
]}

_CB_CORE = """\
CODEBOOK v0.6-lean: plot obstacles (compact rendition of v0.5; same rules).

CORE QUESTION: in this passage, is something standing in the way of what a character wants, in a way that matters for what happens next?
has_obstacle is "yes" only if ALL three hold:
1. A character with a goal, explicit ("she longed to reach London") or clearly implied (escaping, marrying, learning a secret, saving someone).
2. Something impeding it: a thing, a person, a rule, a feeling, or a lack (of news, light, money).
3. Narrative consequence: the impediment is part of the action, not mere description. A storm as scenery does not count; a storm that keeps the doctor from arriving does.
NOT obstacles: a letter merely mentioned; a dark room described for atmosphere; a generic complaint ("times were hard"); a narrator's essayistic reflection with no character goal at stake.
"insufficient_context" when the passage is too fragmentary to tell; otherwise "no"."""
_CB_HARD = """\
DECISION RULES FOR HARD CASES
- Mention is not function: "He sealed the letter" is not an obstacle; "The letter never reached her, and she married another" is.
- Reported past obstacles count if they still shape the present action.
- Hypothetical obstacles ("if the post should fail...") count only if a character acts on the fear.
- Dialogue counts: a character explaining a barrier ("I cannot leave my father") is an obstacle.
- Comic obstacles count the same as serious ones.
- Judge ONLY from the PASSAGE (context is for orientation). No outside knowledge of the book."""
_CB_FIELDS = """\
domains: 1-2 codes answering "what kind of thing is in the way?"
- DISTANCE_TRAVEL: distance, slow or difficult journeys, missed coaches or trains, impassable roads
- COMMUNICATION_INFORMATION: messages failed, delayed, lost, intercepted, forged, unanswered or misread; secrets; ignorance of a key fact; mistaken identity
- DARKNESS_VISIBILITY: not being able to see: night, fog, lack of light, concealment by darkness
- ILLNESS_BODY_DEATH: sickness, injury, weakness, pregnancy, death or dying
- MONEY_PROPERTY_LAW: poverty, debt, inheritance and entail, wills, contracts, courts, police, legal status
- SOCIAL_RANK_CONVENTION: class, propriety, reputation, marriage rules, gender norms, family authority as a rule
- INTERPERSONAL_CONFLICT: a specific person actively opposing, deceiving, threatening or thwarting
- INNER_STATE: the character's own doubt, fear, pride, guilt, desire, conscience or indecision
- NATURE_WEATHER: storms, floods, snow, sea, wild terrain, animals
- OTHER: clearly an obstacle that fits none of the above
When several apply, pick the proximate one: the thing that, if removed, would let the character proceed. A villain who intercepts a letter is COMMUNICATION_INFORMATION (failure_cause intentional_withholding) plus INTERPERSONAL_CONFLICT.

locus: where the resistance comes from.
- material_external: physical world and infrastructure (distance, darkness, weather, illness, lost objects, technical failure)
- social_institutional: other people, rules, law, money, rank, convention, deliberate deception by others
- internal_psychological: the character's own mind
Default: DISTANCE, DARKNESS, NATURE, ILLNESS -> material_external; MONEY/LAW, SOCIAL_RANK, INTERPERSONAL -> social_institutional; INNER_STATE -> internal_psychological; COMMUNICATION by failure cause: infrastructure or accidental -> material_external, withholding or misinterpretation by others -> social_institutional, the character's own refusal to write or speak -> internal_psychological. Override the default whenever the passage says otherwise (illness that is clearly "nerves" may be internal).

failure_cause (only when a domain is COMMUNICATION_INFORMATION, else none):
- infrastructure: slow post, no telegraph office, distance, closed office, the post hasn't come
- accidental_loss: lost, misdelivered, overlooked, arrives at the wrong time
- intentional_withholding: withheld, intercepted, burned, forged, deliberately unanswered, secret kept
- misinterpretation: message misunderstood, ambiguous, mistaken identity
- success_resolution: communication removes an obstacle
message_valence (what a message present carries): catastrophic (death, illness, ruin, arrest, summons) | romantic | financial | practical | none.
technology_named: the communication, travel or light technology that is named AND plot-relevant, else none.
night_function: only if the passage happens at night or in darkness, else none.
resolution_hint: only if the passage shows it, else unknown.
obstacle_summary: at most 10 words, plain modern English, naming the obstacle generically, no character names (e.g. "lover's letter intercepted by jealous aunt").
evidence_quote: copy ONE exact sentence or clause from PASSAGE (never from the context) showing the obstacle, 6-20 consecutive words, verbatim. Do not paraphrase, fix spelling, or join separate sentences.
confidence: 0-1, how sure you are of has_obstacle and domains."""
# v0.5 section order (core, fields, hard-case rules last). The A/B "compact" variant had the hard cases before the fields.
COMPACT_CODEBOOK = _CB_CORE + "\n\n" + _CB_FIELDS + "\n\n" + _CB_HARD
COMPACT_CODEBOOK_A = _CB_CORE + "\n\n" + _CB_HARD.replace("DECISION RULES FOR HARD CASES", "HARD CASES") + "\n\n" + _CB_FIELDS


_LEAN_TAIL = ("If has_obstacle is not \"yes\": domains [], locus, failure_cause, message_valence, technology_named and "
              "night_function \"none\", resolution_hint \"unknown\", obstacle_summary \"\" and evidence_quote \"\". Return only JSON.")
_LEAN_TAIL_ANYOF = "If has_obstacle is not \"yes\", output only has_obstacle and confidence. Return only JSON."
_ROLE = "You are a careful literary annotator of nineteenth- and early-twentieth-century fiction. Apply this codebook exactly.\n\n"
LEAN_SYSTEM = _ROLE + COMPACT_CODEBOOK + "\n\n" + _LEAN_TAIL
LEAN_SYSTEM_ANYOF = _ROLE + COMPACT_CODEBOOK + "\n\n" + _LEAN_TAIL_ANYOF
LEAN_SYSTEM_A = _ROLE + COMPACT_CODEBOOK_A + "\n\n" + _LEAN_TAIL  # A/B record only
LEAN_SYSTEM_ANYOF_A = _ROLE + COMPACT_CODEBOOK_A + "\n\n" + _LEAN_TAIL_ANYOF
# Multi-passage batching (A/B only, see docs/perf_label_ab.md): one codebook prefill shared by K passages.
BATCH_SYSTEM = (LEAN_SYSTEM_A + "\n\nBATCH MODE: the user message holds several numbered passages, each with its own context. "
                "Label each passage independently, as if it were the only one: judge it only from its own PASSAGE, and copy its "
                "evidence_quote verbatim from that same PASSAGE. Return {\"labels\": [...]} with one object per passage, in order, "
                "with \"passage\" set to its number.")
BATCH_USER_ITEM = ("===== PASSAGE {n} =====\nCONTEXT BEFORE (orientation only):\n{ctx_before}\n\nPASSAGE {n}:\n{text}\n\n"
                   "CONTEXT AFTER (orientation only):\n{ctx_after}\n")


def batch_schema(k: int, item_schema: dict | None = None) -> dict:
    """{"labels": [K items]}; each item = the single-passage schema plus a leading "passage" number."""
    pas = {"passage": {"type": "integer", "enum": list(range(1, k + 1))}}
    def add(o: dict) -> dict:
        return {"type": "object", "properties": {**pas, **o["properties"]}, "required": ["passage", *o["required"]]}
    item_schema = item_schema or LEAN_SCHEMA
    item = {"anyOf": [add(b) for b in item_schema["anyOf"]]} if "anyOf" in item_schema else add(item_schema)
    return {"type": "object", "properties": {"labels": {"type": "array", "items": item, "minItems": k, "maxItems": k}},
            "required": ["labels"]}


# v0.5 codebook verbatim, lean output rules (isolates the output-side change)
LEANOUT_SYSTEM = (_ROLE + CODEBOOK_V05 + "\n\nJudge ONLY from the PASSAGE (context is for orientation). Do not use outside knowledge of the book. "
                  "Output overrides: no locus_reason; obstacle_summary at most 10 words; evidence_quote 6-20 consecutive words "
                  "copied verbatim from PASSAGE (never from the context). " + _LEAN_TAIL)
LEANOUT_SYSTEM_ANYOF = LEANOUT_SYSTEM.replace(_LEAN_TAIL, _LEAN_TAIL_ANYOF)

# ---------------------------------------------------------------- v0.9-lean = QA pass-2 edits E1-E6 (docs/qa/label_pass_2.md)
# condensed into the compact codebook, plus the locus changes from the pilot analysis: locus is judged first as the
# proximate source, with a required short locus_reason; the domain->locus table is a typical pattern, not a rule.
V09_CB_VERSION = "v0.9-lean"
V09_CODEBOOK_R1 = """\
CODEBOOK v0.9-lean: plot obstacles.

CORE QUESTION: in this passage, is something standing in the way of what a character wants, in a way that matters for what happens next?
has_obstacle is "yes" only if ALL three hold:
1. A character with a goal, explicit ("she longed to reach London") or clearly implied (escaping, marrying, learning a secret, saving someone).
2. Something impeding it: a thing, a person, a rule, a feeling, or a lack (of news, light, money).
3. Narrative consequence: the impediment is part of the action, not mere description. A storm as scenery does not count; a storm that keeps the doctor from arriving does.
THREE-PART TEST before answering yes: (a) WHO wants WHAT; (b) WHAT, inside the PASSAGE, stops, delays or endangers it; (c) WHERE the passage shows it changing what the character can do or what happens. If you cannot point to (b) and (c) inside the PASSAGE, answer "no".
NOT obstacles: a letter merely mentioned; a dark room described for atmosphere; a generic complaint ("times were hard"); a narrator's essayistic reflection with no character goal at stake; mild discomfort, shyness, fatigue or nervousness the character goes ahead despite; banter, teasing or flirtation; a character merely wondering or speculating; procedural description of work, hunting or travel in which nothing goes wrong; a goal achieved with no impediment left; an obstacle that appears only in CONTEXT BEFORE/AFTER.
"insufficient_context" when the passage is too fragmentary to tell; otherwise "no".

locus: the PROXIMATE SOURCE of the resistance, i.e. the thing that, if removed, would let the character proceed. Judge it from the passage first.
- material_external: physical world and infrastructure (distance, darkness, weather, terrain, animals, illness, lost objects, technical failure)
- social_institutional: other people, rules, law, money, rank, convention, deliberate deception or violence by others
- internal_psychological: the blocked character's own mind (pride, fear, guilt, conscience, indecision)
Typical pattern only, not a rule: DISTANCE, DARKNESS, NATURE, ILLNESS often material; MONEY/LAW, SOCIAL_RANK, INTERPERSONAL often social; INNER_STATE internal; COMMUNICATION: infrastructure or accident material, withholding or misreading by others social, the character's own refusal to write or speak internal. Follow the source, not the domain: death or injury inflicted by people is social; animals and terrain are material; the character's own pride, fear or conscience is internal even under SOCIAL_RANK_CONVENTION; illness that is clearly "nerves" may be internal.
locus_reason: at most 6 words naming that proximate source (e.g. "her own pride", "aunt intercepts the letter", "flooded ford").

domains: 1-2 codes answering "what kind of thing is in the way?"; if several apply, the proximate one first.
- DISTANCE_TRAVEL: distance, slow or difficult journeys, missed coaches or trains, impassable roads
- COMMUNICATION_INFORMATION: messages failed, delayed, lost, intercepted, forged, unanswered or misread; secrets; ignorance of a key fact; mistaken identity
- DARKNESS_VISIBILITY: not being able to see (night, fog, lack of light, concealment by darkness or terrain); use it whenever not-seeing is what stops the character, even if weather or terrain causes it
- ILLNESS_BODY_DEATH: sickness, injury, weakness, pregnancy, death or dying
- MONEY_PROPERTY_LAW: poverty, debt, inheritance and entail, wills, contracts, courts, police, legal status
- SOCIAL_RANK_CONVENTION: class, propriety, reputation, marriage rules, gender norms, family authority as a RULE that would stop anyone in that position. A particular person's wishes, dislike, schemes or commands are INTERPERSONAL_CONFLICT; a party, dress or etiquette that is merely present is not an obstacle
- INTERPERSONAL_CONFLICT: a specific person actively opposing, deceiving, threatening or thwarting
- INNER_STATE: the character's own doubt, fear, pride, guilt, desire, conscience or indecision
- NATURE_WEATHER: storms, floods, snow, sea, wild terrain, animals
- OTHER: clearly an obstacle that fits none of the above
A villain who intercepts a letter is COMMUNICATION_INFORMATION (failure_cause intentional_withholding) plus INTERPERSONAL_CONFLICT.

failure_cause and message_valence are "none" unless COMMUNICATION_INFORMATION is in domains.
- infrastructure: slow, long or costly post or telegraph, no telegraph office, distance, closed office, the post hasn't come
- accidental_loss: lost, misdelivered, overlooked, arrives at the wrong time; a secret forgotten or lost over time
- intentional_withholding: someone deliberately keeps, intercepts, burns, forges or leaves unanswered the message or fact
- misinterpretation: message misunderstood, ambiguous, mistaken identity
- success_resolution: communication removes an obstacle
message_valence (what the message carries): catastrophic (death, illness, ruin, arrest, summons) | romantic | financial | practical | none.
technology_named: the communication, travel or light technology that is named AND plot-relevant, else none.
night_function: "none" unless the scene is at night or in darkness. concealment = someone hides or moves unseen thanks to the dark; danger = the dark exposes someone to harm or terror; otherwise intimacy, labor or leisure.
resolution_hint: only if the passage shows it, else unknown.
obstacle_summary: at most 10 words, plain modern English, naming the obstacle generically, no character names (e.g. "lover's letter intercepted by jealous aunt").
evidence_quote: 6-20 consecutive words copied verbatim from INSIDE the PASSAGE START/END markers that show the obstacle. Never quote the context; if the key sentence runs past a PASSAGE boundary, copy only the part inside. No "...", no dropped words, no joined sentences or speakers, no spelling fixes.
confidence: 0-1, how sure you are of has_obstacle and domains.

DECISION RULES FOR HARD CASES
- Mention is not function: "He sealed the letter" is not an obstacle; "The letter never reached her, and she married another" is.
- Reported past obstacles count if they still shape the present action.
- Hypothetical obstacles ("if the post should fail...") count only if a character acts on the fear.
- Dialogue counts: a character explaining a barrier ("I cannot leave my father") is an obstacle.
- Comic obstacles count the same as serious ones. Comic, epistolary and dialect passages follow the same three-part test; a letter-writer's reflections are not an obstacle unless the letter reports something blocking a goal.
- Judge ONLY from the PASSAGE (context is for orientation). No outside knowledge of the book.
EXAMPLES: "Certainly they are not of such strength that I do not gladly seize upon the favor thus extended, and count myself honored and happy." The speaker is shy of meeting a queen but goes ahead gladly -> no. "And Bart, deciding that his sister's whims had already imposed far too many restrictions upon both his own activities and Carver's, carefully refrained from delivering the message." -> yes, locus social_institutional, COMMUNICATION_INFORMATION, intentional_withholding."""
# r2 (after the first QA-set run): the "her own pride" example pulled bodily states to internal; quotes straddled edges.
V09_CODEBOOK = (V09_CODEBOOK_R1
    .replace('- internal_psychological: the blocked character\'s own mind (pride, fear, guilt, conscience, indecision)',
             '- internal_psychological: only when the blocked character\'s own feeling, will or judgement is the barrier (pride, fear, '
             'guilt, conscience, indecision). The body is not the mind: sickness, injury, sleep or exhaustion is material_external')
    .replace('locus_reason: at most 6 words naming that proximate source (e.g. "her own pride", "aunt intercepts the letter", "flooded ford").',
             'locus_reason: at most 6 words naming that proximate source (e.g. "flooded ford", "father forbids the match", '
             '"fever keeps him abed", "her pride forbids asking").')
    .replace('evidence_quote: 6-20 consecutive words copied verbatim from INSIDE the PASSAGE START/END markers that show the obstacle.',
             'evidence_quote: 6-20 consecutive words copied verbatim from INSIDE the PASSAGE START/END markers that show the obstacle; '
             'prefer a sentence well inside the PASSAGE, away from its first and last lines.'))
assert V09_CODEBOOK.count("The body is not the mind") == 1 and V09_CODEBOOK.count("fever keeps him abed") == 1 and V09_CODEBOOK.count("well inside") == 1
V09_SYSTEM_R2 = _ROLE + V09_CODEBOOK + "\n\n" + _LEAN_TAIL_ANYOF  # A/B "v09lean_r2" (measured)
V09_SYSTEM_R1 = _ROLE + V09_CODEBOOK_R1 + "\n\n" + _LEAN_TAIL_ANYOF  # A/B record only
# Production v0.9 = the docs/codebook.md block, which is r2 with the version line "v0.9" instead of "v0.9-lean".
assert MODEL_CODEBOOK == V09_CODEBOOK.replace("CODEBOOK v0.9-lean: plot obstacles.", "CODEBOOK v0.9: plot obstacles.", 1), \
    "docs/codebook.md block differs from the measured v0.9-lean r2 text: re-run the A/B or update V09_CODEBOOK_R1/r2"
V09_SYSTEM = _ROLE + MODEL_CODEBOOK + "\n\n" + _LEAN_TAIL_ANYOF
V09_USER = ("CONTEXT BEFORE (orientation only; never quote it):\n{ctx_before}\n\n"
            "=== PASSAGE START (judge and quote ONLY this) ===\n{text}\n=== PASSAGE END ===\n\n"
            "CONTEXT AFTER (orientation only; never quote it):\n{ctx_after}")
V09_PROPS = {
    "has_obstacle": _LP["has_obstacle"],
    "locus": {"type": "string", "enum": ["material_external", "social_institutional", "internal_psychological"]},
    "locus_reason": {"type": "string", "minLength": 1},
    "domains": {**_LP["domains"], "minItems": 1},
    **{k: LEAN_PROPS[k] for k in ("failure_cause", "message_valence", "technology_named", "night_function",
                                  "resolution_hint", "obstacle_summary", "evidence_quote", "confidence")},
}
V09_BATCH_SYSTEM = (V09_SYSTEM_R1 + "\n\nBATCH MODE: the user message holds several numbered passages, each with its own context. "
                    "Label each passage independently, as if it were the only one, and copy its evidence_quote from that same "
                    "PASSAGE. Return {\"labels\": [...]} with one object per passage, in order, with \"passage\" set to its number.")
V09_BATCH_USER_ITEM = ("##### ITEM {n} #####\nCONTEXT BEFORE (orientation only; never quote it):\n{ctx_before}\n\n"
                       "=== PASSAGE {n} START (judge and quote ONLY this) ===\n{text}\n=== PASSAGE {n} END ===\n\n"
                       "CONTEXT AFTER (orientation only; never quote it):\n{ctx_after}\n")
V09_SCHEMA = {"anyOf": [
    {"type": "object", "properties": {**V09_PROPS, "has_obstacle": _ENUM("yes")}, "required": list(V09_PROPS)},
    {"type": "object", "properties": {"has_obstacle": _ENUM("no", "insufficient_context"), "confidence": {"type": "number"}},
     "required": ["has_obstacle", "confidence"]},
]}

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
    # v0.9 (docs/perf_label_ab.md): docs/codebook.md block + lean anyOf output (locus first, locus_reason required).
    # num_ctx 4096 lets Ollama reuse the system-prompt prefix (SWA checkpoint), which it cannot at 8192.
    "label": dict(model_ref="gemma4:12b-it-q4_K_M", schema=V09_SCHEMA, system_template=V09_SYSTEM,
                  user_template=V09_USER, num_ctx=4096, num_predict=200, evidence_field="evidence_quote",
                  vram_gb_required=10.0, model_size_gb=8.0, kv_gb_per_slot=0.2, priority=20),  # measured: RTX 3060, docs/perf_label_ab.md
    # cloze at 4096 too: one num_ctx per model, so label <-> cloze switches do not force a reload
    "cloze": dict(model_ref="gemma4:12b-it-q4_K_M", schema=CLOZE_SCHEMA, system_template=CLOZE_SYSTEM,
                  user_template=CLOZE_USER, num_ctx=4096, num_predict=16, evidence_field=None,
                  vram_gb_required=10.0, model_size_gb=8.0, kv_gb_per_slot=0.12, priority=30),
    "alt_label": dict(model_ref="qwen3.5:9b-q4_K_M", schema=V09_SCHEMA, system_template=V09_SYSTEM,
                      user_template=V09_USER, num_ctx=4096, num_predict=200, evidence_field="evidence_quote",
                      vram_gb_required=8.5, model_size_gb=6.6, kv_gb_per_slot=0.5, priority=40),
    "baseline_small": dict(model_ref="qwen3.5:4b-q4_K_M", schema=V09_SCHEMA, system_template=V09_SYSTEM,
                           user_template=V09_USER, num_ctx=4096, num_predict=200, evidence_field="evidence_quote",
                           vram_gb_required=5.0, model_size_gb=3.3, kv_gb_per_slot=0.35, priority=45),
    "embed": dict(model_ref="embeddinggemma:300m-bf16", schema=None, system_template="", user_template="{text}",
                  num_ctx=2048, num_predict=0, evidence_field=None, api="embed",
                  vram_gb_required=0.0, model_size_gb=0.6, kv_gb_per_slot=0.0, priority=50),
}
TIERS = {
    "cpu": {"min_vram_gb": 0, "stages": ["embed"], "num_parallel_hint": 2},
    "t6": {"min_vram_gb": 5.5, "stages": ["workcheck", "baseline_small", "embed"], "num_parallel_hint": 2},
    "t8": {"min_vram_gb": 7.5, "stages": ["workcheck", "baseline_small", "embed"], "num_parallel_hint": 4},
    # kv_cache_type_hint -> OLLAMA_KV_CACHE_TYPE (needs flash attention). q8_0 halves the KV cache: +10-20% on the 3060 at
    # NP=4 (10.6 of 12 GB). NP=6 with q8_0 fits but sits at 11.3 GB for +0-7%, so t12 stays at 4 (docs/perf_label_ab.md).
    "t12": {"min_vram_gb": 11.5, "stages": ["label", "workcheck", "cloze", "alt_label", "embed"], "num_parallel_hint": 4,
            "kv_cache_type_hint": "q8_0"},
    "t16": {"min_vram_gb": 15.5, "stages": ["label", "workcheck", "cloze", "alt_label", "embed"], "num_parallel_hint": 6,
            "kv_cache_type_hint": "q8_0"},
    "t24": {"min_vram_gb": 23.5, "stages": ["label", "workcheck", "cloze", "alt_label", "embed"], "num_parallel_hint": 8,
            "kv_cache_type_hint": "q8_0"},
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
                 codebook_version=s.get("codebook_version", CB_VERSION), temperature=0, seed=0, think=False, unload_others=True)
        stages[name] = s
    reg = {"registry_version": a.version, "codebook_version": CB_VERSION, "tiers": TIERS, "stages": stages}
    out = ROOT / "registry/models.v1.json"
    out.write_text(json.dumps(reg, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", out, "version", a.version, "codebook", CB_VERSION)


if __name__ == "__main__":
    main()
