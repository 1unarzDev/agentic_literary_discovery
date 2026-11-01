"""Result encoding, per-job checkpoints and the durable upload outbox.

On-disk layout under the data dir (all names are ':'-free and short):

    shards/<job>.jsonl.gz          downloaded shard (deleted after final ack)
    jobs/<job>/meta.json           job + pin info, state
    jobs/<job>/checkpoint.jsonl    append-only result lines (fsync every N)
    outbox/<job>.<kind>.<sha12>.gz          result blob awaiting ack
    outbox/<job>.<kind>.<sha12>.json        its upload headers / bookkeeping
    outbox/rejected/...                     non-retryable rejections (kept)
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from .config import atomic_write_bytes, atomic_write_json, read_json, replace_with_retry, safe_name


# --------------------------------------------------------------------------
# JSONL.gz encoding (deterministic: same lines -> same bytes -> same sha)
# --------------------------------------------------------------------------

def dumps_line(obj: dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def encode_jsonl_gz(lines: Iterable[dict[str, Any]]) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0, compresslevel=6) as gz:
        for obj in lines:
            gz.write(dumps_line(obj).encode("utf-8"))
            gz.write(b"\n")
    return buf.getvalue()


def decode_jsonl_gz(data: bytes) -> list[dict[str, Any]]:
    text = gzip.decompress(data).decode("utf-8")
    return [json.loads(l) for l in text.split("\n") if l.strip()]


def read_jsonl_gz(path: Path) -> list[dict[str, Any]]:
    with open(path, "rb") as f:
        return decode_jsonl_gz(f.read())


def write_jsonl_gz(path: Path, lines: Iterable[dict[str, Any]]) -> tuple[bytes, str]:
    data = encode_jsonl_gz(lines)
    atomic_write_bytes(path, data)
    return data, hashlib.sha256(data).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------
# Checkpoint: append-only JSONL per job
# --------------------------------------------------------------------------

class Checkpoint:
    def __init__(self, job_dir: Path, fsync_every: int = 20):
        self.dir = job_dir
        self.path = job_dir / "checkpoint.jsonl"
        self.fsync_every = fsync_every
        self._f = None
        self._since_sync = 0

    def load(self) -> dict[str, dict[str, Any]]:
        """passage_id -> line. Tolerates a torn last line after a crash."""
        out: dict[str, dict[str, Any]] = {}
        if not self.path.exists():
            return out
        with open(self.path, "r", encoding="utf-8", newline="\n") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                pid = obj.get("passage_id")
                if pid is not None and pid not in out:
                    out[pid] = obj
        return out

    def _open(self):
        if self._f is None:
            self.dir.mkdir(parents=True, exist_ok=True)
            # Repair a torn tail so the next append starts on a fresh line.
            if self.path.exists() and self.path.stat().st_size > 0:
                with open(self.path, "rb") as f:
                    f.seek(-1, os.SEEK_END)
                    last = f.read(1)
                if last != b"\n":
                    with open(self.path, "ab") as f:
                        f.write(b"\n")
            self._f = open(self.path, "a", encoding="utf-8", newline="\n")
        return self._f

    def append(self, line: dict[str, Any]) -> None:
        f = self._open()
        f.write(dumps_line(line) + "\n")
        f.flush()
        self._since_sync += 1
        if self._since_sync >= self.fsync_every:
            self.sync()

    def sync(self) -> None:
        if self._f is not None:
            self._f.flush()
            try:
                os.fsync(self._f.fileno())
            except OSError:
                pass
            self._since_sync = 0

    def close(self) -> None:
        if self._f is not None:
            self.sync()
            self._f.close()
            self._f = None


class JobStore:
    """jobs/<job>/ directories (meta + checkpoint) and shards/."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.jobs_dir = self.root / "jobs"
        self.shards_dir = self.root / "shards"

    def job_dir(self, job_id: str) -> Path:
        return self.jobs_dir / safe_name(job_id)

    def shard_path(self, job_id: str) -> Path:
        return self.shards_dir / f"{safe_name(job_id)}.jsonl.gz"

    def checkpoint(self, job_id: str) -> Checkpoint:
        return Checkpoint(self.job_dir(job_id))

    def write_meta(self, job_id: str, meta: dict[str, Any]) -> None:
        atomic_write_json(self.job_dir(job_id) / "meta.json", meta)

    def read_meta(self, job_id_dir: Path) -> dict[str, Any] | None:
        return read_json(job_id_dir / "meta.json")

    def iter_jobs(self) -> Iterator[tuple[Path, dict[str, Any]]]:
        if not self.jobs_dir.exists():
            return
        for d in sorted(self.jobs_dir.iterdir()):
            if d.is_dir():
                meta = self.read_meta(d)
                if meta:
                    yield d, meta

    def remove_job(self, job_id: str) -> None:
        shutil.rmtree(self.job_dir(job_id), ignore_errors=True)
        try:
            self.shard_path(job_id).unlink()
        except FileNotFoundError:
            pass

    def cached_lines(self, pin_hash: str, passage_ids: set[str]) -> dict[str, dict[str, Any]]:
        """Local result cache keyed by (passage_id, pin_hash): reuse lines from
        any checkpoint on disk with the same pin."""
        out: dict[str, dict[str, Any]] = {}
        for d, meta in self.iter_jobs():
            if meta.get("pin_hash") != pin_hash:
                continue
            for pid, line in Checkpoint(d).load().items():
                if pid in passage_ids and line.get("pin_hash") == pin_hash and pid not in out:
                    out[pid] = line
        return out


