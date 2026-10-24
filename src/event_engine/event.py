from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar

from .event_format_error import EventFormatError
from enum import Enum


class EventType(Enum):
    """RD 风格的事件类型枚举（使用点分三段命名），值为事件字符串。

    请根据 RD-EventType 文档扩展此处。当需要新增事件类型时，优先在
    event_engine.event.py 中添加和维护，避免引用 core 模块的定义。
    """
    # time domain (example from RD-Time Event Type)
    TIME_TRADE_OPEN = "time.trade.open"
    TIME_TRADE_PREOPEN = "time.trade.preopen"
    TIME_TRADE_CLOSE = "time.trade.close"
    TIME_TRADE_PAUSE = "time.trade.pause"
    TIME_TRADE_CONTINUED = "time.trade.continued"
    TIME_HOLIDAY_CHINA = "time.holiday.china"
    TIME_HOLIDAY_US = "time.holiday.us"
    TIME_HOLIDAY_UK = "time.holiday.uk"
    TIME_HOLIDAY_GERMANY = "time.holiday.germany"
    TIME_HOLIDAY_JAPAN = "time.holiday.japan"
    TIME_CYCLE_DAILY = "time.cycle.daily"
    TIME_CYCLE_WEEKLY = "time.cycle.weekly"
    TIME_CYCLE_MONTHLY = "time.cycle.monthly"
    TIME_CYCLE_YEARLY = "time.cycle.yearly"
    TIME_TIMEPOINT_CUSTOM = "time.timepoint.custom"

    # legacy / system examples (string-valued canonical names)
    MARKET_DATA_UPDATE = "market.data.update"
    DATA_NEW_DATA = "data.new.data"
    STRATEGY_SIGNAL = "strategy.signal"
    TRADER_ORDER_REQUEST = "trader.order.request"
    EXECUTION_ORDER_FILLED = "execution.order.filled"

    def __str__(self) -> str:  # make str(EventType.X) yield the dotted name
        return self.value


from .event_meta import EventMeta

_TYPE_PATTERN = re.compile(r"^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+){2}$")


