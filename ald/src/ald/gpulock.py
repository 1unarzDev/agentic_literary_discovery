"""``ald work --gpu-lock PATH``: share one GPU with other programs through an advisory ``flock(2)`` lock.

Compatible with util-linux ``flock PATH <cmd>`` (same lock type). The worker holds the lock for the
inference of one shard at a time. Before releasing it, if another process is blocked on the lock, the
worker unloads its model so the next holder gets the VRAM. Waiters are detected from ``/proc/locks``
(Linux). Where that is not available (macOS), the model is unloaded when the worker goes idle instead.

Windows: a no-op (``fcntl`` does not exist there).
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from typing import Callable

try:
    import fcntl  # type: ignore[import-not-found]
except ImportError:  # Windows
    fcntl = None  # type: ignore[assignment]

PROC_LOCKS = Path("/proc/locks")


def parse_waiters(proc_locks: str, inode: int) -> int:
    """Number of processes blocked on an flock of ``inode`` (lines like ``12: -> FLOCK ... 00:25:<inode> 0 EOF``)."""
    n = 0
    for line in proc_locks.splitlines():
        parts = line.split()
        if "->" not in parts or "FLOCK" not in parts:
            continue
        for tok in parts:
            if tok.count(":") == 2 and tok.rsplit(":", 1)[-1] == str(inode):
                n += 1
                break
    return n


class GpuLock:
    def __init__(self, path: str | os.PathLike | None, *, log: Callable[[str], None] = print, poll_s: float = 1.0,
                 platform: str = sys.platform, proc_locks: Path = PROC_LOCKS):
        self.path = Path(path) if path else None
        self.enabled = self.path is not None and fcntl is not None and platform != "win32"
        self.log = log
        self.poll_s = poll_s
        self.proc_locks = proc_locks
        self._fd: int | None = None
        if path and not self.enabled:
            log("[gpu-lock] not supported on this platform; ignoring --gpu-lock")

    @property
    def held(self) -> bool:
        return self._fd is not None

    def acquire(self, stop: threading.Event | None = None, abort: Callable[[], bool] | None = None) -> bool:
        """Block until the lock is ours. False if ``stop`` was set (or ``abort()`` became true) while waiting."""
        if not self.enabled or self.held:
            return True
        assert self.path is not None
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o666)
        waited = False
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._fd = fd
                if waited:
                    self.log(f"[gpu-lock] acquired {self.path}")
                return True
            except BlockingIOError:
                if not waited:
                    self.log(f"[gpu-lock] {self.path} is held by another process; waiting")
                    waited = True
                if stop is None:
                    time.sleep(self.poll_s)
                    stopped = False
                else:
                    stopped = stop.wait(self.poll_s)
                if stopped or (abort is not None and abort()):
                    os.close(fd)
                    return False

    def try_acquire(self) -> bool:
        """Take the lock only if it is free right now."""
        if not self.enabled or self.held:
            return True
        assert self.path is not None
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o666)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return False
        self._fd = fd
        return True

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = None

    def waiters(self) -> int | None:
        """Processes blocked on this lock, or None if that cannot be known on this OS."""
        if not self.enabled or self.path is None:
            return None
        try:
            text = self.proc_locks.read_text(encoding="utf-8", errors="replace")
            ino = os.stat(self.path).st_ino
        except OSError:
            return None
        return parse_waiters(text, ino)
