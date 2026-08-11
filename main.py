#!/opt/application/venv/bin/python3
"""Command-line entry point for the Hermes trading system."""

import os
import signal
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from event_engine.scheduler import PersistentTaskScheduler
from utils.logging_config import log_error, setup_logging
from utils.logmonitor import start_log_monitor


_COMMAND_HELP = """Usage: python main.py <command>

Commands:
    start  Start Hermes. Unix starts as a daemon; Windows stays in the foreground.
    stop   Stop the running Hermes process.
    clear  Clear log files in the log directory.
    help   Show this help message.
"""
_PID_FILE_NAME = "hermes.pid"
_APPLICATION_DIRECTORY = Path("/opt/application")
_LOG_DIRECTORY = _APPLICATION_DIRECTORY / "log"
_DATABASE_DIRECTORY = _APPLICATION_DIRECTORY / "database"
_PID_DIRECTORY = Path("/tmp")


def _get_log_directory() -> Path:
    """Return the directory used for application logs and scheduler data."""
    return _LOG_DIRECTORY


def _clear_logs() -> int:
    """Truncate log files in the log directory. Returns number of files cleared."""
    log_dir = _get_log_directory()
    cleared = 0
    try:
        if not log_dir.exists():
            return 0
        for p in log_dir.iterdir():
            if p.is_file():
                try:
                    # Truncate file
                    with open(p, "w", encoding="utf-8"):
                        pass
                    cleared += 1
                except Exception:
                    # ignore unreadable files
                    continue
    except Exception:
        return 0
    return cleared


def _get_pid_file() -> Path:
    """Return the PID file path for the Hermes process."""
    return _PID_DIRECTORY / _PID_FILE_NAME


def _get_database_directory() -> Path:
    """Return the directory used for persistent application databases."""
    return _DATABASE_DIRECTORY


def _get_task_file() -> Path:
    """Return the task configuration file in the application root."""
    return Path(__file__).resolve().parent / "task.json"


def _should_daemonize() -> bool:
    """Return whether the current platform supports Unix daemon startup."""
    return os.name == "posix"


def _read_pid(pid_file: Path) -> int | None:
    """Return the process ID stored in ``pid_file``, if valid."""
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return pid if pid > 0 else None


def _is_process_running(pid: int) -> bool:
    """Return whether a process with ``pid`` is currently running."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _remove_pid_file(pid_file: Path) -> None:
    """Remove the PID file only when it belongs to this process."""
    if _read_pid(pid_file) == os.getpid():
        pid_file.unlink(missing_ok=True)


def daemonize() -> None:
    """Detach the current process using the standard Unix double-fork pattern."""
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as exc:
        raise RuntimeError(
            f"First daemon fork failed: {exc.errno} ({exc.strerror})"
        ) from exc

    os.setsid()

    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as exc:
        raise RuntimeError(
            f"Second daemon fork failed: {exc.errno} ({exc.strerror})"
        ) from exc

    sys.stdout.flush()
    sys.stderr.flush()
    with open(os.devnull, "r", encoding="utf-8") as null_input:
        os.dup2(null_input.fileno(), sys.stdin.fileno())
    with open(os.devnull, "a", encoding="utf-8") as null_output:
        os.dup2(null_output.fileno(), sys.stdout.fileno())
        os.dup2(null_output.fileno(), sys.stderr.fileno())


def _stop_on_signal(_signum: int, _frame: object) -> None:
    """Convert a stop request into the normal application cleanup path."""
    raise KeyboardInterrupt


def _start_application() -> int:
    """Start Hermes and block until it receives an interrupt or stop request."""
    log_directory = _get_log_directory()
    pid_file = _get_pid_file()
    existing_pid = _read_pid(pid_file)

    if existing_pid and _is_process_running(existing_pid):
        print(f"Hermes is already running with PID {existing_pid}.")
        return 1
    if existing_pid:
        pid_file.unlink(missing_ok=True)

    log_file = setup_logging(log_directory)
    if _should_daemonize():
        daemonize()

    pid_file.write_text(str(os.getpid()), encoding="utf-8")
    signal.signal(signal.SIGTERM, _stop_on_signal)
    monitor_stop_event, monitor_thread = start_log_monitor(log_file)
    print(f"Hermes started with PID {os.getpid()}.")

    event_engine = None
    scheduler = None
    try:
        from event_engine.event_engine import EventEngine

        event_engine = EventEngine()
        event_engine.start()
        scheduler = PersistentTaskScheduler(
            _get_task_file(),
            _get_database_directory() / "scheduler.sqlite3",
        )
        scheduler.start()

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Hermes stopping.")
    except Exception:
        log_error("Hermes stopped because of an unexpected error.", __name__, exc_info=True)
        return 1
    finally:
        monitor_stop_event.set()
        monitor_thread.join(timeout=1)
        if scheduler is not None:
            scheduler.shutdown()
        if event_engine is not None:
            event_engine.stop()
        _remove_pid_file(pid_file)

    return 0


def _stop_application() -> int:
    """Request graceful termination of the process recorded in the PID file."""
    pid_file = _get_pid_file()
    pid = _read_pid(pid_file)
    if pid is None:
        print("Hermes is not running.")
        return 1

    if not _is_process_running(pid):
        pid_file.unlink(missing_ok=True)
        print("Removed stale Hermes PID file.")
        return 0

    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        log_error(f"Unable to stop Hermes process {pid}: {exc}", __name__)
        return 1

    print(f"Stop request sent to Hermes process {pid}.")
    return 0


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the requested Hermes lifecycle command.

    Args:
        arguments: Command arguments without the executable name. Defaults to
            command-line arguments supplied by the operating system.

    Returns:
        A process exit code.
    """
    command_arguments = list(sys.argv[1:] if arguments is None else arguments)
    if not command_arguments or command_arguments == ["help"]:
        print(_COMMAND_HELP)
        return 0
    if command_arguments == ["start"]:
        return _start_application()
    if command_arguments == ["stop"]:
        return _stop_application()
    if command_arguments == ["clear"]:
        n = _clear_logs()
        if n:
            print(f"Cleared {n} log file(s) in {_get_log_directory()}")
        else:
            print(f"No log files cleared in {_get_log_directory()}")
        return 0

    print(_COMMAND_HELP)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
