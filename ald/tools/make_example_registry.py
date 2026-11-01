"""Generate registry/models.v1.example.json (placeholder models; finalize on Day 1)."""
import json
import sys
from pathlib import Path

DOMAINS = ["DISTANCE_TRAVEL", "COMMUNICATION_INFORMATION", "DARKNESS_VISIBILITY", "ILLNESS_BODY_DEATH",
           "MONEY_PROPERTY_LAW", "SOCIAL_RANK_CONVENTION", "INTERPERSONAL_CONFLICT", "INNER_STATE",
           "NATURE_WEATHER", "OTHER"]
LOCUS = ["material_external", "social_institutional", "internal_psychological"]
FAILURE = ["infrastructure", "accidental_loss", "intentional_withholding", "misinterpretation",
           "success_as_resolution", "not_applicable"]
TECH = ["letter", "telegram", "telephone", "railway", "coach", "steamship", "gas", "electric", "candle", "none"]
VALENCE = ["catastrophic", "practical", "romantic", "financial", "not_applicable"]
NIGHT = ["danger", "concealment", "intimacy", "labor", "leisure", "none"]
RESOLUTION = ["overcome_by_technology", "by_person", "by_chance", "unresolved"]
HAS = ["yes", "no", "insufficient_context"]

conf = {"type": "number", "minimum": 0, "maximum": 1}

obstacle = {
    "type": "object",
    "properties": {
        "domain": {"type": "string", "enum": DOMAINS},
        "locus": {"type": "string", "enum": LOCUS},
        "failure_cause": {"type": "string", "enum": FAILURE},
        "technology_named": {"type": "string", "enum": TECH},
        "message_valence": {"type": "string", "enum": VALENCE},
        "night_function": {"type": "string", "enum": NIGHT},
        "resolution_hint": {"type": "string", "enum": RESOLUTION},
        "obstacle_summary": {"type": "string", "maxLength": 120},
        "evidence_quote": {"type": "string", "maxLength": 400},
        "confidence": conf,
    },
    "required": ["domain", "locus", "failure_cause", "technology_named", "message_valence", "night_function",
                 "resolution_hint", "obstacle_summary", "evidence_quote", "confidence"],
    "additionalProperties": False,
}

label_schema = {
    "type": "object",
    "properties": {
        "has_obstacle": {"type": "string", "enum": HAS},
        "obstacles": {"type": "array", "items": obstacle, "maxItems": 2},
        "confidence": conf,
    },
    "required": ["has_obstacle", "obstacles", "confidence"],
    "additionalProperties": False,
}

adjudicate_schema = json.loads(json.dumps(label_schema))
adjudicate_schema["properties"]["rationale"] = {"type": "string", "maxLength": 600}
adjudicate_schema["required"].append("rationale")

CODEBOOK = """CODEBOOK v0.9-draft — PLOT OBSTACLES IN NINETEENTH-CENTURY FICTION

A PLOT OBSTACLE is something in the passage that blocks, delays or endangers a character's goal AND plausibly affects what happens next. Atmosphere, description or a mere mention does not count. Judge only from the passage (context before/after is for orientation; the evidence must come from the PASSAGE).

has_obstacle:
- yes: at least one obstacle as defined above is present in the passage.
- no: no character goal is blocked, delayed or endangered.
- insufficient_context: the passage is too fragmentary (front matter, a list, verse without narrative) to judge.

DOMAINS (pick the mechanism that does the blocking, not the topic of the scene):
- DISTANCE_TRAVEL: distance, journeys, missed or slow transport, impassable roads.
- COMMUNICATION_INFORMATION: letters, messages, news, secrets, identity, misunderstandings of information.
- DARKNESS_VISIBILITY: night, darkness, fog, lack of light, inability to see or be seen.
- ILLNESS_BODY_DEATH: illness, injury, physical weakness, death.
- MONEY_PROPERTY_LAW: money, debt, inheritance, property, contracts, courts, police.
- SOCIAL_RANK_CONVENTION: class, propriety, reputation, marriage and gender norms.
- INTERPERSONAL_CONFLICT: a person actively opposes, threatens or thwarts another.
- INNER_STATE: doubt, fear, desire, conscience, pride, shame inside the character.
- NATURE_WEATHER: storms, floods, snow, terrain, animals.
- OTHER: a real obstacle that fits none of the above.

LOCUS (where the obstacle lives): material_external (things, distance, bodies, weather, darkness), social_institutional (law, money systems, rank, convention), internal_psychological (the character's own mind).

SUB-FIELDS (use not_applicable / none when the domain does not call for them):
- failure_cause (COMMUNICATION_INFORMATION only): infrastructure (the post/wire/system fails), accidental_loss (a letter lost or misdelivered), intentional_withholding (someone hides or suppresses information), misinterpretation (the message arrives but is misread), success_as_resolution (communication succeeds and removes the obstacle).
- technology_named: the single most relevant technology named in the passage, else none.
- message_valence (communication only): catastrophic, practical, romantic, financial.
- night_function (DARKNESS_VISIBILITY, or any obstacle set at night): danger, concealment, intimacy, labor, leisure, else none.
- resolution_hint: overcome_by_technology, by_person, by_chance, unresolved (default when the passage does not say).
- obstacle_summary: at most 15 words, plain words, no names.
- evidence_quote: copy a short span (5-40 words) EXACTLY from the PASSAGE, character for character, including its punctuation. Do not paraphrase, do not join distant sentences, do not add ellipses.
- confidence: 0-1, your probability that the label is right.

At most 2 obstacles per passage, the most plot-relevant first. If has_obstacle is no or insufficient_context, return an empty obstacles list.
Reply with a single JSON object that matches the schema and nothing else."""

