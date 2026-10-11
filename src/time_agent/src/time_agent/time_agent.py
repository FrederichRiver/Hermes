from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .time_core import TimeCore
from .time_engine import TimeEngine
from .time_event import TimeEvent


class TimeAgent:
    """In-memory time scheduler that emits time-specific events to subscribers."""

    def __init__(self, timezone_name: str = "UTC") -> None:
        self.time_core = TimeCore(timezone_name)
        self.time_engine = TimeEngine(timezone_name)
        self.subscribers: List[Callable[[TimeEvent], None]] = []
        self.events: List[TimeEvent] = []

    def subscribe(self, callback: Callable[[TimeEvent], None]) -> None:
        self.subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[TimeEvent], None]) -> None:
        if callback in self.subscribers:
            self.subscribers.remove(callback)

    def emit(self, event: TimeEvent) -> None:
        self.events.append(event)
        for callback in list(self.subscribers):
            callback(event)

    def create_event(
        self,
        *,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        source: str = "time_agent",
        occurs_at: Optional[datetime] = None,
        recurring: bool = False,
        cron: Optional[str] = None,
        timezone: str = "UTC",
    ) -> TimeEvent:
        event = TimeEvent(
            event_type=event_type,
            payload=payload or {},
            source=source,
            timestamp=occurs_at or self.time_engine.now_utc(),
            occurs_at=occurs_at or self.time_engine.now_utc(),
            recurring=recurring,
            cron=cron,
            timezone=timezone,
        )
        return event

    def schedule(self, *, event_type: str, payload: Optional[Dict[str, Any]] = None, source: str = "time_agent", occurs_at: datetime, recurring: bool = False, cron: Optional[str] = None, timezone: str = "UTC") -> TimeEvent:
        event = self.create_event(
            event_type=event_type,
            payload=payload,
            source=source,
            occurs_at=occurs_at,
            recurring=recurring,
            cron=cron,
            timezone=timezone,
        )
        self.emit(event)
        return event

    def now(self) -> datetime:
        return self.time_engine.now_utc()

    def status(self) -> Dict[str, Any]:
        return {
            "timezone": self.time_engine.timezone_name,
            "now": self.now().isoformat(),
            "event_count": len(self.events),
            "subscriber_count": len(self.subscribers),
        }
