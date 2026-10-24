from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional


class TimeEngine:
    """Tracks time-zone normalized scheduling behavior for event dispatch."""

    def __init__(self, timezone_name: str = "UTC") -> None:
        self.timezone_name = timezone_name

    @staticmethod
    def now_utc() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def to_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def local_now(self) -> datetime:
        return self.now_utc().astimezone()

    def next_interval(self, *, seconds: int = 0, minutes: int = 0, hours: int = 0) -> datetime:
        delta = timedelta(seconds=seconds, minutes=minutes, hours=hours)
        return self.now_utc() + delta

    def next_tick(self, *, seconds: int = 1) -> datetime:
        return self.now_utc() + timedelta(seconds=seconds)

    def normalize_time(self, value: Optional[datetime]) -> datetime:
        if value is None:
            return self.now_utc()
        return self.to_utc(value)
