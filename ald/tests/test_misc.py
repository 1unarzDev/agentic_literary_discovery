import json
import os
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


def test_updater_windows_defers_to_helper(tmp_path, monkeypatch):
    monkeypatch.setattr("ald.updater.shutil.which", lambda n: r"C:\u\.local\bin\ald.exe" if n == "ald" else None)
    spawned, exits, run = [], [], FakeRun()
    u = Updater(tmp_path / "u.json", current="0.1.0", run=run, reexec=lambda a: None, which=lambda n: r"C:\u\uv.exe",
                log=lambda m: None, platform="win32", spawn=spawned.append, exit_fn=exits.append, service_mode=True)
    d = decide({"latest_client_version": "0.2.0", "wheel_url": "https://c/dist/ald-0.2.0-py3-none-any.whl"}, current="0.1.0")
    assert u.apply(d, ["work", "--keep-awake", "--service"]) is True
    assert run.calls == [] and exits == [0]  # nothing installed in-process; the process exits
    script = spawned[0].read_bytes().decode("utf-8")
    assert "\r\n" in script and f"PID eq {os.getpid()}" in script
    assert "uv.exe tool install --force --python 3.12 https://c/dist/ald-0.2.0-py3-none-any.whl" in script
    assert script.index("tool install") < script.index("schtasks /Run /TN ald-worker")
    assert not u.can_attempt("0.2.0")  # loop guard still applies
    # interactive `ald work`: relaunch in a new console with the same arguments
    u2 = Updater(tmp_path / "u2.json", current="0.1.0", run=run, which=lambda n: "uv", log=lambda m: None,
                 platform="win32", spawn=spawned.append, exit_fn=exits.append)
    u2.apply(d, ["work", "--hours", "2"])
    assert 'start "ald" C:\\u\\.local\\bin\\ald.exe work --hours 2' in spawned[1].read_text(encoding="utf-8")


def test_updater_without_uv(tmp_path):
    u = Updater(tmp_path / "u.json", run=FakeRun(), reexec=lambda a: None, which=lambda n: None, log=lambda m: None)
    assert u.apply(decide({"latest_client_version": "99.0.0"}), []) is False


# --- service ---------------------------------------------------------------------

