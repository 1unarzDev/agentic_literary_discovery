"""Hardware detection: OS/arch, CPU, RAM, GPU + VRAM, disk."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import psutil

APPLE_USABLE_FRACTION = 0.65
GiB = 1024 ** 3

Runner = Callable[[list[str]], str | None]


def _run(cmd: list[str], timeout: float = 10.0) -> str | None:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8",
                           errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout if p.returncode == 0 else None


@dataclass
class GPU:
    name: str
    vram_gb: float
    vendor: str  # nvidia | amd | apple


@dataclass
class HardwareInfo:
    os: str
    arch: str
    os_release: str
    cpu_model: str
    cpu_cores_physical: int
    cpu_cores_logical: int
    ram_gb: float
    gpus: list[GPU] = field(default_factory=list)
    usable_vram_gb: float = 0.0
    accel: str = "cpu"  # cuda | rocm | metal | cpu
    disk_free_gb: float | None = None
    disk_path: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def gpu_summary(self) -> str:
        if not self.gpus:
            return "none"
        return ", ".join(f"{g.name} ({g.vram_gb:.1f} GB)" for g in self.gpus)

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["gpu_summary"] = self.gpu_summary
        return d


def nvidia_smi_path(which: Callable[[str], str | None] = shutil.which, system: str | None = None) -> str | None:
    p = which("nvidia-smi")
    if p:
        return p
    if (system or platform.system()) == "Windows":
        root = os.environ.get("SystemRoot", r"C:\Windows")
        cand = os.path.join(root, "System32", "nvidia-smi.exe")
        if os.path.exists(cand):
            return cand
        cand = r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"
        if os.path.exists(cand):
            return cand
    return None


def parse_nvidia_smi(out: str) -> list[GPU]:
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            continue
        try:
            mib = float(parts[-1])
        except ValueError:
            continue
        gpus.append(GPU(name=",".join(parts[:-1]), vram_gb=round(mib / 1024, 2), vendor="nvidia"))
    return gpus


def parse_rocm_smi(out: str) -> list[GPU]:
    gpus = []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return gpus
    for card, info in data.items():
        if not isinstance(info, dict):
            continue
        total = None
        for k, v in info.items():
            if "total" in k.lower() and "vram" in k.lower() and "used" not in k.lower():
                try:
                    total = float(v)
                except (TypeError, ValueError):
                    pass
        if total:
            gpus.append(GPU(name=str(info.get("Card series", card)), vram_gb=round(total / GiB, 2), vendor="amd"))
    return gpus


def detect(data_path: Path | None = None, run: Callable[[list[str]], str | None] = _run) -> HardwareInfo:
    system = platform.system()
    arch = platform.machine().lower()
    vm = psutil.virtual_memory()
    info = HardwareInfo(
        os={"Darwin": "macos", "Windows": "windows", "Linux": "linux"}.get(system, system.lower()),
        arch={"amd64": "x86_64", "aarch64": "arm64"}.get(arch, arch),
        os_release=platform.release(),
        cpu_model=platform.processor() or arch,
        cpu_cores_physical=psutil.cpu_count(logical=False) or 1,
        cpu_cores_logical=psutil.cpu_count(logical=True) or 1,
        ram_gb=round(vm.total / GiB, 2),
    )

    # NVIDIA
    smi = nvidia_smi_path(system=system)
    if smi:
        out = run([smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
        if out:
            info.gpus = parse_nvidia_smi(out)
            if info.gpus:
                info.accel = "cuda"
        else:
            info.notes.append("nvidia-smi found but failed; is the driver loaded?")

    # Apple Silicon: unified memory, ~65% usable by the GPU.
    if not info.gpus and system == "Darwin" and info.arch == "arm64":
        out = run(["sysctl", "-n", "hw.memsize"])
        try:
            mem = int(out.strip()) if out else vm.total
        except ValueError:
            mem = vm.total
        brand = (run(["sysctl", "-n", "machdep.cpu.brand_string"]) or "Apple Silicon").strip()
        info.cpu_model = brand
        info.gpus = [GPU(name=brand, vram_gb=round(mem / GiB, 2), vendor="apple")]
        info.accel = "metal"

    # AMD (best effort)
    if not info.gpus and shutil.which("rocm-smi"):
        out = run(["rocm-smi", "--showmeminfo", "vram", "--json"])
        if out:
            info.gpus = parse_rocm_smi(out)
            if info.gpus:
                info.accel = "rocm"

    if info.gpus:
        best = max(g.vram_gb for g in info.gpus)
        if info.accel == "metal":
            info.usable_vram_gb = round(best * APPLE_USABLE_FRACTION, 2)
            info.notes.append(f"Apple unified memory: {APPLE_USABLE_FRACTION:.0%} counted as usable VRAM")
        else:
            info.usable_vram_gb = best
        if len(info.gpus) > 1:
            info.notes.append("multiple GPUs: tier uses the largest single GPU")

    if system == "Linux" and info.cpu_model in ("", "x86_64", "arm64", "aarch64", arch):
        try:
            for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
                if line.startswith("model name"):
                    info.cpu_model = line.split(":", 1)[1].strip()
                    break
        except OSError:
            pass

    if data_path is not None:
        p = Path(data_path)
        p.mkdir(parents=True, exist_ok=True)
        info.disk_path = str(p)
        info.disk_free_gb = round(shutil.disk_usage(str(p)).free / GiB, 2)
    return info
