from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

from event_engine.event import Event

from website_agent.http_utils.client import HttpClient, HttpFatalError
from website_agent.http_utils.robots import RobotsChecker

logger = logging.getLogger(__name__)


class BaseSite(ABC):
    """Site adapter that owns one or more HTTP clients."""

    name: str = "base"
    priority: int = 100

    def __init__(
        self,
        config: Any | None = None,
        http_clients: dict[str, HttpClient] | None = None,
        **client_options: Any,
    ) -> None:
        if http_clients is not None and client_options:
            raise ValueError(
                "Provide http_clients or HttpClient options, not both."
            )
        self._config = config
        if http_clients is None:
            client_options.setdefault("rate", self.rate_limit())
            self._http_clients = {"default": HttpClient(**client_options)}
        else:
            if not http_clients:
                raise ValueError("At least one HTTP client is required.")
            if any(
                not isinstance(client, HttpClient)
                for client in http_clients.values()
            ):
                raise TypeError("Every site HTTP client must be an HttpClient.")
            self._http_clients = dict(http_clients)

    @abstractmethod
    def supports(self, task_type: str) -> bool:
        raise NotImplementedError

    def rate_limit(self) -> float:
        return 5.0

    @abstractmethod
    def request_url(self, task: Any) -> str:
        raise NotImplementedError

    @abstractmethod
    def fetch(self, task: Any) -> list[dict[str, Any]]:
        raise NotImplementedError

    def auth(self) -> dict[str, Any]:
        return {}

    def http_client(self, name: str = "default") -> HttpClient:
        """Return a named HTTP client owned by this site."""
        try:
            return self._http_clients[name]
        except KeyError as exc:
            raise ValueError(f"No HTTP client named {name!r} is registered.") from exc

    @property
    def session(self) -> Any:
        """Expose the default client's session for legacy site integrations."""
        return self.http_client().session

    @session.setter
    def session(self, value: Any) -> None:
        self.http_client().session = value

    @property
    def timeout(self) -> float:
        """Expose the default client's request timeout."""
        return self.http_client().timeout

    @timeout.setter
    def timeout(self, value: float) -> None:
        self.http_client().timeout = value

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        client_name: str = "default",
        **request_options: Any,
    ) -> Any:
        """Send a GET request through one of this site's HTTP clients."""
        return self.http_client(client_name).get(
            url,
            params=params,
            **request_options,
        )

    def post(
        self,
        url: str,
        data: Any = None,
        json: Any = None,
        *,
        client_name: str = "default",
        **request_options: Any,
    ) -> Any:
        return self.http_client(client_name).post(
            url,
            data=data,
            json=json,
            **request_options,
        )

    def get_text(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        client_name: str = "default",
        **request_options: Any,
    ) -> str:
        return self.http_client(client_name).get_text(
            url,
            params=params,
            **request_options,
        )

    def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        client_name: str = "default",
        **request_options: Any,
    ) -> Any:
        return self.http_client(client_name).get_json(
            url,
            params=params,
            **request_options,
        )

    def close(self) -> None:
        """Close every distinct HTTP client held by this site."""
        closed_clients: set[int] = set()
        for client in self._http_clients.values():
            if id(client) not in closed_clients:
                client.close()
                closed_clients.add(id(client))

    def __enter__(self) -> BaseSite:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any | None,
    ) -> None:
        self.close()


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
    """Route fetch tasks to registered site adapters and publish Hermes events."""

    def __init__(
        self,
        config: Any | None = None,
        publisher: Callable[[Event], None] | None = None,
    ) -> None:
        self._config = config
        self._publisher = publisher or (lambda event: None)
        self._robots = RobotsChecker()
        self.sites: list[BaseSite] = []
        self._breaker: dict[str, CircuitState] = {}
        self._breaker_threshold = 5

    def register(self, site: BaseSite) -> None:
        for index, registered_site in enumerate(self.sites):
            if registered_site.name == site.name:
                if registered_site is not site:
                    registered_site.close()
                self.sites[index] = site
                self._breaker.setdefault(site.name, CircuitState())
                return
        self.sites.append(site)
        self._breaker.setdefault(site.name, CircuitState())

    def _route(self, task: FetchTask) -> list[BaseSite]:
        return sorted(
            (site for site in self.sites if site.supports(task.task_type)),
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
        event_type = (
            "market.tick.received"
            if task.task_type.startswith("daily")
            else "data.task.finished"
        )
        payload = {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "rows_count": len(rows),
            "source": site.name,
            "rows": rows,
        }
        event = Event.create(
            event_type,
            "website_agent",
            payload,
            trace_id=task.trace_id,
        )
        self._publisher(event)

    def _emit_error(self, task: FetchTask, error: Exception, site: BaseSite | None) -> None:
        payload = {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "error": str(error),
            "source": site.name if site else "website_agent",
        }
        event = Event.create(
            "data.error.raised",
            "website_agent",
            payload,
            trace_id=task.trace_id,
        )
        self._publisher(event)

    def on_fetch_requested(self, event: Event) -> None:
        task_payload = (
            event.event_data.get("task")
            if isinstance(event.event_data, dict)
            else None
        )
        if not isinstance(task_payload, dict):
            raise ValueError("data.fetch.requested event requires a task payload")

        task = FetchTask(
            task_id=str(task_payload.get("task_id") or event.event_id),
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
                url = site.request_url(task)
                if not self._robots.allowed(url):
                    raise HttpFatalError(f"Robots disallow access for {url}")
                rows = site.fetch(task)
                if rows:
                    self._record_success(site)
                    self._emit_result(task, rows, site)
                    return
                raise ValueError("No rows parsed from site response")
            except Exception as exc:  # pragma: no cover - failover path intentionally broad
                last_error = exc
                final_site = site
                self._record_failure(site)
                logger.warning(
                    "Website fetch failed for %s via %s: %s",
                    task.task_id,
                    site.name,
                    exc,
                )
                continue

        if last_error is not None:
            self._emit_error(task, last_error, final_site)
            logger.error("Website fetch failed for %s: %s", task.task_id, last_error)
            return

        self._emit_error(task, RuntimeError("No compatible site available"), None)

    def close(self) -> None:
        """Close all registered sites and their owned HTTP clients."""
        for site in self.sites:
            site.close()

    def site_status(self) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "breaker": state.failures >= self._breaker_threshold and state.open_until > time.time(),
                "failures": state.failures,
                "open_until": state.open_until,
            }
            for name, state in self._breaker.items()
        }


__all__ = ["BaseSite", "FetchTask", "CircuitState", "WebsiteAgent"]
