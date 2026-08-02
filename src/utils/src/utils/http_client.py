import time
import logging
from typing import Optional, Dict, Any

import time
import logging
import json
from typing import Optional, Dict, Any

try:
    import httpx
    _HAS_HTTPX = True
except Exception:
    import urllib.request as _urllib_request
    import urllib.error as _urllib_error
    import urllib.parse as _urllib_parse
    _HAS_HTTPX = False

logger = logging.getLogger("src.http_client")


class SimpleHttpClient:
    """Small synchronous HTTP client with retries, backoff and throttling.

    Uses `httpx` if available, otherwise falls back to the stdlib `urllib`.
    Provides `get` and `get_json` helpers.
    """

    def __init__(self, timeout: float = 10.0, retries: int = 3, backoff: float = 1.0,
                 headers: Optional[Dict[str, str]] = None, min_interval: float = 0.0):
        self.timeout = timeout
        self.retries = max(1, int(retries))
        self.backoff = float(backoff)
        self.headers = headers or {"User-Agent": "HermesDataAgent/1.0"}
        self.min_interval = float(min_interval)
        self._last_request = 0.0

    def _throttle(self):
        if self.min_interval <= 0:
            return
        now = time.time()
        elapsed = now - self._last_request
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    def get(self, url: str, params: Optional[Dict[str, Any]] = None,
            headers: Optional[Dict[str, str]] = None, timeout: Optional[float] = None) -> str:
        merged_headers = dict(self.headers)
        if headers:
            merged_headers.update(headers)
        timeout = timeout or self.timeout

        last_exc = None
        for attempt in range(self.retries):
            self._throttle()
            try:
                if _HAS_HTTPX:
                    with httpx.Client(timeout=timeout) as client:
                        resp = client.get(url, params=params, headers=merged_headers)
                        resp.raise_for_status()
                        text = resp.text
                else:
                    req_url = url
                    if params:
                        query = _urllib_parse.urlencode(params)
                        connector = '&' if '?' in url else '?'
                        req_url = f"{url}{connector}{query}"
                    req = _urllib_request.Request(req_url, headers=merged_headers)
                    with _urllib_request.urlopen(req, timeout=timeout) as resp:
                        raw = resp.read()
                        text = raw.decode('utf-8', errors='replace')
                self._last_request = time.time()
                return text
            except Exception as e:
                last_exc = e
                wait = self.backoff * (2 ** attempt)
                logger.warning("HTTP GET failed (attempt %d/%d) %s: %s; retrying in %.1fs",
                               attempt + 1, self.retries, url, e, wait)
                time.sleep(wait)
        logger.error("HTTP GET giving up after %d attempts: %s", self.retries, url)
        raise last_exc

    def get_json(self, url: str, params: Optional[Dict[str, Any]] = None,
                 headers: Optional[Dict[str, str]] = None, timeout: Optional[float] = None) -> Any:
        """Fetch URL and attempt to parse JSON from the response.

        Returns parsed JSON (dict/list) or raises an exception on failure.
        """
        text = self.get(url, params=params, headers=headers, timeout=timeout)
        try:
            return json.loads(text)
        except Exception:
            # try httpx json decode if available
            if _HAS_HTTPX:
                try:
                    with httpx.Client(timeout=timeout or self.timeout) as client:
                        resp = client.get(url, params=params, headers=headers)
                        resp.raise_for_status()
                        return resp.json()
                except Exception:
                    pass
            logger.debug("Response not JSON, raising JSON parse error")
            raise
