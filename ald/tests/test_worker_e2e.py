"""Fake coordinator + fake Ollama end-to-end tests of ``ald work``."""

from __future__ import annotations

import copy
import hashlib
import json

import pytest

from ald.registry import Registry
from ald.results import Outbox
from ald.scheduler import GB
from conftest import LABEL_MODEL, WC_MODEL, make_passages


class Killed(BaseException):
    """Simulates the process dying (not an Exception: nothing catches it)."""


def label_pin(env):
    return env.registry.stages["label"].pin_hash()


def wc_pin(env):
    return env.registry.stages["workcheck"].pin_hash()


def finals(coord, job_id=None):
    return [p for p in coord.puts if not p["partial"] and (job_id is None or p["job_id"] == job_id)]


def partials(coord, job_id=None):
    return [p for p in coord.puts if p["partial"] and (job_id is None or p["job_id"] == job_id)]


# ---------------------------------------------------------------------------

def test_lease_to_result_put(env):
    env.coord.add_job("job-1", "label", label_pin(env), make_passages("w1", 6))
    env.coord.add_job("job-2", "workcheck", wc_pin(env), make_passages("w2", 4))
    w = env.make_worker(max_concurrency=2)
    w.run()

    assert env.coord.state == {"job-1": "done", "job-2": "done"}
    put = finals(env.coord, "job-1")[0]
    h = put["headers"]
    assert h["x-pin-hash"] == label_pin(env)
    assert h["x-model-digest"] == env.registry.stages["label"].model_digest
    assert h["x-backend-version"].startswith("ollama/0.12.5")
    stats = json.loads(h["x-stats"])
    assert set(stats) == {"n_ok", "n_flagged", "tok_s", "wall_s", "prompt_tokens", "gen_tokens"}
    assert stats["n_ok"] == 6 and stats["n_flagged"] == 0 and stats["gen_tokens"] == 6 * 40
    lines = put["lines"]
    assert [l["passage_id"] for l in lines] == [f"w1_p{i:04d}" for i in range(6)]  # shard order
    for l in lines:
        assert {"passage_id", "stage", "pin_hash", "model_digest", "backend_version", "output", "valid_schema",
                "evidence", "latency_ms", "prompt_tokens", "gen_tokens"} <= set(l)
        assert l["valid_schema"] is True
        ev = l["evidence"][0]
        assert ev["status"] == "normalized"  # quote used '-' for the source's em-dashes
        text = make_passages("w1", 6)[int(l["passage_id"][-4:])]["text"]
        assert text[ev["start"]:ev["end"]].startswith("The letter—which")
    # Inference options per contract / plan.
    body = env.ollama.chats[0]
    assert body["options"]["temperature"] == 0 and body["options"]["seed"] == 0
    assert body["keep_alive"] == "30m" and body["stream"] is False and body["think"] is False
    assert body["messages"][0]["role"] == "system" and "CODEBOOK" in body["messages"][0]["content"]
    assert body["messages"][-1]["content"].rstrip().endswith("It was _very_ dark.")  # passage LAST
    assert body["format"]["type"] == "object"
    # Local files cleaned up after the 200 ack.
    assert Outbox(env.root).entries() == []
    assert not any((env.root / "shards").iterdir())
    assert not any((env.root / "jobs").iterdir())


def test_pin_mismatch_refused_and_released(env):
    env.coord.add_job("bad", "label", "f" * 64, make_passages("w1", 3))
    env.coord.add_job("good", "workcheck", wc_pin(env), make_passages("w2", 2))
    w = env.make_worker()
    w.run()
    assert ["bad"] in env.coord.releases
    assert [p["job_id"] for p in env.coord.puts] == ["good"]
    assert not any("PLACEHOLDER" in c["model"] for c in env.ollama.chats)
    assert any("refusing bad" in m for m in env.logs)


def test_wrong_local_digest_excludes_stage(env):
    env.ollama.models[LABEL_MODEL] = "9" * 64
    env.coord.add_job("j", "label", label_pin(env), make_passages("w1", 2))
    w = env.make_worker(auto_pull=False)
    w.run()
    assert "label" not in w.stages and "digest" in w.excluded["label"]
    assert all("label" not in l["stages"] for l in env.coord.leases)
    assert env.coord.puts == []


