from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class EventMeta:
    """Envelope metadata describing the transport and routing context."""

    message_id: str = ""
    routing_key: str = ""
    schema_version: str = "1.0"
    trace_id: Optional[str] = None
    delivery: str = "at_least_once"
    headers: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "routing_key": self.routing_key,
            "schema_version": self.schema_version,
            "trace_id": self.trace_id,
            "delivery": self.delivery,
            "headers": dict(self.headers),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "EventMeta":
        return cls(
            message_id=payload.get("message_id", ""),
            routing_key=payload.get("routing_key", ""),
            schema_version=payload.get("schema_version", "1.0"),
            trace_id=payload.get("trace_id"),
            delivery=payload.get("delivery", "at_least_once"),
            headers=dict(payload.get("headers", {})),
        )
