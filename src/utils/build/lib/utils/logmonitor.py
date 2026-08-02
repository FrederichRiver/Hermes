"""Monitor and restore the shared application log file."""

import logging
import threading
from pathlib import Path

from .logging_config import setup_logging


_LOG_CHECK_INTERVAL_SECONDS = 5.0


def monitor_log_file(
    log_file: str | Path,
    stop_event: threading.Event,
    *,
    check_interval_seconds: float = _LOG_CHECK_INTERVAL_SECONDS,
) -> None:
    """Restore the shared log file if it is deleted while Hermes is running.

    Args:
        log_file: Active log file created by ``setup_logging``.
        stop_event: Event used to end monitoring promptly during shutdown.
        check_interval_seconds: File existence check interval in seconds.

    Raises:
        ValueError: If ``check_interval_seconds`` is not positive.
    """
    if check_interval_seconds <= 0:
        raise ValueError("check_interval_seconds must be positive")

    log_path = Path(log_file)
    while not stop_event.wait(check_interval_seconds):
        if not log_path.exists():
            setup_logging(log_path.parent)
            logging.getLogger(__name__).warning(
                "Recreated missing log file: %s",
                log_path,
            )


def start_log_monitor(
    log_file: str | Path,
    *,
    check_interval_seconds: float = _LOG_CHECK_INTERVAL_SECONDS,
) -> tuple[threading.Event, threading.Thread]:
    """Start a daemon thread that monitors the shared log file.

    Args:
        log_file: Active log file created by ``setup_logging``.
        check_interval_seconds: File existence check interval in seconds.

    Returns:
        A stop event and the running monitor thread.
    """
    stop_event = threading.Event()
    monitor_thread = threading.Thread(
        target=monitor_log_file,
        args=(log_file, stop_event),
        kwargs={"check_interval_seconds": check_interval_seconds},
        name="hermes-log-monitor",
        daemon=True,
    )
    monitor_thread.start()
    return stop_event, monitor_thread
