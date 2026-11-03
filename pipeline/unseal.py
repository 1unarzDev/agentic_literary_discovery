"""One-command unseal of the Confirmation split (docs/migration_plan.md section 3). Owner only, after preregistration.

  uv run --project ald --with pyrage python -I pipeline/unseal.py --key /media/usb/ald-sealed.agekey

Steps (it stops at the first failure and writes nothing):
1. Reads the OSF registration hash from docs/prereg.md (a 64-hex sha256 on the "OSF registration hash" line).
2. Fetches the platform's one-way unseal record (GET <base>/v1/admin/unseal: {prereg_hash, unsealed_at, audit}).
   It refuses unless the recorded hash equals docs/prereg.md.
3. Lists the sealed results and partials (GET <base>/v1/admin/results?split=confirmation) and downloads each
   ciphertext. It checks the ciphertext sha256, decrypts it with the key, and checks the plaintext sha256.
4. Writes plaintext ONLY under data/work/results_sealed_unsealed/<job_id>/<worker_id>[.part<n>].jsonl.gz, plus
   MANIFEST.json, for `pipeline/sync_results.py --sealed`. Re-running skips files that already verify.

  --from-export DIR   decrypt a migration export (manifest_sealed.jsonl + sealed/*.age) instead of the platform
                      (still requires the platform unseal record unless --dry-run with a throwaway key)
  --base URL          default https://research.lunarz.dev/p/ald ; admin token from ~/.config/ald-admin.json
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ald/src"))
OUT = ROOT / "data/work/results_sealed_unsealed"
HEX64 = re.compile(r"\b[0-9a-f]{64}\b")


def prereg_hash(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if "OSF registration hash" in line:
            m = HEX64.search(line.lower())
            if m:
                return m.group(0)
            raise SystemExit(f"{path}: the OSF registration hash line has no sha256 yet ({line.strip()[:80]})")
    raise SystemExit(f"{path}: no 'OSF registration hash' line")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def target_path(job_id: str, worker_id: str, part_n) -> Path:
    from ald.config import safe_name
    name = safe_name(worker_id) + (f".part{part_n}" if part_n is not None else "") + ".jsonl.gz"
    return OUT / safe_name(job_id) / name


def main() -> None:
    from ald import sealed
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True, help="private key file (AGE-SECRET-KEY-1...)")
    ap.add_argument("--base", default="https://research.lunarz.dev/p/ald")
    ap.add_argument("--prereg", default=str(ROOT / "docs/prereg.md"))
    ap.add_argument("--from-export")
    ap.add_argument("--dry-run", action="store_true",
                    help="tests only: synthetic exports (--synthetic-sealed) into a separate --out; skips the record")
    ap.add_argument("--out", help="output dir (default data/work/results_sealed_unsealed; required for --dry-run)")
    a = ap.parse_args()
    global OUT
    if a.dry_run:
        if not a.from_export or not a.out:
            raise SystemExit("--dry-run needs --from-export (a --synthetic-sealed export) and a separate --out")
        if Path(a.out).resolve().is_relative_to((ROOT / "data").resolve()):
            raise SystemExit("--dry-run must not write under data/")
    if a.out:
        OUT = Path(a.out)
    key = Path(a.key).read_text()

    want = None if a.dry_run else prereg_hash(Path(a.prereg))
    http = None
    if not a.dry_run or not a.from_export:
        import httpx
        cfg = json.loads((Path.home() / ".config/ald-admin.json").read_text())
        http = httpx.Client(base_url=a.base.rstrip("/"), timeout=120,
                            headers={"Authorization": f"Bearer {cfg['admin_token']}"})
    if not a.dry_run:
        rec = http.get("/v1/admin/unseal")
        rec.raise_for_status()
        rec = rec.json()
        if (rec.get("prereg_hash") or "").lower().removeprefix("sha256:") != want:
            raise SystemExit(f"REFUSED: platform unseal record {rec.get('prereg_hash')} != docs/prereg.md {want}")
        print(f"unseal record OK: {want} at {rec.get('unsealed_at')} ({len(rec.get('audit') or [])} audit entries)")

    items = []  # (job_id, worker_id, part_n, fetch(), cipher_sha, plain_sha)
    if a.from_export:
        d = Path(a.from_export)
        for line in (d / "manifest_sealed.jsonl").read_text(encoding="utf-8").splitlines():
            e = json.loads(line)
            if a.dry_run and not e.get("synthetic"):
                raise SystemExit("REFUSED: --dry-run on an export that holds REAL sealed data (not --synthetic-sealed)")
            f = d / "sealed" / (e["key"][len("sealed/"):] + ".age")
            items.append((e["job_id"], e["worker_id"], e["part_n"], f.read_bytes, e["cipher_sha256"], e["plain_sha256"]))
    else:
        r = http.get("/v1/admin/results", params={"split": "confirmation", "since": "1970-01-01T00:00:00Z"})
        r.raise_for_status()
        for x in r.json()["results"]:
            k = x["r2_key"]
            items.append((x["job_id"], x["worker_id"], x.get("part_n"),
                          (lambda k=k: http.get("/v1/admin/blob", params={"key": k}).raise_for_status().content),
                          x.get("cipher_sha256") or x.get("content_sha256"), x.get("plain_sha256")))

    OUT.mkdir(parents=True, exist_ok=True)
    manifest, wrote, skipped = [], 0, 0
    for job_id, worker_id, part_n, fetch, cipher_sha, plain_sha in items:
        dest = target_path(job_id, worker_id, part_n)
        if dest.exists() and plain_sha and sha(dest.read_bytes()) == plain_sha:
            skipped += 1
        else:
            ct = fetch()
            if cipher_sha and sha(ct) != cipher_sha:
                raise SystemExit(f"ciphertext sha256 mismatch for {job_id}/{worker_id}; nothing written for it")
            pt = sealed.decrypt(ct, key)
            if plain_sha and sha(pt) != plain_sha:
                raise SystemExit(f"plaintext sha256 mismatch for {job_id}/{worker_id}")
            gzip.decompress(pt)  # must be a valid result blob
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(pt)
            wrote += 1
        manifest.append({"job_id": job_id, "worker_id": worker_id, "part_n": part_n,
                         "file": str(dest.relative_to(OUT)), "plain_sha256": sha(dest.read_bytes())})
    (OUT / "MANIFEST.json").write_text(json.dumps({"prereg_hash": want, "n": len(manifest), "items": manifest},
                                                  indent=1), encoding="utf-8")
    print(f"unsealed {wrote} file(s), {skipped} already present; {len(manifest)} in {OUT}/MANIFEST.json")


if __name__ == "__main__":
    main()
