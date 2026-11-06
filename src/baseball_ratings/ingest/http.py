"""Polite, cached HTTP client shared by all ingest modules.

MLBAM terms allow "individual, non-commercial, non-bulk" use, so every response is cached on
disk (outside the repo) and live requests are rate limited. Both MLB endpoints can return HTTP
200 for failures (empty CSV, an HTML page, ``{"message": "Internal error occurred"}``), so
responses are validated here rather than trusted on status code.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx

USER_AGENT = "baseball-ratings/0.1 (personal research; +https://github.com/harlanljones/baseball-ratings)"
DEFAULT_CACHE = Path(os.environ.get("BR_CACHE_DIR", Path.home() / ".cache" / "baseball-ratings"))


class DataSourceError(RuntimeError):
    """Raised when an endpoint answers with something that is not the data we asked for."""


def strip_bom(text: str) -> str:
    return text[1:] if text.startswith("﻿") else text


def check_csv_text(text: str, url: str) -> str:
    text = strip_bom(text)
    head = text.lstrip()[:200].lower()
    if head.startswith("<") or "<html" in head:
        raise DataSourceError(f"expected CSV but got HTML from {url}")
    if not text.strip():
        raise DataSourceError(f"empty CSV body from {url}")
    return text


def check_json(payload: Any, url: str) -> Any:
    if isinstance(payload, dict) and set(payload) <= {"message", "copyright"} and "message" in payload:
        raise DataSourceError(f"API error from {url}: {payload['message']}")
    return payload


class HttpClient:
    def __init__(
        self,
        cache_dir: Path | None = None,
        min_interval_s: float = 1.0,
        max_retries: int = 4,
        offline: bool = False,
        client: httpx.Client | None = None,
    ) -> None:
        self.cache_dir = Path(cache_dir or DEFAULT_CACHE) / "http"
        self.min_interval_s = min_interval_s
        self.max_retries = max_retries
        self.offline = offline
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(120.0, connect=15.0),
            headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"},
            follow_redirects=True,
        )
        self._last_request = 0.0

    # -- cache -----------------------------------------------------------------------------
    def _key(self, url: str, params: Mapping[str, Any] | None) -> Path:
        items = dict(params or {})
        canon = url + "?" + "&".join(f"{k}={items[k]}" for k in sorted(items))
        digest = hashlib.sha256(canon.encode()).hexdigest()
        return self.cache_dir / digest[:2] / digest

    def _get(self, url: str, params: Mapping[str, Any] | None, use_cache: bool) -> str:
        path = self._key(url, params)
        if use_cache and path.exists():
            return path.read_text(encoding="utf-8")
        if self.offline:
            raise DataSourceError(f"offline and not cached: {url} {dict(params or {})}")
        text = self._fetch(url, params)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
        return text

    def _fetch(self, url: str, params: Mapping[str, Any] | None) -> str:
        delay = 2.0
        for attempt in range(self.max_retries + 1):
            wait = self.min_interval_s - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()
            try:
                resp = self._client.get(url, params=dict(params or {}))
            except httpx.TransportError:
                if attempt == self.max_retries:
                    raise
            else:
                if resp.status_code < 400:
                    return resp.content.decode("utf-8-sig", errors="replace")
                if resp.status_code not in (429, 500, 502, 503, 504) or attempt == self.max_retries:
                    raise DataSourceError(f"HTTP {resp.status_code} from {resp.url}")
            time.sleep(delay)
            delay *= 2
        raise DataSourceError(f"unreachable: {url}")  # pragma: no cover

    # -- public ----------------------------------------------------------------------------
    def get_json(self, url: str, params: Mapping[str, Any] | None = None, use_cache: bool = True) -> Any:
        text = self._get(url, params, use_cache)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            self._key(url, params).unlink(missing_ok=True)
            raise DataSourceError(f"invalid JSON from {url}") from exc
        try:
            return check_json(payload, url)
        except DataSourceError:
            self._key(url, params).unlink(missing_ok=True)
            raise

    def get_csv_text(self, url: str, params: Mapping[str, Any] | None = None, use_cache: bool = True) -> str:
        text = self._get(url, params, use_cache)
        try:
            return check_csv_text(text, url)
        except DataSourceError:
            self._key(url, params).unlink(missing_ok=True)
            raise
