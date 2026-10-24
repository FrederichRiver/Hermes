#!/opt/application/venv/bin/python3
"""Command-line entry point for the Hermes trading system."""

import os
import signal
import sys
import time
from collections.abc import Sequence
from pathlib import Path

_COMMAND_HELP = """Usage: python main.py <command>

Commands:
    start  Run the EventEngine in the foreground.
    help   Show this help message.

Use the dedicated systemd services to manage deployed modules.
"""


def _load_help_text() -> str:
    """Return the embedded command help text."""
    return _COMMAND_HELP


_APPLICATION_DIRECTORY = Path("/opt/application")
_DATABASE_DIRECTORY = _APPLICATION_DIRECTORY / "database"


def _get_database_directory() -> Path:
    """Return the directory used for persistent application databases."""
    return _DATABASE_DIRECTORY


def _get_task_file() -> Path:
    """Return the task configuration file in the application root."""
    return Path(__file__).resolve().parent / "task.json"


def _stop_on_signal(_signum: int, _frame: object) -> None:
    """Convert a stop request into the normal application cleanup path."""
    raise KeyboardInterrupt


def _build_event_bus() -> object:
    """Build the configured event bus transport."""
    from event_engine.event_bus import InMemoryEventBus, RedisEventBus

    event_bus_type = "redis"

    if event_bus_type == "redis":
        import redis

        redis_client = redis.Redis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            username=os.environ["REDIS_USERNAME"],
            password=os.environ["REDIS_PASSWORD"],
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        return RedisEventBus(redis_client)
    else:
        return InMemoryEventBus()


def _start_application() -> int:
    """Start Hermes and block until it receives an interrupt or stop request.

    Heavy runtime dependencies are imported lazily so the --help path can run
    on systems where the full runtime isn't available.
    """
    # Lazy imports so 'help' doesn't fail if optional packages aren't installed.
    from utils.logging import configure_logging, get_logger

    configure_logging()
    logger = get_logger(__name__)
    signal.signal(signal.SIGTERM, _stop_on_signal)
    logger.info(f"Hermes started with PID {os.getpid()}.")

    event_engine = None
    try:
        from event_engine.event_engine import EventEngine

        event_bus = _build_event_bus()
        event_engine = EventEngine(bus=event_bus)
        event_engine.start()

        startup_event = event_engine.emit(
            "hermes.system.startup",
            {"pid": os.getpid()},
        )
        stream_entry_id = event_engine.xadd(
            "hermes:events",
            startup_event.to_envelope(),
        )
        logger.info(f"Startup event stored in hermes:events with ID {stream_entry_id}.")

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Hermes stopping.")
    except Exception:
        logger.exception("Hermes stopped because of an unexpected error.")
        return 1
    finally:
        if event_engine is not None:
            event_engine.stop()

    return 0


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the requested foreground command.

    Args:
        arguments: Command arguments without the executable name. Defaults to
            command-line arguments supplied by the operating system.

    Returns:
        A process exit code.
    """
    command_arguments = list(sys.argv[1:] if arguments is None else arguments)
    if not command_arguments or command_arguments == ["help"]:
        print(_load_help_text())
        return 0
    if command_arguments == ["start"]:
        return _start_application()

    print(_load_help_text())
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
