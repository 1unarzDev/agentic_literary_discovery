import copy
import hashlib
import json
from pathlib import Path

import pytest

from ald.registry import (
    Registry, RegistryError, Stage, bare_digest, canonical_json, compute_pin_hash, digests_match,
    render_template, version_in_range, version_lt,
)

RAW = {
    "model_ref": "m:1", "model_digest": "sha256:" + "ab" * 32, "ollama_version_range": ">=0.12.0",
    "codebook_version": "1.0", "num_ctx": 4096, "num_predict": 64, "think": False,
    "system_template": "SYS", "user_template": "{{text}}", "retry_template": "R {error}",
    "schema": {"type": "object", "properties": {"a": {"type": "string"}}},
}

GOLDEN_PROMPT = "024dd744a4306eeb3d3614b303d97a62dc66acc2b61f1f4a085713c7eafd369c"
GOLDEN_PIN = "b70d04f818f5bbe3f35861d7f44d3d903dedca8549decf4db48224581505fdad"


def test_prompt_hash_golden():
    """Changing this hash invalidates every pin in the fleet: only on purpose."""
    assert Stage("screen", RAW).prompt_hash() == GOLDEN_PROMPT
    assert Stage("screen", RAW).pin_hash() == GOLDEN_PIN


def test_prompt_hash_definition_independent_reimplementation():
    doc = {"template": {"system": "SYS", "user": "{{text}}", "retry": "R {error}"}, "codebook_version": "1.0",
           "schema": RAW["schema"],
           "options": {"temperature": 0, "seed": 0, "num_ctx": 4096, "num_predict": 64, "think": False}}
    ph = hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                        .encode()).hexdigest()
    assert ph == GOLDEN_PROMPT
    assert hashlib.sha256((ph + "ab" * 32 + "screen").encode()).hexdigest() == GOLDEN_PIN


def test_hash_independent_of_key_order():
    shuffled = dict(reversed(list(RAW.items())))
    shuffled["schema"] = {"properties": {"a": {"type": "string"}}, "type": "object"}
    assert Stage("screen", shuffled).prompt_hash() == GOLDEN_PROMPT


def test_digest_prefix_does_not_matter():
    a = dict(RAW, model_digest="ab" * 32)
    assert Stage("screen", a).pin_hash() == GOLDEN_PIN


@pytest.mark.parametrize("field,value", [
    ("system_template", "SYS2"), ("user_template", "{{text}} "), ("retry_template", "x"),
    ("codebook_version", "1.1"), ("num_ctx", 8192), ("num_predict", 65), ("think", None), ("temperature", 0.1),
    ("seed", 1), ("schema", {"type": "object"}),
])
def test_every_component_changes_prompt_hash(field, value):
    assert Stage("screen", dict(RAW, **{field: value})).prompt_hash() != GOLDEN_PROMPT


def test_pin_depends_on_digest_and_stage():
    s = Stage("screen", RAW)
    assert s.pin_hash("cd" * 32) != GOLDEN_PIN
    assert Stage("label", RAW).pin_hash() != GOLDEN_PIN
    # Fields outside the pin (model_ref, sizes) do not change it.
    assert Stage("screen", dict(RAW, model_ref="other:2", model_size_gb=3)).pin_hash() == GOLDEN_PIN


def test_canonical_json_unicode():
    assert canonical_json({"b": "—", "a": 1}) == '{"a":1,"b":"—"}'.encode("utf-8")


def test_pin_object(registry_raw):
    reg = Registry.from_dict(registry_raw)
    po = reg.stages["label"].pin_object()
    assert set(po) == {"pin_hash", "stage", "model_ref", "model_digest", "prompt_hash", "schema_hash", "options"}
    assert po["pin_hash"] == compute_pin_hash(po["prompt_hash"], po["model_digest"], "label")


def test_example_registry_file_validates():
    root = Path(__file__).resolve().parents[2]
    p = root / "registry" / "models.v1.example.json"
    if not p.exists():
        pytest.skip("repo registry not present")
    reg = Registry.load(p)
    assert set(reg.stages) == {"workcheck", "label", "alt_label", "cloze", "adjudicate", "embed"}
    assert reg.stages["label"].schema["properties"]["has_obstacle"]["enum"] == ["yes", "no", "insufficient_context"]
    assert reg.stages["embed"].kind == "embed" and reg.stages["embed"].evidence_keys == []
    assert reg.stages["workcheck"].evidence_keys == [] and reg.stages["cloze"].evidence_keys == []
    assert reg.stages["label"].evidence_keys == ["evidence_quote"]
    # alt_label differs from label only by model: same prompt hash, different pin.
    assert reg.stages["alt_label"].prompt_hash() == reg.stages["label"].prompt_hash()
    assert reg.stages["alt_label"].pin_hash() != reg.stages["label"].pin_hash()
    assert reg.unload_others is True and reg.num_parallel_hint("t16") == 4
    lab = reg.stages["label"].schema["properties"]["obstacles"]["items"]["properties"]
    for f in ("domain", "locus", "failure_cause", "night_function", "technology_named", "message_valence",
              "resolution_hint", "obstacle_summary", "evidence_quote", "confidence"):
        assert f in lab
    # The bundled copy matches the repo copy.
    from importlib import resources
    bundled = json.loads(resources.files("ald.data").joinpath("models.v1.example.json").read_text("utf-8"))
    assert bundled == json.loads(p.read_text("utf-8"))


