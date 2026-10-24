#!/opt/application/venv/bin/python3
"""Foreground event-engine service entry point for systemd."""

from __future__ import annotations

import importlib
import os
import signal
import threading
from types import FrameType
from typing import TYPE_CHECKING, Any

from basic_utils.logging import configure_logging, get_logger

if TYPE_CHECKING:
    from event_engine.event_bus import RedisEventBus
    from event_engine.event_engine import EventEngine


logger = get_logger(__name__)
_STARTUP_STREAM = "event"
_DEFAULT_REDIS_URL = "redis://localhost:6379/0"


def create_redis_event_bus(
    url: str | None = None,
    *,
    default_url: str = _DEFAULT_REDIS_URL,
    stream_name: str = "event",
) -> RedisEventBus:
    """Create an authenticated Redis event bus.

    Args:
        url: Optional Redis URL, which takes precedence over ``REDIS_URL``.
        default_url: Fallback URL used when ``REDIS_URL`` is not set.
        stream_name: Redis Stream assigned to the calling module.

    Returns:
        The configured ``RedisEventBus``. The Redis client is managed internally.

    Raises:
        KeyError: If ``REDIS_USERNAME`` or ``REDIS_PASSWORD`` is not set.
        RuntimeError: If the ``redis`` package is unavailable.
    """
    try:
        redis = importlib.import_module("redis")
    except ModuleNotFoundError as error:
        if error.name != "redis":
            raise
        raise RuntimeError(
            "redis package is required to create a Redis event bus."
        ) from error

    from event_engine.event_bus import RedisEventBus

    redis_url = (
        url
        if url is not None
        else os.environ.get("REDIS_URL", default_url)
    )
    redis_client = redis.Redis.from_url(
        redis_url,
        username=os.environ["REDIS_USERNAME"],
        password=os.environ["REDIS_PASSWORD"],
        decode_responses=False,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    return RedisEventBus(redis_client, stream_name=stream_name)


def main() -> int:
    """Run the event engine in the foreground until systemd requests shutdown."""
    configure_logging()

    shutdown_requested = threading.Event()
    event_bus: RedisEventBus | None = None
    event_engine: EventEngine | None = None
    previous_handlers: dict[signal.Signals, Any] = {}

    def request_shutdown(_signum: int, _frame: FrameType | None) -> None:
        shutdown_requested.set()

    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous_handlers[signum] = signal.signal(signum, request_shutdown)

        from event_engine.event_engine import EventEngine

        event_bus = create_redis_event_bus(stream_name=_STARTUP_STREAM)
        event_bus.ping()

        event_engine = EventEngine(bus=event_bus)
        event_engine.start()
        startup_event = event_engine.emit(
            "hermes.system.startup",
            {"pid": os.getpid()},
            source="event_service",
        )
        stream_entry_id = event_engine.xadd(_STARTUP_STREAM, startup_event.to_envelope())
        logger.info(
            f"Event engine started; startup event stored with ID {stream_entry_id}."
        )
        shutdown_requested.wait()
        logger.info("Event engine shutdown requested.")
        return 0
    except Exception:
        logger.exception("Event service stopped because of an unexpected error.")
        return 1
    finally:
        for signum, previous_handler in previous_handlers.items():
            signal.signal(signum, previous_handler)
        if event_engine is not None:
            event_engine.stop()
        if event_bus is not None:
            event_bus.close()


if __name__ == "__main__":
    raise SystemExit(main())
