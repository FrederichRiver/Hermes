#!/opt/application/venv/bin/python3
"""Foreground DataAgent service entry point for systemd."""

from __future__ import annotations

import os
import signal
import threading
from types import FrameType
from typing import Any

from basic_utils.logging import configure_logging, get_logger


logger = get_logger(__name__)
_DEFAULT_REDIS_URL = "redis://localhost:6379/0"
_STOCK_DATABASE = "stock_data"


def main() -> int:
    """Run DataAgent in the foreground until systemd requests shutdown."""
    configure_logging()

    shutdown_requested = threading.Event()
    redis_client: Any | None = None
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

        import redis
        from data_agent.data_agent import DataAgent
        from data_agent.mysql_meta import MySQLDB
        from event_engine.event_bus import RedisEventBus

        redis_url = os.environ.get("REDIS_URL", _DEFAULT_REDIS_URL)
        redis_client = redis.Redis.from_url(
            redis_url,
            username=os.environ["REDIS_USERNAME"],
            password=os.environ["REDIS_PASSWORD"],
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        redis_client.ping()

        mysql_db = MySQLDB(
            host=None,
            port=None,
            user=None,
            password=None,
            database=_STOCK_DATABASE,
            name=_STOCK_DATABASE,
        )
        mysql_db.connect()

        redis_event_bus = RedisEventBus(redis_client)
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
        if redis_event_bus is not None:
            try:
                redis_event_bus.stop_listener()
            except Exception:
                logger.exception("Failed to stop the Redis event listener.")
                exit_code = 1
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
