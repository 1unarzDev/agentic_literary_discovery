"""Tier-specific Ollama server settings (``ald setup`` / ``ald work``)."""

from __future__ import annotations

import subprocess

import pytest

from ald import ollama_env as oe


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ALD_HOME", str(tmp_path))
    return tmp_path


def test_wanted_env():
    assert oe.wanted_env(2, "cuda") == {"OLLAMA_NUM_PARALLEL": "2", "OLLAMA_KEEP_ALIVE": "30m",
                                        "OLLAMA_FLASH_ATTENTION": "1", "OLLAMA_MAX_LOADED_MODELS": "1",
                                        "LLAMA_ARG_CACHE_RAM": "0"}
    assert oe.wanted_env(None, "cpu") == {"OLLAMA_NUM_PARALLEL": "1", "OLLAMA_KEEP_ALIVE": "30m",
                                          "OLLAMA_MAX_LOADED_MODELS": "1", "LLAMA_ARG_CACHE_RAM": "0"}
    assert oe.wanted_env(2, "cuda", host_prompt_cache_mb=1024)["LLAMA_ARG_CACHE_RAM"] == "1024"
    assert oe.wanted_env(6, "metal")["OLLAMA_FLASH_ATTENTION"] == "1"


def test_dropin_text():
    t = oe._dropin_text({"OLLAMA_NUM_PARALLEL": "6", "OLLAMA_KEEP_ALIVE": "30m"})
    assert "[Service]\n" in t
    assert 'Environment="OLLAMA_KEEP_ALIVE=30m"\nEnvironment="OLLAMA_NUM_PARALLEL=6"\n' in t


def _fake(monkeypatch, *, platform, running=True, match=None, stop_ok=True):
    calls = {"stop": 0, "start": [], "run": []}
    monkeypatch.setattr(oe.sys, "platform", platform)
    monkeypatch.setattr(oe, "up", lambda url="", timeout=2.0: running or bool(calls["start"]))
    monkeypatch.setattr(oe, "wait_up", lambda url, s: True)
    monkeypatch.setattr(oe, "_running_matches", lambda env: match)
    monkeypatch.setattr(oe, "_systemd_ollama", lambda: False)
    monkeypatch.setattr(oe.time, "sleep", lambda s: None)

    def stop(log):
        calls["stop"] += 1
        return stop_ok

    def start(env, log, prefer_app=True):
        calls["start"].append((dict(env), prefer_app))
        return "started"

    def run(cmd, timeout=60):
        calls["run"].append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(oe, "stop", stop)
    monkeypatch.setattr(oe, "start", start)
    monkeypatch.setattr(oe, "_run", run)
    return calls


def test_linux_user_ollama_restarted_only_when_its_env_differs(home, monkeypatch):
    env = oe.wanted_env(6, "cuda")
    calls = _fake(monkeypatch, platform="linux", match=True)
    monkeypatch.setattr(oe, "DROPIN", home / "no-such-dir" / "ald.conf")
    rep = oe.ensure(env, url="http://x", log=lambda m: None)
    assert not rep["restarted"] and calls["stop"] == 0
    assert (home / "config" / "ollama.env").read_text() == \
        "LLAMA_ARG_CACHE_RAM=0\nOLLAMA_FLASH_ATTENTION=1\nOLLAMA_KEEP_ALIVE=30m\nOLLAMA_MAX_LOADED_MODELS=1\nOLLAMA_NUM_PARALLEL=6\n"
    calls = _fake(monkeypatch, platform="linux", match=False)
    rep = oe.ensure(env, url="http://x", log=lambda m: None)
    assert rep["restarted"] and calls["stop"] == 1 and calls["start"][0][0] == env


def test_windows_setx_marker_and_service_mode(home, monkeypatch):
    env = oe.wanted_env(2, "cuda")
    calls = _fake(monkeypatch, platform="win32", match=None)
    monkeypatch.setattr(oe, "_persist_windows", lambda e, log: True)  # values changed
    rep = oe.ensure(env, url="http://x", log=lambda m: None, service_mode=True)
    assert rep["restarted"] and calls["start"] == [(env, False)]  # service: plain `ollama serve`, not the tray app
    # Second run: already applied and nothing changed -> no restart.
    calls = _fake(monkeypatch, platform="win32", match=None)
    monkeypatch.setattr(oe, "_persist_windows", lambda e, log: False)
    rep = oe.ensure(env, url="http://x", log=lambda m: None)
    assert not rep["restarted"] and calls["stop"] == 0


def test_starts_ollama_when_down(home, monkeypatch):
    env = oe.wanted_env(2, "cuda")
    calls = _fake(monkeypatch, platform="win32", running=False)
    monkeypatch.setattr(oe, "_persist_windows", lambda e, log: False)
    rep = oe.ensure(env, url="http://x", log=lambda m: None)
    assert rep["started"] == "started" and calls["start"] == [(env, True)] and calls["stop"] == 0


def test_persist_windows_uses_setx(monkeypatch):
    seen = []
    monkeypatch.setattr(oe, "_run", lambda cmd, timeout=60: (seen.append(cmd), subprocess.CompletedProcess(cmd, 0))[1])
    assert oe._persist_windows({"OLLAMA_NUM_PARALLEL": "2"}, log=lambda m: None) is True  # no winreg here
    assert seen == [["setx", "OLLAMA_NUM_PARALLEL", "2"]]
