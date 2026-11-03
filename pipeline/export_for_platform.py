"""Export the Cloudflare coordinator (D1 + R2) for import into the research platform (docs/migration_plan.md §4).

Layout (what `research-server import ald <dir>` expects, DECISIONS-ALD.md):
  <out>/<stamp>/
    d1/dump.sql                      wrangler d1 export (schema + data)
    d1/<table>.jsonl                 one JSON object per row, per migrated table
    d1/counts.json                   row counts per table + jobs per (wave, stage, status)
    r2/<key>                         plain objects: shards/, results/ (discovery), registry/, dist/, install/
    sealed/<key>.age                 confirmation results/partials, age-encrypted to the project recipient
    manifest_r2.jsonl                {key, size, sha256, d1_sha256}
    manifest_sealed.jsonl            {key, plain_sha256 (= D1 content_sha256), cipher_sha256, size, cipher_size, ...}
    export_report.json

Sealed objects are fetched into memory only, checked against D1, encrypted and written as ciphertext:
plaintext never touches disk. R2 originals are not modified. Resumable: files already exported and matching
their manifest entry are skipped.

usage:
  uv run --project ald python -I pipeline/export_for_platform.py --out /tmp/ald-export \\
      --recipient age1...        # the owner's public key (or a throwaway key for a dry run)
      [--limit N]                # per category, for tests
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ald/src"))
import httpx  # noqa: E402

from ald import sealed  # noqa: E402

COORD = ROOT / "coordinator"
D1 = "ald-coordinator"
BUCKET = "ald-coordinator"
ACCOUNT = "caa986c8bf3907b23e49eace3b4401f1"
TABLES = ["config", "workers", "invites", "pins", "shards", "jobs", "leases", "results", "job_partials", "seal",
          "viewer_tokens"]  # annotation tables stay on Cloudflare (migration_plan §1)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# --------------------------------------------------------------------------- Cloudflare access
def _token() -> str:
    p = Path.home() / ".config/.wrangler/config/default.toml"
    d = tomllib.loads(p.read_text())
    exp = d.get("expiration_time")
    if exp and time.time() > time.mktime(time.strptime(str(exp)[:19], "%Y-%m-%dT%H:%M:%S")) - 120:
        subprocess.run(["npx", "wrangler", "whoami"], cwd=COORD, capture_output=True)  # refreshes the OAuth token
        d = tomllib.loads(p.read_text())
    return d["oauth_token"]


class R2:
    def __init__(self) -> None:
        self.http = httpx.Client(timeout=120)
        self._refresh()

    def _refresh(self) -> None:
        self.http.headers["Authorization"] = f"Bearer {_token()}"

    def _url(self, key: str = "") -> str:
        base = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/r2/buckets/{BUCKET}/objects"
        return f"{base}/{httpx.URL(key).raw_path.decode() if key else ''}".rstrip("/")

    def get(self, key: str) -> bytes | None:
        for attempt in range(4):
            r = self.http.get(self._url(key))
            if r.status_code == 401:
                self._refresh()
                continue
            if r.status_code == 404:
                return None
            if r.status_code >= 500 or r.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.content
        raise RuntimeError(f"R2 get failed for {key}")

    def list(self, prefix: str = "") -> list[dict]:
        out, cursor = [], None
        while True:
            params = {"prefix": prefix, "per_page": 1000, **({"cursor": cursor} if cursor else {})}
            r = self.http.get(self._url(), params=params)
            if r.status_code == 401:
                self._refresh()
                continue
            r.raise_for_status()
            j = r.json()
            out += j.get("result") or []
            cursor = (j.get("result_info") or {}).get("cursor")
            if not cursor or not (j.get("result_info") or {}).get("is_truncated", False):
                return out


def d1(sql: str) -> list[dict]:
    for attempt in range(3):
        p = subprocess.run(["npx", "wrangler", "d1", "execute", D1, "--remote", "--json", "--command", sql],
                           cwd=COORD, capture_output=True, text=True)
        if p.returncode == 0:
            return json.loads(p.stdout)[0]["results"]
        time.sleep(3 * (attempt + 1))
    raise SystemExit(f"d1 failed: {p.stderr[-500:]}")


# --------------------------------------------------------------------------- export
def export_d1(out: Path) -> dict:
    dd = out / "d1"
    dd.mkdir(parents=True, exist_ok=True)
    if not (dd / "dump.sql").exists():
        subprocess.run(["npx", "wrangler", "d1", "export", D1, "--remote", "--output", str(dd / "dump.sql")],
                       cwd=COORD, check=True, capture_output=True)
    counts = {}
    for t in TABLES:
        rows, off = [], 0
        while True:
            page = d1(f"SELECT * FROM {t} ORDER BY rowid LIMIT 1000 OFFSET {off}")
            rows += page
            off += len(page)
            if len(page) < 1000:
                break
        with open(dd / f"{t}.jsonl", "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        counts[t] = len(rows)
    counts["jobs_by_wave_stage_status"] = d1(
        "SELECT wave, stage, status, COUNT(*) AS n, SUM(n_passages) AS p FROM jobs GROUP BY 1,2,3 ORDER BY 1,2,3")
    (dd / "counts.json").write_text(json.dumps(counts, indent=1), encoding="utf-8")
    return counts


def load_manifest(p: Path) -> dict[str, dict]:
    if not p.exists():
        return {}
    return {e["key"]: e for e in (json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip())}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--stamp", default=time.strftime("%Y%m%dT%H%M%S"))
    ap.add_argument("--recipient", required=True, help="age1... public key the sealed blobs are encrypted to")
    ap.add_argument("--limit", type=int, default=0, help="max objects per category (tests)")
    ap.add_argument("--skip-d1", action="store_true")
    ap.add_argument("--synthetic-sealed", action="store_true",
                    help="DRY RUNS: export synthetic stand-ins (same keys) instead of the real sealed blobs")
    a = ap.parse_args()
    # Real sealed (Confirmation) data may only ever be encrypted to the owner's key, which is pinned in the
    # client release at the key ceremony. Anything else (a throwaway test key) gets synthetic stand-ins.
    if not a.synthetic_sealed and (not sealed.PINNED_RECIPIENT or a.recipient.strip() != sealed.PINNED_RECIPIENT):
        raise SystemExit("REFUSED: real sealed blobs are only encrypted to the owner's pinned key "
                         "(ald.sealed.PINNED_RECIPIENT). For a dry run use --synthetic-sealed.")
    out = Path(a.out) / a.stamp
    out.mkdir(parents=True, exist_ok=True)
    report: dict = {"stamp": a.stamp, "recipient": a.recipient, "started": time.time(), "errors": []}
    if not a.skip_d1:
        report["d1_counts"] = {k: v for k, v in export_d1(out).items() if k != "jobs_by_wave_stage_status"}

    r2 = R2()
    # Expected objects + their D1 sha256: plain vs sealed.
    shards = d1("SELECT shard_key AS key, content_sha256 AS sha, split FROM shards")
    res = d1("SELECT r2_key AS key, content_sha256 AS sha, split, job_id, worker_id, NULL AS part_n FROM results "
             "UNION ALL SELECT r2_key, content_sha256, split, job_id, worker_id, part_n FROM job_partials")
    plain = [(s["key"], s["sha"]) for s in shards] + [(r["key"], r["sha"]) for r in res if not r["key"].startswith("sealed/")]
    seal_rows = [r for r in res if r["key"].startswith("sealed/")]
    extra = [o["key"] for p in ("registry/", "dist/", "install/") for o in r2.list(p)]
    plain += [(k, None) for k in extra]
    if a.limit:
        plain, seal_rows = plain[: a.limit], seal_rows[: a.limit]

    # ---- plain objects
    mp = out / "manifest_r2.jsonl"
    done = load_manifest(mp)
    with open(mp, "a", encoding="utf-8") as mf:
        for key, d1sha in plain:
            dest = out / "r2" / key
            if key in done and dest.exists() and sha(dest.read_bytes()) == done[key]["sha256"]:
                continue
            body = r2.get(key)
            if body is None:
                report["errors"].append({"key": key, "error": "missing in R2"})
                continue
            h = sha(body)
            if d1sha and h != d1sha:
                report["errors"].append({"key": key, "error": "sha256 != D1 content_sha256", "r2": h, "d1": d1sha})
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(body)
            mf.write(json.dumps({"key": key, "size": len(body), "sha256": h, "d1_sha256": d1sha}) + "\n")

    # ---- sealed objects: memory only -> encrypt -> ciphertext on disk
    ms = out / "manifest_sealed.jsonl"
    done_s = load_manifest(ms)
    with open(ms, "a", encoding="utf-8") as mf:
        for r in seal_rows:
            key = r["key"]
            dest = out / "sealed" / (key[len("sealed/"):] + ".age")
            if key in done_s and dest.exists() and sha(dest.read_bytes()) == done_s[key]["cipher_sha256"]:
                continue
            if a.synthetic_sealed:  # never fetch the real blob in a dry run
                import gzip as _gz
                body = _gz.compress(json.dumps({"synthetic": True, "key": key}).encode() + b"\n", mtime=0)
                r = {**r, "sha": sha(body)}
            else:
                body = r2.get(key)
            if body is None:
                report["errors"].append({"key": key, "error": "missing in R2"})
                continue
            h = sha(body)
            if h != r["sha"]:
                report["errors"].append({"key": key, "error": "sealed sha256 != D1 content_sha256"})
                del body
                continue
            ct = sealed.encrypt(body, a.recipient)
            size = len(body)
            del body  # plaintext only ever existed in this process's memory
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(ct)
            mf.write(json.dumps({"key": key, "plain_sha256": h, "cipher_sha256": sha(ct), "size": size,
                                 "cipher_size": len(ct), "job_id": r["job_id"], "worker_id": r["worker_id"],
                                 "part_n": r["part_n"], "scheme": sealed.SEALED_SCHEME,
                                 **({"synthetic": True} if a.synthetic_sealed else {})}) + "\n")

    report.update(finished=time.time(), plain_objects=len(load_manifest(mp)), sealed_objects=len(load_manifest(ms)),
                  expected_plain=len(plain), expected_sealed=len(seal_rows))
    (out / "export_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "errors"} | {"errors": len(report["errors"])}, indent=1))
    if report["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    os.umask(0o077)  # exports contain worker token hashes and invites: owner-only files
    main()