def test_schema_invalid_retry_once_then_flag(env):
    env.ollama.invalid_for = {"Passage 0 of w1", "Passage 1 of w1"}
    env.ollama.always_invalid = {"Passage 1 of w1"}
    env.coord.add_job("j", "workcheck", wc_pin(env), make_passages("w1", 3))
    env.make_worker().run()
    lines = {l["passage_id"]: l for l in finals(env.coord)[0]["lines"]}
    assert lines["w1_p0000"]["valid_schema"] is True and "retried" in lines["w1_p0000"]["flags"]
    assert lines["w1_p0001"]["valid_schema"] is False and "schema_invalid" in lines["w1_p0001"]["flags"]
    assert "flags" not in lines["w1_p0002"]
    assert json.loads(finals(env.coord)[0]["headers"]["x-stats"])["n_flagged"] == 1
    assert len(env.ollama.chats) == 5  # 3 + 2 retries, never more than one retry


def test_kill_mid_shard_restart_partial_then_skip_ids(env):
    passages = make_passages("w1", 10)
    env.coord.add_job("job-k", "label", label_pin(env), passages)

    def die(body, n):
        if n == 5:
            raise Killed()

    env.ollama.on_chat = die
    w1 = env.make_worker()
    w1.startup()
    [hj] = w1.lease_jobs()
    with pytest.raises(Killed):
        w1.run_job(hj)  # process "dies": no shutdown, no release, no upload
    assert env.coord.puts == [] and env.coord.releases == []
    assert env.coord.state["job-k"] == "leased"

    # Restart: before leasing, the checkpoint is uploaded as a partial and the job released.
    env.ollama.on_chat = None
    w2 = env.make_worker()
    w2.run()
    part = partials(env.coord, "job-k")
    assert len(part) == 1
    done_first = [l["passage_id"] for l in part[0]["lines"]]
    assert done_first == [p["passage_id"] for p in passages[:4]]
    assert ["job-k"] in env.coord.releases
    # Re-lease carried skip_passage_ids; the final has only the new passages.
    assert env.coord.leases[-1]  # leased again
    fin = finals(env.coord, "job-k")
    assert len(fin) == 1
    rest = [l["passage_id"] for l in fin[0]["lines"]]
    assert rest == [p["passage_id"] for p in passages[4:]]
    assert set(done_first).isdisjoint(rest)
    assert env.coord.state["job-k"] == "done"
    # Passages already done were not re-run.
    assert len(env.ollama.chats) == 4 + 1 + 6  # 4 ok + the fatal one + remaining 6


def test_graceful_stop_uploads_partial_and_releases(env):
    env.coord.add_job("job-s", "label", label_pin(env), make_passages("w1", 10))
    holder = {}

    def stop_after(body, n):
        if n == 3:
            holder["w"].stop.set()

    env.ollama.on_chat = stop_after
    w = env.make_worker()
    holder["w"] = w
    w.run()
    part = partials(env.coord, "job-s")
    assert len(part) == 1 and len(part[0]["lines"]) == 3
    assert ["job-s"] in env.coord.releases
    assert finals(env.coord) == []
    assert Outbox(env.root).entries() == []


def test_offline_upload_stays_in_outbox_then_flushes_on_restart(env):
    env.coord.add_job("job-o", "workcheck", wc_pin(env), make_passages("w1", 3))
    env.coord.down = {"/v1/result"}
    w = env.make_worker()
    w.run()
    assert env.coord.puts == []
    es = Outbox(env.root).entries()
    assert len(es) == 1 and not es[0].partial and es[0].meta["attempts"] >= 1
    # Network returns; a new process (e.g. after reboot) flushes before leasing.
    env.coord.down = set()
    w2 = env.make_worker()
    w2.startup()
    assert [p["job_id"] for p in finals(env.coord)] == ["job-o"]
    assert Outbox(env.root).entries() == []
    assert not any((env.root / "jobs").iterdir())


