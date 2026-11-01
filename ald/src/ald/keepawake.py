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
        self.active = False  # True once sleep is actually inhibited

    def __enter__(self) -> "KeepAwake":
        if not self.enabled:
            return self
        try:
            if sys.platform == "win32":
                import ctypes
                ok = ctypes.windll.kernel32.SetThreadExecutionState(self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED)
                self._win = True
                self.active = bool(ok)
                self.log("[keep-awake] SetThreadExecutionState(ES_SYSTEM_REQUIRED)")
            elif sys.platform == "darwin":
                self._proc = subprocess.Popen(["caffeinate", "-i", "-m", "-s", "-w", str(os.getpid())])
                self.active = True
                self.log("[keep-awake] caffeinate -i -m -s -w <pid> (idle+system sleep blocked on AC; closing the lid still sleeps unless an external display is attached)")
            else:
                inhibit = shutil.which("systemd-inhibit")
                if inhibit:
                    holder = ["tail", f"--pid={os.getpid()}", "-f", "/dev/null"]
                    self._proc = subprocess.Popen(
                        [inhibit, "--what=sleep:idle:handle-lid-switch", "--who=ald", "--why=ald work is labeling passages",
                         "--mode=block", *holder],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self.active = True
                    self.log("[keep-awake] systemd-inhibit --what=sleep:idle:handle-lid-switch")
                else:
                    self.log("[keep-awake] systemd-inhibit not available; sleep is not inhibited")
        except Exception as e:  # noqa: BLE001
            self.log(f"[keep-awake] could not inhibit sleep: {e}")
        return self

    def alive(self) -> bool:
        if self._proc is not None:
            return self._proc.poll() is None
        return self.active

    def __exit__(self, *exc: Any) -> None:
        self.active = False
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


def battery_ok(min_percent: int = 30) -> tuple[bool, str]:
    """False when running on battery below ``min_percent`` (pause leasing to avoid draining laptops)."""
    try:
        import psutil
        b = psutil.sensors_battery()
    except Exception:  # noqa: BLE001
        return True, "battery: unknown"
    if b is None:
        return True, "battery: none (desktop)"
    if b.power_plugged:
        return True, f"battery: {b.percent:.0f}% plugged in"
    if b.percent < min_percent:
        return False, f"battery: {b.percent:.0f}% on battery (< {min_percent}%) - pausing new leases"
    return True, f"battery: {b.percent:.0f}% on battery"


def battery_info() -> dict[str, Any]:
    try:
        import psutil
        b = psutil.sensors_battery()
    except Exception:  # noqa: BLE001
        return {}
    if b is None:
        return {"percent": None, "plugged": None}
    return {"percent": round(float(b.percent)), "plugged": bool(b.power_plugged)}
