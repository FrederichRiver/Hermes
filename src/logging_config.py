import logging
import logging.handlers
import sys
import json
import datetime
from typing import Optional


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_record = {}
        # ISO8601 UTC timestamp
        created = datetime.datetime.utcfromtimestamp(record.created).isoformat() + "Z"
        log_record["timestamp"] = created
        log_record["level"] = record.levelname
        log_record["module"] = record.name
        log_record["message"] = record.getMessage()

        # include common extras if present
        for key in ("error_code", "correlation_id", "trace_id", "span_id", "context"):
            if hasattr(record, key):
                try:
                    log_record[key] = getattr(record, key)
                except Exception:
                    pass

        if record.exc_info:
            log_record["stack"] = self.formatException(record.exc_info)

        try:
            return json.dumps(log_record, ensure_ascii=False)
        except Exception:
            # fallback to plain message
            return record.getMessage()


def setup_logging(level: int = logging.INFO, logfile: Optional[str] = None, json_format: bool = False, max_bytes: int = 10 * 1024 * 1024, backup_count: int = 5):
    """Configure root logging for the application.

    - `json_format=True` writes structured JSON logs.
    - `logfile` if provided will write rotating logs to that path.
    """
    root = logging.getLogger()
    root.setLevel(level)

    # remove existing handlers to avoid duplicate logs when re-running setup
    for h in list(root.handlers):
        root.removeHandler(h)

    if json_format:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%dT%H:%M:%S%z")

    # stream handler (stdout)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    root.addHandler(sh)

    # optional rotating file handler
    if logfile:
        fh = logging.handlers.RotatingFileHandler(logfile, maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8')
        fh.setFormatter(formatter)
        root.addHandler(fh)


def get_logger(name: str):
    return logging.getLogger(name)
