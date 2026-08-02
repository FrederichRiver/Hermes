"""Centralized application error logging.

Call ``setup_logging`` once when the system starts. Modules can then send error
messages to ``log_error``; this module adds the timestamp, severity, and module
name before writing to the shared log file.
"""

import logging
import logging.handlers
import sys
import threading
from pathlib import Path


_LOG_FILE_NAME = "hermes.log"
_LOG_RETENTION_DAYS = 30
_LOG_ROTATION_INTERVAL_HOURS = 24
_MANAGED_HANDLER_ATTRIBUTE = "_hermes_logging_config_handler"
_CONFIGURATION_LOCK = threading.RLock()


def _is_managed_handler(handler: logging.Handler) -> bool:
    """Return whether this module created ``handler`` during a prior setup."""
    return bool(getattr(handler, _MANAGED_HANDLER_ATTRIBUTE, False))


def _mark_managed_handler(handler: logging.Handler) -> None:
    """Mark a handler so a later setup can replace it safely."""
    setattr(handler, _MANAGED_HANDLER_ATTRIBUTE, True)


def setup_logging(
    log_directory: str | Path,
    level: int = logging.INFO,
) -> Path:
    """Configure the shared application logger.

    The configured file is rotated every 24 hours. Thirty rotated files are
    retained, so error records are available for the preceding 30 days.

    Args:
        log_directory: Directory in which ``hermes.log`` and its rotated files
            are stored. The directory is created if needed.
        level: Minimum log severity accepted by the root logger.

    Returns:
        The path of the active log file.
    """
    with _CONFIGURATION_LOCK:
        directory = Path(log_directory)
        directory.mkdir(parents=True, exist_ok=True)
        log_file = directory / _LOG_FILE_NAME

        root_logger = logging.getLogger()
        root_logger.setLevel(level)

        for handler in list(root_logger.handlers):
            if _is_managed_handler(handler):
                root_logger.removeHandler(handler)
                handler.close()

        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        _mark_managed_handler(console_handler)
        root_logger.addHandler(console_handler)

        file_handler = logging.handlers.TimedRotatingFileHandler(
            log_file,
            when="h",
            interval=_LOG_ROTATION_INTERVAL_HOURS,
            backupCount=_LOG_RETENTION_DAYS,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        _mark_managed_handler(file_handler)
        root_logger.addHandler(file_handler)

    return log_file


def log_error(
    message: str,
    module_name: str,
    *,
    exc_info: bool = False,
) -> None:
    """Write an error message through the configured shared logger.

    Args:
        message: Error description to record.
        module_name: Name of the module where the error occurred, usually
            ``__name__``.
        exc_info: Whether to include the active exception traceback.

    Raises:
        ValueError: If ``module_name`` is empty.
    """
    if not module_name:
        raise ValueError("module_name must not be empty")

    logging.getLogger(module_name).error(message, exc_info=exc_info)
