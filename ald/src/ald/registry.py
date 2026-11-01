"""Model registry (``models.v1.json``): loading, validation, hashing, tiers.

Hash definitions (shared with the admin tooling that registers pins):

* ``canonical_json(x)`` = ``json.dumps(x, sort_keys=True, separators=(",", ":"),
  ensure_ascii=False)`` encoded as UTF-8.
* ``prompt_hash`` = sha256(canonical_json({"template": {"system", "user",
  "retry"}, "codebook_version", "schema", "options"})) where ``options`` =
  ``{temperature, seed, num_ctx, num_predict, think}``.
* ``schema_hash`` = sha256(canonical_json(schema)).
* ``pin_hash`` = sha256((prompt_hash + model_digest + stage).encode()) using
  hex strings and the bare digest (any ``sha256:`` prefix stripped).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema

DEFAULT_RETRY_TEMPLATE = (
    "Your previous reply was not valid JSON for the required schema "
    "({error}). Reply again with ONLY a JSON object that matches the schema."
)

REGISTRY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["registry_version", "tiers", "stages"],
    "properties": {
        "registry_version": {"type": ["string", "integer"]},
        # Coordinator-compatible tier table (coordinator/src/registry.ts):
        #   {"<tier>": {"min_vram_gb": 15.5, "stages": [...]}}  or  {"<tier>": [...]}
        # A list of {"name", "min_vram_gb", "allowed_stages"} is also accepted.
        "tiers": {
            "anyOf": [
                {"type": "object", "minProperties": 1, "additionalProperties": {
                    "anyOf": [
                        {"type": "array", "items": {"type": "string"}},
                        {"type": "object", "properties": {
                            "min_vram_gb": {"type": "number", "minimum": 0},
                            "num_parallel_hint": {"type": "integer", "minimum": 1},
                            "stages": {"type": "array", "items": {"type": "string"}},
                            "allowed_stages": {"type": "array", "items": {"type": "string"}},
                        }},
                    ]}},
                {"type": "array", "minItems": 1, "items": {
                    "type": "object", "required": ["name", "min_vram_gb"],
                    "properties": {"name": {"type": "string"}, "min_vram_gb": {"type": "number", "minimum": 0},
                                   "allowed_stages": {"type": "array", "items": {"type": "string"}},
                                   "stages": {"type": "array", "items": {"type": "string"}}}}},
            ],
        },
        "active_pins": {"type": "array", "items": {"type": "string"}},
        "unload_others": {"type": "boolean"},
        "stages": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                # Kind-specific requirements are checked in validate_registry().
                "required": ["model_ref", "model_digest", "ollama_version_range"],
                "properties": {
                    "kind": {"enum": ["chat", "embed"]},
                    "api": {"enum": ["chat", "embed"]},
                    "evidence_field": {"type": ["string", "null"]},
                    "model_ref": {"type": "string", "minLength": 1},
                    "model_digest": {"type": "string", "minLength": 1},
                    "model_size_gb": {"type": "number", "minimum": 0},
                    "vram_gb_required": {"type": "number", "minimum": 0},
                    "kv_gb_per_slot": {"type": "number", "minimum": 0},
                    "ollama_version_range": {"type": "string"},
                    "codebook_version": {"type": "string"},
                    "num_ctx": {"type": "integer", "minimum": 128},
                    "num_predict": {"type": "integer", "minimum": 1},
                    "temperature": {"type": "number"},
                    "seed": {"type": "integer"},
                    "think": {"type": ["boolean", "null"]},
                    "system_template": {"type": "string"},
                    "user_template": {"type": "string"},
                    "retry_template": {"type": "string"},
                    "schema": {"type": "object"},
                    "evidence_keys": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}


class RegistryError(ValueError):
    pass


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def bare_digest(d: str | None) -> str:
    d = (d or "").strip().lower()
    return d.split(":", 1)[1] if d.startswith("sha256:") else d


def digests_match(a: str | None, b: str | None) -> bool:
    """Equal digests; a 12+ char prefix (``ollama list`` style) also matches."""
    a, b = bare_digest(a), bare_digest(b)
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    return len(short) >= 12 and long_.startswith(short)


@dataclass(frozen=True)
class Stage:
    name: str
    raw: dict[str, Any]

    @property
    def kind(self) -> str:
        """``chat`` (templates + JSON schema via /api/chat) or ``embed`` (/api/embed)."""
        return self.raw.get("kind") or self.raw.get("api") or "chat"

    @property
    def model_ref(self) -> str:
        return self.raw["model_ref"]

    @property
    def model_digest(self) -> str:
        return bare_digest(self.raw["model_digest"])

    @property
    def num_ctx(self) -> int:
        return int(self.raw.get("num_ctx", 2048))

    @property
    def num_predict(self) -> int:
        return int(self.raw.get("num_predict", 0 if self.kind == "embed" else 512))

    @property
    def think(self) -> bool | None:
        return self.raw.get("think")

    @property
    def schema(self) -> dict[str, Any]:
        return self.raw.get("schema") or {}

    @property
    def system_template(self) -> str:
        return self.raw.get("system_template", "")

    @property
    def user_template(self) -> str:
        return self.raw.get("user_template", "{{text}}")

    @property
    def retry_template(self) -> str:
        return self.raw.get("retry_template", DEFAULT_RETRY_TEMPLATE if self.kind == "chat" else "")

    @property
    def codebook_version(self) -> str:
        return str(self.raw.get("codebook_version", ""))

    @property
    def version_range(self) -> str:
        return self.raw["ollama_version_range"]

    @property
    def model_size_gb(self) -> float:
        return float(self.raw.get("model_size_gb", 0.0))

    @property
    def vram_gb_required(self) -> float:
        return float(self.raw.get("vram_gb_required", self.model_size_gb))

    @property
    def kv_gb_per_slot(self) -> float:
        return float(self.raw.get("kv_gb_per_slot", 0.0))

    @property
    def evidence_keys(self) -> list[str]:
        """Fields whose quotes are verified. ``evidence_field: null`` (or an
        embed stage) disables verification."""
        if self.kind == "embed":
            return []
        if "evidence_field" in self.raw:
            f = self.raw["evidence_field"]
            return [] if f is None else ([f] if isinstance(f, str) else list(f))
        return list(self.raw.get("evidence_keys", ["evidence_quote"]))

    def options(self) -> dict[str, Any]:
        """Inference options that are part of the pin."""
        return {
            "temperature": self.raw.get("temperature", 0),
            "seed": self.raw.get("seed", 0),
            "num_ctx": self.num_ctx,
            "num_predict": self.num_predict,
            "think": self.think,
        }

    def ollama_options(self) -> dict[str, Any]:
        o = self.options()
        o.pop("think")
        return o

    def template(self) -> dict[str, str]:
        return {"system": self.system_template, "user": self.user_template, "retry": self.retry_template}

    def prompt_hash(self) -> str:
        doc: dict[str, Any] = {
            "template": self.template(),
            "codebook_version": self.codebook_version,
            "schema": self.schema,
            "options": self.options(),
        }
        if self.kind != "chat":
            doc["kind"] = self.kind  # chat hashes stay identical to the original definition
        return sha256_hex(canonical_json(doc))

    def schema_hash(self) -> str:
        return sha256_hex(canonical_json(self.schema))

    def pin_hash(self, model_digest: str | None = None) -> str:
        return compute_pin_hash(self.prompt_hash(), model_digest or self.model_digest, self.name)

    def pin_object(self) -> dict[str, Any]:
        return {
            "pin_hash": self.pin_hash(),
            "stage": self.name,
            "model_ref": self.model_ref,
            "model_digest": self.model_digest,
            "prompt_hash": self.prompt_hash(),
            "schema_hash": self.schema_hash(),
            "options": self.options(),
        }

    def render_user(self, passage: dict[str, Any]) -> str:
        return render_template(self.user_template, passage)


def compute_pin_hash(prompt_hash: str, model_digest: str, stage: str) -> str:
    return sha256_hex(prompt_hash + bare_digest(model_digest) + stage)


_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def render_template(template: str, values: dict[str, Any]) -> str:
    """``{{name}}`` substitution (no format-string brace escaping needed for
    JSON examples in the codebook). ``{{passage}}`` aliases ``text``."""

    def sub(m: re.Match[str]) -> str:
        key = m.group(1)
        if key == "passage":
            key = "text"
        v = values.get(key, "")
        return "" if v is None else str(v)

    return _PLACEHOLDER.sub(sub, template)


@dataclass
class Registry:
    raw: dict[str, Any]
    stages: dict[str, Stage] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Registry":
        validate_registry(raw)
        return cls(raw=raw, stages={k: Stage(k, v) for k, v in raw["stages"].items()})

    @classmethod
    def load(cls, path: str | Path) -> "Registry":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    @property
    def version(self) -> str:
        return str(self.raw.get("registry_version"))

    @property
    def content_hash(self) -> str:
        return sha256_hex(canonical_json(self.raw))

    @property
    def tiers(self) -> list[dict[str, Any]]:
        """Normalized: [{"name", "min_vram_gb", "allowed_stages"}] sorted by VRAM."""
        return sorted(normalize_tiers(self.raw["tiers"]), key=lambda t: t["min_vram_gb"])

    def tier(self, name: str) -> dict[str, Any] | None:
        return next((t for t in self.tiers if t["name"] == name), None)

    def select_tier(self, usable_vram_gb: float) -> dict[str, Any]:
        """Highest tier whose ``min_vram_gb`` fits; the lowest tier otherwise."""
        tiers = self.tiers
        chosen = tiers[0]
        for t in tiers:
            if usable_vram_gb + 1e-9 >= float(t["min_vram_gb"]):
                chosen = t
        return chosen

    def allowed_stages(self, tier_name: str) -> list[str]:
        t = self.tier(tier_name)
        if not t:
            return []
        return [s for s in t["allowed_stages"] if s in self.stages]

    @property
    def unload_others(self) -> bool:
        return bool(self.raw.get("unload_others", True))

    def num_parallel_hint(self, tier_name: str) -> int | None:
        t = self.tier(tier_name)
        return int(t["num_parallel_hint"]) if t and t.get("num_parallel_hint") else None

    def pin_is_active(self, pin_hash: str) -> bool:
        """If the registry carries ``active_pins`` (the coordinator uses it to
        deactivate pins), a pin outside it is stale and must not run."""
        ap = self.raw.get("active_pins")
        return True if ap is None else pin_hash in ap

    def active_pins(self) -> dict[str, str]:
        """pin_hash -> stage for every (active) stage in this registry."""
        return {st.pin_hash(): name for name, st in self.stages.items() if self.pin_is_active(st.pin_hash())}


def normalize_tiers(tiers: Any) -> list[dict[str, Any]]:
    out = []
    if isinstance(tiers, dict):
        for name, v in tiers.items():
            if isinstance(v, list):
                out.append({"name": name, "min_vram_gb": 0.0, "allowed_stages": list(v), "num_parallel_hint": None})
            else:
                out.append({"name": name, "min_vram_gb": float(v.get("min_vram_gb", 0.0)),
                            "allowed_stages": list(v.get("stages", v.get("allowed_stages", []))),
                            "num_parallel_hint": v.get("num_parallel_hint")})
    else:
        for t in tiers:
            out.append({"name": t["name"], "min_vram_gb": float(t["min_vram_gb"]),
                        "allowed_stages": list(t.get("allowed_stages", t.get("stages", []))),
                        "num_parallel_hint": t.get("num_parallel_hint")})
    return out


def validate_registry(raw: dict[str, Any]) -> None:
    try:
        jsonschema.validate(raw, REGISTRY_SCHEMA)
    except jsonschema.ValidationError as e:
        raise RegistryError(f"registry invalid at {list(e.absolute_path)}: {e.message}") from e
    names = [t["name"] for t in normalize_tiers(raw["tiers"])]
    if len(set(names)) != len(names):
        raise RegistryError("duplicate tier names")
    for name, st in raw["stages"].items():
        kind = st.get("kind") or st.get("api") or "chat"
        if kind == "chat":
            missing = [k for k in ("codebook_version", "num_ctx", "num_predict", "system_template",
                                   "user_template", "schema") if k not in st]
            if missing:
                raise RegistryError(f"stage {name}: chat stage missing {missing}")
        if "schema" in st:
            try:
                jsonschema.Draft202012Validator.check_schema(st["schema"])
            except jsonschema.SchemaError as e:
                raise RegistryError(f"stage {name}: output schema invalid: {e.message}") from e
        parse_version_range(st["ollama_version_range"])


# --- version ranges -------------------------------------------------------

def parse_version(v: str) -> tuple[int, ...]:
    v = v.strip().lstrip("vV")
    m = re.match(r"^(\d+(?:\.\d+)*)", v)
    if not m:
        raise RegistryError(f"bad version: {v!r}")
    return tuple(int(x) for x in m.group(1).split("."))


def _cmp(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    n = max(len(a), len(b))
    a = a + (0,) * (n - len(a))
    b = b + (0,) * (n - len(b))
    return (a > b) - (a < b)


def parse_version_range(spec: str) -> list[tuple[str, tuple[int, ...]]]:
    out = []
    for part in [p.strip() for p in spec.split(",") if p.strip()]:
        m = re.match(r"^(>=|<=|==|!=|>|<|~=)?\s*(.+)$", part)
        if not m:
            raise RegistryError(f"bad version range: {spec!r}")
        out.append((m.group(1) or "==", parse_version(m.group(2))))
    return out


def version_in_range(version: str, spec: str) -> bool:
    try:
        v = parse_version(version)
    except RegistryError:
        return False
    for op, ref in parse_version_range(spec):
        c = _cmp(v, ref)
        ok = {
            ">=": c >= 0, "<=": c <= 0, ">": c > 0, "<": c < 0, "==": c == 0, "!=": c != 0,
            "~=": c >= 0 and v[: max(1, len(ref) - 1)] == ref[: max(1, len(ref) - 1)],
        }[op]
        if not ok:
            return False
    return True


def version_lt(a: str, b: str) -> bool:
    return _cmp(parse_version(a), parse_version(b)) < 0