def test_background_flush_when_network_returns(env):
    env.coord.add_job("job-b", "workcheck", wc_pin(env), make_passages("w1", 2))
    env.coord.down = {"/v1/result"}
    w = env.make_worker()
    w.startup()
    [hj] = w.lease_jobs()
    assert w.run_job(hj) == "done"
    assert len(Outbox(env.root).entries()) == 1
    env.coord.down = set()
    env.clock.advance(10_000)
    assert w.flush_outbox()["acked"] == 1


def test_revoked_job_abandoned(env):
    env.coord.add_job("job-r", "label", label_pin(env), make_passages("w1", 10))
    holder = {}

    def revoke(body, n):
        if n == 2:
            env.coord.revoked.add("job-r")
            holder["w"].heartbeat_once()

    env.ollama.on_chat = revoke
    w = env.make_worker()
    holder["w"] = w
    w.run()
    assert env.coord.puts == []
    assert len(env.ollama.chats) <= 3
    assert any("revoked" in m for m in env.logs)
    assert not any((env.root / "jobs").iterdir())


def test_heartbeat_extends_and_reports(env):
    env.coord.add_job("job-h", "workcheck", wc_pin(env), make_passages("w1", 2))
    w = env.make_worker()
    w.startup()
    [hj] = w.lease_jobs()
    resp = w.heartbeat_once()
    assert resp["extended"] == ["job-h"]
    hb = env.coord.heartbeats[-1]
    assert hb["job_ids"] == ["job-h"] and set(hb["stats"]) == {"tok_s", "passages_done"}


def test_registry_hot_reload_new_pin(env, registry_raw):
    w = env.make_worker()
    w.startup()
    old_label_pin = label_pin(env)
    raw2 = copy.deepcopy(registry_raw)
    raw2["registry_version"] = "test.2"
    raw2["stages"]["label"]["codebook_version"] = "1.0"
    new_pin = Registry.from_dict(raw2).stages["label"].pin_hash()
    assert new_pin != old_label_pin
    env.coord.set_registry(raw2, '"r2"')
    env.coord.add_job("job-new", "label", new_pin, make_passages("w1", 2))
    w.run()
    assert w.registry.version == "test.2"
    assert [p["job_id"] for p in finals(env.coord)] == ["job-new"]
    assert any("hot-reloaded" in m for m in env.logs)


def test_registry_change_retires_running_job(env, registry_raw):
    env.coord.add_job("job-old", "label", label_pin(env), make_passages("w1", 10))
    raw2 = copy.deepcopy(registry_raw)
    raw2["registry_version"] = "test.2"
    raw2["stages"]["label"]["codebook_version"] = "1.0"
    holder = {}

    def swap(body, n):
        if n == 3:
            env.coord.set_registry(raw2, '"r2"')
            holder["w"].refresh_registry(force=True)

    env.ollama.on_chat = swap
    w = env.make_worker()
    holder["w"] = w
    w.run()
    assert ["job-old"] in env.coord.releases
    assert len(partials(env.coord, "job-old")) == 1
    assert finals(env.coord) == []


def test_registry_poll_uses_etag(env):
    w = env.make_worker()
    w.startup()
    assert w.refresh_registry(force=True) is False  # 304


def test_new_model_pulled_automatically(env, registry_raw):
    raw2 = copy.deepcopy(registry_raw)
    raw2["registry_version"] = "test.3"
    raw2["stages"]["workcheck"]["model_ref"] = "fake-wc-v2:4b"
    raw2["stages"]["workcheck"]["model_digest"] = "9" * 64
    env.ollama.pull_digests["fake-wc-v2:4b"] = "9" * 64
    env.coord.set_registry(raw2, '"r3"')
    w = env.make_worker()
    w.startup()
    assert env.ollama.pulls == ["fake-wc-v2:4b"]
    assert "workcheck" in w.stages


