"""One passage through one pinned stage -> one result line."""

from __future__ import annotations

import base64
import hashlib
import json
import struct
import time
from typing import Any

import jsonschema

from .backend.ollama import OllamaBackend
from .evidence import VERIFIED_STATUSES, verify_output
from .registry import Stage


def build_messages(stage: Stage, passage: dict[str, Any]) -> list[dict[str, str]]:
    """Static system prompt (codebook + few-shot) FIRST, passage LAST, so the
    backend can reuse the KV cache for the shared prefix."""
    return [
        {"role": "system", "content": stage.system_template},
        {"role": "user", "content": stage.render_user(passage)},
    ]


def _parse(content: str, validator: jsonschema.protocols.Validator) -> tuple[Any, str | None]:
    try:
        obj = json.loads(content)
    except json.JSONDecodeError as e:
        return None, f"invalid JSON: {e.msg} at {e.pos}"
    errs = sorted(validator.iter_errors(obj), key=lambda e: list(e.absolute_path))
    if errs:
        e = errs[0]
        return obj, f"schema violation at {list(e.absolute_path)}: {e.message}"
    return obj, None


_VALIDATORS: dict[str, Any] = {}


def _validator(stage: Stage) -> Any:
    h = stage.schema_hash()
    v = _VALIDATORS.get(h)
    if v is None:
        v = jsonschema.Draft202012Validator(stage.schema)
        _VALIDATORS[h] = v
    return v


def encode_f16(vec: list[float]) -> str:
    """Little-endian IEEE float16, base64."""
    return base64.b64encode(struct.pack(f"<{len(vec)}e", *vec)).decode("ascii")


def decode_f16(b64: str) -> list[float]:
    raw = base64.b64decode(b64)
    return list(struct.unpack(f"<{len(raw) // 2}e", raw))


def run_embed(backend: OllamaBackend, stage: Stage, passage: dict[str, Any], *, pin_hash: str,
              model_digest: str, backend_version: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    opts = {k: v for k, v in stage.ollama_options().items() if k in ("num_ctx", "seed", "temperature")}
    res = backend.embed(stage.model_ref, stage.render_user(passage), options=opts)
    vec = json.loads(res.content)
    flags: list[str] = []
    text = passage.get("text", "") or ""
    tsha = passage.get("text_sha256")
    if tsha and hashlib.sha256(text.encode("utf-8")).hexdigest() != tsha:
        flags.append("text_sha256_mismatch")
    line: dict[str, Any] = {
        "passage_id": passage["passage_id"], "stage": stage.name, "pin_hash": pin_hash,
        "model_digest": model_digest, "backend_version": backend_version,
        "output": {"embedding_f16_b64": encode_f16(vec), "dim": len(vec), "dtype": "float16_le"},
        "valid_schema": True, "evidence": [],
        "latency_ms": int(round((time.perf_counter() - t0) * 1000)),
        "prompt_tokens": res.prompt_tokens, "gen_tokens": 0,
    }
    if flags:
        line["flags"] = flags
    return line


def run_passage(
    backend: OllamaBackend,
    stage: Stage,
    passage: dict[str, Any],
    *,
    pin_hash: str,
    model_digest: str,
    backend_version: str,
) -> dict[str, Any]:
    """Run inference (retry once on invalid output), verify evidence and
    return a result line per the contract. Backend errors propagate."""
    if stage.kind == "embed":
        return run_embed(backend, stage, passage, pin_hash=pin_hash, model_digest=model_digest,
                         backend_version=backend_version)
    validator = _validator(stage)
    messages = build_messages(stage, passage)
    t0 = time.perf_counter()
    res = backend.chat(stage.model_ref, messages, schema=stage.schema,
                       options=stage.ollama_options(), think=stage.think)
    prompt_tokens, gen_tokens = res.prompt_tokens, res.gen_tokens
    eval_s = res.eval_s
    output, err = _parse(res.content, validator)
    flags: list[str] = []
    retried = False
    if err is not None:
        retried = True
        retry_msgs = messages + [
            {"role": "assistant", "content": res.content},
            {"role": "user", "content": stage.retry_template.replace("{error}", err)},
        ]
        res2 = backend.chat(stage.model_ref, retry_msgs, schema=stage.schema,
                            options=stage.ollama_options(), think=stage.think)
        prompt_tokens += res2.prompt_tokens
        gen_tokens += res2.gen_tokens
        eval_s += res2.eval_s
        output2, err2 = _parse(res2.content, validator)
        if err2 is None:
            output, err = output2, None
        else:
            output = output2 if output2 is not None else output
            err = err2
            flags.append("schema_invalid")
    latency_ms = int(round((time.perf_counter() - t0) * 1000))

    text = passage.get("text", "") or ""
    evidence = verify_output(output, text, stage.evidence_keys) if output is not None else []
    if any(ev.status not in VERIFIED_STATUSES for ev in evidence):
        flags.append("evidence_unverified")
    tsha = passage.get("text_sha256")
    if tsha and hashlib.sha256(text.encode("utf-8")).hexdigest() != tsha:
        flags.append("text_sha256_mismatch")
    if retried:
        flags.append("retried")

    line: dict[str, Any] = {
        "passage_id": passage["passage_id"],
        "stage": stage.name,
        "pin_hash": pin_hash,
        "model_digest": model_digest,
        "backend_version": backend_version,
        "output": output,
        "valid_schema": err is None,
        "evidence": [ev.to_json() for ev in evidence],
        "latency_ms": latency_ms,
        "prompt_tokens": prompt_tokens,
        "gen_tokens": gen_tokens,
        "eval_s": round(eval_s, 4),
    }
    if flags:
        line["flags"] = flags
    if err is not None:
        line["error"] = err
    return line


def is_flagged(line: dict[str, Any]) -> bool:
    return (not line.get("valid_schema", False)) or any(
        f in ("schema_invalid", "evidence_unverified", "text_sha256_mismatch", "backend_error")
        for f in line.get("flags", [])
    )