FEW_SHOT_LABEL = """EXAMPLES

PASSAGE: The letter which should have told her of his return lay three days in the wrong office at Bath, and when at last it came the coach had gone without her.
OUTPUT: {"has_obstacle":"yes","obstacles":[{"domain":"COMMUNICATION_INFORMATION","locus":"material_external","failure_cause":"accidental_loss","technology_named":"letter","message_valence":"romantic","night_function":"none","resolution_hint":"unresolved","obstacle_summary":"misdirected letter delays news of a lover's return","evidence_quote":"lay three days in the wrong office at Bath","confidence":0.86}],"confidence":0.86}

PASSAGE: The drawing-room was hung with yellow silk, and the evening passed in cards and music until the candles burned low.
OUTPUT: {"has_obstacle":"no","obstacles":[],"confidence":0.9}

PASSAGE: He had the money in his pocket and the door before him; only his own pride, which would not let him knock, kept him in the street.
OUTPUT: {"has_obstacle":"yes","obstacles":[{"domain":"INNER_STATE","locus":"internal_psychological","failure_cause":"not_applicable","technology_named":"none","message_valence":"not_applicable","night_function":"none","resolution_hint":"unresolved","obstacle_summary":"pride stops a man from asking for help","evidence_quote":"only his own pride, which would not let him knock, kept him in the street","confidence":0.8}],"confidence":0.8}"""

LABEL_SYSTEM = CODEBOOK + "\n\n" + FEW_SHOT_LABEL
ADJ_SYSTEM = (CODEBOOK + "\n\nTASK (ADJUDICATE): you are the senior annotator. Label the passage from scratch "
              "with the full schema and add a rationale (at most 80 words) that cites the passage.\n\n" + FEW_SHOT_LABEL)

USER = ("CONTEXT BEFORE (orientation only):\n{ctx_before}\n\nCONTEXT AFTER (orientation only):\n{ctx_after}\n\n"
        "PASSAGE (label this):\n{text}")

RETRY = ("Your previous reply was not valid for the required schema ({error}). Reply again with ONLY one JSON "
         "object that matches the schema.")

WORKCHECK_SCHEMA = {
    "type": "object",
    "properties": {
        "is_fiction": {"type": "string", "enum": ["yes", "no", "unsure"]},
        "is_translation": {"type": "string", "enum": ["yes", "no", "unsure"]},
        "is_juvenile": {"type": "string", "enum": ["yes", "no", "unsure"]},
        "setting_period": {"type": "string", "enum": ["contemporary", "historical", "future", "mixed", "unclear"]},
        "confidence": conf,
    },
    "required": ["is_fiction", "is_translation", "is_juvenile", "setting_period", "confidence"],
    "additionalProperties": False,
}

WORKCHECK_SYSTEM = """WORK CHECK. You see the opening (~1,500 words) of a Project Gutenberg text. Decide:
- is_fiction: yes if it is a novel, novella or short-story collection; no for history, essays, sermons, travel, drama, verse collections, periodicals; unsure if you cannot tell.
- is_translation: yes if the text says it is translated, or names a translator, or is plainly a foreign work in English dress.
- is_juvenile: yes if it is written for children (school stories, fairy tales, primers, boys'/girls' adventure series).
- setting_period: contemporary (set at about the time it was written), historical (set at least ~30 years before it was written), future, mixed, or unclear.
- confidence: 0-1.
Ignore the Project Gutenberg licence header. Reply with a single JSON object matching the schema and nothing else."""

