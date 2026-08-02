"""Event-engine task scheduler synchronized from ``task.json``.

The task file contains a ``tasks`` array. Each task requires a stable ``uid``
and a callable in ``package.module:function`` format. Supported task types are
``cron`` for recurring tasks and ``date`` for a task that runs once at a
specific ISO 8601 timestamp.
"""

import hashlib
import importlib
import json
import logging
import sqlite3
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger


_SYNC_INTERVAL_MINUTES = 5
_SYNC_JOB_ID = "hermes-task-file-sync"
_TASK_JOB_PREFIX = "task:"
_TASKS_TABLE = "scheduled_tasks"


class PersistentTaskScheduler:
    """Synchronize ``task.json`` tasks into SQLite and APScheduler.

    Args:
        task_file: JSON task definition file.
        database_path: SQLite database used to persist task definitions.
    """

    def __init__(self, task_file: str | Path, database_path: str | Path) -> None:
        self._task_file = Path(task_file)
        self._database_path = Path(database_path)
        self._scheduler = BackgroundScheduler(timezone="UTC")
        self._lock = threading.RLock()
        self._logger = logging.getLogger(__name__)
        self._module_versions: dict[str, int] = {}
        self._pending_module_reloads: set[str] = set()
        self._running_task_count = 0

    def start(self) -> None:
        """Start task scheduling and synchronize task definitions immediately."""
        with self._lock:
            self._initialize_database()
            self._scheduler.start()
            self._restore_persisted_tasks()
            self._scheduler.add_job(
                self.sync_tasks,
                trigger=IntervalTrigger(minutes=_SYNC_INTERVAL_MINUTES),
                id=_SYNC_JOB_ID,
                name="Synchronize task.json",
                replace_existing=True,
            )
            self.sync_tasks()

    def shutdown(self) -> None:
        """Stop scheduling without waiting for currently executing tasks."""
        with self._lock:
            if self._scheduler.running:
                self._scheduler.shutdown(wait=False)

    def sync_tasks(self) -> dict[str, int]:
        """Apply task creations, updates, and deletions from ``task.json``.

        Returns:
            Counts of created, updated, and deleted task definitions.
        """
        with self._lock:
            self._initialize_database()
            tasks = self._load_tasks()
            task_by_uid = {task["uid"]: task for task in tasks}
            persisted_tasks = self._load_persisted_tasks()
            changes = {"created": 0, "updated": 0, "deleted": 0}

            for uid, task in task_by_uid.items():
                content_hash = self._task_hash(task)
                if persisted_tasks.get(uid) == content_hash:
                    continue

                self._schedule_task(task)
                self._upsert_task(uid, task, content_hash)
                change_type = "created" if uid not in persisted_tasks else "updated"
                changes[change_type] += 1

            for uid in persisted_tasks:
                if uid in task_by_uid:
                    continue

                self._remove_task_job(uid)
                self._delete_task(uid)
                changes["deleted"] += 1

            self._detect_module_updates()
            return changes

    def _initialize_database(self) -> None:
        """Create the persistent task table when it does not exist."""
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {_TASKS_TABLE} (
                    uid TEXT PRIMARY KEY,
                    task_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def _load_tasks(self) -> list[dict[str, object]]:
        """Load and validate task definitions from the JSON task file."""
        try:
            document = json.loads(self._task_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self._logger.warning("Task file does not exist: %s", self._task_file)
            return []
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid task JSON: {self._task_file}") from exc

        tasks = document.get("tasks") if isinstance(document, dict) else None
        if not isinstance(tasks, list):
            raise ValueError("task.json must contain a 'tasks' array")

        task_by_uid: dict[str, dict[str, object]] = {}
        for task in tasks:
            if not isinstance(task, dict):
                raise ValueError("Every task must be a JSON object")
            normalized_task = dict(task)
            uid = normalized_task.get("uid")
            if not isinstance(uid, str) or not uid:
                raise ValueError("Every task requires a non-empty string uid")
            if uid in task_by_uid:
                raise ValueError(f"Duplicate task uid: {uid}")
            self._validate_task(normalized_task)
            task_by_uid[uid] = normalized_task

        return list(task_by_uid.values())

    def _validate_task(self, task: dict[str, object]) -> None:
        """Validate the scheduling fields required by one task definition."""
        task_type = task.get("type")
        callable_path = task.get("callable")
        if task_type not in {"cron", "date"}:
            raise ValueError(f"Unsupported task type for {task['uid']}: {task_type}")
        if not isinstance(callable_path, str) or ":" not in callable_path:
            raise ValueError(f"Task {task['uid']} requires a callable path")
        if task_type == "cron" and not isinstance(task.get("cron"), str):
            raise ValueError(f"Cron task {task['uid']} requires a cron expression")
        if task_type == "date" and not isinstance(task.get("run_at"), str):
            raise ValueError(f"Date task {task['uid']} requires an ISO timestamp")
        if not isinstance(task.get("args", []), list):
            raise ValueError(f"Task {task['uid']} args must be an array")
        if not isinstance(task.get("kwargs", {}), dict):
            raise ValueError(f"Task {task['uid']} kwargs must be an object")

    def _restore_persisted_tasks(self) -> None:
        """Restore database tasks before the first file synchronization."""
        with sqlite3.connect(self._database_path) as connection:
            rows = connection.execute(
                f"SELECT task_json FROM {_TASKS_TABLE} ORDER BY uid"
            ).fetchall()

        for (task_json,) in rows:
            task = json.loads(task_json)
            self._schedule_task(task)

    def _load_persisted_tasks(self) -> dict[str, str]:
        """Return persisted task hashes keyed by UID."""
        with sqlite3.connect(self._database_path) as connection:
            rows = connection.execute(
                f"SELECT uid, content_hash FROM {_TASKS_TABLE}"
            ).fetchall()
        return {uid: content_hash for uid, content_hash in rows}

    def _upsert_task(
        self,
        uid: str,
        task: dict[str, object],
        content_hash: str,
    ) -> None:
        """Persist a created or updated task definition."""
        task_json = json.dumps(task, ensure_ascii=False, sort_keys=True)
        updated_at = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                f"""
                INSERT INTO {_TASKS_TABLE} (uid, task_json, content_hash, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(uid) DO UPDATE SET
                    task_json = excluded.task_json,
                    content_hash = excluded.content_hash,
                    updated_at = excluded.updated_at
                """,
                (uid, task_json, content_hash, updated_at),
            )

    def _delete_task(self, uid: str) -> None:
        """Remove one task definition from SQLite."""
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(f"DELETE FROM {_TASKS_TABLE} WHERE uid = ?", (uid,))

    def _schedule_task(self, task: dict[str, object]) -> None:
        """Create or replace the APScheduler job represented by ``task``."""
        uid = task["uid"]
        if not isinstance(uid, str):
            raise ValueError("Task uid must be a string")
        if task.get("enabled", True) is False:
            self._remove_task_job(uid)
            return

        callable_path = task["callable"]
        if not isinstance(callable_path, str):
            raise ValueError(f"Task {uid} has an invalid callable")
        self._resolve_callable(callable_path)
        trigger = self._build_trigger(task)
        args = task.get("args", [])
        kwargs = task.get("kwargs", {})
        if not isinstance(args, list) or not isinstance(kwargs, dict):
            raise ValueError(f"Task {uid} has invalid arguments")

        # APScheduler defers jobs added before startup, so explicit removal is
        # required for UID updates to replace pending jobs as well.
        self._remove_task_job(uid)
        self._scheduler.add_job(
            self._run_task,
            trigger=trigger,
            id=f"{_TASK_JOB_PREFIX}{uid}",
            name=str(task.get("name", uid)),
            args=[uid, callable_path, args, kwargs],
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

    def _remove_task_job(self, uid: str) -> None:
        """Remove a scheduled job when it exists."""
        try:
            self._scheduler.remove_job(f"{_TASK_JOB_PREFIX}{uid}")
        except JobLookupError:
            pass

    def _resolve_callable(self, callable_path: str) -> Callable[..., object]:
        """Import and return a task callable from ``package.module:function``."""
        module_name, attribute_name = callable_path.split(":", maxsplit=1)
        module = importlib.import_module(module_name)
        self._module_versions.setdefault(
            module_name,
            self._get_module_version(module),
        )
        task_callable = getattr(module, attribute_name)
        if not callable(task_callable):
            raise ValueError(f"Task target is not callable: {callable_path}")
        return task_callable

    def _run_task(
        self,
        uid: str,
        callable_path: str,
        args: list[object],
        kwargs: dict[str, object],
    ) -> None:
        """Execute one task while coordinating deferred module reloads."""
        with self._lock:
            self._running_task_count += 1

        try:
            task_callable = self._resolve_callable(callable_path)
            self._logger.info("Executing task %s", uid)
            task_callable(*args, **kwargs)
            self._logger.info("Completed task %s", uid)
        except Exception:
            self._logger.exception("Task %s failed", uid)
        finally:
            with self._lock:
                self._running_task_count -= 1
                if self._running_task_count == 0:
                    self._reload_pending_modules()

    def _detect_module_updates(self) -> None:
        """Reload changed task modules now or defer them until tasks are idle."""
        changed_modules = {
            module_name
            for module_name, recorded_version in self._module_versions.items()
            if self._module_has_changed(module_name, recorded_version)
        }
        if not changed_modules:
            return
        if self._running_task_count:
            self._pending_module_reloads.update(changed_modules)
            self._logger.info(
                "Deferring module reload until %d running task(s) complete: %s",
                self._running_task_count,
                ", ".join(sorted(changed_modules)),
            )
            return
        self._reload_modules(changed_modules)

    def _module_has_changed(self, module_name: str, recorded_version: int) -> bool:
        """Return whether a task module's source has changed since it was loaded."""
        module = importlib.import_module(module_name)
        return self._get_module_version(module) != recorded_version

    def _reload_pending_modules(self) -> None:
        """Reload every update deferred while a task was running."""
        if not self._pending_module_reloads:
            return
        modules = self._pending_module_reloads.copy()
        self._pending_module_reloads.clear()
        self._reload_modules(modules)

    def _reload_modules(self, module_names: set[str]) -> None:
        """Reload task modules and store their new source versions."""
        importlib.invalidate_caches()
        for module_name in module_names:
            try:
                module = importlib.import_module(module_name)
                reloaded_module = importlib.reload(module)
                self._module_versions[module_name] = self._get_module_version(
                    reloaded_module
                )
                self._logger.info("Reloaded task module: %s", module_name)
            except Exception:
                self._pending_module_reloads.add(module_name)
                self._logger.exception("Failed to reload task module: %s", module_name)

    @staticmethod
    def _get_module_version(module: ModuleType) -> int:
        """Return the source modification timestamp used to detect code updates."""
        module_file = getattr(module, "__file__", None)
        if not module_file:
            return 0
        try:
            return Path(module_file).stat().st_mtime_ns
        except OSError:
            return 0

    def _build_trigger(self, task: dict[str, object]) -> CronTrigger | DateTrigger:
        """Create an APScheduler trigger from one validated task definition."""
        task_type = task["type"]
        if task_type == "cron":
            cron_expression = task["cron"]
            if not isinstance(cron_expression, str):
                raise ValueError(f"Task {task['uid']} has an invalid cron expression")
            return CronTrigger.from_crontab(cron_expression, timezone="UTC")

        run_at = task["run_at"]
        if not isinstance(run_at, str):
            raise ValueError(f"Task {task['uid']} has an invalid run_at value")
        return DateTrigger(run_date=run_at, timezone="UTC")

    @staticmethod
    def _task_hash(task: dict[str, object]) -> str:
        """Return a stable hash for comparison with the persisted definition."""
        serialized_task = json.dumps(
            task,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized_task.encode("utf-8")).hexdigest()
