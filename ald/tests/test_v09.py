"""v0.9 rollout: shared-model num_ctx, KV cache type, lean anyOf schema, pause/resume."""

from __future__ import annotations

import json

import pytest

from ald import ollama_env as oe
from ald.registry import Registry, Stage
from conftest import make_passages


def label_pin(env):
    return env.registry.stages["label"].pin_hash()


# --- 1. one model, one num_ctx at a time ------------------------------------------------------------
def test_model_with_other_num_ctx_is_unloaded_before_job(env, monkeypatch):
    env.coord.add_job("job-1", "label", label_pin(env), make_passages("w1", 2))
    w = env.make_worker()
    w.startup()
    st = w.registry.stages["label"]
    model = st.model_ref
    env.ollama.loaded[model] = 6_000_000_000
    real_handler = env.ollama.handler

    def handler(req):  # /api/ps reports the resident copy with another context size
        r = real_handler(req)
        if req.url.path == "/api/ps":
            data = r.json()
            for m in data["models"]:
                m["context_length"] = 2048 if m["name"] == model and st.num_ctx != 2048 else st.num_ctx
            import httpx
            return httpx.Response(200, json=data)
        return r

    env.ollama.handler = handler
    w.backend._http._transport = __import__("httpx").MockTransport(handler)
    w.run()
    assert env.coord.state == {"job-1": "done"}
    assert model in env.ollama.unloads
    assert any("reloading" in m for m in env.logs)


def test_matching_num_ctx_is_kept(env):
    w = env.make_worker()
    w.startup()
    st = w.registry.stages["label"]
    assert w.ensure_model_context(st) is False  # not loaded
    env.ollama.loaded[st.model_ref] = 1
    assert w.ensure_model_context(st) is False  # FakeOllama reports no context_length -> unknown, keep


# --- 2. KV cache type ------------------------------------------------------------------------------------
def test_kv_cache_type_hint_env(registry_raw):
    raw = json.loads(json.dumps(registry_raw))
    first = next(iter(raw["tiers"])) if isinstance(raw["tiers"], dict) else None
    if first is None:
        pytest.skip("list-form tiers")
    raw["tiers"][first] = {**raw["tiers"][first], "kv_cache_type_hint": "q8_0", "num_parallel_hint": 4}
    reg = Registry.from_dict(raw)
    assert reg.kv_cache_type_hint(first) == "q8_0"
    env = oe.tier_env(reg, first, "cpu")
    assert env["OLLAMA_KV_CACHE_TYPE"] == "q8_0" and env["OLLAMA_FLASH_ATTENTION"] == "1"  # q8_0 needs FA
    assert env["OLLAMA_NUM_PARALLEL"] == "4"
    assert "OLLAMA_KV_CACHE_TYPE" not in oe.wanted_env(4, "cuda")


# --- 4. lean anyOf schema ---------------------------------------------------------------------------------
LEAN = {"anyOf": [
    {"type": "object", "properties": {"has_obstacle": {"const": "no"}, "confidence": {"type": "number"}},
     "required": ["has_obstacle", "confidence"], "additionalProperties": False},
    {"type": "object", "properties": {"has_obstacle": {"enum": ["yes", "unclear"]}, "confidence": {"type": "number"},
                                      "evidence_quote": {"type": "string"}},
     "required": ["has_obstacle", "confidence", "evidence_quote"]},
]}


class _Backend:
    def __init__(self, reply):
        self.reply = reply

    def chat(self, model, messages, *, schema, options, think):
        from ald.backend.ollama import ChatResult
        return ChatResult(content=json.dumps(self.reply), prompt_tokens=10, gen_tokens=5, eval_s=0.1, total_s=0.1, raw={})


@pytest.mark.parametrize("reply,flagged", [
    ({"has_obstacle": "no", "confidence": 0.9}, False),                                   # no quote: not a failure
    ({"has_obstacle": "yes", "confidence": 0.8, "evidence_quote": "the door was locked"}, False),
    ({"has_obstacle": "yes", "confidence": 0.8, "evidence_quote": "a dragon ate the moon whole"}, True),
    ({"has_obstacle": "no"}, True),                                                       # schema failure
])
def test_lean_schema_flagging(reply, flagged):
    from ald.inference import is_flagged, run_passage
    st = Stage("label", {"model_ref": "m", "model_digest": "d", "ollama_version_range": ">=0", "schema": LEAN,
                         "system_template": "s", "user_template": "{text}", "evidence_field": "evidence_quote"})
    p = {"passage_id": "p1", "text": "She tried, but the door was locked and the key was gone."}
    line = run_passage(_Backend(reply), st, p, pin_hash="x", model_digest="d", backend_version="t")
    assert is_flagged(line) is flagged
    if reply.get("has_obstacle") == "no" and "confidence" in reply:
        assert line["evidence"] == [] and line["valid_schema"] is True


# --- 5. pause / resume ------------------------------------------------------------------------------------
def test_pause_interrupts_job_uploads_partial_and_blocks_updates(env, monkeypatch, tmp_path):
    from ald import config as cfgmod
    marker = tmp_path / "paused"
    monkeypatch.setattr(cfgmod, "pause_marker", lambda: marker)
    env.coord.add_job("job-1", "label", label_pin(env), make_passages("w1", 6))

    def on_chat(body, n):
        if n == 2:  # an update is released and the volunteer pauses, mid-job
            env.coord.ping_resp.update({"latest_client_version": "99.0.0", "wheel_url": "http://coord.test/dist/x.whl"})
            marker.write_text("paused")
            env.clock.advance(400)

    env.ollama.on_chat = on_chat
    w = env.make_worker(auto_update=True)
    w.run()  # exit_when_idle: returns once paused
    assert env.coord.state == {"job-1": "queued"}            # handed back...
    assert [p["partial"] for p in env.coord.puts] == [True]   # ...after uploading what it had
    assert env.reexec_calls == [] and any("[pause]" in m for m in env.logs)  # no update while paused


def test_cli_pause_resume(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from ald.cli import app
    from ald import config as cfgmod
    monkeypatch.setenv("ALD_HOME", str(tmp_path))
    assert CliRunner().invoke(app, ["pause"]).exit_code == 0 and cfgmod.pause_marker().exists()
    assert CliRunner().invoke(app, ["resume"]).exit_code == 0 and not cfgmod.pause_marker().exists()


def test_windows_update_helper_respects_pause_and_disabled(tmp_path):
    from ald.updater import windows_update_script
    s = windows_update_script(["uv", "tool", "install"], "schtasks /Run /TN ald-worker", 42, tmp_path / "u.log",
                              pause_file=tmp_path / "paused")
    i_inst, i_pause, i_dis, i_run = (s.index("uv tool install"), s.index("paused: not relaunching"),
                                     s.index('find /i "Disabled"'), s.index("schtasks /Run"))
    assert i_inst < i_pause < i_run and i_dis < i_run and ":end" in s