CLOZE_SCHEMA = {"type": "object", "properties": {"name": {"type": "string", "maxLength": 60}},
                "required": ["name"], "additionalProperties": False}
CLOZE_SYSTEM = ("NAME CLOZE. The passage comes from a published novel. One character's proper name has been "
                "replaced by [MASK]. Reply with the single most likely name, as a JSON object {\"name\": \"...\"}. "
                "Reply with one name even if you are unsure.")

USER_WORK = "OPENING OF THE TEXT:\n{text}"
USER_CLOZE = "PASSAGE:\n{text}"


def stage(model_ref, size, vram, kv, num_ctx, num_predict, system, schema, codebook_version, user=USER,
          evidence_field="evidence_quote", digest_tag="0"):
    return {
        "kind": "chat",
        "model_ref": model_ref,
        # Digests are filled in from `ollama show`/`/api/tags` at freeze time; never hard-coded in code.
        "model_digest": "sha256:" + digest_tag * 64,
        "model_size_gb": size,
        "vram_gb_required": vram,
        "kv_gb_per_slot": kv,
        "ollama_version_range": ">=0.12.0,<1.0.0",
        "codebook_version": codebook_version,
        "num_ctx": num_ctx,
        "num_predict": num_predict,
        "temperature": 0,
        "seed": 0,
        "think": False,
        "system_template": system,
        "user_template": user,
        "retry_template": RETRY,
        "schema": schema,
        "evidence_field": evidence_field,
    }

reg = {
    "$comment": ("EXAMPLE ONLY: digests are placeholders (all-same-hex); the real registry/models.v1.json is "
                 "generated at freeze time. min_vram_gb thresholds sit ~0.5 GB under the nominal card size "
                 "because drivers report slightly less (a 16 GB card shows 15.99 GiB)."),
    "registry_version": "2026-10-31.example.2",
    "unload_others": True,
    # Coordinator-compatible tier table: the coordinator limits leases to
    # tiers[<tier>].stages; the client picks the tier by min_vram_gb.
    "tiers": {
        "cpu": {"min_vram_gb": 0, "num_parallel_hint": 1, "stages": ["embed"]},
        "t8": {"min_vram_gb": 7.5, "num_parallel_hint": 2, "stages": ["workcheck"]},
        "t16": {"min_vram_gb": 15.5, "num_parallel_hint": 4, "stages": ["label", "alt_label", "cloze", "workcheck"]},
        "t24": {"min_vram_gb": 23.5, "num_parallel_hint": 4,
                "stages": ["adjudicate", "label", "alt_label", "cloze", "workcheck", "embed"]},
    },
    "stages": {
        "workcheck": stage("qwen3.5:4b-q4_K_M", 3.2, 4.5, 0.25, 4096, 96, WORKCHECK_SYSTEM, WORKCHECK_SCHEMA,
                           "workcheck-0.1", user=USER_WORK, evidence_field=None, digest_tag="1"),
        "label": stage("gemma4:12b-it-q4_K_M", 7.6, 10.0, 0.5, 6144, 512, LABEL_SYSTEM, label_schema,
                       "0.9-draft", digest_tag="2"),
        "alt_label": stage("qwen3.5:9b-q4_K_M", 6.2, 8.5, 0.4, 6144, 512, LABEL_SYSTEM, label_schema,
                           "0.9-draft", digest_tag="3"),
        "cloze": stage("gemma4:12b-it-q4_K_M", 7.6, 10.0, 0.3, 2048, 24, CLOZE_SYSTEM, CLOZE_SCHEMA,
                       "cloze-0.1", user=USER_CLOZE, evidence_field=None, digest_tag="2"),
        "adjudicate": stage("qwen3.8:27b-q4_K_M", 17.0, 21.0, 0.8, 8192, 768, ADJ_SYSTEM, adjudicate_schema,
                            "0.9-draft", digest_tag="4"),
        "embed": {
            "kind": "embed",
            "model_ref": "embeddinggemma:300m-bf16",
            "model_digest": "sha256:" + "5" * 64,
            "model_size_gb": 0.6,
            "vram_gb_required": 1.0,
            "kv_gb_per_slot": 0.05,
            "ollama_version_range": ">=0.12.0,<1.0.0",
            "codebook_version": "embed-0.1",
            "num_ctx": 2048,
            "user_template": "{text}",
            "evidence_field": None,
        },
    },
}

if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out}")
