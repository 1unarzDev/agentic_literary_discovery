"""Owner key ceremony for SEALED results (docs/migration_plan.md section 3).

Run on a machine you trust (not the platform server):

  uv run --with pyrage python pipeline/seal_keygen.py --out /media/usb/ald-sealed.agekey
      writes the PRIVATE key (mode 600) and prints the PUBLIC recipient "age1...": the only line to share.
  uv run --with pyrage python pipeline/seal_keygen.py --check /media/usb/ald-sealed.agekey [--recipient age1...]
      proves a backup copy works: encrypts a test message to the recipient and decrypts it with the file.

Equivalent with the age CLI: `age-keygen -o ald-sealed.agekey`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path


def main() -> None:
    import pyrage
    from pyrage import x25519
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--out", help="where to write the new private key")
    g.add_argument("--check", help="an existing private key file to test")
    ap.add_argument("--recipient", help="with --check: the published public key it must match")
    a = ap.parse_args()
    if a.out:
        p = Path(a.out)
        if p.exists():
            sys.exit(f"{p} exists; refusing to overwrite a key")
        ident = x25519.Identity.generate()
        pub = str(ident.to_public())
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(f"# created: {dt.datetime.now().isoformat(timespec='seconds')}\n# public key: {pub}\n{ident}\n")
        print(f"private key written to {p} (keep it offline; see docs/migration_plan.md section 3)")
        print(f"PUBLIC recipient (share this line only):\n{pub}")
        return
    text = Path(a.check).read_text()
    line = next((l.strip() for l in text.splitlines() if l.strip().startswith("AGE-SECRET-KEY-")), None)
    if not line:
        sys.exit("no AGE-SECRET-KEY line in that file")
    ident = x25519.Identity.from_str(line)
    pub = str(ident.to_public())
    if a.recipient and a.recipient.strip() != pub:
        sys.exit(f"MISMATCH: this key's public key is {pub}, not {a.recipient}")
    msg = b"ald sealed key check"
    assert pyrage.decrypt(pyrage.encrypt(msg, [x25519.Recipient.from_str(pub)]), [ident]) == msg
    print(f"OK: the key file works; its public key is {pub}")


if __name__ == "__main__":
    main()
