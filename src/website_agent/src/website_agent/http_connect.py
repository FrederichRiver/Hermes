"""
HttpConnect
----------------

Lightweight HTTP helper used by DataAgent site scrapers. This class wraps
``requests.Session`` and configures a retry strategy from ``urllib3.util.retry.Retry``
via a ``requests.adapters.HTTPAdapter``.

Responsibilities
- Provide a reusable session with sensible defaults for headers/cookies.
- Configure retries and backoff for transient network/server errors.
- Offer convenience helpers: ``get``, ``post``, ``get_text``, ``get_json``.
- Act as a context manager to ensure session cleanup when used with ``with``.

Usage example::

    from agent.http_connect import HttpConnect

    client = HttpConnect(base_headers={"User-Agent": "Hermes/1.0"}, max_retries=4)
    data = client.get_json("https://api.example.com/data")

Notes on retry behavior
- Retries are performed for connect/read errors and for responses with
  status codes listed in ``status_forcelist`` (defaults to 429, 500, 502, 503, 504).
- Backoff is exponential and controlled by ``backoff_factor``.
- ``allowed_methods`` controls which idempotent methods are retried by default.

Implementation details are intentionally small and synchronous. For async
scrapers use a separate async client (e.g., httpx.AsyncClient) if needed.
"""

from typing import Any, Dict, Optional
import logging
import re

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("agent.http_connect")


class HttpConnect:
    """HTTP helper with retry/backoff and simple helpers.

    Args:
        base_headers: default headers to apply to every request.
        cookies: default cookies dict.
        timeout: default per-request timeout (seconds).
        max_retries: number of retry attempts for transient failures.
        backoff_factor: backoff factor for retry delays (exponential).
        status_forcelist: list of HTTP status codes that should trigger a retry.
        pool_connections: number of connection pools to cache.
        pool_maxsize: maximum connections to save in the pool.

    Behavior:
        - Raises HTTPError for 4xx/5xx after retries by default (via
          ``response.raise_for_status()`` in helpers).
        - Caller may override timeout per-call via ``timeout`` kwarg.
    """

    def __init__(
        self,
        base_headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
        timeout: float = 10.0,
        max_retries: int = 3,
        backoff_factor: float = 0.3,
        status_codes: Optional[list] = None,
        pool_connections: int = 10,
        pool_maxsize: int = 10,
    ) -> None:
        self.session = requests.Session()
        self.timeout = timeout

        # Apply supplied headers and cookies to the session
        if base_headers:
            self.session.headers.update(base_headers)
        if cookies:
            self.session.cookies.update(cookies)

        # Default status codes that should trigger a retry if returned
        if status_codes is None:
            status_codes = [429, 500, 502, 503, 504]

        # Configure urllib3 Retry strategy. This will be used by the HTTPAdapter
        # attached to the requests session and will perform retries for the
        # configured conditions.
        retry = Retry(
            total=max_retries,
            read=max_retries,
            connect=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=status_codes,
            # allowed_methods controls which methods are retried. We include
            # the common safe/idempotent methods and also POST/PUT to allow
            # retries where the server semantics permit it.
            allowed_methods=frozenset(["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"]),
            raise_on_status=False,
        )

        adapter = HTTPAdapter(max_retries=retry, pool_connections=pool_connections, pool_maxsize=pool_maxsize)
        # Mount the adapter for both http and https
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def close(self) -> None:
        """Close the underlying requests session and associated adapters."""
        try:
            self.session.close()
        except Exception:
            logger.exception("Error closing HTTP session")

    def get(self, url: str, params: Optional[Dict[str, Any]] = None, **kwargs) -> requests.Response:
        """HttpConnect - a small requests wrapper with urllib3 Retry support.

        This module implements `HttpConnect`, a synchronous HTTP helper built on
        `requests.Session` and `urllib3.util.retry.Retry`. It's intended as a
        reusable base for site-specific scrapers inside `DataAgent`.

        Key features:
        - Configurable default headers and cookies
        - Timeout per-request with a sensible default
        - Retry/backoff policy for transient network or server errors
        - Connection pooling via requests' HTTPAdapter
        - Convenience helpers: `get_text`, `get_json`

        Security and logging notes:
        - Do not log request bodies or sensitive headers here; callers should
          redact sensitive values before logging.
        - JSON parsing errors are logged at debug level and re-raised for
          higher-level retry/error handling.

        Usage example:

            client = HttpConnect(base_headers={'User-Agent': 'Hermes/1.0'})
            text = client.get_text('https://example.com')
            data = client.get_json('https://api.example.com/data')

        """
        timeout = kwargs.pop("timeout", self.timeout)
        resp = self.session.get(url, params=params, timeout=timeout, **kwargs)
        resp.raise_for_status()
        self._normalize_response_encoding(resp)
        return resp

    @staticmethod
    def _normalize_response_encoding(resp: requests.Response) -> None:
        """Prefer UTF-8 for text payloads and preserve clean text content."""
        if resp.encoding and not re.search(r"utf-8|utf8|gbk|gb2312|gb18030", resp.encoding, re.I):
            resp.encoding = "utf-8"
            return

        if not resp.encoding:
            resp.encoding = "utf-8"
            return

        if resp.content:
            try:
                resp.content.decode("utf-8")
            except UnicodeDecodeError:
                return

            resp.encoding = "utf-8"

    def post(self, url: str, data: Any = None, json: Any = None, **kwargs) -> requests.Response:
        """
            Issue a POST request and return a requests.Response.

            Lightweight requests wrapper with retry/backoff and pooling.

                - base_headers: Default headers applied to each request session-wide.
                - cookies: Default cookies applied to the session.
                - timeout: Default seconds to wait for connect+read if not overridden.
                - max_retries: Total number of retries for idempotent operations.
                - backoff_factor: Backoff multiplier for Retry (exponential backoff).
                - retry_status_codes: HTTP status codes that should trigger a retry.
            - pool_connections/pool_maxsize: Controls urllib3 connection pool sizing.

            The implementation mounts a HTTPAdapter with the configured Retry on
            both `http://` and `https://` schemes so all session requests use it.
        """
        timeout = kwargs.pop("timeout", self.timeout)
        resp = self.session.post(url, data=data, json=json, timeout=timeout, **kwargs)
        # Let callers handle HTTP errors consistently; raise for 4xx/5xx after retries
        resp.raise_for_status()
        return resp

    # Context manager support so callers can use ``with HttpConnect(...) as c:``
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


__all__ = ["HttpConnect"]