def test_systemd_unit_and_install(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    calls = []
    msgs = service.install(run=lambda c: (calls.append(c), P(0, "", ""))[1], platform="linux")
    unit = (tmp_path / "systemd" / "user" / "ald-worker.service").read_text()
    assert "ExecStart=" in unit and " work --service" in unit and "Restart=always" in unit
    assert "KillSignal=SIGTERM" in unit
    assert ["systemctl", "--user", "enable", "--now", "ald-worker.service"] in calls
    assert any("enable-linger" in m for m in msgs)
    # idempotent
    service.install(run=lambda c: P(0, "", ""), platform="linux")
    service.uninstall(run=lambda c: P(0, "", ""), platform="linux")
    assert not (tmp_path / "systemd" / "user" / "ald-worker.service").exists()


def test_service_without_systemctl(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("PATH", str(tmp_path))  # nothing on PATH
    msgs = service.install(platform="linux")
    assert any("-> 127" in m for m in msgs)  # reported, not raised


def test_launchd_plist():
    xml = service.launchd_plist(["/u/bin/ald", "work", "--keep-awake"], Path("/tmp/l.log"))
    assert "<string>org.ald.worker</string>" in xml and "<string>work</string>" in xml
    assert "<key>RunAtLoad</key><true/>" in xml


def test_windows_task_xml():
    cmd = service.windows_command(python=r"C:\Users\a b\tools\ald\Scripts\python.exe")
    assert cmd[0].endswith("pythonw.exe") and cmd[1:] == ["-m", "ald", "work", "--service"]
    xml = service.windows_task_xml(cmd, r"PC\a b", s4u=True, workdir=r"C:\Users\a b")
    import xml.etree.ElementTree as ET
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    root = ET.fromstring(xml.replace('encoding="UTF-16"', ""))
    assert root.find("t:Principals/t:Principal/t:LogonType", ns).text == "S4U"
    assert root.find("t:Triggers/t:BootTrigger", ns) is not None
    st = root.find("t:Settings", ns)
    assert st.find("t:ExecutionTimeLimit", ns).text == "PT0S"  # no 72 h default limit
    assert st.find("t:DisallowStartIfOnBatteries", ns).text == "false"
    assert st.find("t:StopIfGoingOnBatteries", ns).text == "false"
    assert root.find("t:Actions/t:Exec/t:Arguments", ns).text == "-m ald work --service"
    xml = service.windows_task_xml(cmd, r"PC\a", s4u=False, workdir="C:\\")
    root = ET.fromstring(xml.replace('encoding="UTF-16"', ""))
    assert root.find("t:Principals/t:Principal/t:LogonType", ns).text == "InteractiveToken"
    assert root.find("t:Triggers/t:BootTrigger", ns) is None


def test_windows_install_falls_back_to_logon_task(monkeypatch):
    monkeypatch.setattr(service, "_windows_user", lambda: "PC\\vol")
    calls, xmls = [], []

    def run(c):
        calls.append(c)
        if c[:2] == ["schtasks", "/Create"]:
            xmls.append(Path(c[c.index("/XML") + 1]).read_bytes().decode("utf-16"))
            return P(1, "", "ERROR: Access is denied.") if len(xmls) == 1 else P(0, "SUCCESS", "")
        return P(0, "", "")

    msgs = service.install(run=run, platform="win32")
    assert "<LogonType>S4U</LogonType>" in xmls[0] and "<LogonType>InteractiveToken</LogonType>" in xmls[1]
    assert ["schtasks", "/Run", "/TN", "ald-worker"] in calls
    assert any("while PC\\vol is signed in" in m for m in msgs)


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
    assert {p["stage"] for p in pins} == {"workcheck", "label", "alt_label", "cloze", "adjudicate", "embed"}


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


def test_service_verify(tmp_path):
    import time
    p = tmp_path / "state.json"
    assert service.verify(p)[0] is False
    now = time.time()
    p.write_text(json.dumps({"pid": os.getpid(), "updated": now, "last_contact": now - 5, "client_version": "x",
                             "report": {"state": "idle", "keep_awake": True}}))
    ok, msg = service.verify(p, now=now)
    assert ok and "keep-awake on" in msg
    p.write_text(json.dumps({"pid": os.getpid(), "updated": now, "last_contact": None}))
    assert service.verify(p, now=now)[0] is False
    p.write_text(json.dumps({"pid": 2 ** 22 + 12345, "updated": now, "last_contact": now}))
    assert "not running" in service.verify(p, now=now)[1]


def test_windows_xml_has_repeating_trigger():
    xml = service.windows_task_xml(["C:\\py\\pythonw.exe", "-m", "ald"], "PC\\a", s4u=False, workdir="C:\\")
    assert "<Interval>PT10M</Interval>" in xml and "<MultipleInstancesPolicy>IgnoreNew" in xml
    assert "<Count>999</Count>" in xml


def test_refresh_definition_keeps_extra_args_linux(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    p = tmp_path / "systemd" / "user" / "ald-worker.service"
    p.parent.mkdir(parents=True)
    p.write_text("[Service]\nExecStart=/h/.local/bin/ald work --keep-awake --service --gpu-lock /tmp/g.lock\nRestart=on-failure\n")
    calls = []
    msg = service.refresh_definition(run=lambda c: (calls.append(c), P(0, "", ""))[1], platform="linux")
    unit = p.read_text()
    assert "Restart=always" in unit and unit.rstrip().count("--gpu-lock /tmp/g.lock") == 1
    assert ["systemctl", "--user", "daemon-reload"] in calls and "refreshed" in msg
    assert not any("restart" in " ".join(c) for c in calls)  # never restarts the running worker


def test_refresh_definition_windows_keeps_logon_type(monkeypatch):
    monkeypatch.setattr(service, "_windows_user", lambda: "PC\\vol")
    old = "<Task><Principals><Principal><LogonType>S4U</LogonType></Principal></Principals>" \
          "<Actions><Exec><Arguments>-m ald work --keep-awake --service --max-concurrency 2</Arguments></Exec></Actions></Task>"
    created = []

    def run(c):
        if c[:2] == ["schtasks", "/Query"]:
            return P(0, old, "")
        created.append(Path(c[c.index("/XML") + 1]).read_bytes().decode("utf-16"))
        return P(0, "SUCCESS", "")

    msg = service.refresh_definition(run=run, platform="win32")
    assert "S4U" in msg and len(created) == 1
    assert "<LogonType>S4U</LogonType>" in created[0] and "--service --max-concurrency 2</Arguments>" in created[0]
    assert "<Interval>PT10M</Interval>" in created[0]


def test_ui_ascii_fallback(monkeypatch):
    import io
    import sys
    from ald import ui
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(io.BytesIO(), encoding="cp1252"))
    assert set(ui.sparkline([0, 1, 5, 10])) <= set(ui.SPARK_ASCII)
    t = ui.bar([(1, "green"), (1, "grey37")], 10).plain
    assert t.encode("cp1252") and set(t) <= {"#", "."}


def test_config_menu_scripted(cli_home):
    import io
    from rich.console import Console
    from ald import ui
    from ald.config import Config
    answers = iter(["3", "mon-fri 25:00-01:00", "3", "mon-fri 21:00-05:00,07:00-15:00; sat-sun 21:00-05:00",
                    "5", "0", "5", "3", "9", "no", "s", "n"])  # bad schedule and "0" are rejected, then retried
    changed = ui.config_menu(Console(file=io.StringIO()), lambda q: next(answers), restart=lambda: [])
    cfg = Config.load()
    assert changed and cfg.schedule == "mon-fri 21:00-05:00,07:00-15:00; sat-sun 21:00-05:00"
    assert cfg.max_concurrency == 3 and cfg.keep_awake is False


def test_config_set_cli(cli_home):
    from ald.cli import app
    from ald.config import Config
    r = CliRunner().invoke(app, ["config", "set", "stages", "label,workcheck"])
    assert r.exit_code == 0 and Config.load().stages == ["label", "workcheck"]
    assert CliRunner().invoke(app, ["config", "set", "active_hours", "25:00-01:00"]).exit_code == 2
    assert CliRunner().invoke(app, ["config", "set", "nope", "1"]).exit_code == 2


def test_windows_install_keeps_admin_created_task(monkeypatch):
    monkeypatch.setattr(service, "_windows_user", lambda: "PC\\vol")
    calls = []

    def run(c):
        calls.append(c)
        if c[:2] == ["schtasks", "/Create"]:
            return P(1, "", "ERROR: Access is denied.")
        return P(0, "", "")

    msgs = service.install(run=run, platform="win32")
    assert any("kept it" in m for m in msgs) and not any(m.startswith("FAILED") for m in msgs)
    assert ["schtasks", "/Run", "/TN", "ald-worker"] in calls


def test_launchd_plist_is_valid_and_robust():
    import plistlib
    d = plistlib.loads(service.launchd_plist(["/Users/a b/.local/bin/ald", "work", "--service", "--gpu-lock", "/tmp/x&y"],
                                             Path("/Users/a b/Library/Logs/ald-worker.log")).encode())
    assert d["Label"] == "org.ald.worker" and d["RunAtLoad"] is True and d["KeepAlive"] is True
    assert d["ThrottleInterval"] == 30 and d["ProgramArguments"][-1] == "/tmp/x&y"
    assert "/opt/homebrew/bin" in d["EnvironmentVariables"]["PATH"]


def test_mac_refresh_definition_keeps_args(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    p = tmp_path / "Library" / "LaunchAgents" / "org.ald.worker.plist"
    p.parent.mkdir(parents=True)
    p.write_text(service.launchd_plist(["/u/ald", "work", "--keep-awake", "--service", "--max-concurrency", "3"],
                                       tmp_path / "l.log"))
    assert "refreshed" in service.refresh_definition(run=lambda c: P(0, "", ""), platform="darwin")
    import plistlib
    assert plistlib.loads(p.read_bytes())["ProgramArguments"][-2:] == ["--max-concurrency", "3"]


def test_client_reads_retry_after():
    import httpx
    from ald.client import CoordinatorClient
    t = httpx.MockTransport(lambda req: httpx.Response(200, json={"jobs": [], "retry_after": 300}))
    c = CoordinatorClient("http://c.test", "tok", transport=t)
    assert c.lease("t12", ["label"], 1) == [] and c.last_retry_after == 300.0
    t2 = httpx.MockTransport(lambda req: httpx.Response(200, json={"jobs": [{"job_id": "j"}]}))
    c2 = CoordinatorClient("http://c.test", "tok", transport=t2)
    assert c2.lease("t12", ["label"], 1) == [{"job_id": "j"}] and c2.last_retry_after is None


def test_tests_never_touch_the_real_config():
    from ald import config as cfgmod
    assert str(Path.home()) not in str(cfgmod.config_path().resolve()) or "pytest" in str(cfgmod.config_path())


def test_config_survives_update_and_stale_writers(tmp_path):
    """Values set with `ald config set` survive a client self-update (new version reads the old file, with a
    key it does not know) and a long-running process that holds an older Config."""
    from ald.config import Config, config_path
    c = Config(coordinator_url="https://coord", token="tok", worker_id="w1", name="box", tier="t16")
    c.save()
    stale = Config.load()                     # e.g. the running worker / a benchmark, loaded earlier
    user = Config.load()
    user.update(min_free_ram_gb=5.0, gpu_lock="/tmp/g.lock", schedule="daily 22:00-07:00")  # `ald config set`
    stale.update(tier="t12")                  # the stale holder writes one field later
    raw = json.loads(config_path().read_text())
    raw["some_future_key"] = 1                # a later release added a field
    config_path().write_text(json.dumps(raw))
    after = Config.load()                     # what the updated client reads
    assert (after.min_free_ram_gb, after.gpu_lock, after.schedule, after.tier) == (5.0, "/tmp/g.lock", "daily 22:00-07:00", "t12")
    assert (after.token, after.worker_id, after.coordinator_url) == ("tok", "w1", "https://coord")
    after.update(name="box2")
    assert json.loads(config_path().read_text())["some_future_key"] == 1  # unknown keys are kept too