def test_low_disk_pauses_leasing_then_resumes(env):
    env.coord.add_job("job-d", "workcheck", wc_pin(env), make_passages("w1", 2))
    env.free[0] = 20 * GB + 1024  # below one job's projected bytes above the reserve
    w = env.make_worker()
    w.run()
    assert env.coord.leases == []
    assert any("leasing paused" in m for m in env.logs)
    env.free[0] = 200 * GB
    env.make_worker().run()
    assert env.coord.state["job-d"] == "done"


def test_oom_at_concurrency_one_demotes_stage(env):
    from ald.backend.ollama import BackendOOM
    env.coord.add_job("job-big", "label", label_pin(env), make_passages("w1", 5))
    env.coord.add_job("job-small", "workcheck", wc_pin(env), make_passages("w2", 2))

    def oom(body, n):
        if "obstacles" in body["format"]["properties"]:
            raise BackendOOM("CUDA error: out of memory")

    env.ollama.on_chat = oom
    w = env.make_worker(idle_polls_before_exit=2)
    w.run()
    assert "label" not in w.stages and w.excluded["label"] == "demoted: OOM at concurrency 1"
    assert ["job-big"] in env.coord.releases
    assert env.coord.state["job-small"] == "done"
    assert env.registry.stages["label"].model_ref == LABEL_MODEL  # pin untouched


def test_window_end_stops_and_releases(env):
    from ald.scheduler import RunWindow
    env.coord.add_job("job-w", "label", label_pin(env), make_passages("w1", 10))

    def tick(body, n):
        env.clock.advance(100)

    env.ollama.on_chat = tick
    w = env.make_worker(window=RunWindow(env.clock.time() + 250, env.clock))
    w.run()
    assert ["job-w"] in env.coord.releases
    assert len(partials(env.coord, "job-w")) == 1


def test_dup_final_supersedes_unacked_partial(env):
    """Partial queued offline, job re-leased (no skip ids yet): final carries
    everything and the stale partial is dropped."""
    passages = make_passages("w1", 6)
    env.coord.add_job("job-x", "label", label_pin(env), passages)
    holder = {}

    def stop(body, n):
        if n == 2:
            env.coord.down = {"/v1/result"}
            holder["w"].stop.set()

    env.ollama.on_chat = stop
    w = env.make_worker()
    holder["w"] = w
    w.run()
    assert len(Outbox(env.root).entries()) == 1
    env.ollama.on_chat = None
    env.coord.down = {"/v1/result"}
    w2 = env.make_worker()
    w2.run()  # leases again; local checkpoint reused as cache
    es = Outbox(env.root).entries()
    assert len(es) == 1 and not es[0].partial and es[0].meta["n_lines"] == 6
    env.coord.down = set()
    env.make_worker().startup()
    assert len(finals(env.coord, "job-x")) == 1 and partials(env.coord) == []
    assert len(env.ollama.chats) == 2 + 4  # the two cached lines were not re-run


# --- auto-update -------------------------------------------------------------

def test_update_available_installs_and_reexecs(env):
    env.coord.ping_resp = {"ok": True, "min_client_version": "0.0.1", "latest_client_version": "9.9.9",
                           "wheel_url": "https://coord.test/ald-9.9.9-py3-none-any.whl"}
    env.coord.add_job("job-u", "workcheck", wc_pin(env), make_passages("w1", 2))
    w = env.make_worker(auto_update=True, argv=["work", "--keep-awake"])
    w.run()
    assert env.run.calls == [["/usr/bin/uv", "tool", "install", "--force", "--python", "3.12",
                              "https://coord.test/ald-9.9.9-py3-none-any.whl"]]
    assert env.reexec_calls == [["work", "--keep-awake"]]
    # Loop guard: a second process within the hour does not retry the same version.
    w2 = env.make_worker(auto_update=True)
    w2.run()
    assert len(env.run.calls) == 1
    env.clock.advance(3601)
    w3 = env.make_worker(auto_update=True)
    w3.run()
    assert len(env.run.calls) == 2


