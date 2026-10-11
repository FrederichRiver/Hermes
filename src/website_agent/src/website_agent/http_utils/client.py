from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class HttpRetryableError(RuntimeError):
    """Retryable network or server-side failure."""


class HttpFatalError(RuntimeError):
    """Non-retryable HTTP error or robots-disallowed fetch."""


@dataclass(slots=True)
class RequestSpec:
    method: str
    url: str
    params: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)


class TokenBucket:
    """Simple token bucket rate limiter."""

    def __init__(self, rate_per_second: float = 5.0) -> None:
        self.rate_per_second = max(float(rate_per_second), 0.001)
        self.capacity = self.rate_per_second
        self.tokens = float(self.capacity)
        self.updated_at = time.monotonic()

    def acquire(self) -> None:
        while True:
            now = time.monotonic()
            elapsed = max(now - self.updated_at, 0.0)
            self.updated_at = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_per_second)
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return
            time.sleep((1.0 - self.tokens) / self.rate_per_second)


class HttpClient:
    """Shared HTTP client with retry, rate limiting and UA rotation."""

    def __init__(
        self,
        timeout: float = 10.0,
        max_retry: int = 3,
        backoff: float = 1.0,
        rate: float = 5.0,
        user_agents: list[str] | None = None,
    ) -> None:
        self._session = requests.Session()
        self._timeout = float(timeout)
        self._max_retry = int(max_retry)
        self._backoff = float(backoff)
        self._token_bucket = TokenBucket(rate)
        self._user_agents = user_agents or [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        ]
        self._ua_index = 0
        retry = Retry(
            total=self._max_retry,
            read=self._max_retry,
            connect=self._max_retry,
            backoff_factor=self._backoff,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "POST", "HEAD", "OPTIONS", "PUT", "DELETE"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

    def _acquire_token(self) -> None:
        self._token_bucket.acquire()

    def _pick_ua(self) -> str:
        ua = self._user_agents[self._ua_index % len(self._user_agents)]
        self._ua_index += 1
        return ua

    def _do_request(self, req: RequestSpec) -> requests.Response:
        headers = dict(req.headers)
        headers.setdefault("User-Agent", self._pick_ua())
        response = self._session.request(
            req.method,
            req.url,
            params=req.params,
            headers=headers,
            timeout=self._timeout,
        )
        if response.status_code in (429, 500, 502, 503, 504):
            raise HttpRetryableError(f"Retryable status {response.status_code} for {req.url}")
        if 400 <= response.status_code < 500:
            raise HttpFatalError(f"Fatal status {response.status_code} for {req.url}")
        return response

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: Any = None,
        headers: dict[str, str] | None = None,
    ) -> requests.Response:
        req = RequestSpec(method=method.upper(), url=url, params=params or {}, headers=headers or {})
        for attempt in range(self._max_retry + 1):
            try:
                self._acquire_token()
                if data is not None:
                    request_headers = {**req.headers, "User-Agent": self._pick_ua()}
                    return self._session.request(
                        req.method,
                        req.url,
                        params=req.params,
                        data=data,
                        headers=request_headers,
                        timeout=self._timeout,
                    )
                return self._do_request(req)
            except HttpRetryableError as exc:
                if attempt == self._max_retry:
                    raise HttpFatalError(f"Request failed after retries for {url}") from exc
                time.sleep(self._backoff * (2 ** attempt))
            except requests.RequestException as exc:
                if attempt == self._max_retry:
                    raise HttpFatalError(f"Network error for {url}") from exc
                time.sleep(self._backoff * (2 ** attempt))
        raise HttpFatalError(f"Unknown request failure for {url}")

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


__all__ = ["HttpClient", "HttpFatalError", "HttpRetryableError", "RequestSpec", "TokenBucket"]
