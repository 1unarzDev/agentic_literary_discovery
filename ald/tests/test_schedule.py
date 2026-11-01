"""Weekly work schedule (`ald config set schedule ...`)."""

import datetime as dt

import pytest

from ald.scheduler import in_schedule, legacy_hours_to_schedule, next_schedule_change, parse_schedule

USER = "mon-fri 21:00-05:00,07:00-15:00; sat-sun 21:00-05:00"


def at(day: str, hhmm: str) -> float:
    """Local time in the week of Mon 2026-11-02."""
    d = {"mon": 2, "tue": 3, "wed": 4, "thu": 5, "fri": 6, "sat": 7, "sun": 8, "nextmon": 9}[day]
    h, m = (int(x) for x in hhmm.split(":"))
    return dt.datetime(2026, 11, d, h, m).timestamp()


@pytest.mark.parametrize("day,t,inside", [
    ("mon", "00:30", True),   # Sun 21:00 -> Mon 05:00 carries over
    ("mon", "04:59", True), ("mon", "05:00", False), ("mon", "06:59", False),
    ("mon", "07:00", True), ("mon", "14:59", True), ("mon", "15:00", False), ("mon", "20:59", False),
    ("mon", "21:00", True), ("tue", "03:00", True),
    ("fri", "12:00", True), ("fri", "16:00", False), ("fri", "22:00", True),
    ("sat", "04:00", True),   # Fri 21:00 -> Sat 05:00
    ("sat", "05:00", False), ("sat", "08:00", False), ("sat", "12:00", False), ("sat", "20:59", False),
    ("sat", "21:00", True), ("sun", "02:00", True), ("sun", "10:00", False), ("sun", "23:00", True),
    ("nextmon", "04:30", True), ("nextmon", "05:30", False),
])
def test_user_schedule(day, t, inside):
    assert in_schedule(USER, at(day, t)) is inside


def test_next_change():
    assert dt.datetime.fromtimestamp(next_schedule_change(USER, at("sat", "12:00"))).strftime("%a %H:%M") == "Sat 21:00"
    assert dt.datetime.fromtimestamp(next_schedule_change(USER, at("mon", "16:00"))).strftime("%a %H:%M") == "Mon 21:00"
    assert dt.datetime.fromtimestamp(next_schedule_change(USER, at("mon", "08:00"))).strftime("%a %H:%M") == "Mon 15:00"
    assert next_schedule_change(None, at("mon", "08:00")) is None
    assert next_schedule_change("daily 00:00-00:00", at("mon", "08:00")) is None  # always on


def test_parse_and_legacy():
    assert len(parse_schedule(USER)) == 5 * 2 + 2
    assert parse_schedule("mon,wed 09:00-10:00") == [(0, 540, 600), (2, 540, 600)]
    assert {r[0] for r in parse_schedule("fri-mon 22:00-06:00")} == {4, 5, 6, 0}  # wrap-around day range
    for bad in ("mon 25:00-01:00", "funday 09:00-10:00", "mon", "mon 9-10", ""):
        with pytest.raises(ValueError):
            parse_schedule(bad)
    assert in_schedule("garbage", at("mon", "06:00")) is True  # malformed never stops work
    legacy = legacy_hours_to_schedule("22:00-07:00")
    assert in_schedule(legacy, at("sat", "23:00")) and not in_schedule(legacy, at("sat", "12:00"))


def test_worker_idles_outside_schedule(env):
    from conftest import make_passages
    env.coord.add_job("j", "label", env.registry.stages["label"].pin_hash(), make_passages("w", 2))
    now = dt.datetime.fromtimestamp(env.clock.time())
    a, b = (now + dt.timedelta(hours=2)).strftime("%H:%M"), (now + dt.timedelta(hours=3)).strftime("%H:%M")
    day = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[now.weekday()]
    w = env.make_worker(schedule=f"{day} {a}-{b}")
    w.run()
    assert env.coord.state == {"j": "queued"} and any("idle until" in m for m in env.logs)
    w2 = env.make_worker(schedule=f"daily {now.strftime('%H:%M')}-{b}")
    w2.run()
    assert env.coord.state == {"j": "done"}
