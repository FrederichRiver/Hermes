from __future__ import annotations

import logging
import urllib.parse
from urllib.robotparser import RobotFileParser

logger = logging.getLogger(__name__)


class RobotsChecker:
    """Simple robots.txt guard with domain-level cache."""

    def __init__(self) -> None:
        self._cache: dict[str, RobotFileParser] = {}

    def _load(self, domain: str) -> RobotFileParser:
        parser = self._cache.get(domain)
        if parser is not None:
            return parser

        robots_url = urllib.parse.urljoin(f"https://{domain}/", "/robots.txt")
        parser = RobotFileParser()
        parser.set_url(robots_url)
        try:
            parser.read()
        except Exception:  # pragma: no cover - network failure should be conservative
            logger.warning("robots.txt unavailable or unreadable for %s; denying by default.", domain)
            parser = RobotFileParser()
            parser.parse([])
        self._cache[domain] = parser
        return parser

    def allowed(self, url: str) -> bool:
        if not url:
            return False
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc or parsed.hostname
        if not domain:
            return False
        parser = self._load(domain)
        return parser.can_fetch("*", url)


__all__ = ["RobotsChecker"]
