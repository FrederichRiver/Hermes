from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any, Dict, Iterable, Optional

from .event import EventType

from .event import Event
from .event_bus import EventBus, InMemoryEventBus
from .event_meta import EventMeta


class EventEngine:
    """Lightweight event bus that supports registration, dispatch, and metadata."""

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        self.bus = bus or InMemoryEventBus()
        self.handlers: Dict[str, list[Callable[[Event], None]]] = defaultdict(list)
        self.running = False

    def register(self, event_type: str | EventType, handler: Callable[[Event], None]) -> None:
        name = event_type.name if isinstance(event_type, EventType) else str(event_type)
        self.handlers[name].append(handler)

    def unregister(self, event_type: str | EventType, handler: Callable[[Event], None]) -> None:
        name = event_type.name if isinstance(event_type, EventType) else str(event_type)
        handlers = self.handlers.get(name, [])
        if handler in handlers:
            handlers.remove(handler)

    def emit(
        self,
        event_type: str | EventType,
        event_data: Optional[Dict[str, Any]] = None,
        *,
        source: str = "event_engine",
        priority: int = 5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Event:
        # Normalize event_type to string for the Event factory
        et = event_type.name if isinstance(event_type, EventType) else str(event_type)
        # Create Event using the canonical factory (Event.create)
        event = Event.create(
            event_type=et,
            source=source,
            event_data=event_data or {},
            trace_id=(metadata or {}).get("trace_id") if metadata else None,
        )
        # Determine handler key: EventType-like names are registered as strings
        handler_key = event.event_type if isinstance(event.event_type, str) else event.event_type.name
        for handler in list(self.handlers.get(handler_key, [])):
            handler(event)
        return event

    def publish(
        self,
        event_type: str | EventType,
        event_data: Optional[Dict[str, Any]] = None,
        *,
        source: str = "event_engine",
        priority: int = 5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Event:
        event = self.emit(
            event_type,
            event_data,
            source=source,
            priority=priority,
            metadata=metadata,
        )
        if hasattr(self.bus, "publish"):
            self.bus.publish(event)
        return event

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False

    @property
    def subscribers(self) -> Iterable[str]:
        return tuple(self.handlers.keys())

    def __repr__(self) -> str:
        return f"EventEngine(running={self.running}, handlers={len(self.handlers)})"


__all__ = ["Event", "EventEngine", "EventMeta", "EventBus"]
