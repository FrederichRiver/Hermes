from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

from event_engine.event_engine import Event


@dataclass
class TimeEvent(Event):
    """Event specialized for clock and schedule driven notifications."""

    timezone: str = "UTC"
    occurs_at: Optional[datetime] = None
    recurring: bool = False
    cron: Optional[str] = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.occurs_at is None:
            self.occurs_at = self.timestamp

    def to_dict(self) -> Dict[str, Any]:
        payload = super().to_dict()
        payload.update(
            {
                "timezone": self.timezone,
                "occurs_at": self.occurs_at.isoformat() if self.occurs_at else None,
                "recurring": self.recurring,
                "cron": self.cron,
            }
        )
        return payload
