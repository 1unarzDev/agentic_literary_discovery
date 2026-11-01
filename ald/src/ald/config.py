"""User configuration and on-disk layout.

``ALD_HOME`` overrides every location (handy for tests and for keeping cache
paths short on Windows). Otherwise platformdirs decides:

* config: ``user_config_dir("ald")/config.json`` (chmod 600 where supported)
* data:   ``user_data_dir("ald")`` with ``shards/``, ``jobs/``, ``outbox/``
"""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import platformdirs

APP = "ald"
DEFAULT_OLLAMA_URL = "http://localhost:11434"


def _home() -> Path | None:
    h = os.environ.get("ALD_HOME")
    return Path(h) if h else None


def config_dir() -> Path:
    h = _home()
    return (h / "config") if h else Path(platformdirs.user_config_dir(APP, appauthor=False))


def data_dir() -> Path:
    h = _home()
    return (h / "data") if h else Path(platformdirs.user_data_dir(APP, appauthor=False))


def pause_marker() -> Path:
    """Exists while the worker is paused (`ald pause`); read by the worker and the Windows update helper."""
    return data_dir() / "paused"


def config_path() -> Path:
    return config_dir() / "config.json"


_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def safe_name(s: str, maxlen: int = 80) -> str:
    """Filesystem-safe on every OS: no ':' or path separators, short."""
    out = _SAFE.sub("_", s)[:maxlen]
    return out or "_"


def replace_with_retry(src: str | os.PathLike, dst: str | os.PathLike, attempts: int = 10) -> None:
    """``os.replace`` that tolerates transient Windows sharing violations
    (antivirus, indexers)."""
    delay = 0.05
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 1.0)


def atomic_write_bytes(path: Path, data: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            try:
                os.chmod(tmp, mode)
            except OSError:
                pass
        replace_with_retry(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_json(path: Path, obj: Any, mode: int | None = None) -> None:
    atomic_write_bytes(path, (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8"), mode)


def read_json(path: Path, default: Any = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


@dataclass
class Config:
    coordinator_url: str | None = None
    token: str | None = None
    worker_id: str | None = None
    name: str | None = None
    tier: str | None = None
    ollama_url: str = DEFAULT_OLLAMA_URL
    disk_budget_gb: float | None = None
    bench: dict[str, Any] = field(default_factory=dict)  # stage -> {best_concurrency, pph, tok_s}
    manage_ollama: bool = True  # start Ollama / apply the tier's OLLAMA_* settings (ALD_MANAGE_OLLAMA=0: never)
    # `ald work` settings (edit with `ald config`; the background service reads them at every start).
    max_concurrency: int | None = None   # upper bound for auto-tuned concurrency (default 8)
    stages: list[str] | None = None      # subset of the tier's stages (default: all allowed)
    active_hours: str | None = None      # "HH:MM-HH:MM" local time, may wrap midnight (default: always)
    gpu_lock: str | None = None          # flock(2) path shared with other GPU programs (Linux/macOS)
    auto_update: bool = True
    keep_awake: bool = True              # False = allow sleep while working
    min_free_ram_gb: float = 8.0         # pause / hand back work when available system RAM drops below this
    host_prompt_cache_mb: int = 0        # llama-server host-RAM prompt cache (LLAMA_ARG_CACHE_RAM); 0 = off

    @classmethod
    def load(cls) -> "Config":
        raw = read_json(config_path(), {}) or {}
        known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        cfg = cls(**known)
        env_url = os.environ.get("ALD_COORDINATOR")
        if env_url:
            cfg.coordinator_url = env_url
        env_tok = os.environ.get("ALD_TOKEN")
        if env_tok:
            cfg.token = env_tok
        if os.environ.get("ALD_MANAGE_OLLAMA", "").strip().lower() in ("0", "false", "no"):
            cfg.manage_ollama = False
        env_ollama = os.environ.get("OLLAMA_HOST")
        if env_ollama and "ollama_url" not in raw:
            cfg.ollama_url = env_ollama if env_ollama.startswith("http") else f"http://{env_ollama}"
        return cfg

    def save(self) -> Path:
        p = config_path()
        atomic_write_json(p, asdict(self), mode=stat.S_IRUSR | stat.S_IWUSR)
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass
        return p
