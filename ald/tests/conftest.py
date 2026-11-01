"""Fakes: coordinator (httpx.MockTransport), Ollama (httpx.MockTransport),
clock, disk usage."""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import random
import threading
from collections import namedtuple
from importlib import resources
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest

from ald.backend.ollama import OllamaBackend
from ald.client import CoordinatorClient
from ald.config import Config
from ald.hw import GPU, HardwareInfo
from ald.registry import Registry
from ald.results import decode_jsonl_gz, encode_jsonl_gz
from ald.scheduler import GB, StorageManager
from ald.updater import Updater
from ald.worker import Worker

DU = namedtuple("DU", "total used free")

SCREEN_MODEL = "fake-screen:8b"
LABEL_MODEL = "fake-label:14b"
SCREEN_DIGEST = "a" * 64
LABEL_DIGEST = "b" * 64


def example_registry_raw() -> dict[str, Any]:
    text = resources.files("ald.data").joinpath("models.v1.example.json").read_text(encoding="utf-8")
    raw = json.loads(text)
    raw["stages"]["screen"]["model_ref"] = SCREEN_MODEL
    raw["stages"]["screen"]["model_digest"] = "sha256:" + SCREEN_DIGEST
    raw["stages"]["label"]["model_ref"] = LABEL_MODEL
    raw["stages"]["label"]["model_digest"] = "sha256:" + LABEL_DIGEST
    raw["registry_version"] = "test.1"
    return raw


@pytest.fixture
def registry_raw() -> dict[str, Any]:
    return example_registry_raw()


class FakeClock:
    """Monotonic/wall clock that advances only via sleep() or advance()."""

    def __init__(self, t: float = 1_800_000_000.0):
        self.t = t
        self.mono = 1000.0
        self.lock = threading.Lock()
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.t

    def monotonic(self) -> float:
        return self.mono

    def advance(self, s: float) -> None:
        with self.lock:
            self.t += s
            self.mono += s

    def sleep(self, seconds: float, stop: Any = None) -> bool:
        self.sleeps.append(seconds)
        self.advance(max(0.0, seconds))
        return bool(stop and stop.is_set())


def make_passages(prefix: str, n: int) -> list[dict[str, Any]]:
    out = []
    for i in range(n):
        text = (f"Passage {i} of {prefix}. The letter—which should have come by the evening post—"
                f"was lost, and she could not go to him. It was _very_ dark.")
        out.append({"passage_id": f"{prefix}_p{i:04d}", "work_id": prefix, "decade": 1850, "stratum": "random",
                    "text": text, "ctx_before": "", "ctx_after": "",
                    "text_sha256": hashlib.sha256(text.encode()).hexdigest()})
    return out