def test_failed_optional_update_keeps_working(env):
    env.run.rc = 1
    env.coord.ping_resp = {"ok": True, "min_client_version": "0.0.1", "latest_client_version": "9.9.9",
                           "wheel_url": None}
    env.coord.add_job("job-f", "workcheck", wc_pin(env), make_passages("w1", 2))
    w = env.make_worker(auto_update=True)
    w.run()
    assert env.run.calls == [["/usr/bin/uv", "tool", "upgrade", "ald"]]
    assert env.reexec_calls == []
    assert env.coord.state["job-f"] == "done"


def test_required_update_blocks_leasing_when_it_fails(env):
    env.run.rc = 1
    env.coord.lease_status = 426
    env.coord.ping_resp = {"ok": True, "min_client_version": "9.0.0", "latest_client_version": "9.0.0",
                           "wheel_url": None}
    env.coord.add_job("job-q", "workcheck", wc_pin(env), make_passages("w1", 2))
    holder = {"n": 0}
    w = env.make_worker(auto_update=True, exit_when_idle=False)

    orig_sleep = env.clock.sleep

    def sleep(s, stop=None):
        holder["n"] += 1
        if holder["n"] >= 3:
            w.stop.set()
        return orig_sleep(s, stop)

    env.clock.sleep = sleep
    w.run()
    assert env.coord.leases == []  # never leased below min_client_version
    assert len(env.run.calls) == 1


def test_no_auto_update_opt_out(env):
    env.coord.ping_resp = {"ok": True, "min_client_version": "0.0.1", "latest_client_version": "9.9.9"}
    env.coord.add_job("job-n", "workcheck", wc_pin(env), make_passages("w1", 1))
    env.make_worker(auto_update=False).run()
    assert env.run.calls == [] and env.coord.state["job-n"] == "done"


def test_shard_text_sha_mismatch_flagged(env):
    ps = make_passages("w1", 2)
    ps[1]["text_sha256"] = "0" * 64
    env.coord.add_job("job-t", "workcheck", wc_pin(env), ps)
    env.make_worker().run()
    lines = finals(env.coord)[0]["lines"]
    assert "text_sha256_mismatch" in lines[1]["flags"]


# --- GPU residency ---------------------------------------------------------------

def test_stray_models_unloaded_before_work(env):
    env.ollama.loaded = {"someone-elses-model:70b": 40_000_000_000}
    env.coord.add_job("job-g", "workcheck", wc_pin(env), make_passages("w1", 2))
    env.make_worker().run()
    assert "someone-elses-model:70b" in env.ollama.unloads
    assert any("unloaded resident model" in m for m in env.logs)
    assert env.coord.state["job-g"] == "done"


def test_other_stage_model_unloaded_between_jobs(env):
    env.coord.add_job("job-a", "workcheck", wc_pin(env), make_passages("w1", 2))
    env.coord.add_job("job-b", "label", label_pin(env), make_passages("w2", 2))
    env.make_worker().run()
    # When the label job starts, the screen model is evicted first.
    assert WC_MODEL in env.ollama.unloads


def test_split_model_reloaded_then_demoted(env):
    env.ollama.split = {LABEL_MODEL}
    env.coord.add_job("job-split", "label", label_pin(env), make_passages("w1", 6))
    env.coord.add_job("job-ok", "workcheck", wc_pin(env), make_passages("w2", 2))
    w = env.make_worker(idle_polls_before_exit=2)
    w.run()
    assert any("only 50% on GPU" in m for m in env.logs)
    assert "label" not in w.stages and w.excluded["label"] == "demoted: model only 50% on GPU"
    assert ["job-split"] in env.coord.releases
    assert len(partials(env.coord, "job-split")) == 1
    assert env.coord.state["job-ok"] == "done"


def test_cpu_only_machine_skips_residency(env):
    from ald.hw import HardwareInfo
    hw = HardwareInfo(os="linux", arch="x86_64", os_release="t", cpu_model="t", cpu_cores_physical=8,
                      cpu_cores_logical=8, ram_gb=64, usable_vram_gb=20.0, accel="cpu")
    env.ollama.loaded = {"other:1b": 1}
    env.coord.add_job("job-c", "workcheck", wc_pin(env), make_passages("w1", 1))
    env.make_worker(hw=hw).run()
    assert env.ollama.unloads == []


