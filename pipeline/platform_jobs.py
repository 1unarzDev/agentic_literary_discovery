"""The single place that builds what ALD submits to the research platform (rc-job/1 jobs, rc-panel/1 sections).

Rules enforced here (platform DECISIONS-ALD.md + migration 0013_blind):
- split "confirmation" -> outputs {"class": "sealed", "seal_id": <seal>} (the platform answers 400 otherwise);
  split "discovery" -> outputs {"class": "summary"}. Nothing else is accepted.
- dup_group -> anti_affinity {"keys": ["dup:<group>"], "scope": "host"} (twins never on the same worker/host).
- Panel sections that concern the sealed split may only be of kind progress / workers / milestone, and carry
  counts only (no quality, flag, quote, schema or label figures).
"""
from __future__ import annotations

from typing import Any

SEAL_ID = "ald-confirmation-v09"
SUBMITTER = "fiction-obstacles-research-plan"
SEALED_PANEL_KINDS = {"progress", "workers", "milestone"}
FORBIDDEN_SEALED_PANEL_WORDS = ("flag", "quote", "schema", "quality", "obstacle", "label", "agree", "kappa", "rate")


def outputs_for(split: str, seal_id: str | None = SEAL_ID) -> dict[str, Any]:
    if split == "confirmation":
        if not seal_id:
            raise ValueError("confirmation jobs need a seal_id (create the seal first: key ceremony -> pinned client)")
        return {"class": "sealed", "seal_id": seal_id}
    if split == "discovery":
        return {"class": "summary"}
    raise ValueError(f"unknown split {split!r}")


def rc_job(*, job_id: str, stage: str, wave: str, split: str, pin_hash: str, shard_sha256: str, shard_size: int,
           n_items: int, campaign: str, purpose: str, est_seconds: int, dup_group: str | None = None,
           cell: str | None = None, priority: int = 100, vram_gb: float = 10.0,
           seal_id: str | None = SEAL_ID) -> dict[str, Any]:
    job: dict[str, Any] = {
        "schema": "rc-job/1", "job_id": job_id, "kind": "ald-shard", "purpose": purpose, "est_seconds": int(est_seconds),
        "submitter": SUBMITTER, "campaign": campaign, "priority_class": "background", "priority": int(priority),
        "needs": {"gpu": True, "vram_gb": float(vram_gb)}, "preemptible": True,
        "pin": {"pin_hash": pin_hash},
        "inputs": [{"name": "shard", "sha256": shard_sha256, "size": int(shard_size)}],
        "items": {"count": int(n_items), "id_field": "passage_id"},
        "spec": {"stage": stage, "wave": wave, "split": split, **({"cell": cell} if cell else {})},
        "outputs": outputs_for(split, seal_id),
    }
    if dup_group:
        job["anti_affinity"] = {"keys": [f"dup:{dup_group}"], "scope": "host"}
    return job


def check_jobs(jobs: list[dict[str, Any]]) -> None:
    """Refuse a batch that could put confirmation outputs anywhere but a seal."""
    for j in jobs:
        split = (j.get("spec") or {}).get("split")
        out = j.get("outputs") or {}
        if split == "confirmation" and (out.get("class") != "sealed" or not out.get("seal_id")):
            raise ValueError(f"{j.get('job_id')}: confirmation job must have outputs.class=sealed with a seal_id")
        if split == "discovery" and out.get("class") == "sealed":
            raise ValueError(f"{j.get('job_id')}: discovery job marked sealed")
        if split not in ("confirmation", "discovery"):
            raise ValueError(f"{j.get('job_id')}: spec.split must be discovery|confirmation")


def panel_section(*, kind: str, title: str, body: dict[str, Any], concerns_sealed: bool) -> dict[str, Any]:
    """rc-panel/1 section. Sealed-split sections: progress/workers/milestone only, and counts only."""
    if concerns_sealed:
        if kind not in SEALED_PANEL_KINDS:
            raise ValueError(f"a section about the sealed split may only be {sorted(SEALED_PANEL_KINDS)}")
        text = (title + " " + " ".join(map(str, body.keys()))).lower()
        bad = [w for w in FORBIDDEN_SEALED_PANEL_WORDS if w in text]
        if bad:
            raise ValueError(f"sealed-split panel section mentions outcome-related terms: {bad}")
    return {"kind": kind, "title": title, **body}
