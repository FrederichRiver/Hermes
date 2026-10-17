from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


class TimeCore:
    """Simple public clock primitive used by TimeAgent and TimeEngine."""

    def __init__(self, timezone_name: str = "UTC") -> None:
        self.timezone_name = timezone_name

    @staticmethod
    def utc_now() -> datetime:
        return datetime.now(timezone.utc)

    def now(self) -> datetime:
        return self.utc_now()

    def timestamp(self) -> str:
        return self.now().isoformat()

    def is_due(self, now: datetime, due_at: datetime) -> bool:
        return now >= due_at

    def build_status(self, **extra: Any) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {
            "timezone": self.timezone_name,
            "timestamp": self.timestamp(),
        }
        metadata.update(extra)
        return metadata
