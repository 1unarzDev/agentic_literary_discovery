"""Ollama HTTP backend (the only supported backend: other kernels would be a
confound)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from ..registry import bare_digest, digests_match

OOM_MARKERS = (
    "out of memory", "cudamalloc", "cuda error", "insufficient memory", "requires more system memory",
    "failed to allocate", "metal: error", "unable to allocate",
)


class BackendError(Exception):
    pass


class BackendUnavailable(BackendError):
    """Ollama is not reachable (not installed, not running, or restarting)."""


class BackendOOM(BackendError):
    pass


@dataclass
class ChatResult:
    content: str
    prompt_tokens: int
    gen_tokens: int
    eval_s: float
    total_s: float
    raw: dict[str, Any]


def _classify(status: int, text: str) -> BackendError:
    low = text.lower()
    if any(m in low for m in OOM_MARKERS):
        return BackendOOM(f"Ollama OOM ({status}): {text[:300]}")
    return BackendError(f"Ollama error ({status}): {text[:300]}")


class OllamaBackend:
    name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434", *, transport: httpx.BaseTransport | None = None,
                 timeout: float = 600.0):
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(base_url=self.base_url, timeout=httpx.Timeout(timeout, connect=5.0),
                                  transport=transport)
        self._version: str | None = None

    def close(self) -> None:
        self._http.close()

    def _req(self, method: str, path: str, **kw: Any) -> httpx.Response:
        try:
            r = self._http.request(method, path, **kw)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.RemoteProtocolError, httpx.ReadError) as e:
            raise BackendUnavailable(f"Ollama not reachable at {self.base_url}: {e}") from e
        if r.status_code >= 400:
            raise _classify(r.status_code, r.text)
        return r

    # -- metadata ---------------------------------------------------------
    def version(self, refresh: bool = False) -> str:
        if self._version is None or refresh:
            self._version = str(self._req("GET", "/api/version").json().get("version", "0"))
        return self._version

    def available(self) -> bool:
        try:
            self.version(refresh=True)
            return True
        except BackendError:
            return False

    def tags(self) -> list[dict[str, Any]]:
        return self._req("GET", "/api/tags").json().get("models", []) or []

    def local_digest(self, model_ref: str) -> str | None:
        want = {model_ref, model_ref if ":" in model_ref else f"{model_ref}:latest"}
        for m in self.tags():
            if m.get("name") in want or m.get("model") in want:
                return bare_digest(m.get("digest"))
        return None

    def has_model(self, model_ref: str, digest: str | None = None) -> bool:
        d = self.local_digest(model_ref)
        if d is None:
            return False
        return digests_match(d, digest) if digest else True

    def show(self, model_ref: str) -> dict[str, Any]:
        return self._req("POST", "/api/show", json={"model": model_ref}).json()

    def ps(self) -> list[dict[str, Any]]:
        try:
            return self._req("GET", "/api/ps").json().get("models", []) or []
        except BackendError:
            return []

    @staticmethod
    def same_model(name: str | None, model_ref: str) -> bool:
        if not name:
            return False
        norm = lambda n: n if ":" in n else f"{n}:latest"  # noqa: E731
        return norm(name) == norm(model_ref)

    def unload(self, model: str) -> None:
        """Evict a resident model (``keep_alive: 0``)."""
        self._req("POST", "/api/generate", json={"model": model, "keep_alive": 0})

    def unload_others(self, keep: set[str]) -> list[str]:
        """Unload every resident model not in ``keep`` (model refs). Returns names unloaded."""
        out = []
        for m in self.ps():
            name = m.get("name") or m.get("model")
            if name and not any(self.same_model(name, k) for k in keep):
                try:
                    self.unload(name)
                    out.append(name)
                except BackendError:
                    pass
        return out

    def residency(self, model_ref: str) -> float | None:
        """Fraction of the resident model held in VRAM (1.0 = fully on GPU),
        or None if it is not loaded."""
        for m in self.ps():
            if self.same_model(m.get("name") or m.get("model"), model_ref):
                size = float(m.get("size") or 0)
                vram = float(m.get("size_vram") or 0)
                return (vram / size) if size > 0 else None
        return None

    def pull(self, model_ref: str, progress: Callable[[dict[str, Any]], None] | None = None) -> None:
        try:
            with self._http.stream("POST", "/api/pull", json={"model": model_ref, "stream": True},
                                   timeout=httpx.Timeout(None, connect=5.0)) as r:
                if r.status_code >= 400:
                    r.read()
                    raise _classify(r.status_code, r.text)
                for line in r.iter_lines():
                    if not line.strip():
                        continue
                    ev = json.loads(line)
                    if ev.get("error"):
                        raise BackendError(f"pull {model_ref}: {ev['error']}")
                    if progress:
                        progress(ev)
        except httpx.ConnectError as e:
            raise BackendUnavailable(str(e)) from e

    def backend_version(self, accel: str | None = None) -> str:
        v = f"ollama/{self.version()}"
        return f"{v}+{accel}" if accel else v

    # -- inference ----------------------------------------------------------
    def chat(self, model: str, messages: list[dict[str, str]], *, schema: dict[str, Any] | None,
             options: dict[str, Any], think: bool | None) -> ChatResult:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": options,
            "keep_alive": -1,
        }
        if schema is not None:
            body["format"] = schema
        if think is not None:
            body["think"] = think
        r = self._req("POST", "/api/chat", json=body)
        data = r.json()
        if data.get("error"):
            raise _classify(500, str(data["error"]))
        msg = data.get("message") or {}
        return ChatResult(
            content=msg.get("content", "") or "",
            prompt_tokens=int(data.get("prompt_eval_count", 0) or 0),
            gen_tokens=int(data.get("eval_count", 0) or 0),
            eval_s=(data.get("eval_duration", 0) or 0) / 1e9,
            total_s=(data.get("total_duration", 0) or 0) / 1e9,
            raw=data,
        )