@dataclass(slots=True)
class Event:
    """Unified event envelope for the Hermes event system.

    New events expire 60 seconds after creation by default. The expiration
    timestamp is encoded as a UTC Unix millisecond value in transport envelopes.
    External envelopes may omit it for backward compatibility.

    NOTE: field names follow the in-repo 'Note:' annotations. External envelopes
    (wire format) may still use the legacy keys (id/type/ts/data). The class
    accepts both on input and prefers the canonical names on construction.
    """
    # canonical names per notes
    event_id: str
    event_type: str
    source: str
    timestamp: int
    event_data: dict[str, Any]
    trace_id: str | None = None
    event_meta: EventMeta = field(default_factory=EventMeta, repr=False)
    expires_at: int | None = field(
        default_factory=lambda: Event._now_ms()
        + Event.DEFAULT_EXPIRATION_SECONDS * 1000
    )

    DEFAULT_EXPIRATION_SECONDS: ClassVar[int] = 60

    def __post_init__(self) -> None:
        # Backwards-compat shim: allow callers that passed legacy names via kwargs
        # (e.g., id -> event_id). Already handled by factory methods below.
        self._validate()

    def _validate(self) -> None:
        if not isinstance(self.event_id, str) or not self.event_id:
            raise EventFormatError("event_id is required and must be a non-empty string.")
        try:
            uuid.UUID(self.event_id)
        except ValueError as exc:  # pragma: no cover - validation branch
            raise EventFormatError(f"event_id is not a valid UUID: {self.event_id!r}") from exc

        if not isinstance(self.event_type, str) or not _TYPE_PATTERN.fullmatch(self.event_type):
            raise EventFormatError(
                f"event_type must be a dotted three-part name like 'market.tick.received': {self.event_type!r}"
            )

        if not isinstance(self.source, str) or not self.source:
            raise EventFormatError("source is required and must be a non-empty string.")

        if not isinstance(self.timestamp, int) or self.timestamp <= 0:
            raise EventFormatError("timestamp must be a positive millisecond Unix timestamp.")

        if self.timestamp > 10_000_000_000_000:
            raise EventFormatError("timestamp is outside the supported millisecond range.")

        if not isinstance(self.event_data, dict):
            raise EventFormatError("event_data must be a dictionary.")

        if self.trace_id is not None and not isinstance(self.trace_id, str):
            raise EventFormatError("trace_id must be a string when provided.")

        if self.expires_at is not None and (
            isinstance(self.expires_at, bool)
            or not isinstance(self.expires_at, int)
            or self.expires_at <= 0
            or self.expires_at > 10_000_000_000_000
        ):
            raise EventFormatError(
                "expires_at must be a valid millisecond Unix timestamp."
            )

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
            raise EventFormatError("event_data payload must be a JSON string or dict.")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise EventFormatError(f"event_data payload is not valid JSON: {raw!r}") from exc
        if not isinstance(parsed, dict):
            raise EventFormatError("event_data payload must deserialize to a dictionary.")
        return parsed

    @staticmethod
    def validate_event_type(event_type: object) -> None:
        """Validate a dotted event type string used across bus and transport layers."""
        if not isinstance(event_type, str) or not event_type or _TYPE_PATTERN.fullmatch(event_type) is None:
            raise EventFormatError(
                f"event_type must be a dotted three-part name like 'market.tick.received': {event_type!r}"
            )

    @classmethod
    def create(
        cls,
        event_type: str,
        source: str,
        event_data: dict[str, Any] | None = None,
        *,
        trace_id: str | None = None,
        expires_in_seconds: int = DEFAULT_EXPIRATION_SECONDS,
    ) -> "Event":
        """Create a new event and set its expiration relative to creation time.

        Args:
            event_type: Three-part event type name.
            source: Identifier for the event-producing process or component.
            event_data: Optional business payload; defaults to an empty mapping.
            trace_id: Optional identifier shared by events in one trace.
            expires_in_seconds: Time-to-live in seconds; defaults to 60.

        Returns:
            A new Event with a generated UUID, creation timestamp, and expiry.

        Raises:
            ValueError: If the expiration duration is not a non-negative integer.
            EventFormatError: If the event type is invalid.
        """
        if (
            isinstance(expires_in_seconds, bool)
            or not isinstance(expires_in_seconds, int)
            or expires_in_seconds < 0
        ):
            raise ValueError("expires_in_seconds must be a non-negative integer.")

        normalized_type = str(event_type)
        cls.validate_event_type(normalized_type)
        timestamp = cls._now_ms()
        return cls(
            event_id=str(uuid.uuid4()),
            event_type=normalized_type,
            source=str(source),
            timestamp=timestamp,
            event_data=dict(event_data or {}),
            trace_id=trace_id,
            expires_at=timestamp + expires_in_seconds * 1000,
        )

    @classmethod
    def from_json(cls, payload: str | bytes) -> "Event":
        """Deserialize an Event instance from its JSON transport representation."""
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        if not isinstance(payload, str):
            raise EventFormatError("event payload must be a JSON string.")
        try:
            value = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise EventFormatError(f"event payload is not valid JSON: {payload!r}") from exc
        if not isinstance(value, dict):
            raise EventFormatError("event payload must deserialize to a dictionary.")
        return cls.from_envelope(value)

    @classmethod
    def from_envelope(cls, fields: dict[str, Any]) -> "Event":
        """Deserialize a transport envelope, including its optional expiration.

        Legacy envelopes without ``expires_at`` remain valid and do not expire
        automatically.

        Args:
            fields: Canonical or legacy event-envelope fields.

        Returns:
            The corresponding Event instance.

        Raises:
            EventFormatError: If a required field or its value is invalid.
        """
        if not isinstance(fields, dict):
            raise EventFormatError("envelope must be a dictionary.")

        # accept either legacy wire keys or canonical names
        event_id = fields.get("event_id") if "event_id" in fields else fields.get("id")
        if event_id is None:
            raise EventFormatError("missing required field: event_id/id")

        event_type = fields.get("event_type") if "event_type" in fields else fields.get("type")
        if event_type is None:
            raise EventFormatError("missing required field: event_type/type")

        source = fields.get("source")
        if source is None:
            raise EventFormatError("missing required field: source")

        ts_value = fields.get("timestamp") if "timestamp" in fields else fields.get("ts")
        if ts_value is None:
            raise EventFormatError("missing required field: timestamp/ts")

        try:
            ts = int(ts_value)
        except (TypeError, ValueError) as exc:
            raise EventFormatError(f"timestamp must be an integer millisecond timestamp: {ts_value!r}") from exc

        raw_data = fields.get("event_data") if "event_data" in fields else fields.get("data")
        if raw_data is None:
            raise EventFormatError("missing required field: event_data/data")

        payload = cls._parse_data(raw_data)
        trace_id = fields.get("trace_id")
        if trace_id is not None and not isinstance(trace_id, str):
            raise EventFormatError("trace_id must be a string when present.")
        raw_expires_at = fields.get("expires_at")
        if isinstance(raw_expires_at, bool) or (
            raw_expires_at is not None
            and not isinstance(raw_expires_at, (str, int))
        ):
            raise EventFormatError(
                f"expires_at must be a millisecond Unix timestamp: {raw_expires_at!r}"
            )
        try:
            expires_at = (
                int(raw_expires_at) if raw_expires_at is not None else None
            )
        except (TypeError, ValueError) as exc:
            raise EventFormatError(
                f"expires_at must be a millisecond Unix timestamp: {raw_expires_at!r}"
            ) from exc

        # construct with canonical field names
        return cls(
            event_id=str(event_id),
            event_type=str(event_type),
            source=str(source),
            timestamp=ts,
            event_data=payload,
            trace_id=trace_id,
            expires_at=expires_at,
        )

    def to_envelope(self, *, wire_legacy: bool = False) -> dict[str, str]:
        """Serialize to an envelope dict.

        By default produces canonical keys (event_id/event_type/timestamp/event_data).
        If wire_legacy=True it will produce legacy transport keys (id/type/ts/data) to
        remain compatible with existing systems. ``expires_at`` is included when set.
        """
        if wire_legacy:
            envelope: dict[str, str] = {
                "id": self.event_id,
                "type": self.event_type,
                "source": self.source,
                "ts": str(self.timestamp),
                "data": json.dumps(self.event_data, separators=(",", ":"), ensure_ascii=False),
            }
            if self.trace_id:
                envelope["trace_id"] = self.trace_id
            if self.expires_at is not None:
                envelope["expires_at"] = str(self.expires_at)
            return envelope

        envelope: dict[str, str] = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source": self.source,
            "timestamp": str(self.timestamp),
            "event_data": json.dumps(self.event_data, separators=(",", ":"), ensure_ascii=False),
        }
        if self.trace_id:
            envelope["trace_id"] = self.trace_id
        if self.expires_at is not None:
            envelope["expires_at"] = str(self.expires_at)
        return envelope

    def to_json(self, *, wire_legacy: bool = False) -> str:
        """Serialize the event to JSON, preserving its expiry timestamp."""
        if wire_legacy:
            payload = {
                "id": self.event_id,
                "type": self.event_type,
                "source": self.source,
                "ts": self.timestamp,
                "data": self.event_data,
                "trace_id": self.trace_id,
                "expires_at": self.expires_at,
            }
        else:
            payload = {
                "event_id": self.event_id,
                "event_type": self.event_type,
                "source": self.source,
                "timestamp": self.timestamp,
                "event_data": self.event_data,
                "trace_id": self.trace_id,
                "expires_at": self.expires_at,
            }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def get_data(self, key: str, default: Any = None) -> Any:
        return self.event_data.get(key, default)

    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp / 1000, tz=timezone.utc)

    @property
    def domain(self) -> str:
        return self.event_type.split(".", 1)[0]

    @property
    def action(self) -> str:
        return self.event_type.rsplit(".", 1)[-1]

    def __repr__(self) -> str:
        return f"Event(event_type={self.event_type!r}, event_id={self.event_id[:8]}, timestamp={self.timestamp})"


__all__ = ["Event", "EventMeta", "EventFormatError"]
