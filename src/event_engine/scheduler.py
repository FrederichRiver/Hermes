"""APScheduler-based Scheduler with hot-reload support using Watchdog.

Config schema (example in qts/config/scheduler.json):

jobs:
  - id: fetch_data_job
    name: Fetch Market Data
    func: qts.agents.data_agent:fetch_data
    enabled: true
    trigger:
      type: cron
      cron: '*/5 * * * *'
    args: []
    kwargs:
      source: market
    max_instances: 1
    misfire_grace_time: 60

This Scheduler supports 'cron' and 'interval' triggers and will reload jobs when
the config file is modified.
"""

import os
import time
import threading
import logging
import importlib
from typing import Any, Dict, Optional

import json
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger


logger = logging.getLogger("qts.scheduler")


class Scheduler:
    def __init__(self, config_path: str = 'qts/config/scheduler.json', use_watchdog: bool = True):
        self.config_path = os.path.abspath(config_path)
        self.use_watchdog = use_watchdog
        self.scheduler = BackgroundScheduler()
        self.jobs_meta: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.RLock()
        self.observer: Optional[Any] = None
        # Debounce seconds used when file changes are detected to avoid
        # reloading multiple times for a single save operation.
        self.reload_debounce_seconds = 1.0

        if not logger.handlers:
            ch = logging.StreamHandler()
            ch.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s"))
            logger.addHandler(ch)
            logger.setLevel(logging.INFO)

    def load_config(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            logger.warning("Scheduler config not found: %s", self.config_path)
            return {}
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f) or {}
            return cfg
        except Exception:
            logger.exception("Failed to read scheduler config: %s", self.config_path)
            return {}

    def _get_job_func(self, func_path: str):
        if not func_path or ':' not in func_path:
            return None
        module_name, func_name = func_path.split(':', 1)
        try:
            module = importlib.import_module(module_name)
            return getattr(module, func_name)
        except Exception:
            logger.exception("Failed to import %s", func_path)
            return None

    def _build_trigger(self, job_conf: Dict[str, Any]):
        trigger_conf = job_conf.get('trigger')
        # Backwards compatible: allow top-level 'cron' string
        if not trigger_conf and 'cron' in job_conf:
            try:
                return CronTrigger.from_crontab(job_conf['cron'])
            except Exception:
                logger.exception("Invalid cron expression for job %s", job_conf.get('id'))
                return None

        if not trigger_conf:
            logger.warning("No trigger defined for job %s", job_conf.get('id'))
            return None

        ttype = trigger_conf.get('type', 'cron')
        if ttype == 'cron':
            cron_expr = trigger_conf.get('cron')
            if cron_expr:
                try:
                    return CronTrigger.from_crontab(cron_expr)
                except Exception:
                    logger.exception("Invalid cron for job %s", job_conf.get('id'))
                    # try fields
            fields = trigger_conf.get('fields')
            if isinstance(fields, dict):
                try:
                    return CronTrigger(**fields)
                except Exception:
                    logger.exception("Invalid cron fields for job %s", job_conf.get('id'))
            return None
        elif ttype == 'interval':
            interval_args = trigger_conf.get('interval', {}) or {}
            try:
                return IntervalTrigger(**interval_args)
            except Exception:
                logger.exception("Invalid interval trigger for job %s", job_conf.get('id'))
                return None
        else:
            logger.warning("Unsupported trigger type '%s' for job %s", ttype, job_conf.get('id'))
            return None

    def _job_wrapper(self, func, args, kwargs, job_id: str):
        def _run_job():
            try:
                logger.info("Executing job %s", job_id)
                func(*args, **(kwargs or {}))
                logger.info("Job %s finished", job_id)
            except Exception:
                logger.exception("Job %s raised an exception", job_id)
        return _run_job

    def register_jobs(self, cfg: Dict[str, Any] | None = None):
        cfg = cfg or self.load_config()
        jobs = cfg.get('jobs', []) if cfg else []
        if not jobs:
            logger.info("No jobs configured.")
            return

        with self.lock:
            try:
                self.scheduler.remove_all_jobs()
            except Exception:
                pass
            self.jobs_meta.clear()

            for job in jobs:
                job_id = job.get('id') or job.get('name')
                if not job_id:
                    logger.warning("Skipping job without id/name: %s", job)
                    continue
                if job.get('enabled') is False:
                    logger.info("Job %s disabled; skipping", job_id)
                    continue
                func = self._get_job_func(job.get('func'))
                if not func:
                    logger.warning("Function not found for job %s: %s", job_id, job.get('func'))
                    continue
                trigger = self._build_trigger(job)
                if not trigger:
                    logger.warning("Trigger not valid for job %s; skipping", job_id)
                    continue
                args = job.get('args', []) or []
                kwargs = job.get('kwargs', {}) or {}
                max_instances = job.get('max_instances', 1)
                misfire_grace_time = job.get('misfire_grace_time')
                coalesce = job.get('coalesce', True)
                replace_existing = job.get('replace_existing', True)

                wrapper = self._job_wrapper(func, args, kwargs, job_id)
                try:
                    self.scheduler.add_job(
                        wrapper,
                        trigger,
                        id=job_id,
                        name=job.get('name', job_id),
                        max_instances=max_instances,
                        coalesce=coalesce,
                        misfire_grace_time=misfire_grace_time,
                        replace_existing=replace_existing,
                    )
                    self.jobs_meta[job_id] = job
                    logger.info("Registered job %s", job_id)
                except Exception:
                    logger.exception("Failed to add job %s", job_id)

    def start(self):
        with self.lock:
            cfg = self.load_config()
            # allow debounce to be configured in JSON: reload_debounce_seconds (float)
            try:
                if cfg:
                    rb = cfg.get('reload_debounce_seconds')
                    if rb is not None:
                        self.reload_debounce_seconds = float(rb)
            except Exception:
                logger.warning("Invalid reload_debounce_seconds in config, using %s", self.reload_debounce_seconds)
            self.register_jobs(cfg)
            try:
                self.scheduler.start()
            except Exception:
                logger.exception("Failed to start APScheduler")
            logger.info("Scheduler started with %d jobs", len(self.jobs_meta))
            if self.use_watchdog:
                self._start_watcher()

    def _start_watcher(self):
        """
        Start a file system watcher for the config file. Watchdog is imported
        lazily so the Scheduler module can still be imported when the optional
        dependency is not installed.
        """
        if not os.path.exists(self.config_path):
            logger.warning("Config file for watcher not found: %s", self.config_path)
            return

        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
        except Exception:
            logger.warning("Watchdog not available; hot-reload disabled. Install 'watchdog' to enable.")
            return

        scheduler = self

        class _Handler(FileSystemEventHandler):
            def __init__(self):
                super().__init__()
                self._last = 0

            def _maybe_reload(self, path):
                now = time.time()
                if now - self._last < scheduler.reload_debounce_seconds:
                    return
                self._last = now
                logger.info("Config change detected, reloading jobs: %s", path)
                scheduler.reload_jobs()

            def on_modified(self, event):
                try:
                    src = os.path.abspath(event.src_path)
                except Exception:
                    src = None
                if src and src == scheduler.config_path:
                    self._maybe_reload(event.src_path)

            def on_created(self, event):
                try:
                    src = os.path.abspath(event.src_path)
                except Exception:
                    src = None
                if src and src == scheduler.config_path:
                    self._maybe_reload(event.src_path)

        handler = _Handler()
        self.observer = Observer()
        self.observer.schedule(handler, path=os.path.dirname(self.config_path) or '.', recursive=False)
        self.observer.daemon = True
        self.observer.start()
        logger.info("Started config watcher for %s", self.config_path)

    def reload_jobs(self):
        with self.lock:
            try:
                cfg = self.load_config()
                self.register_jobs(cfg)
                logger.info("Reloaded scheduler jobs from config")
            except Exception:
                logger.exception("Error reloading jobs")

    def shutdown(self):
        with self.lock:
            if self.observer:
                try:
                    self.observer.stop()
                    self.observer.join(timeout=2)
                except Exception:
                    logger.exception("Error stopping observer")
            try:
                self.scheduler.shutdown(wait=False)
            except Exception:
                logger.exception("Error shutting down scheduler")
            logger.info("Scheduler stopped")