class FakeOllama:
    def __init__(self, models: dict[str, str] | None = None, version: str = "0.12.5"):
        self.models = dict(models if models is not None else {SCREEN_MODEL: SCREEN_DIGEST, LABEL_MODEL: LABEL_DIGEST})
        self.version = version
        self.chats: list[dict[str, Any]] = []
        self.on_chat: Callable[[dict[str, Any], int], None] | None = None
        self.invalid_for: set[str] = set()  # "Passage <i> of <prefix>" -> invalid JSON first
        self.always_invalid: set[str] = set()
        self.pull_digests: dict[str, str] = {}
        self.loaded: dict[str, int] = {}  # model -> size
        self.split: set[str] = set()      # models that only partly fit on GPU
        self.unloads: list[str] = []
        self.pulls: list[str] = []
        self.lock = threading.Lock()

    def handler(self, req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p == "/api/version":
            return httpx.Response(200, json={"version": self.version})
        if p == "/api/tags":
            return httpx.Response(200, json={"models": [
                {"name": n, "model": n, "digest": d, "size": 1} for n, d in self.models.items()]})
        if p == "/api/ps":
            return httpx.Response(200, json={"models": [
                {"name": n, "model": n, "size": sz, "size_vram": sz // 2 if n in self.split else sz}
                for n, sz in self.loaded.items()]})
        if p == "/api/generate":
            body = json.loads(req.content)
            if body.get("keep_alive") == 0:
                self.unloads.append(body["model"])
                self.loaded.pop(body["model"], None)
            return httpx.Response(200, json={"done": True})
        if p == "/api/pull":
            body = json.loads(req.content)
            m = body["model"]
            self.pulls.append(m)
            self.models[m] = self.pull_digests.get(m, "c" * 64)
            lines = [{"status": "pulling manifest"}, {"status": "success"}]
            return httpx.Response(200, content="\n".join(json.dumps(x) for x in lines).encode())
        if p == "/api/chat":
            body = json.loads(req.content)
            with self.lock:
                self.chats.append(body)
                n = len(self.chats)
                self.loaded.setdefault(body["model"], 6_000_000_000)
            if self.on_chat:
                self.on_chat(body, n)
            user = body["messages"][1]["content"]
            text = user.split("PASSAGE (label this):\n", 1)[1]
            retry = len(body["messages"]) > 2
            props = body["format"]["properties"]
            key = text.split(".", 1)[0]  # "Passage <i> of <prefix>"
            if key in self.invalid_for and (not retry or key in self.always_invalid):
                content = '{"has_obstacle": "maybe"'
            elif "coarse_domain" in props:
                content = json.dumps({"has_obstacle": "yes", "coarse_domain": "COMMUNICATION_INFORMATION",
                                      "confidence": 0.8})
            else:
                # Quote with straight quotes/hyphen vs the source's em-dash: "normalized".
                quote = "The letter-which should have come by the evening post-was lost"
                content = json.dumps({"has_obstacle": "yes", "obstacles": [{
                    "domain": "COMMUNICATION_INFORMATION", "locus": "material_external",
                    "failure_cause": "accidental_loss", "technology_named": "letter",
                    "message_valence": "romantic", "night_function": "none", "resolution_hint": "unresolved",
                    "obstacle_summary": "lost letter keeps lovers apart", "evidence_quote": quote,
                    "confidence": 0.8}], "confidence": 0.8})
            return httpx.Response(200, json={
                "message": {"role": "assistant", "content": content}, "done": True,
                "prompt_eval_count": 900, "eval_count": 40, "eval_duration": 200_000_000,
                "total_duration": 300_000_000})
        return httpx.Response(404, json={"error": f"no route {p}"})


class FakeCoordinator:
    TOKEN = "tok-123"

    def __init__(self, registry_raw: dict[str, Any]):
        self.registry_raw = registry_raw
        self.etag = '"r1"'
        self.jobs: dict[str, dict[str, Any]] = {}
        self.shards: dict[str, bytes] = {}
        self.state: dict[str, str] = {}
        self.covered: dict[str, set[str]] = {}
        self.puts: list[dict[str, Any]] = []
        self.releases: list[list[str]] = []
        self.heartbeats: list[dict[str, Any]] = []
        self.leases: list[dict[str, Any]] = []
        self.revoked: set[str] = set()
        self.down: set[str] = set()  # paths (prefixes) that raise ConnectError
        self.ping_resp: dict[str, Any] = {"ok": True, "min_client_version": "0.0.1",
                                          "latest_client_version": "0.1.0", "wheel_url": None}
        self.lease_status: int | None = None
        self.lock = threading.Lock()

    def set_registry(self, raw: dict[str, Any], etag: str) -> None:
        self.registry_raw, self.etag = raw, etag

    def add_job(self, job_id: str, stage: str, pin_hash: str, passages: list[dict[str, Any]]) -> None:
        self.jobs[job_id] = {"job_id": job_id, "stage": stage, "pin_hash": pin_hash,
                             "shard_url": f"/v1/shard/{job_id}", "n_passages": len(passages)}
        self.shards[job_id] = encode_jsonl_gz(passages)
        self.state[job_id] = "queued"
        self.covered[job_id] = set()

    def handler(self, req: httpx.Request) -> httpx.Response:
        p = req.url.path
        for d in self.down:
            if p.startswith(d):
                raise httpx.ConnectError("network down", request=req)
        if p == "/v1/ping":
            return httpx.Response(200, json=self.ping_resp)
        if req.headers.get("Authorization") != f"Bearer {self.TOKEN}" and p != "/v1/join":
            return httpx.Response(401, json={"error": "bad token"})
        with self.lock:
            return self._route(req, p)

    def _route(self, req: httpx.Request, p: str) -> httpx.Response:
        if p == "/v1/registry":
            if req.headers.get("If-None-Match") == self.etag:
                return httpx.Response(304)
            return httpx.Response(200, json=self.registry_raw, headers={"ETag": self.etag})
        if p == "/v1/lease":
            if self.lease_status:
                return httpx.Response(self.lease_status, json={"error": "upgrade"})
            body = json.loads(req.content)
            self.leases.append(body)
            out = []
            for jid, j in self.jobs.items():
                if len(out) >= body["max_jobs"]:
                    break
                if self.state[jid] == "queued" and j["stage"] in body["stages"]:
                    self.state[jid] = "leased"
                    jj = dict(j, lease_expires="2030-01-01T00:00:00Z")
                    if self.covered[jid]:
                        jj["skip_passage_ids"] = sorted(self.covered[jid])
                    out.append(jj)
            return httpx.Response(200, json={"jobs": out})
        if p.startswith("/v1/shard/"):
            jid = p.rsplit("/", 1)[1]
            if self.state.get(jid) != "leased":
                return httpx.Response(403, json={"error": "not lease holder"})
            return httpx.Response(200, content=self.shards[jid])
        if p.startswith("/v1/result/"):
            jid = p.rsplit("/", 1)[1]
            body = req.content
            sha = hashlib.sha256(body).hexdigest()
            if req.headers.get("X-Content-Sha256") != sha:
                return httpx.Response(400, json={"error": "sha mismatch"})
            if req.headers.get("X-Pin-Hash") != self.jobs[jid]["pin_hash"]:
                return httpx.Response(412, json={"error": "pin mismatch"})
            partial = req.url.params.get("partial") == "1"
            lines = decode_jsonl_gz(body)
            if partial:
                import base64
                ids = json.loads(gzip.decompress(base64.b64decode(req.headers["X-Passage-Ids"])))
                assert ids == [l["passage_id"] for l in lines]
            self.puts.append({"job_id": jid, "partial": partial, "lines": lines, "headers": dict(req.headers)})
            self.covered[jid] |= {l["passage_id"] for l in lines}
            if not partial:
                self.state[jid] = "done"
            return httpx.Response(200, json={"status": "stored"})
        if p == "/v1/release":
            ids = json.loads(req.content)["job_ids"]
            self.releases.append(ids)
            for jid in ids:
                if self.state.get(jid) == "leased":
                    self.state[jid] = "queued"
            return httpx.Response(200, json={"ok": True})
        if p == "/v1/heartbeat":
            body = json.loads(req.content)
            self.heartbeats.append(body)
            rev = [j for j in body["job_ids"] if j in self.revoked]
            return httpx.Response(200, json={"extended": [j for j in body["job_ids"] if j not in rev],
                                             "revoked": rev})
        if p == "/v1/status":
            return httpx.Response(200, json={"workers": [], "queue": {}, "eta_hours": {}, "cells": []})
        return httpx.Response(404, json={"error": f"no route {p}"})


class FakeRun:
    def __init__(self, rc: int = 0):
        self.rc = rc
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str], **kw: Any) -> Any:
        self.calls.append(cmd)
        return namedtuple("P", "returncode stdout stderr")(self.rc, "", "boom" if self.rc else "")


