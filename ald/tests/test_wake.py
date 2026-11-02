"""Sleep / wake around the weekly schedule."""

import datetime as dt
import subprocess
import xml.etree.ElementTree as ET
from collections import namedtuple

from ald import service
from conftest import make_passages

P = namedtuple("P", "returncode stdout stderr")
USER = "mon-fri 21:00-05:00,07:00-15:00; sat-sun 21:00-05:00"
NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


class FakeKA:
    enabled = True

    def __init__(self):
        self.held = False
        self.calls = []

    def hold(self):
        self.calls.append("hold")
        self.held = True

    def release(self):
        self.calls.append("release")
        self.held = False

    def alive(self):
        return self.held


def _sched_around(clock, start_in_h, length_h=1):
    now = dt.datetime.fromtimestamp(clock.time())
    a = now + dt.timedelta(hours=start_in_h)
    b = a + dt.timedelta(hours=length_h)
    day = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[a.weekday()]
    return f"{day} {a:%H:%M}-{b:%H:%M}"


def test_short_gap_stays_awake(env):
    w = env.make_worker(schedule=_sched_around(env.clock, 1))  # next window in 1 h < 120 min
    w.keep_awake = FakeKA()
    w.keep_awake_policy()
    assert w.keep_awake.held


def test_long_gap_reports_then_allows_sleep(env, monkeypatch):
    armed = []
    monkeypatch.setattr(service, "schedule_wake_at", lambda epoch, **k: (armed.append(epoch), "rtcwake: ok")[1])
    w = env.make_worker(schedule=_sched_around(env.clock, 5))  # 5 h away
    w.keep_awake = FakeKA()
    w.keep_awake.held = True
    n = len(env.coord.heartbeats)
    w.keep_awake_policy()
    assert not w.keep_awake.held
    hb = env.coord.heartbeats[n]  # reported BEFORE allowing sleep
    assert hb["stats"]["state"] == "outside_hours" and hb["stats"]["next_window"] and hb["stats"]["may_sleep"] is False
    assert armed and abs(armed[0] - hb["stats"]["next_window"]) < 60
    assert any("may sleep until" in m for m in env.logs)


def test_inside_window_holds_and_paused_releases(env):
    w = env.make_worker(schedule=None)
    w.keep_awake = FakeKA()
    w.keep_awake_policy()
    assert w.keep_awake.held
    (env.root / "paused").parent.mkdir(parents=True, exist_ok=True)
    (env.root / "paused").write_text("x")
    w.keep_awake_policy()
    assert not w.keep_awake.held


def test_wake_task_xml():
    xml = service.windows_wake_task_xml(USER, "PC\\vol", s4u=True, python=r"C:\t\Scripts\python.exe")
    root = ET.fromstring(xml.replace('encoding="UTF-16"', ""))
    assert root.find("t:Settings/t:WakeToRun", NS).text == "true"
    trig = root.findall("t:Triggers/t:CalendarTrigger", NS)
    got = {(t.find("t:StartBoundary", NS).text[11:16],
            tuple(sorted(c.tag.split("}")[1] for c in t.find("t:ScheduleByWeek/t:DaysOfWeek", NS))))
           for t in trig}
    assert got == {("07:00", tuple(sorted(("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")))),
                   ("21:00", tuple(sorted(("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"))))}
    exe = root.find("t:Actions/t:Exec/t:Command", NS).text
    args = root.find("t:Actions/t:Exec/t:Arguments", NS).text
    assert exe.endswith("pythonw.exe") and "schtasks" in args and "ald-worker" in args  # starts the worker task only
    assert root.find("t:Principals/t:Principal/t:LogonType", NS).text == "S4U"


def test_sync_wake_windows(monkeypatch):
    monkeypatch.setattr(service, "_windows_user", lambda: "PC\\vol")
    calls, created = [], []

    def run(c):
        calls.append(c)
        if c[:2] == ["schtasks", "/Query"]:
            return P(0, "<LogonType>S4U</LogonType>", "")
        if c[:2] == ["schtasks", "/Create"]:
            created.append(c[c.index("/TN") + 1])
            return P(0, "SUCCESS", "")
        if c[:2] == ["powercfg", "/QUERY"]:
            return P(0, "    Current AC Power Setting Index: 0x00000002\n", "")
        return P(0, "", "")

    msgs = service.sync_wake(USER, run=run, platform="win32")
    assert created == ["ald-wake"]
    assert ["powercfg", "/SETACVALUEINDEX", "SCHEME_CURRENT", "SUB_SLEEP", "RTCWAKE", "1"] in calls
    assert any("enabled wake timers" in m for m in msgs)
    # no admin: a clear warning
    def run_noadmin(c):
        if c[:2] == ["powercfg", "/SETACVALUEINDEX"]:
            return P(1, "", "Access denied")
        return run(c)
    assert any(m.startswith("WARNING: wake timers") for m in service.sync_wake(USER, run=run_noadmin, platform="win32"))
    # schedule removed -> wake task deleted
    calls.clear()
    service.sync_wake(None, run=run, platform="win32")
    assert ["schtasks", "/Delete", "/TN", "ald-wake", "/F"] in calls


def test_one_shot_wake_alarms():
    seen = []
    ok = lambda c: (seen.append(c), P(0, "", ""))[1]  # noqa: E731
    t = dt.datetime(2026, 11, 2, 21, 0).timestamp()
    assert "scheduled" in service.schedule_wake_at(t, run=ok, platform="darwin")
    assert seen[-1][:5] == ["sudo", "-n", "pmset", "schedule", "wake"] and seen[-1][5] == "11/02/2026 21:00:00"
    assert "scheduled" in service.schedule_wake_at(t, run=ok, platform="linux")
    assert seen[-1] == ["sudo", "-n", "rtcwake", "-m", "no", "-t", str(int(t))]
    fail = lambda c: P(1, "", "a password is required")  # noqa: E731
    assert service.schedule_wake_at(t, run=fail, platform="linux").startswith("WARNING")
