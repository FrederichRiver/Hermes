#!/opt/application/venv/bin/python3
"""Foreground TimeAgent service entry point for systemd."""

from __future__ import annotations

import signal
import threading
from types import FrameType
from typing import Any

from basic_utils.logging import configure_logging, get_logger
from event_service import create_redis_event_bus


logger = get_logger(__name__)


def main() -> int:
    """Run TimeAgent with its one-minute and five-minute timers."""
    configure_logging()

    shutdown_requested = threading.Event()
    previous_handlers: dict[signal.Signals, Any] = {}
    event_bus: Any | None = None
    time_agent: Any | None = None
    exit_code = 1

    def request_shutdown(_signum: int, _frame: FrameType | None) -> None:
        shutdown_requested.set()

    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous_handlers[signum] = signal.signal(signum, request_shutdown)

        event_bus = create_redis_event_bus(stream_name="time")
        event_bus.ping()
        from time_agent import TimeAgent

        time_agent = TimeAgent(event_bus=event_bus)
        logger.info(f"TimeAgent started with status: {time_agent.status()}")

        time_agent.set_timer_interval(0, 60)
        time_agent.start_timer(0)
        logger.info("Started TimeAgent timer 1 with a 60-second interval.")

        time_agent.set_timer_interval(1, 300)
        time_agent.start_timer(1)
        logger.info("Started TimeAgent timer 2 with a 300-second interval.")

        shutdown_requested.wait()
        logger.info("TimeAgent shutdown requested.")
        exit_code = 0
    except Exception:
        logger.exception("TimeAgent service stopped because of an unexpected error.")
    finally:
        if time_agent is not None:
            try:
                time_agent.stop_timers()
            except Exception:
                logger.exception("Failed to stop TimeAgent timers.")
                exit_code = 1
        if event_bus is not None:
            try:
                event_bus.close()
            except Exception:
                logger.exception("Failed to close the Redis event bus.")
                exit_code = 1
        for signum, previous_handler in previous_handlers.items():
            signal.signal(signum, previous_handler)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
