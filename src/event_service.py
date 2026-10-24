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
    from event_engine.event_engine import EventEngine


logger = get_logger(__name__)
_DEFAULT_REDIS_URL = "redis://localhost:6379/0"
_STARTUP_STREAM = "hermes:events"


def main() -> int:
    """Run the event engine in the foreground until systemd requests shutdown."""
    configure_logging()

    shutdown_requested = threading.Event()
    redis_client: Any | None = None
    event_engine: EventEngine | None = None
    previous_handlers: dict[signal.Signals, Any] = {}

    def request_shutdown(_signum: int, _frame: FrameType | None) -> None:
        shutdown_requested.set()

    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous_handlers[signum] = signal.signal(signum, request_shutdown)

        redis = importlib.import_module("redis")
        from event_engine.event_bus import RedisEventBus
        from event_engine.event_engine import EventEngine

        redis_url = os.environ.get("REDIS_URL", _DEFAULT_REDIS_URL)
        redis_client = redis.Redis.from_url(
            redis_url,
            username=os.environ["REDIS_USERNAME"],
            password=os.environ["REDIS_PASSWORD"],
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        redis_client.ping()

        event_engine = EventEngine(bus=RedisEventBus(redis_client))
        event_engine.start()
        startup_event = event_engine.emit(
            "hermes.system.startup",
            {"pid": os.getpid()},
            source="event_service",
        )
        stream_entry_id = event_engine.xadd(
            _STARTUP_STREAM,
            startup_event.to_envelope(),
        )
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
        if redis_client is not None:
            redis_client.close()


if __name__ == "__main__":
    raise SystemExit(main())
