"""HTTP client for the coordinator (see docs/api_contract.md)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx

from . import CLIENT_VERSION


def encode_passage_ids(body: bytes) -> str:
    """``X-Passage-Ids`` for partial uploads: base64(gzip(JSON list)) of the
    passage ids in the blob (coordinator/DEPLOY.md)."""
    import base64
    import gzip
    import json
    ids = []
    for line in gzip.decompress(body).decode("utf-8").split("\n"):
        if line.strip():
            ids.append(json.loads(line)["passage_id"])
    raw = json.dumps(ids, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(gzip.compress(raw, mtime=0)).decode("ascii")


class CoordinatorError(Exception):
    def __init__(self, status: int, message: str, body: Any = None):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.body = body


class UpgradeRequired(CoordinatorError):
    """426 from /v1/lease: client_version < MIN_CLIENT_VERSION."""


NETWORK_ERRORS = (httpx.TransportError,)


class CoordinatorClient:
    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 60.0,
        client_version: str = CLIENT_VERSION,
    ):
        self.base_url = base_url.rstrip("/") + "/"
        self.token = token
        self.client_version = client_version
        headers = {"User-Agent": f"ald/{client_version}", "X-Client-Version": client_version}
        self._http = httpx.Client(
            base_url=self.base_url, headers=headers, timeout=timeout, transport=transport,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._http.close()

    # -- helpers --------------------------------------------------------
    def _auth(self, token: str | None = None) -> dict[str, str]:
        t = token or self.token
        return {"Authorization": f"Bearer {t}"} if t else {}

    def _check(self, r: httpx.Response) -> httpx.Response:
        if r.status_code >= 400:
            try:
                body = r.json()
                msg = body.get("error") or body.get("message") or r.text
            except Exception:
                body, msg = None, r.text[:300]
            cls = UpgradeRequired if r.status_code == 426 else CoordinatorError
            raise cls(r.status_code, str(msg), body)
        return r

    def _url(self, path: str) -> str:
        return path.lstrip("/")

    def _json(self, method: str, path: str, body: Any = None, token: str | None = None) -> Any:
        r = self._http.request(method, self._url(path), json=body, headers=self._auth(token))
        self._check(r)
        return r.json() if r.content else {}

    # -- worker endpoints -------------------------------------------------
    def join(self, invite: str, info: dict[str, Any]) -> dict[str, Any]:
        body = {"invite": invite, **info, "client_version": self.client_version}
        r = self._http.post(self._url("/v1/join"), json=body)
        self._check(r)
        return r.json()

    last_retry_after: float | None = None

    def lease(self, tier: str, stages: list[str], max_jobs: int) -> list[dict[str, Any]]:
        body = {"tier": tier, "stages": stages, "max_jobs": max_jobs,
                "client_version": self.client_version}
        resp = self._json("POST", "/v1/lease", body)
        ra = resp.get("retry_after")
        self.last_retry_after = float(ra) if isinstance(ra, (int, float)) and ra > 0 else None
        return resp.get("jobs", []) or []

    def heartbeat(self, job_ids: list[str], stats: dict[str, Any]) -> dict[str, Any]:
        return self._json("POST", "/v1/heartbeat", {"job_ids": job_ids, "stats": stats})

    def release(self, job_ids: list[str]) -> dict[str, Any]:
        if not job_ids:
            return {}
        return self._json("POST", "/v1/release", {"job_ids": job_ids})

    def download_shard(self, job: dict[str, Any], dest: Path) -> int:
        """Stream the shard to ``dest`` (atomically). Uses ``shard_url`` if the
        lease gave one, else ``/v1/shard/<job_id>``."""
        url = job.get("shard_url") or f"/v1/shard/{job['job_id']}"
        headers = self._auth()
        if url.startswith("http://") or url.startswith("https://"):
            target = url
            # Never leak the bearer token to a different host (e.g. a signed R2 URL).
            if httpx.URL(url).host != httpx.URL(self.base_url).host:
                headers = {}
        else:
            target = self._url(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".part")
        n = 0
        with self._http.stream("GET", target, headers=headers) as r:
            if r.status_code >= 400:
                r.read()
                self._check(r)
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes(1 << 16):
                    f.write(chunk)
                    n += len(chunk)
        from .config import replace_with_retry
        replace_with_retry(tmp, dest)
        return n

    def put_result(self, job_id: str, body: bytes, headers: dict[str, str], partial: bool = False) -> dict[str, Any]:
        params = {"partial": "1"} if partial else None
        h = {**self._auth(), "Content-Type": "application/gzip", **headers}
        if partial and "X-Passage-Ids" not in h:
            h["X-Passage-Ids"] = encode_passage_ids(body)
        r = self._http.put(self._url(f"/v1/result/{job_id}"), content=body, headers=h, params=params)
        self._check(r)
        try:
            return r.json()
        except Exception:
            return {"status": "stored"}

    def registry(self, etag: str | None = None) -> tuple[dict[str, Any] | None, str | None]:
        """Returns (registry_or_None_if_304, etag)."""
        h = self._auth()
        if etag:
            h["If-None-Match"] = etag
        r = self._http.get(self._url("/v1/registry"), headers=h)
        if r.status_code == 304:
            return None, etag
        self._check(r)
        return r.json(), r.headers.get("ETag")

    def ping(self) -> dict[str, Any]:
        r = self._http.get(self._url("/v1/ping"))
        self._check(r)
        return r.json()

    def status(self, token: str | None = None) -> dict[str, Any]:
        """Admin endpoint per the contract; pass an admin token (or set
        ALD_ADMIN_TOKEN) or expect 401/403."""
        import os
        return self._json("GET", "/v1/status", token=token or os.environ.get("ALD_ADMIN_TOKEN"))

    def bwtest(self, max_seconds: float = 20.0) -> dict[str, float]:
        t0 = time.perf_counter()
        n = 0
        with self._http.stream("GET", self._url("/v1/bwtest"), headers=self._auth(),
                               timeout=max_seconds + 10) as r:
            if r.status_code >= 400:
                r.read()
                self._check(r)
            for chunk in r.iter_bytes(1 << 16):
                n += len(chunk)
                if time.perf_counter() - t0 > max_seconds:
                    break
        dt = max(time.perf_counter() - t0, 1e-6)
        return {"bytes": n, "seconds": dt, "mbit_s": n * 8 / dt / 1e6}
