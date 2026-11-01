"""Efficiency monitor: polls /v1/status every N s, appends JSONL snapshots + flags anomalies.

Writes data/work/monitor.jsonl and data/work/monitor_latest.md (human summary the
efficiency-monitor agent reads). Run detached:
  setsid nohup uv run --project ald python -I pipeline/monitor.py --every 600 > data/work/monitor.log 2>&1 &
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/work"


def cfg():
    c = json.loads((Path.home() / ".config/ald-admin.json").read_text())
    return c["url"].rstrip("/"), {"Authorization": f"Bearer {c['admin_token']}"}


def summarize(s: dict) -> tuple[str, list[str]]:
    flags = []
    lines = [f"# Fleet status {time.strftime('%Y-%m-%d %H:%M:%S')}", "", "| worker | tier | os | pass/h (1h) | pass/24h | tok/s | last seen |", "|---|---|---|---|---|---|---|"]
    now = time.time()
    total_1h = 0
    for w in s.get("workers", []):
        p1 = w.get("passages_1h") or 0
        total_1h += p1
        lines.append(f"| {w.get('name')} | {w.get('tier')} | {w.get('os')} | {p1} | {w.get('passages_24h') or 0} | {w.get('tok_s')} | {w.get('last_seen')} |")
        try:
            age = now - time.mktime(time.strptime(w["last_seen"][:19], "%Y-%m-%dT%H:%M:%S")) + time.timezone
        except Exception:  # noqa: BLE001
            age = 0
        if age > 1800:
            flags.append(f"worker {w.get('name')} silent for {age/60:.0f} min")
        elif p1 == 0:
            flags.append(f"worker {w.get('name')} online but 0 passages in last hour (idle? wrong tier? GPU lock?)")
    lines += ["", "| stage | queued | leased | done | dead | ETA h |", "|---|---|---|---|---|---|"]
    for st, q in (s.get("queue") or {}).items():
        if not any(q.get(k) for k in ("queued", "leased", "done", "dead")):
            continue
        lines.append(f"| {st} | {q.get('queued')} | {q.get('leased')} | {q.get('done')} | {q.get('dead')} | {(s.get('eta_hours') or {}).get(st)} |")
        if q.get("dead"):
            flags.append(f"stage {st}: {q['dead']} dead jobs (3 failed attempts) - inspect")
        if q.get("queued") and not q.get("leased"):
            flags.append(f"stage {st}: {q['queued']} queued but nothing leased - no capable worker online?")
    lines += ["", f"Fleet throughput (1h): {total_1h} passages/h", "", "## Flags"] + [f"- {f}" for f in flags or ["none"]]
    return "\n".join(lines), flags


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--every", type=int, default=600)
    a = ap.parse_args()
    url, h = cfg()
    while True:
        try:
            s = httpx.get(f"{url}/v1/status", headers=h, timeout=60).json()
            md, flags = summarize(s)
            (OUT / "monitor_latest.md").write_text(md, encoding="utf-8")
            with open(OUT / "monitor.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": time.time(), "status": s, "flags": flags}) + "\n")
            print(time.strftime("%H:%M:%S"), "flags:", flags, flush=True)
        except Exception as e:  # noqa: BLE001
            print("monitor error", e, flush=True)
        time.sleep(a.every)


if __name__ == "__main__":
    main()