def test_static_system_prompt_has_no_passage_placeholders(registry_raw):
    import re
    for st in Registry.from_dict(registry_raw).stages.values():
        # static prefix -> KV cache reuse (literal JSON braces in few-shot examples are fine)
        assert not re.search(r"\{\{?\s*(text|passage|ctx_before|ctx_after)\s*\}?\}", st.system_template)
        assert st.user_template.rstrip().endswith("{text}")  # passage LAST


def test_production_registry_validates_if_present():
    root = Path(__file__).resolve().parents[2]
    p = root / "registry" / "models.v1.json"
    if not p.exists():
        pytest.skip("no production registry yet")
    from ald.registry import compute_pin
    reg = Registry.load(p)
    for name, st in reg.stages.items():
        assert compute_pin(name, reg.raw["stages"][name])["pin_hash"] == st.pin_hash()


def test_single_and_double_brace_placeholders():
    vals = {"text": "T", "subjects": ["a", "b"], "ctx_before": None}
    assert render_template("{subjects}|{{text}}|{ctx_before}|{\"json\": 1}", vals) == 'a; b|T||{"json": 1}'


def test_invalid_registry_rejected(registry_raw):
    bad = copy.deepcopy(registry_raw)
    del bad["stages"]["label"]["model_digest"]
    with pytest.raises(RegistryError):
        Registry.from_dict(bad)
    bad = copy.deepcopy(registry_raw)
    bad["stages"]["label"]["schema"] = {"type": "nonsense"}
    with pytest.raises(RegistryError):
        Registry.from_dict(bad)
    bad = copy.deepcopy(registry_raw)
    del bad["stages"]["label"]["system_template"]  # chat stages need templates
    with pytest.raises(RegistryError):
        Registry.from_dict(bad)


# --- tiers ---------------------------------------------------------------------

@pytest.mark.parametrize("vram,tier", [
    (0, "cpu"), (4.0, "cpu"), (7.6, "t8"), (11.9, "t8"), (15.99, "t16"), (16, "t16"), (23.99, "t24"),
    (48, "t24"), (24 * 0.65, "t16"), (16 * 0.65, "t8"), (128 * 0.65, "t24"),
])
def test_select_tier(registry_raw, vram, tier):
    assert Registry.from_dict(registry_raw).select_tier(vram)["name"] == tier


def test_allowed_stages_only_defined(registry_raw):
    reg = Registry.from_dict(registry_raw)
    assert reg.allowed_stages("cpu") == ["embed"]
    assert reg.allowed_stages("t8") == ["workcheck"]
    assert reg.allowed_stages("t16") == ["label", "alt_label", "cloze", "workcheck"]
    assert set(reg.allowed_stages("t24")) == set(reg.stages)
    assert reg.allowed_stages("nope") == []


# --- misc ------------------------------------------------------------------------

def test_versions():
    assert version_in_range("0.12.5", ">=0.12.0,<1.0.0")
    assert not version_in_range("0.11.9", ">=0.12.0,<1.0.0")
    assert not version_in_range("1.0.0", ">=0.12.0,<1.0.0")
    assert version_in_range("0.12.0-rc1", ">=0.12.0")
    assert not version_in_range("garbage", ">=0.1")
    assert version_lt("0.1.0", "0.2.0") and not version_lt("0.10.0", "0.9.9")


def test_digests():
    assert bare_digest("sha256:ABC") == "abc"
    assert digests_match("sha256:" + "a" * 64, "a" * 64)
    assert digests_match("a" * 12, "a" * 64)
    assert not digests_match("a" * 8, "a" * 64)
    assert not digests_match(None, "a")


def test_render_template():
    assert render_template("{{ctx_before}}|{{passage}}|{{ missing }}", {"text": "T", "ctx_before": None}) == "|T|"


def test_tier_table_shapes():
    from ald.registry import normalize_tiers
    d = normalize_tiers({"t8": {"min_vram_gb": 7.5, "stages": ["screen"]}, "cpu": ["embed"]})
    assert {"name": "t8", "min_vram_gb": 7.5, "allowed_stages": ["screen"], "num_parallel_hint": None} in d
    assert {"name": "cpu", "min_vram_gb": 0.0, "allowed_stages": ["embed"], "num_parallel_hint": None} in d
    l = normalize_tiers([{"name": "t16", "min_vram_gb": 15.5, "allowed_stages": ["label"], "num_parallel_hint": 3}])
    assert l == [{"name": "t16", "min_vram_gb": 15.5, "allowed_stages": ["label"], "num_parallel_hint": 3}]


def test_active_pins_mark_stale(registry_raw):
    reg = Registry.from_dict(registry_raw)
    pin = reg.stages["workcheck"].pin_hash()
    raw = dict(registry_raw, active_pins=[pin])
    reg2 = Registry.from_dict(raw)
    assert reg2.pin_is_active(pin) and not reg2.pin_is_active(reg.stages["label"].pin_hash())
    assert set(reg2.active_pins().values()) == {"workcheck"}


def test_embed_stage_minimal_and_hash_includes_kind():
    raw = {"kind": "embed", "model_ref": "e:1", "model_digest": "ab" * 32, "ollama_version_range": ">=0.12"}
    st = Stage("embed", raw)
    chat_like = Stage("embed", dict(raw, kind="chat"))
    assert st.prompt_hash() != chat_like.prompt_hash()
    assert st.evidence_keys == [] and st.user_template == "{text}"


def test_evidence_field_null_disables_verification():
    assert Stage("x", dict(RAW, evidence_field=None)).evidence_keys == []
    assert Stage("x", dict(RAW, evidence_field="quote")).evidence_keys == ["quote"]
    assert Stage("x", RAW).evidence_keys == ["evidence_quote"]
