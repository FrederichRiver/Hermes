"""Configure application logging for foreground services."""

from __future__ import annotations

import logging
import os
import sys
import threading


_MANAGED_HANDLER_ATTRIBUTE = "_hermes_logging_handler"
_CONFIGURATION_LOCK = threading.RLock()
_LOG_FORMAT = "{asctime} {levelname} {name}: {message}"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def _resolve_level(level: int | str | None) -> int:
    if level is None:
        level = os.environ.get("LOG_LEVEL", "INFO")

    if isinstance(level, str):
        resolved_level = logging.getLevelName(level.upper())
        if not isinstance(resolved_level, int):
            raise ValueError(f"Invalid logging level: {level}")
        return resolved_level

    if not isinstance(level, int):
        raise TypeError("level must be an integer, a level name, or None")

    return level


def configure_logging(level: int | str | None = None) -> None:
    """Configure the root logger to write formatted records to stdout."""
    with _CONFIGURATION_LOCK:
        root_logger = logging.getLogger()
        root_logger.setLevel(_resolve_level(level))

        for handler in list(root_logger.handlers):
            if getattr(handler, _MANAGED_HANDLER_ATTRIBUTE, False):
                root_logger.removeHandler(handler)
                handler.close()

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT, style="{")
        )
        setattr(console_handler, _MANAGED_HANDLER_ATTRIBUTE, True)
        root_logger.addHandler(console_handler)


def get_logger(module_name: str) -> logging.Logger:
    """Return a standard logger identified by its module name."""
    if not module_name:
        raise ValueError("module_name must not be empty")

    return logging.getLogger(module_name)