@pytest.fixture
def hw16() -> HardwareInfo:
    return HardwareInfo(os="linux", arch="x86_64", os_release="test", cpu_model="test", cpu_cores_physical=8,
                        cpu_cores_logical=16, ram_gb=32.0, gpus=[GPU("Fake 16G", 16.0, "nvidia")],
                        usable_vram_gb=15.99, accel="cuda")


@pytest.fixture
def env(tmp_path, registry_raw, hw16):
    """A factory for workers sharing one fake coordinator / Ollama / data dir."""
    coord = FakeCoordinator(registry_raw)
    ollama = FakeOllama()
    clock = FakeClock()

    class Env:
        pass

    e = Env()
    e.coord, e.ollama, e.clock, e.root, e.hw = coord, ollama, clock, tmp_path / "data", hw16
    e.registry = Registry.from_dict(registry_raw)
    e.free = [500 * GB]
    e.run = FakeRun()
    e.reexec_calls = []
    e.logs = []

    def make_worker(**kw: Any) -> Worker:
        cfg = Config(coordinator_url="http://coord.test", token=FakeCoordinator.TOKEN, tier="t16")
        client = CoordinatorClient("http://coord.test", FakeCoordinator.TOKEN,
                                   transport=httpx.MockTransport(coord.handler))
        backend = OllamaBackend("http://ollama.test", transport=httpx.MockTransport(ollama.handler))
        storage = StorageManager(e.root, disk_usage=lambda p: DU(1000 * GB, 0, e.free[0]))
        updater = Updater(e.root / "update_state.json", run=e.run, reexec=e.reexec_calls.append,
                          clock=clock.time, which=lambda n: "/usr/bin/uv", log=e.logs.append)
        defaults = dict(data_root=e.root, hw=hw16, clock=clock, storage=storage, updater=updater,
                        auto_update=False, background=False, exit_when_idle=True, max_concurrency=1,
                        log=e.logs.append, rng=random.Random(0))
        defaults.update(kw)
        return Worker(cfg, client, backend, **defaults)

    e.make_worker = make_worker
    return e
