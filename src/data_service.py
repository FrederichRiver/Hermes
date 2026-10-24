#!/opt/application/venv/bin/python3
"""Foreground DataAgent service entry point for systemd."""

from __future__ import annotations

import os
import signal
import threading
from types import FrameType
from typing import Any

from basic_utils.logging import configure_logging, get_logger
from event_service import create_redis_event_bus


logger = get_logger(__name__)
_STOCK_DATABASE = "stock_data"


def main() -> int:
    """Run DataAgent in the foreground until systemd requests shutdown."""
    configure_logging()

    shutdown_requested = threading.Event()
    redis_event_bus: Any | None = None
    mysql_db: Any | None = None
    data_agent: Any | None = None
    previous_handlers: dict[signal.Signals, Any] = {}
    exit_code = 1

    def request_shutdown(_signum: int, _frame: FrameType | None) -> None:
        shutdown_requested.set()

    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous_handlers[signum] = signal.signal(signum, request_shutdown)

        from data_agent.data_agent import DataAgent
        from data_agent.mysql_meta import MySQLDB

        redis_event_bus = create_redis_event_bus(stream_name="data")
        redis_event_bus.ping()

        mysql_db = MySQLDB(
            host=os.environ["MYSQL_HOST"],
            port=int(os.environ["MYSQL_PORT"]),
            user="stock",
            password=None,
            database=_STOCK_DATABASE,
            name=_STOCK_DATABASE,
        )
        mysql_db.connect()

        data_agent = DataAgent(
            event_bus=redis_event_bus,
            mysql_dbs={_STOCK_DATABASE: mysql_db},
        )
        logger.info(
            "DataAgent started and subscribed to data.fetch.requested and "
            "data.task.finished."
        )
        shutdown_requested.wait()
        logger.info("DataAgent shutdown requested.")
        exit_code = 0
    except Exception:
        logger.exception("Data service stopped because of an unexpected error.")
    finally:
        if data_agent is not None:
            try:
                data_agent.close()
            except Exception:
                logger.exception("Failed to close DataAgent resources.")
                exit_code = 1
        elif mysql_db is not None:
            try:
                mysql_db.close()
            except Exception:
                logger.exception("Failed to close the MySQL connection.")
                exit_code = 1
        if redis_event_bus is not None:
            try:
                redis_event_bus.close()
            except Exception:
                logger.exception("Failed to close the Redis event bus.")
                exit_code = 1
        for signum, previous_handler in previous_handlers.items():
            signal.signal(signum, previous_handler)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
