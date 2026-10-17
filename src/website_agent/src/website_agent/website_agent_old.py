from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from event_engine.event import Event

from website_agent.http_utils.client import HttpClient, HttpFatalError
from website_agent.http_utils.robots import RobotsChecker
from website_agent.website.agent import BaseSite

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class FetchTask:
    task_id: str
    task_type: str
    params: dict[str, Any] = field(default_factory=dict)
    trace_id: str | None = None


@dataclass(slots=True)
class CircuitState:
    failures: int = 0
    open_until: float = 0.0


class WebsiteAgent:
    """Routes fetch tasks across site adapters and emits Hermes events."""

    def __init__(
        self,
        config: Any | None = None,
        publisher: Callable[[Event], None] | None = None,
        client: HttpClient | None = None,
    ) -> None:
        self._config = config
        self._publisher = publisher or (lambda event: None)
        self._client = client or HttpClient(timeout=10.0, max_retry=3, backoff=1.0, rate=5.0)
        self._robots = RobotsChecker()
        self._sites: dict[str, BaseSite] = {}
        self._breaker: dict[str, CircuitState] = {}
        self._breaker_threshold = 5

    def register(self, site: BaseSite) -> None:
        self._sites[site.name] = site
        self._breaker.setdefault(site.name, CircuitState())

    def _route(self, task: FetchTask) -> list[BaseSite]:
        return sorted(
            (site for site in self._sites.values() if site.supports(task.task_type)),
            key=lambda site: site.priority,
        )

    def _check_breaker(self, site: BaseSite) -> bool:
        state = self._breaker.get(site.name, CircuitState())
        if state.failures >= self._breaker_threshold:
            if state.open_until > 0 and state.open_until > time.time():
                return False
            state.failures = 0
            state.open_until = 0.0
        return True

    def _record_failure(self, site: BaseSite) -> None:
        state = self._breaker.setdefault(site.name, CircuitState())
        state.failures += 1
        if state.failures >= self._breaker_threshold:
            state.open_until = time.time() + 300

    def _record_success(self, site: BaseSite) -> None:
        state = self._breaker.setdefault(site.name, CircuitState())
        state.failures = 0
        state.open_until = 0.0

    def _emit_result(self, task: FetchTask, rows: list[dict[str, Any]], site: BaseSite) -> None:
        event_type = "market.tick.received" if task.task_type.startswith("daily") else "data.task.finished"
        payload = {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "rows_count": len(rows),
            "source": site.name,
            "rows": rows,
        }
        event = Event.create(event_type, "website_agent", payload, trace_id=task.trace_id)
        self._publisher(event)

    def _emit_error(self, task: FetchTask, error: Exception, site: BaseSite | None) -> None:
        payload = {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "error": str(error),
            "source": site.name if site else "website_agent",
        }
        event = Event.create("data.error.raised", "website_agent", payload, trace_id=task.trace_id)
        self._publisher(event)

    def on_fetch_requested(self, event: Event) -> None:
        task_payload = event.data.get("task") if isinstance(event.data, dict) else None
        if not isinstance(task_payload, dict):
            raise ValueError("data.fetch.requested event requires a task payload")

        task = FetchTask(
            task_id=str(task_payload.get("task_id") or event.id),
            task_type=str(task_payload.get("task_type") or "unknown"),
            params=dict(task_payload.get("params") or {}),
            trace_id=event.trace_id,
        )

        last_error: Exception | None = None
        final_site: BaseSite | None = None
        for site in self._route(task):
            if not self._check_breaker(site):
                continue
            try:
                request = site.build_request(task)
                if not self._robots.allowed(request.url):
                    raise HttpFatalError(f"Robots disallow access for {request.url}")
                response = self._client.request(request.method, request.url, params=request.params, headers=request.headers)
                response.raise_for_status()
                rows = site.parse(response)
                if rows:
                    self._record_success(site)
                    self._emit_result(task, rows, site)
                    return
                raise ValueError("No rows parsed from site response")
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                final_site = site
                self._record_failure(site)
                logger.warning("Website fetch failed for %s via %s: %s", task.task_id, site.name, exc)
                continue

        if last_error is not None:
            self._emit_error(task, last_error, final_site)
            logger.error("Website fetch failed for %s: %s", task.task_id, last_error)
            return

        self._emit_error(task, RuntimeError("No compatible site available"), None)

    def site_status(self) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "breaker": state.failures >= self._breaker_threshold and state.open_until > time.time(),
                "failures": state.failures,
                "open_until": state.open_until,
            }
            for name, state in self._breaker.items()
        }


__all__ = ["WebsiteAgent", "FetchTask", "CircuitState"]