def test_stale_pin_not_in_active_pins_is_not_run(env, registry_raw):
    raw = copy.deepcopy(registry_raw)
    raw["active_pins"] = [wc_pin(env)]
    env.coord.set_registry(raw, '"r-ap"')
    env.coord.add_job("job-l", "label", label_pin(env), make_passages("w1", 1))
    w = env.make_worker()
    w.run()
    assert "stale" in w.excluded["label"]
    assert all("label" not in l["stages"] for l in env.coord.leases)


def test_426_body_drives_update(env):
    env.coord.lease_status = 426
    env.coord.ping_resp = {"ok": True, "min_client_version": "0.0.1", "latest_client_version": "0.1.0",
                           "wheel_url": None}
    env.coord.add_job("job-z", "workcheck", wc_pin(env), make_passages("w1", 1))
    w = env.make_worker(auto_update=True, idle_polls_before_exit=1)
    w.startup()
    w.lease_jobs()
    assert w._update_required
    # FakeCoordinator's 426 body has no version info -> ping decides; with info the body wins.
    from ald.client import UpgradeRequired
    from ald.updater import decide
    d = decide({"min_client_version": "9.0.0", "latest_client_version": "9.1.0", "wheel_url": "http://x/w.whl"})
    assert d.required and d.update_available and d.wheel_url == "http://x/w.whl"


# --- generic stages ---------------------------------------------------------------

def test_embed_stage_generic(env):
    from ald.inference import decode_f16
    from ald.hw import HardwareInfo
    hw = HardwareInfo(os="linux", arch="x86_64", os_release="t", cpu_model="t", cpu_cores_physical=8,
                      cpu_cores_logical=8, ram_gb=16, usable_vram_gb=0.0, accel="cpu")
    pin = env.registry.stages["embed"].pin_hash()
    env.coord.add_job("job-e", "embed", pin, make_passages("w1", 3))
    w = env.make_worker(hw=hw)
    w.cfg.tier = None
    w.tier = None
    w.run()
    assert w.tier == "cpu" and w.stages == ["embed"]
    put = finals(env.coord, "job-e")[0]
    l = put["lines"][0]
    assert l["evidence"] == [] and l["valid_schema"] is True
    vec = decode_f16(l["output"]["embedding_f16_b64"])
    assert len(vec) == l["output"]["dim"] == 8
    assert env.ollama.chats[0]["model"] == "fake-embed:300m" and "input" in env.ollama.chats[0]


def test_null_evidence_field_skips_verification(env):
    env.coord.add_job("job-c", "cloze", env.registry.stages["cloze"].pin_hash(), make_passages("w1", 2))
    env.make_worker().run()
    l = finals(env.coord, "job-c")[0]["lines"][0]
    assert l["output"] == {"name": "Elizabeth"} and l["evidence"] == [] and "flags" not in l


def test_worker_requests_all_allowed_stages(env):
    w = env.make_worker()
    w.run()
    assert env.coord.leases[0]["stages"] == ["label", "alt_label", "cloze", "workcheck"]
    assert w.tuners["label"].current == 1  # max_concurrency=1 in tests caps the tier hint (4)


def test_shared_model_not_unloaded_between_stages(env):
    # label and cloze share one model: switching between them must not evict it.
    env.coord.add_job("job-l", "label", label_pin(env), make_passages("w1", 1))
    env.coord.add_job("job-c", "cloze", env.registry.stages["cloze"].pin_hash(), make_passages("w2", 1))
    env.make_worker().run()
    assert LABEL_MODEL not in env.ollama.unloads


def test_coordinator_unknown_stage_dropped(env):
    env.coord.unknown_stages = {"alt_label", "workcheck"}
    env.coord.add_job("job-1", "label", label_pin(env), make_passages("w1", 1))
    w = env.make_worker()
    w.run()
    assert env.coord.state["job-1"] == "done"
    assert env.coord.leases[-1]["stages"] == ["label", "cloze"]
    assert w.excluded["workcheck"] == "coordinator does not know this stage"
