#!/opt/application/venv/bin/python3
"""Foreground TimeAgent service entry point for systemd."""

from __future__ import annotations

import os
import signal
import threading
from types import FrameType
from typing import Any

from utils.logging import configure_logging, get_logger


logger = get_logger(__name__)
_DEFAULT_REDIS_URL = "redis://localhost:6379/0"
_REFRESH_INTERVAL_SECONDS = 5 * 60
_REFRESH_EVENT_TYPE = "data.fetch.requested"
_EVENT_STREAM = "hermes:events"


def main() -> int:
    """Publish an SSE refresh request every five minutes until shutdown."""
    configure_logging()

    shutdown_requested = threading.Event()
    previous_handlers: dict[signal.Signals, Any] = {}
    redis_client: Any | None = None
    exit_code = 1

    def request_shutdown(_signum: int, _frame: FrameType | None) -> None:
        shutdown_requested.set()

    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous_handlers[signum] = signal.signal(signum, request_shutdown)

        from time_agent import TimeAgent
        import redis
        from event_engine.event import Event
        from event_engine.event_bus import RedisEventBus

        time_agent = TimeAgent()
        logger.info(f"TimeAgent started with status: {time_agent.status()}")
        redis_url = os.environ.get("REDIS_URL", _DEFAULT_REDIS_URL)
        redis_client = redis.Redis.from_url(
            redis_url,
            username=os.environ["REDIS_USERNAME"],
            password=os.environ["REDIS_PASSWORD"],
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        redis_client.ping()
        event_bus = RedisEventBus(redis_client)

        while not shutdown_requested.wait(_REFRESH_INTERVAL_SECONDS):
            event = Event.create(
                _REFRESH_EVENT_TYPE,
                source="time_agent",
                event_data={
                    "task": {
                        "task_type": "symbol_list",
                        "params": {},
                    }
                },
            )
            event_bus.publish(event)
            stream_entry_id = redis_client.xadd(
                _EVENT_STREAM,
                event.to_envelope(),
            )
            logger.info(
                f"Published SSE refresh request to {_EVENT_STREAM} with ID {stream_entry_id}."
            )

        logger.info("TimeAgent shutdown requested.")
        exit_code = 0
    except Exception:
        logger.exception("TimeAgent service stopped because of an unexpected error.")
    finally:
        if redis_client is not None:
            try:
                redis_client.close()
            except Exception:
                logger.exception("Failed to close the Redis client.")
                exit_code = 1
        for signum, previous_handler in previous_handlers.items():
            signal.signal(signum, previous_handler)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
