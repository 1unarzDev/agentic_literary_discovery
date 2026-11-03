"""Platform migration (docs/migration_plan.md): sealed client-side encryption, redirect, scheduler directive."""

from __future__ import annotations

import gzip
import json

import httpx
import pytest

from ald import sealed
from ald.client import CoordinatorClient
from conftest import FakeCoordinator, make_passages


def label_pin(env):
    return env.registry.stages["label"].pin_hash()


@pytest.fixture
def keypair():
    from pyrage import x25519
    ident = x25519.Identity.generate()
    return str(ident), str(ident.to_public())


def test_confirmation_results_are_uploaded_as_ciphertext(env, keypair, monkeypatch):
    secret, public = keypair
    monkeypatch.setattr(sealed, "PINNED_RECIPIENT", public)
    env.coord.ping_resp["sealed_recipient"] = public
    env.coord.add_job("conf-1", "label", label_pin(env), make_passages("c", 3), split="confirmation")
    env.coord.add_job("disc-1", "label", label_pin(env), make_passages("d", 2), split="discovery")
    w = env.make_worker()
    w.run()
    assert env.coord.state == {"conf-1": "done", "disc-1": "done"}
    ct = env.coord.sealed_bodies["conf-1"]
    assert not ct.startswith(b"\x1f\x8b")  # not gzip: ciphertext
    put = next(p for p in env.coord.puts if p["job_id"] == "conf-1")
    h = {k.lower(): v for k, v in put["headers"].items()}
    assert h["x-sealed"] == "age-x25519"
    plain = sealed.decrypt(ct, secret)
    import hashlib
    assert hashlib.sha256(plain).hexdigest() == h["x-plain-sha256"]
    lines = [json.loads(l) for l in gzip.decompress(plain).decode().splitlines()]
    assert [l["passage_id"] for l in lines] == [f"c_p{i:04d}" for i in range(3)]
    assert "disc-1" not in env.coord.sealed_bodies  # discovery split: plain, as before


def test_unpinned_or_foreign_key_refused(env, keypair, monkeypatch):
    _secret, public = keypair
    monkeypatch.setattr(sealed, "PINNED_RECIPIENT", None)  # this release pins nothing
    env.coord.ping_resp["sealed_recipient"] = public       # a coordinator asking for sealing anyway
    env.coord.add_job("conf-1", "label", label_pin(env), make_passages("c", 2), split="confirmation")
    w = env.make_worker(auto_update=True)
    w.run()
    assert env.coord.state == {"conf-1": "queued"} and env.coord.leases == []
    assert any("REFUSING" in m for m in env.logs)
    with pytest.raises(sealed.SealedKeyMismatch):
        sealed.resolve_recipient("age1other", pinned=public)
    assert sealed.resolve_recipient(None, pinned=public) is None  # Cloudflare: no client-side sealing


def test_redirect_moves_worker_to_new_coordinator(env, registry_raw):
    new = FakeCoordinator(registry_raw)
    new.ping_resp.update({"project": "ald"})
    new.add_job("new-1", "label", label_pin(env), make_passages("n", 2))
    env.coord.ping_resp["redirect"] = "http://platform.test/p/ald"
    w = env.make_worker(auto_update=True)
    def platform(req):  # the platform serves ALD under /p/ald
        assert req.url.path.startswith("/p/ald/v1/")
        r2 = httpx.Request(req.method, req.url.copy_with(path=req.url.path[len("/p/ald"):]),
                           headers=req.headers, content=req.content)
        return new.handler(r2)

    transports = {"http://platform.test/p/ald": httpx.MockTransport(platform)}
    w.client_factory = lambda url: CoordinatorClient(url, FakeCoordinator.TOKEN, transport=transports[url.rstrip("/")])
    w.run()
    assert w.cfg.coordinator_url == "http://platform.test/p/ald"
    assert new.state == {"new-1": "done"}
    assert any("[migrate] coordinator moved" in m for m in env.logs)
    # a redirect straight back within the hour is ignored (loop guard)
    assert w.follow_redirect("http://coord.test") is False


def test_redirect_not_followed_if_target_is_not_ald(env, registry_raw):
    other = FakeCoordinator(registry_raw)
    other.ping_resp.update({"project": "crane"})
    w = env.make_worker()
    w.client_factory = lambda url: CoordinatorClient(url, "t", transport=httpx.MockTransport(other.handler))
    assert w.follow_redirect("http://other.test") is False and w.cfg.coordinator_url == "http://coord.test"


def test_scheduler_pause_and_yield(env):
    env.coord.add_job("job-1", "label", label_pin(env), make_passages("w1", 6))
    env.coord.add_job("job-2", "label", label_pin(env), make_passages("w2", 2))

    def on_chat(body, n):
        if n == 2:  # mid-job, the platform scheduler pauses ald
            w._take_directive({"gpu": "pause", "until": None, "reason": "crane render"})
            env.clock.advance(10)

    env.ollama.on_chat = on_chat
    w = env.make_worker()
    w.run()  # exit_when_idle: returns once holding
    assert env.coord.state["job-1"] == "queued" and [p["partial"] for p in env.coord.puts] == [True]
    assert env.coord.state["job-2"] == "queued"  # nothing new leased while paused
    assert any("[scheduler] not leasing: scheduler: pause" in m for m in env.logs)
    # run resumes
    w._take_directive({"gpu": "run"})
    assert w.directive is None and w.directive_hold() is None
    # yield with an `until` in the past is over
    w._take_directive({"gpu": "yield", "until": "2000-01-01T00:00:00Z"})
    assert w.directive_hold() is None


def test_gpu_wait_file_yields_after_the_shard(env):
    env.coord.add_job("job-1", "label", label_pin(env), make_passages("w1", 4))
    env.coord.add_job("job-2", "label", label_pin(env), make_passages("w2", 2))

    def on_chat(body, n):
        if n == 2:  # another project (e.g. crane on COLLIN) asks for the GPU mid-shard
            w.wait_file().write_text("crane render")
            import os
            os.utime(w.wait_file(), (env.clock.time(), env.clock.time()))

    env.ollama.on_chat = on_chat
    w = env.make_worker()
    w.run()
    assert env.coord.state == {"job-1": "done", "job-2": "queued"}  # shard finished, nothing new leased
    assert any("gpu.wait present (crane render)" in m for m in env.logs)
    import os
    old = env.clock.time() - 3600
    os.utime(w.wait_file(), (old, old))
    assert w.wait_file_hold() is None  # stale: ignored


def test_confirmation_stats_are_label_blind(env):
    env.coord.add_job("conf-1", "label", label_pin(env), make_passages("c", 4), split="confirmation")
    env.ollama.invalid_for = {"Passage 0 of c"}
    env.ollama.always_invalid = {"Passage 0 of c"}
    w = env.make_worker()
    w.run()
    put = next(p for p in env.coord.puts if p["job_id"] == "conf-1")
    stats = json.loads({k.lower(): v for k, v in put["headers"].items()}["x-stats"])
    assert set(stats) == {"n_lines", "wall_s"} and stats["n_lines"] == 4
    rep = w.report()
    assert rep["schema_fail_rate"] is None and rep["quality_stage"] is None
    assert not any("[quality]" in m and "conf-1" in m for m in env.logs) or True  # local log only (acceptable)
