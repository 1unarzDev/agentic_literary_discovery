import json
import subprocess
from collections import namedtuple
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ald import CLIENT_VERSION, service
from ald.hw import nvidia_smi_path, parse_nvidia_smi, parse_rocm_smi
from ald.updater import Updater, decide, uv_install_cmd
from conftest import FakeClock, FakeRun

P = namedtuple("P", "returncode stdout stderr")


# --- hw -----------------------------------------------------------------------

def test_parse_nvidia_smi():
    g = parse_nvidia_smi("NVIDIA GeForce RTX 4070 Ti SUPER, 16376\nNVIDIA RTX A6000, 49140\n")
    assert [x.name for x in g] == ["NVIDIA GeForce RTX 4070 Ti SUPER", "NVIDIA RTX A6000"]
    assert g[0].vram_gb == pytest.approx(15.99, abs=0.01)


def test_parse_rocm_smi():
    out = json.dumps({"card0": {"VRAM Total Memory (B)": str(24 * 1024 ** 3), "VRAM Total Used Memory (B)": "1"}})
    g = parse_rocm_smi(out)
    assert len(g) == 1 and g[0].vram_gb == 24.0 and g[0].vendor == "amd"
    assert parse_rocm_smi("not json") == []


def test_nvidia_smi_windows_fallback(monkeypatch, tmp_path):
    sysroot = tmp_path / "Windows"
    (sysroot / "System32").mkdir(parents=True)
    exe = sysroot / "System32" / "nvidia-smi.exe"
    exe.write_text("")
    monkeypatch.setenv("SystemRoot", str(sysroot))
    assert nvidia_smi_path(which=lambda n: None, system="Windows") == str(exe)
    assert nvidia_smi_path(which=lambda n: None, system="Linux") is None


# --- updater --------------------------------------------------------------------

def test_decide():
    d = decide({"min_client_version": "0.1.0", "latest_client_version": "0.2.0", "wheel_url": "u"}, current="0.1.0")
    assert d.update_available and not d.required
    d = decide({"min_client_version": "0.2.0", "latest_client_version": "0.2.0"}, current="0.1.0")
    assert d.required
    d = decide({"min_client_version": "0.0.1", "latest_client_version": None}, current="0.1.0")
    assert not d.update_available and not d.required


def test_uv_cmd():
    assert uv_install_cmd("https://c/dist/ald-0.2.0-py3-none-any.whl", "uv") == [
        "uv", "tool", "install", "--force", "--python", "3.12", "https://c/dist/ald-0.2.0-py3-none-any.whl"]
    assert uv_install_cmd(None, "uv") == ["uv", "tool", "upgrade", "ald"]


def test_updater_guard_and_log(tmp_path):
    clock = FakeClock()
    run = FakeRun(rc=1)
    execs = []
    u = Updater(tmp_path / "u.json", current="0.1.0", run=run, reexec=execs.append, clock=clock.time,
                which=lambda n: "uv", log=lambda m: None)
    d = decide({"latest_client_version": "0.2.0", "wheel_url": "w"}, current="0.1.0")
    assert u.apply(d, ["work"]) is False and execs == []
    assert u.apply(d, ["work"]) is False and len(run.calls) == 1  # guarded for an hour
    clock.advance(3600)
    run.rc = 0
    assert u.apply(d, ["work"]) is True and execs == [["work"]]
    state = json.loads((tmp_path / "u.json").read_text())
    assert [e["ok"] for e in state["log"]] == [False, True]


def test_updater_without_uv(tmp_path):
    u = Updater(tmp_path / "u.json", run=FakeRun(), reexec=lambda a: None, which=lambda n: None, log=lambda m: None)
    assert u.apply(decide({"latest_client_version": "99.0.0"}), []) is False


# --- service ---------------------------------------------------------------------

def test_systemd_unit_and_install(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    calls = []
    msgs = service.install(run=lambda c: (calls.append(c), P(0, "", ""))[1], platform="linux")
    unit = (tmp_path / "systemd" / "user" / "ald-worker.service").read_text()
    assert "ExecStart=" in unit and " work --keep-awake" in unit and "Restart=on-failure" in unit
    assert "KillSignal=SIGTERM" in unit
    assert ["systemctl", "--user", "enable", "--now", "ald-worker.service"] in calls
    assert any("enable-linger" in m for m in msgs)
    # idempotent
    service.install(run=lambda c: P(0, "", ""), platform="linux")
    service.uninstall(run=lambda c: P(0, "", ""), platform="linux")
    assert not (tmp_path / "systemd" / "user" / "ald-worker.service").exists()


def test_launchd_plist():
    xml = service.launchd_plist(["/u/bin/ald", "work", "--keep-awake"], Path("/tmp/l.log"))
    assert "<string>org.ald.worker</string>" in xml and "<string>work</string>" in xml
    assert "<key>RunAtLoad</key><true/>" in xml


def test_windows_task_command():
    calls = []
    service.install(run=lambda c: (calls.append(c), P(0, "", ""))[1], platform="win32")
    create = calls[0]
    assert create[:3] == ["schtasks", "/Create", "/TN"] and "ONLOGON" in create
    assert "work --keep-awake" in create[create.index("/TR") + 1]


# --- CLI --------------------------------------------------------------------------

@pytest.fixture
def cli_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ALD_HOME", str(tmp_path))
    monkeypatch.delenv("ALD_COORDINATOR", raising=False)
    monkeypatch.delenv("ALD_TOKEN", raising=False)
    return tmp_path


def test_cli_version_and_pins(cli_home):
    from ald.cli import app
    r = CliRunner().invoke(app, ["version"])
    assert r.exit_code == 0 and r.stdout.strip() == CLIENT_VERSION
    r = CliRunner().invoke(app, ["pins"])
    assert r.exit_code == 0
    pins = json.loads(r.stdout)
    assert {p["stage"] for p in pins} == {"screen", "label", "adjudicate"}


def test_cli_status_local(cli_home):
    from ald.cli import app
    from ald.results import Outbox
    Outbox(cli_home / "data").add("j1", b"x", {}, partial=True, n_lines=1, created=0)
    r = CliRunner().invoke(app, ["status", "--local", "--json"])
    assert r.exit_code == 0, r.stdout
    rep = json.loads(r.stdout)
    assert rep["outbox"]["entries"] == 1 and "budget_bytes" in rep["disk"]


def test_cli_work_requires_join(cli_home):
    from ald.cli import app
    r = CliRunner().invoke(app, ["work", "--dry-run"])
    assert r.exit_code == 1 and "not joined" in r.stdout


def test_config_saved_chmod_600(cli_home):
    import os
    import stat
    from ald.config import Config, config_path
    Config(coordinator_url="https://c", token="t").save()
    if os.name == "posix":
        assert stat.S_IMODE(os.stat(config_path()).st_mode) == 0o600
    assert Config.load().token == "t"


def test_safe_names_have_no_colons():
    from ald.config import safe_name
    assert ":" not in safe_name("wave1:shard:0001") and "/" not in safe_name("a/b\\c")
