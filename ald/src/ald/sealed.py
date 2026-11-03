"""Client-side encryption of SEALED (confirmation-split) results: age v1, X25519 recipient.

The platform stores ciphertext only. The private key is held offline by the owner and is used once, at
unseal, by pipeline/unseal.py (docs/migration_plan.md section 3).

The recipient served by the coordinator (`/v1/ping` `sealed_recipient`) must equal ``PINNED_RECIPIENT``, which
ships in the client release. A server cannot substitute its own key. While nothing is pinned (before the owner's
key ceremony) or the server offers nothing, uploads stay as they are today on the Cloudflare coordinator, which
keeps confirmation blobs sealed server-side.
"""

from __future__ import annotations

import hashlib

# Set to the owner's public key ("age1...") at the key ceremony, then release the client.
PINNED_RECIPIENT: str | None = None

SEALED_SCHEME = "age-x25519"


class SealedKeyMismatch(Exception):
    """The coordinator offered a recipient that is not the one pinned in this release."""


def resolve_recipient(offered: str | None, pinned: str | None = None) -> str | None:
    """The recipient to encrypt to, or None if this coordinator does not use client-side sealing.
    Raises SealedKeyMismatch if the coordinator asks for sealing with an unpinned/different key."""
    pinned = PINNED_RECIPIENT if pinned is None else pinned
    if not offered:
        return None
    if not pinned or offered.strip() != pinned.strip():
        raise SealedKeyMismatch(f"coordinator sealed_recipient {offered[:16]}... is not the key pinned in this "
                                f"release ({(pinned or 'none')[:16]}...)")
    return pinned.strip()


def encrypt(plaintext: bytes, recipient: str) -> bytes:
    import pyrage
    from pyrage import x25519
    return pyrage.encrypt(plaintext, [x25519.Recipient.from_str(recipient)])


def decrypt(ciphertext: bytes, identity_text: str) -> bytes:
    import pyrage
    from pyrage import x25519
    ident = None
    for line in identity_text.splitlines():
        line = line.strip()
        if line.startswith("AGE-SECRET-KEY-"):
            ident = x25519.Identity.from_str(line)
            break
    if ident is None:
        raise ValueError("no AGE-SECRET-KEY line in the key file")
    return pyrage.decrypt(ciphertext, [ident])


def seal_headers(plaintext: bytes, ciphertext: bytes) -> dict[str, str]:
    return {"X-Content-Sha256": hashlib.sha256(ciphertext).hexdigest(),
            "X-Plain-Sha256": hashlib.sha256(plaintext).hexdigest(),
            "X-Sealed": SEALED_SCHEME}
