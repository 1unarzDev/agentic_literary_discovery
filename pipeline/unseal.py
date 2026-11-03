"""One-command unseal of the Confirmation split (docs/migration_plan.md section 3). Owner only, after preregistration.

  uv run --project ald --with pyrage python -I pipeline/unseal.py --key /media/usb/ald-sealed.agekey

Steps (it stops at the first failure and writes nothing):
1. Reads the OSF registration hash from docs/prereg.md (a 64-hex sha256 on the "OSF registration hash" line).
2. Platform (default): GET /v1/projects/ald/seals/<seal_id>. It refuses unless the state is "unsealed" and the
   recorded prereg_hash equals docs/prereg.md. (Lodge it first, at least min_lodge_hours before:
   `pipeline/unseal.py --lodge`.)
3. Lists the sealed objects (GET .../seals/<seal_id>/objects, which carries both hashes) and downloads each
   ciphertext (.../objects/<key>). It checks the ciphertext sha256, decrypts it with the key, and checks the
   plaintext sha256.
   --source cloudflare: the old coordinator kept sealed blobs server-side as plaintext. After its one-way
   POST /v1/admin/unseal (`--cloudflare-unseal` performs it), it downloads and checks content_sha256; no key needed.
4. Writes plaintext ONLY under data/work/results_sealed_unsealed/<job_id>/<worker_id>[.part<n>].jsonl.gz, plus
   MANIFEST.json, for `pipeline/sync_results.py --sealed`. Re-running skips files that already verify.

  --from-export DIR   decrypt a migration export (manifest_sealed.jsonl + sealed/*.age) instead of the platform
                      (still requires the platform unseal record unless --dry-run with a throwaway key)
  --seal-id ID        default ald-confirmation-v09 (platform)
  --lodge             platform: lodge docs/prereg.md's hash on the seal (step 1 of 2), then exit
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
    ap.add_argument("--key", help="private key file (AGE-SECRET-KEY-1...); not needed for --source cloudflare/--lodge")
    ap.add_argument("--source", choices=["platform", "cloudflare"], default="platform")
    ap.add_argument("--platform", default="https://research.lunarz.dev")
    ap.add_argument("--seal-id", default="ald-confirmation-v09")
    ap.add_argument("--lodge", action="store_true")
    ap.add_argument("--prereg-ref", default="", help="with --lodge: the OSF registration URL")
    ap.add_argument("--cloudflare-unseal", action="store_true", help="perform the old coordinator's one-way unseal")
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
    key = Path(a.key).read_text() if a.key else None
    import httpx
    want = None if a.dry_run else prereg_hash(Path(a.prereg))
    items = []  # (job_id, worker_id, part_n, fetch(), cipher_sha | None, plain_sha | None, encrypted)
    if a.from_export:
        if not key:
            raise SystemExit("--key is required to decrypt an export")
        if not a.dry_run:
            raise SystemExit("--from-export is for dry runs; real unseal reads from the platform")
        d = Path(a.from_export)
        for line in (d / "manifest_sealed.jsonl").read_text(encoding="utf-8").splitlines():
            e = json.loads(line)
            if not e.get("synthetic"):
                raise SystemExit("REFUSED: --dry-run on an export that holds REAL sealed data (not --synthetic-sealed)")
            f = d / "sealed" / (e["key"][len("sealed/"):] + ".age")
            items.append((e["job_id"], e["worker_id"], e["part_n"], f.read_bytes, e["cipher_sha256"], e["plain_sha256"], True))
    elif a.source == "platform":
        tokf = Path.home() / ".config/research-cluster/ald-admin.token"
        http = httpx.Client(base_url=a.platform.rstrip("/"), timeout=300,
                            headers={"Authorization": f"Bearer {tokf.read_text().strip()}"})
        base = f"/v1/projects/ald/seals/{a.seal_id}"
        if a.lodge:
            r = http.post(f"{base}/lodge", json={"prereg_hash": want, "prereg_ref": a.prereg_ref})
            print(r.status_code, r.text[:300])
            raise SystemExit(0 if r.status_code < 300 else 1)
        st = http.get(base)
        st.raise_for_status()
        st = st.json()
        if st.get("state") != "unsealed" and not a.dry_run:
            raise SystemExit(f"seal {a.seal_id} is '{st.get('state')}', not unsealed. Lodge first (--lodge), wait "
                             f"min_lodge_hours, then POST {base}/unseal (or /p/ald/v1/admin/unseal).")
        if (st.get("prereg_hash") or "").lower().removeprefix("sha256:") != want:
            raise SystemExit(f"REFUSED: seal prereg_hash {st.get('prereg_hash')} != docs/prereg.md {want}")
        print(f"seal {a.seal_id} unsealed at {st.get('unsealed_at')} with {want} ({len(st.get('audit') or [])} audit entries)")
        if not key:
            raise SystemExit("--key is required to decrypt")
        lst = http.get(f"{base}/objects")
        lst.raise_for_status()
        objs = lst.json()
        objs = objs.get("objects", objs) if isinstance(objs, dict) else objs
        for o in objs:
            k = o["key"]
            items.append((o.get("job_id") or k.split("/")[-2], o.get("worker_id") or Path(k).name.split(".")[0],
                          o.get("part_n"), (lambda k=k: http.get(f"{base}/objects/{k}").raise_for_status().content),
                          o.get("cipher_sha256") or o.get("sha256"), o.get("plain_sha256"), True))
    else:  # cloudflare: server-side sealed plaintext, one-way unseal there
        cfg = json.loads((Path.home() / ".config/ald-admin.json").read_text())
        http = httpx.Client(base_url=cfg["url"].rstrip("/"), timeout=300,
                            headers={"Authorization": f"Bearer {cfg['admin_token']}"})
        if a.cloudflare_unseal:
            r = http.post("/v1/admin/unseal", json={"prereg_hash": want})
            if r.status_code >= 300:
                raise SystemExit(f"Cloudflare unseal refused: {r.status_code} {r.text[:200]}")
            if (r.json().get("prereg_hash") or "") != want:
                raise SystemExit(f"REFUSED: Cloudflare seal was unsealed with {r.json().get('prereg_hash')}, not {want}")
            print("Cloudflare:", r.json().get("status"), r.json().get("unsealed_at"))
        r = http.get("/v1/admin/results", params={"split": "confirmation", "since": "1970-01-01T00:00:00Z"})
        if r.status_code == 403:
            raise SystemExit("Cloudflare coordinator is still sealed (run with --cloudflare-unseal)")
        r.raise_for_status()
        for x in r.json()["results"]:
            k = x["r2_key"]
            items.append((x["job_id"], x["worker_id"], x.get("part_n"),
                          (lambda k=k: http.get("/v1/admin/blob", params={"key": k}).raise_for_status().content),
                          None, x.get("content_sha256"), False))

    OUT.mkdir(parents=True, exist_ok=True)
    manifest, wrote, skipped = [], 0, 0
    for job_id, worker_id, part_n, fetch, cipher_sha, plain_sha, encrypted in items:
        dest = target_path(job_id, worker_id, part_n)
        if dest.exists() and plain_sha and sha(dest.read_bytes()) == plain_sha:
            skipped += 1
        else:
            ct = fetch()
            if cipher_sha and sha(ct) != cipher_sha:
                raise SystemExit(f"ciphertext sha256 mismatch for {job_id}/{worker_id}; nothing written for it")
            pt = sealed.decrypt(ct, key) if encrypted else ct
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
