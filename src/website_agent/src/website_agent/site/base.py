from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from website_agent.http_utils.client import RequestSpec


class BaseSite(ABC):
    """Abstract adapter for a single website data source."""

    name: str = "base"
    priority: int = 100

    def __init__(self, config: Any | None = None) -> None:
        self._config = config

    def supports(self, task_type: str) -> bool:
        raise NotImplementedError

    def rate_limit(self) -> float:
        return 5.0

    def auth(self) -> dict[str, Any]:
        return {}

    @abstractmethod
    def build_request(self, task: Any) -> RequestSpec:
        raise NotImplementedError

    @abstractmethod
    def parse(self, response: Any) -> list[dict[str, Any]]:
        raise NotImplementedError


__all__ = ["BaseSite"]
