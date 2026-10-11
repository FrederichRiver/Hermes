from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .event_format_error import EventFormatError
from .event_meta import EventMeta

_TYPE_PATTERN = re.compile(r"^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+){2}$")


@dataclass(slots=True)
class Event:
    """Unified event envelope for the Hermes event system."""

    id: str
    type: str
    source: str
    ts: int
    data: dict[str, Any]
    trace_id: str | None = None
    meta: EventMeta = field(default_factory=EventMeta, repr=False)

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise EventFormatError("id is required and must be a non-empty string.")
        try:
            uuid.UUID(self.id)
        except ValueError as exc:  # pragma: no cover - validation branch
            raise EventFormatError(f"id is not a valid UUID: {self.id!r}") from exc

        if not isinstance(self.type, str) or not _TYPE_PATTERN.fullmatch(self.type):
            raise EventFormatError(
                f"type must be a dotted three-part name like 'market.tick.received': {self.type!r}"
            )

        if not isinstance(self.source, str) or not self.source:
            raise EventFormatError("source is required and must be a non-empty string.")

        if not isinstance(self.ts, int) or self.ts <= 0:
            raise EventFormatError("ts must be a positive millisecond Unix timestamp.")

        if self.ts > 10_000_000_000_000:
            raise EventFormatError("ts is outside the supported millisecond range.")

        if not isinstance(self.data, dict):
            raise EventFormatError("data must be a dictionary.")

        if self.trace_id is not None and not isinstance(self.trace_id, str):
            raise EventFormatError("trace_id must be a string when provided.")

    @staticmethod
    def _now_ms() -> int:
        return int(datetime.now(timezone.utc).timestamp() * 1000)

    @staticmethod
    def _parse_data(raw: str | dict[str, Any] | None) -> dict[str, Any]:
        if raw is None:
            return {}
        if isinstance(raw, dict):
            return raw
        if not isinstance(raw, str):
            raise EventFormatError("data payload must be a JSON string or dict.")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise EventFormatError(f"data payload is not valid JSON: {raw!r}") from exc
        if not isinstance(parsed, dict):
            raise EventFormatError("data payload must deserialize to a dictionary.")
        return parsed

    @classmethod
    def create(
        cls,
        event_type: str,
        source: str,
        data: dict[str, Any] | None = None,
        *,
        trace_id: str | None = None,
    ) -> "Event":
        normalized_type = str(event_type)
        return cls(
            id=str(uuid.uuid4()),
            type=normalized_type,
            source=str(source),
            ts=cls._now_ms(),
            data=dict(data or {}),
            trace_id=trace_id,
        )

    @classmethod
    def from_envelope(cls, fields: dict[str, Any]) -> "Event":
        if not isinstance(fields, dict):
            raise EventFormatError("envelope must be a dictionary.")

        event_id = fields.get("id")
        if event_id is None:
            raise EventFormatError("missing required field: id")

        event_type = fields.get("type")
        if event_type is None:
            raise EventFormatError("missing required field: type")

        source = fields.get("source")
        if source is None:
            raise EventFormatError("missing required field: source")

        ts_value = fields.get("ts")
        if ts_value is None:
            raise EventFormatError("missing required field: ts")

        try:
            ts = int(ts_value)
        except (TypeError, ValueError) as exc:
            raise EventFormatError(f"ts must be an integer millisecond timestamp: {ts_value!r}") from exc

        raw_data = fields.get("data")
        if raw_data is None:
            raise EventFormatError("missing required field: data")

        payload = cls._parse_data(raw_data)
        trace_id = fields.get("trace_id")
        if trace_id is not None and not isinstance(trace_id, str):
            raise EventFormatError("trace_id must be a string when present.")

        return cls(
            id=str(event_id),
            type=str(event_type),
            source=str(source),
            ts=ts,
            data=payload,
            trace_id=trace_id,
        )

    def to_envelope(self) -> dict[str, str]:
        envelope: dict[str, str] = {
            "id": self.id,
            "type": self.type,
            "source": self.source,
            "ts": str(self.ts),
            "data": json.dumps(self.data, separators=(",", ":"), ensure_ascii=False),
        }
        if self.trace_id:
            envelope["trace_id"] = self.trace_id
        return envelope

    def to_json(self) -> str:
        payload = {
            "id": self.id,
            "type": self.type,
            "source": self.source,
            "ts": self.ts,
            "data": self.data,
            "trace_id": self.trace_id,
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def get_data(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.ts / 1000, tz=timezone.utc)

    @property
    def domain(self) -> str:
        return self.type.split(".", 1)[0]

    @property
    def action(self) -> str:
        return self.type.rsplit(".", 1)[-1]

    def __repr__(self) -> str:
        return f"Event(type={self.type!r}, id={self.id[:8]}, ts={self.ts})"


__all__ = ["Event", "EventMeta", "EventFormatError"]
