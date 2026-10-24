from __future__ import annotations

import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter

from .user_agent import DEFAULT_USER_AGENTS


class HttpRetryableError(RuntimeError):
    """Retryable network or server-side failure."""


class HttpFatalError(RuntimeError):
    """Non-retryable HTTP error or robots-disallowed fetch."""


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
            self.tokens = min(
                self.capacity, self.tokens + elapsed * self.rate_per_second
            )
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
        base_headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        status_codes: list[int] | None = None,
        pool_connections: int = 10,
        pool_maxsize: int = 10,
        max_retries: int | None = None,
        backoff_factor: float | None = None,
    ) -> None:
        if max_retries is not None:
            max_retry = max_retries
        if backoff_factor is not None:
            backoff = backoff_factor
        self._session = requests.Session()
        if base_headers:
            self._session.headers.update(base_headers)
        self._has_default_user_agent = any(
            key.lower() == "user-agent" for key in (base_headers or {})
        )
        if cookies:
            self._session.cookies.update(cookies)
        self._timeout = float(timeout)
        self._max_retry = int(max_retry)
        self._backoff = float(backoff)
        self._retry_status_codes = frozenset(
            status_codes if status_codes is not None else (429, 500, 502, 503, 504)
        )
        self._token_bucket = TokenBucket(rate)
        self._user_agents = user_agents or list(DEFAULT_USER_AGENTS)
        self._ua_index = 0
        adapter = HTTPAdapter(
            max_retries=0,
            pool_connections=pool_connections,
            pool_maxsize=pool_maxsize,
        )
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

    @property
    def session(self) -> requests.Session:
        """Return the underlying requests session."""
        return self._session

    @session.setter
    def session(self, value: requests.Session) -> None:
        self._session = value

    @property
    def timeout(self) -> float:
        """Return the default request timeout."""
        return self._timeout

    @timeout.setter
    def timeout(self, value: float) -> None:
        self._timeout = float(value)

    def _acquire_token(self) -> None:
        self._token_bucket.acquire()

    def _pick_ua(self) -> str:
        ua = self._user_agents[self._ua_index % len(self._user_agents)]
        self._ua_index += 1
        return ua

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        **request_options: Any,
    ) -> requests.Response:
        """Send a GET request with rate limiting, retries, and encoding handling."""
        timeout = request_options.pop("timeout", None)
        if timeout is None:
            timeout = self._timeout
        headers = dict(request_options.pop("headers", None) or {})
        has_user_agent = (
            any(key.lower() == "user-agent" for key in headers)
            or self._has_default_user_agent
        )
        if not has_user_agent:
            headers["User-Agent"] = self._pick_ua()
        for attempt in range(self._max_retry + 1):
            try:
                self._acquire_token()
                response = self._session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=timeout,
                    **request_options,
                )
                self._normalize_response_encoding(response)
                if response.status_code in self._retry_status_codes:
                    raise HttpRetryableError(
                        f"Retryable status {response.status_code} for {url}"
                    )
                if response.status_code >= 400:
                    raise HttpFatalError(
                        f"Fatal status {response.status_code} for {url}"
                    )
                return response
            except HttpRetryableError as exc:
                if attempt == self._max_retry:
                    raise HttpFatalError(
                        f"Request failed after retries for {url}"
                    ) from exc
                time.sleep(self._backoff * (2**attempt))
            except requests.RequestException as exc:
                if attempt == self._max_retry:
                    raise HttpFatalError(f"Network error for {url}") from exc
                time.sleep(self._backoff * (2**attempt))
        raise HttpFatalError(f"Unknown request failure for {url}")

    @staticmethod
    def _normalize_response_encoding(response: requests.Response) -> None:
        """Prefer UTF-8 for text payloads while preserving valid legacy encodings."""
        if response.encoding and not any(
            encoding in response.encoding.lower()
            for encoding in ("utf-8", "utf8", "gbk", "gb2312", "gb18030")
        ):
            response.encoding = "utf-8"
            return
        if not response.encoding:
            response.encoding = "utf-8"
            return
        if response.content:
            try:
                response.content.decode("utf-8")
            except UnicodeDecodeError:
                return
            response.encoding = "utf-8"

    def post(
        self,
        url: str,
        data: Any = None,
        json: Any = None,
        **request_options: Any,
    ) -> requests.Response:
        """POST request placeholder; implementation will be added later."""
        raise NotImplementedError("POST requests are not implemented yet.")

    def put(
        self,
        url: str,
        data: Any = None,
        **request_options: Any,
    ) -> requests.Response:
        """PUT request placeholder; implementation will be added later."""
        raise NotImplementedError("PUT requests are not implemented yet.")

    def patch(
        self,
        url: str,
        data: Any = None,
        **request_options: Any,
    ) -> requests.Response:
        """PATCH request placeholder; implementation will be added later."""
        raise NotImplementedError("PATCH requests are not implemented yet.")

    def delete(
        self,
        url: str,
        **request_options: Any,
    ) -> requests.Response:
        """DELETE request placeholder; implementation will be added later."""
        raise NotImplementedError("DELETE requests are not implemented yet.")

    def head(
        self,
        url: str,
        **request_options: Any,
    ) -> requests.Response:
        """HEAD request placeholder; implementation will be added later."""
        raise NotImplementedError("HEAD requests are not implemented yet.")

    def options(
        self,
        url: str,
        **request_options: Any,
    ) -> requests.Response:
        """OPTIONS request placeholder; implementation will be added later."""
        raise NotImplementedError("OPTIONS requests are not implemented yet.")

    def get_text(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        **request_options: Any,
    ) -> str:
        """Return the decoded response body from a GET request."""
        return self.get(url, params=params, **request_options).text

    def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        **request_options: Any,
    ) -> Any:
        """Return the parsed JSON body from a GET request."""
        return self.get(url, params=params, **request_options).json()

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


__all__ = ["HttpClient", "HttpFatalError", "HttpRetryableError", "TokenBucket"]
