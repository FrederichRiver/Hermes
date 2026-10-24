"""Canonical event contract for the quant trading system."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import re
from uuid import uuid4


_EVENT_TYPE_PATTERN = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+")


@dataclass(frozen=True, slots=True)
class QuantEvent:
    """An immutable event exchanged between decoupled quant-system modules.

    Attributes:
        event_type: Lowercase dotted event name, such as ``market.open``.
        payload: Business data carried by the event.
        timestamp: ISO 8601 UTC time at which the event was created.
        source: Name of the module that emitted the event.
        trace_id: Correlation ID preserved through the complete event flow.
    """

    event_type: str
    payload: dict[str, object]
    timestamp: str
    source: str
    trace_id: str

    @classmethod
    def create(
        cls,
        event_type: str,
        payload: dict[str, object],
        source: str,
        trace_id: str | None = None,
    ) -> "QuantEvent":
        """Create a validated event with an ISO 8601 timestamp and trace ID."""
        cls._validate_event_type(event_type)
        if not isinstance(payload, dict):
            raise ValueError("payload must be a dictionary.")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("source must be a non-empty string.")
        if trace_id is not None and (not isinstance(trace_id, str) or not trace_id):
            raise ValueError("trace_id must be a non-empty string when provided.")
        return cls(
            event_type=event_type,
            payload=payload,
            timestamp=datetime.now(timezone.utc).isoformat(),
            source=source.strip(),
            trace_id=trace_id or uuid4().hex,
        )

    def to_json(self) -> str:
        """Serialize the event without losing Unicode payload values."""
        return json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_json(cls, text: str | bytes) -> "QuantEvent":
        """Deserialize and validate an event received from an event transport."""
        if isinstance(text, bytes):
            text = text.decode("utf-8")
        if not isinstance(text, str):
            raise ValueError("event JSON must be text.")
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("event JSON is invalid.") from exc
        if not isinstance(value, dict):
            raise ValueError("event JSON must contain an object.")

        event_type = value.get("event_type")
        payload = value.get("payload")
        timestamp = value.get("timestamp")
        source = value.get("source")
        trace_id = value.get("trace_id")
        cls._validate_event_type(event_type)
        if not isinstance(payload, dict):
            raise ValueError("event payload must be a dictionary.")
        if not isinstance(timestamp, str):
            raise ValueError("event timestamp must be a string.")
        try:
            datetime.fromisoformat(timestamp)
        except ValueError as exc:
            raise ValueError("event timestamp must be ISO 8601.") from exc
        if not isinstance(source, str) or not source.strip():
            raise ValueError("event source must be a non-empty string.")
        if not isinstance(trace_id, str) or not trace_id:
            raise ValueError("event trace_id must be a non-empty string.")
        return cls(event_type, payload, timestamp, source, trace_id)

    @staticmethod
    def _validate_event_type(event_type: object) -> None:
        """Reject event names that do not follow the documented contract."""
        if (
            not isinstance(event_type, str)
            or _EVENT_TYPE_PATTERN.fullmatch(event_type) is None
        ):
            raise ValueError(
                "event_type must be lowercase dotted text, such as 'data.updated'."
            )