# --------------------------------------------------------------------------
# Outbox
# --------------------------------------------------------------------------

@dataclass
class OutboxEntry:
    blob: Path
    meta_path: Path
    meta: dict[str, Any]

    @property
    def job_id(self) -> str:
        return self.meta["job_id"]

    @property
    def partial(self) -> bool:
        return bool(self.meta.get("partial"))


class Outbox:
    RETRYABLE = {401, 408, 425, 426, 429, 500, 502, 503, 504}

    def __init__(self, root: Path):
        self.dir = Path(root) / "outbox"
        self.rejected = self.dir / "rejected"

    def add(self, job_id: str, body: bytes, headers: dict[str, str], *, partial: bool,
            n_lines: int, created: float) -> OutboxEntry:
        sha = sha256_bytes(body)
        kind = "partial" if partial else "final"
        stem = f"{safe_name(job_id, 60)}.{kind}.{sha[:12]}"
        blob = self.dir / f"{stem}.gz"
        meta_path = self.dir / f"{stem}.json"
        # Blob first, meta second: an entry exists only once its meta exists.
        atomic_write_bytes(blob, body)
        meta = {"job_id": job_id, "partial": partial, "headers": headers, "sha256": sha,
                "n_lines": n_lines, "created": created, "attempts": 0, "next_attempt": 0.0,
                "last_error": None}
        atomic_write_json(meta_path, meta)
        return OutboxEntry(blob, meta_path, meta)

    def entries(self) -> list[OutboxEntry]:
        if not self.dir.exists():
            return []
        out = []
        for mp in sorted(self.dir.glob("*.json")):
            meta = read_json(mp)
            blob = mp.with_suffix(".gz")
            if not meta or not blob.exists():
                continue
            out.append(OutboxEntry(blob, mp, meta))
        # Finals before partials, oldest first.
        out.sort(key=lambda e: (e.partial, e.meta.get("created", 0)))
        return out

    def size(self) -> tuple[int, int]:
        es = self.entries()
        return len(es), sum(e.blob.stat().st_size for e in es if e.blob.exists())

    def remove(self, e: OutboxEntry) -> None:
        for p in (e.meta_path, e.blob):
            try:
                p.unlink()
            except FileNotFoundError:
                pass

    def reject(self, e: OutboxEntry, reason: str) -> None:
        self.rejected.mkdir(parents=True, exist_ok=True)
        e.meta["rejected"] = reason
        atomic_write_json(self.rejected / e.meta_path.name, e.meta)
        replace_with_retry(e.blob, self.rejected / e.blob.name)
        try:
            e.meta_path.unlink()
        except FileNotFoundError:
            pass

    def flush(
        self,
        put: Callable[[str, bytes, dict[str, str], bool], dict[str, Any]],
        *,
        now: float,
        on_ack: Callable[[OutboxEntry, dict[str, Any]], None] | None = None,
        on_reject: Callable[[OutboxEntry, str], None] | None = None,
        backoff: Callable[[int], float] = lambda n: min(600.0, 5.0 * (2 ** n)),
        force: bool = False,
        is_network_error: Callable[[BaseException], bool] = lambda e: False,
    ) -> dict[str, int]:
        """Try every due entry once. Returns counts. ``put(job_id, body,
        headers, partial)`` raises ``CoordinatorError``-like exceptions with a
        ``status`` attribute, or network errors."""
        counts = {"acked": 0, "rejected": 0, "deferred": 0}
        for e in self.entries():
            if not force and e.meta.get("next_attempt", 0) > now:
                counts["deferred"] += 1
                continue
            body = e.blob.read_bytes()
            if sha256_bytes(body) != e.meta.get("sha256"):
                self.reject(e, "corrupt blob (sha mismatch)")
                counts["rejected"] += 1
                continue
            try:
                resp = put(e.job_id, body, e.meta["headers"], e.partial)
            except Exception as exc:  # noqa: BLE001
                status = getattr(exc, "status", None)
                # 409 on a partial = concurrent partial upload; the coordinator says retry.
                retryable = status in self.RETRYABLE or (status == 409 and e.partial)
                if status is not None and not retryable:
                    reason = f"HTTP {status}: {exc}"
                    self.reject(e, reason)
                    counts["rejected"] += 1
                    if on_reject:
                        on_reject(e, reason)
                    continue
                e.meta["attempts"] = int(e.meta.get("attempts", 0)) + 1
                e.meta["next_attempt"] = now + backoff(e.meta["attempts"])
                e.meta["last_error"] = str(exc)[:300]
                atomic_write_json(e.meta_path, e.meta)
                counts["deferred"] += 1
                if is_network_error(exc):
                    # Network is down: don't hammer the remaining entries.
                    break
                continue
            self.remove(e)
            counts["acked"] += 1
            if on_ack:
                on_ack(e, resp)
        return counts
