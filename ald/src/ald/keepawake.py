"""Prevent system sleep while ``ald work --keep-awake`` runs."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Any


class KeepAwake:
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001

    def __init__(self, enabled: bool = True, log: Any = print):
        self.enabled = enabled
        self.log = log
        self._proc: subprocess.Popen | None = None
        self._win = False

    def __enter__(self) -> "KeepAwake":
        if not self.enabled:
            return self
        try:
            if sys.platform == "win32":
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED)
                self._win = True
                self.log("[keep-awake] SetThreadExecutionState(ES_SYSTEM_REQUIRED)")
            elif sys.platform == "darwin":
                self._proc = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
                self.log("[keep-awake] caffeinate -i -w <pid>")
            else:
                inhibit = shutil.which("systemd-inhibit")
                if inhibit:
                    holder = ["tail", f"--pid={os.getpid()}", "-f", "/dev/null"]
                    self._proc = subprocess.Popen(
                        [inhibit, "--what=sleep:idle", "--who=ald", "--why=ald work is labeling passages",
                         "--mode=block", *holder],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self.log("[keep-awake] systemd-inhibit --what=sleep:idle")
                else:
                    self.log("[keep-awake] systemd-inhibit not available; sleep is not inhibited")
        except Exception as e:  # noqa: BLE001
            self.log(f"[keep-awake] could not inhibit sleep: {e}")
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._win:
            try:
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(self.ES_CONTINUOUS)
            except Exception:  # noqa: BLE001
                pass
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                pass
