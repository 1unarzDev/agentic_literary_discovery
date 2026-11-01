"""Admin helper for the ALD coordinator: repeatable release / registry / invite / test-seed steps.

The admin config lives OUTSIDE the repo in ~/.config/ald-admin.json ({"url": ..., "admin_token": ...});
override the path with ALD_ADMIN_CONFIG. The token is read here and never printed.

Run from the repo root inside the ald project env (it imports ald.registry for pin hashing):

  uv run --project ald python -I pipeline/admin.py status
  uv run --project ald python -I pipeline/admin.py release --bump patch      # build, upload wheel, client_release, installers
  uv run --project ald python -I pipeline/admin.py release                   # re-release the current version (no bump)
  uv run --project ald python -I pipeline/admin.py installers                # only re-upload install.sh / install.ps1
  uv run --project ald python -I pipeline/admin.py upload-registry --regen   # make_registry.py, register pins, PUT registry
  uv run --project ald python -I pipeline/admin.py pins                      # print the pin objects
  uv run --project ald python -I pipeline/admin.py invite 3
  uv run --project ald python -I pipeline/admin.py seed-test                 # TEST wave 'wtest' (label + workcheck)
  uv run --project ald python -I pipeline/admin.py close-wave wtest          # cancel open jobs of a wave
  uv run --project ald python -I pipeline/admin.py purge-wave wtest          # delete a TEST wave's rows + R2 blobs

Test data convention: every test job lives in wave ``wtest`` with job ids ``wtest_*``. Real waves are
named ``wNN_*`` (pipeline/make_jobs.py). After a test, ``close-wave`` cancels what is still open and
``purge-wave`` deletes the wave's jobs, results, partials, leases, shards and result blobs, so nothing from a
test reaches /v1/admin/results.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALD = ROOT / "ald"
COORD_DIR = ROOT / "coordinator"
INIT = ALD / "src/ald/__init__.py"
REGISTRY = ROOT / "registry/models.v1.json"
D1_NAME = "ald-coordinator"
R2_BUCKET = "ald-coordinator"
TEST_WAVE = "wtest"

try:
    import httpx
    sys.path.insert(0, str(ALD / "src"))
    from ald.registry import Registry  # noqa: E402  (single source of truth for pin hashing)
except ImportError:  # wrong env: re-run inside the ald project
    if os.environ.get("_ALD_ADMIN_REEXEC"):
        raise
    os.environ["_ALD_ADMIN_REEXEC"] = "1"
    os.execvp("uv", ["uv", "run", "--project", str(ALD), "python", "-I", __file__, *sys.argv[1:]])


# ---------------------------------------------------------------------------- plumbing
def admin_cfg() -> tuple[str, str]:
    p = Path(os.environ.get("ALD_ADMIN_CONFIG", Path.home() / ".config/ald-admin.json"))
    cfg = json.loads(p.read_text(encoding="utf-8"))
    return cfg["url"].rstrip("/"), cfg["admin_token"]


def client() -> httpx.Client:
    url, tok = admin_cfg()
    return httpx.Client(base_url=url, headers={"Authorization": f"Bearer {tok}"}, timeout=300)


def ok(r: httpx.Response) -> dict:
    if r.status_code >= 400:
        raise SystemExit(f"{r.request.method} {r.request.url.path} -> {r.status_code}: {r.text[:500]}")
    try:
        return r.json()
    except ValueError:
        return {}


def current_version() -> str:
    m = re.search(r'__version__\s*=\s*"([^"]+)"', INIT.read_text(encoding="utf-8"))
    if not m:
        raise SystemExit(f"no __version__ in {INIT}")
    return m.group(1)


def bump(v: str, part: str) -> str:
    nums = [int(x) for x in v.split(".")[:3]] + [0] * (3 - len(v.split(".")[:3]))
    i = {"major": 0, "minor": 1, "patch": 2}[part]
    nums[i] += 1
    nums[i + 1:] = [0] * (2 - i)
    return ".".join(map(str, nums))


def set_version(v: str) -> None:
    s = INIT.read_text(encoding="utf-8")
    INIT.write_text(re.sub(r'__version__\s*=\s*"[^"]+"', f'__version__ = "{v}"', s), encoding="utf-8")


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------- release
def upload_installers(c: httpx.Client) -> None:
    for name in ("install.sh", "install.ps1"):
        body = (ALD / "install" / name).read_bytes()
        if b"\r\n" in body and name == "install.sh":
            raise SystemExit("install.sh has CRLF line endings; refusing to upload")
        r = ok(c.put(f"/v1/admin/install/{name}", content=body, headers={"content-type": "text/plain"}))
        served = httpx.get(r["url"], timeout=60).text
        if "__COORDINATOR_URL__" in served or c.base_url.host not in served:
            raise SystemExit(f"{name}: coordinator URL was not substituted when served")
        print(f"uploaded {name} -> {r['url']}")


def cmd_release(a: argparse.Namespace) -> None:
    v = current_version()
    if a.bump != "none":
        v = bump(v, a.bump)
        set_version(v)
        print(f"bumped ald to {v} ({INIT.relative_to(ROOT)})")
    if a.version:
        v = a.version
        set_version(v)
    whl = ALD / "dist" / f"ald-{v}-py3-none-any.whl"
    if not a.no_build or not whl.exists():
        if whl.exists():
            whl.unlink()
        subprocess.run(["uv", "build", "--wheel"], cwd=ALD, check=True)
    if not whl.exists():
        raise SystemExit(f"build did not produce {whl}")
    with client() as c:
        ping = ok(c.get("/v1/ping"))
        min_v = a.min_version or ping.get("min_client_version") or v
        if a.min_same:
            min_v = v
        r = ok(c.put(f"/v1/admin/dist/{whl.name}", content=whl.read_bytes()))
        if r["sha256"] != sha256_file(whl):
            raise SystemExit("uploaded wheel sha256 mismatch")
        print(f"uploaded {whl.name} ({whl.stat().st_size / 1e3:.0f} kB, sha256 {r['sha256'][:12]})")
        r = ok(c.put("/v1/admin/client_release", json={"version": v, "min_version": min_v}))
        print(f"client_release: latest={r['latest_client_version']} min={r['min_client_version']}")
        if not a.no_installers:
            upload_installers(c)
        ping = ok(c.get("/v1/ping"))
        if ping.get("latest_client_version") != v or not ping.get("wheel_url"):
            raise SystemExit(f"/v1/ping does not show the release: {ping}")
        got = httpx.get(ping["wheel_url"], timeout=120)
        if got.status_code != 200 or hashlib.sha256(got.content).hexdigest() != sha256_file(whl):
            raise SystemExit(f"wheel_url {ping['wheel_url']} does not serve the uploaded wheel")
        print(f"/v1/ping: latest_client_version={ping['latest_client_version']} "
              f"min_client_version={ping['min_client_version']} wheel_url={ping['wheel_url']}")


def cmd_installers(_a: argparse.Namespace) -> None:
    with client() as c:
        upload_installers(c)


# ---------------------------------------------------------------------------- registry + pins
def load_registry() -> Registry:
    return Registry.from_dict(json.loads(REGISTRY.read_text(encoding="utf-8")))


def cmd_pins(_a: argparse.Namespace) -> None:
    print(json.dumps([st.pin_object() for st in load_registry().stages.values()], indent=2))


def register_pins(c: httpx.Client, reg: Registry) -> dict[str, str]:
    out = {}
    for name, st in reg.stages.items():
        pin = st.pin_object()
        r = ok(c.post("/v1/admin/pin", json=pin))
        out[name] = pin["pin_hash"]
        print(f"pin {name:10s} {pin['pin_hash'][:16]} {st.model_ref} -> {r.get('status')}")
    return out


def cmd_upload_registry(a: argparse.Namespace) -> None:
    if a.regen:
        # make_registry.py runs in the research (root) env: it imports analysis/bench_models.py and
        # reads model digests from the local Ollama.
        subprocess.run(["uv", "run", "python", "-I", "pipeline/make_registry.py"], cwd=ROOT, check=True)
    text = REGISTRY.read_text(encoding="utf-8")
    reg = Registry.from_dict(json.loads(text))  # validates
    with client() as c:
        if not a.no_pins:
            register_pins(c, reg)
        r = ok(c.put("/v1/admin/registry", content=text.encode("utf-8"), headers={"content-type": "application/json"}))
        print(f"registry {reg.version} uploaded: coordinator registry_version={r['registry_version']} "
              f"etag={r['etag'][:12]} unknown_pins={r.get('unknown_pins')}")
        served = c.get("/v1/registry")
        if hashlib.sha256(served.content).hexdigest() != r["etag"]:
            raise SystemExit("GET /v1/registry does not match the upload")


# ---------------------------------------------------------------------------- invites / status
def cmd_invite(a: argparse.Namespace) -> None:
    with client() as c:
        for code in ok(c.post("/v1/admin/invite", json={"n": a.n}))["invites"]:
            print(code)


def cmd_status(a: argparse.Namespace) -> None:
    with client() as c:
        ping = ok(c.get("/v1/ping"))
        st = ok(c.get("/v1/status"))
    if a.json:
        print(json.dumps({"ping": ping, "status": st}, indent=2))
        return
    print(f"client: latest={ping.get('latest_client_version')} min={ping.get('min_client_version')} "
          f"wheel={ping.get('wheel_url')}  registry_version={ping.get('registry_version')}")
    print("queue:")
    for stage, q in sorted((st.get("queue") or {}).items()):
        print(f"  {stage:10s} " + " ".join(f"{k}={v}" for k, v in sorted(q.items())) +
              f"  eta_h={(st.get('eta_hours') or {}).get(stage, '-')}")
    print("workers:")
    for w in st.get("workers") or []:
        print(f"  {str(w.get('name')):20s} {str(w.get('tier')):5s} {str(w.get('os')):8s} last_seen={w.get('last_seen')} "
              f"p1h={w.get('passages_1h')} p24h={w.get('passages_24h')} tok_s={w.get('tok_s')}")


# ---------------------------------------------------------------------------- test seed
TEST_BOOKS = ("1400", "145", "345")  # Great Expectations, Middlemarch, Dracula (PG ids)
START = re.compile(r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG.*?\*\*\*", re.I | re.S)
END = re.compile(r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG", re.I)


def pg_body(pg: str) -> str:
    t = (ROOT / f"data/raw/pg/{pg}/pg{pg}.txt").read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    m, e = START.search(t), END.search(t)
    return t[m.end() if m else 0: e.start() if e else len(t)]


def pg_meta(pg: str) -> tuple[int | None, str]:
    import csv
    csv.field_size_limit(10 ** 7)
    decade, subjects = None, ""
    with open(ROOT / "data/catalog/pg_catalog.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["Text#"] == pg:
                subjects = row.get("Subjects") or ""
                break
    dates = ROOT / "data/catalog/pgdates/_best-performance__LLM_first_last_gemma.csv"
    if dates.exists():
        with open(dates, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if row["Book_ID"] == pg:
                    try:
                        decade = int(str(row["Result"]).strip()[:4]) // 10 * 10
                    except ValueError:
                        pass
                    break
    return decade, subjects


def passages_from(pg: str, n: int, words: int = 350) -> list[dict]:
    """~``words``-word passages made of whole paragraphs, from the middle of the book, with ~120-word
    context windows (the shard line schema in docs/api_contract.md, plus ``subjects`` for workcheck)."""
    paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", pg_body(pg))]
    paras = [p for p in paras if len(p.split()) >= 8]
    chunks, cur = [], []
    for p in paras:
        n_cur, n_p = sum(len(x.split()) for x in cur), len(p.split())
        if cur and n_cur + n_p > words * 1.25:  # close the chunk before it gets too long
            chunks.append(cur)
            cur = []
        cur.append(p)
        if sum(len(x.split()) for x in cur) >= words * 0.85:
            chunks.append(cur)
            cur = []
    chunks = [ch for ch in chunks if words * 0.7 <= len(" ".join(ch).split()) <= words * 1.4]
    mid = max(0, len(chunks) // 2 - n)
    picked = list(range(mid, len(chunks) - 1, 2))[:n]  # every other chunk: neighbours give real context
    decade, subjects = pg_meta(pg)
    out = []
    for i in picked:
        text = "\n\n".join(chunks[i])
        before = " ".join(" ".join(chunks[i - 1]).split()[-120:]) if i > 0 else ""
        after = " ".join(" ".join(chunks[i + 1]).split()[:120]) if i + 1 < len(chunks) else ""
        out.append({"passage_id": f"pg{pg}_p{i:04d}", "work_id": f"pg{pg}", "decade": decade, "stratum": "random",
                    "text": text, "ctx_before": before, "ctx_after": after,
                    "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "subjects": subjects[:400]})
    return out


def gz_jsonl(rows: list[dict]) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as g:
        for r in rows:
            g.write((json.dumps(r, ensure_ascii=False) + "\n").encode("utf-8"))
    return buf.getvalue()


def cmd_seed_test(a: argparse.Namespace) -> None:
    reg = load_registry()
    tag = a.tag or time.strftime("%m%d%H%M")
    stages = [s.strip() for s in a.stages.split(",") if s.strip()]
    with client() as c:
        pins = register_pins(c, reg)
        jobs = []
        for k, pg in enumerate(TEST_BOOKS[: a.n_shards]):
            rows = passages_from(pg, a.passages)
            sid = f"{TEST_WAVE}_s{k:02d}_pg{pg}_n{len(rows)}"
            r = ok(c.put(f"/v1/admin/shard/{TEST_WAVE}/{sid}", content=gz_jsonl(rows),
                         headers={"X-Split": "discovery", "X-N-Passages": str(len(rows)),
                                  "X-Decades": str(rows[0]["decade"] or "")}))
            print(f"shard {r['shard_key']} {len(rows)} passages "
                  f"(~{sum(len(x['text'].split()) for x in rows) // len(rows)} words each) -> {r['status']}")
            for stage in stages:
                jobs.append({"job_id": f"{TEST_WAVE}_{tag}_s{k:02d}_{stage}", "stage": stage, "wave": TEST_WAVE,
                             "shard_key": r["shard_key"], "pin_hash": pins[stage], "n_passages": len(rows),
                             "split": "discovery", "dup_group": None, "priority": 1, "cell": "TEST"})
        r = ok(c.post("/v1/admin/jobs", json={"jobs": jobs}))
        print(f"jobs: inserted={r['inserted']} skipped_existing={r['skipped_existing']}")
        for j in jobs:
            print(f"  {j['job_id']}")


def cmd_close_wave(a: argparse.Namespace) -> None:
    with client() as c:
        r = ok(c.post("/v1/admin/close_jobs", json={"wave": a.wave}))
    print(f"closed {len(r['closed'])} job(s) in wave {a.wave}: {', '.join(r['closed']) or '-'}")


def wrangler(*args: str) -> str:
    p = subprocess.run(["npx", "wrangler", *args], cwd=COORD_DIR, capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"wrangler {' '.join(args[:3])} failed: {p.stderr[-800:]}")
    return p.stdout


def d1(sql: str) -> list[dict]:
    out = wrangler("d1", "execute", D1_NAME, "--remote", "--json", "--command", sql)
    return json.loads(out)[0]["results"]


def cmd_purge_wave(a: argparse.Namespace) -> None:
    w = a.wave
    if not re.fullmatch(r"[A-Za-z0-9._-]+", w):
        raise SystemExit("bad wave name")
    if not (w == TEST_WAVE or w.startswith("wtest") or a.yes_real_wave):
        raise SystemExit(f"refusing to purge non-test wave {w!r} (pass --yes-real-wave)")
    sel = f"SELECT job_id FROM jobs WHERE wave = '{w}'"
    keys = [r["r2_key"] for r in d1(f"SELECT r2_key FROM results WHERE job_id IN ({sel}) "
                                    f"UNION SELECT r2_key FROM job_partials WHERE job_id IN ({sel}) "
                                    f"UNION SELECT shard_key AS r2_key FROM shards WHERE wave = '{w}'")]
    for k in keys:
        wrangler("r2", "object", "delete", f"{R2_BUCKET}/{k}", "--remote")
    d1(f"DELETE FROM job_partials WHERE job_id IN ({sel}); DELETE FROM results WHERE job_id IN ({sel}); "
       f"DELETE FROM leases WHERE job_id IN ({sel}); DELETE FROM jobs WHERE wave = '{w}'; "
       f"DELETE FROM shards WHERE wave = '{w}';")
    left = d1(f"SELECT (SELECT COUNT(*) FROM jobs WHERE wave = '{w}') AS jobs, "
              f"(SELECT COUNT(*) FROM shards WHERE wave = '{w}') AS shards")[0]
    print(f"purged wave {w}: deleted {len(keys)} R2 object(s); remaining rows {left}")


# ---------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("release", help="build + upload the wheel, record the client release, upload installers")
    p.add_argument("--bump", choices=["none", "patch", "minor", "major"], default="none")
    p.add_argument("--version", help="explicit version (overrides --bump)")
    p.add_argument("--min-version", help="min_client_version (default: keep the coordinator's current value)")
    p.add_argument("--min-same", action="store_true", help="force every client to this version (min = version)")
    p.add_argument("--no-build", action="store_true", help="reuse dist/ald-<v>-py3-none-any.whl if present")
    p.add_argument("--no-installers", action="store_true")
    p.set_defaults(fn=cmd_release)
    p = sub.add_parser("installers", help="upload install.sh and install.ps1")
    p.set_defaults(fn=cmd_installers)
    p = sub.add_parser("upload-registry", help="register pins and PUT registry/models.v1.json")
    p.add_argument("--regen", action="store_true", help="run pipeline/make_registry.py first")
    p.add_argument("--no-pins", action="store_true")
    p.set_defaults(fn=cmd_upload_registry)
    p = sub.add_parser("pins", help="print the pin objects for the local registry")
    p.set_defaults(fn=cmd_pins)
    p = sub.add_parser("invite", help="create N single-use invites")
    p.add_argument("n", type=int)
    p.set_defaults(fn=cmd_invite)
    p = sub.add_parser("status", help="/v1/ping + /v1/status")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_status)
    p = sub.add_parser("seed-test", help=f"upload small TEST shards + jobs in wave {TEST_WAVE}")
    p.add_argument("--n-shards", type=int, default=3)
    p.add_argument("--passages", type=int, default=16, help="passages per shard")
    p.add_argument("--stages", default="label,workcheck")
    p.add_argument("--tag", help="job id tag (default: MMDDHHMM), so a re-seed creates fresh jobs")
    p.set_defaults(fn=cmd_seed_test)
    p = sub.add_parser("close-wave", help="cancel queued/leased jobs of a wave (POST /v1/admin/close_jobs)")
    p.add_argument("wave")
    p.set_defaults(fn=cmd_close_wave)
    p = sub.add_parser("purge-wave", help="delete a TEST wave's jobs/results/partials/shards (wrangler, D1 + R2)")
    p.add_argument("wave")
    p.add_argument("--yes-real-wave", action="store_true")
    p.set_defaults(fn=cmd_purge_wave)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
