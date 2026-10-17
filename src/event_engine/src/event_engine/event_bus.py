"""Redis-compatible Pub/Sub and List queue event transports."""

from collections import defaultdict
from collections.abc import Callable, Iterator, Mapping
from datetime import date
import logging
import threading
from typing import Protocol

from .event import Event


logger = logging.getLogger(__name__)


class EventBus(Protocol):
    """Transport contract used by producers and consumers of Hermes events."""

    def publish(self, event: Event) -> None:
        """Publish an event to the notification channel."""

    def xadd(
        self,
        stream_name: str,
        fields: Mapping[str, str | bytes | int | float],
    ) -> str | bytes:
        """Append fields to a named stream and return the generated entry ID."""

    def enqueue(self, queue_name: str, event: Event) -> None:
        """Append a durable task event to a named queue."""

    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Event], None],
    ) -> None:
        """Register a local notification handler."""


class EventRecordStore(Protocol):
    """
    Idempotency and fallback-query storage for generated market events.
    """

    def record_once(
        self,
        market: str,
        trading_date: date,
        event: Event,
    ) -> bool:
        """Store an event once and return whether this invocation recorded it."""

    def events_for(
        self,
        market: str,
        trading_date: date,
    ) -> list[Event]:
        """Return all generated events for a market on a calendar date."""


class RedisClient(Protocol):
    """The minimal Redis API needed by Hermes event infrastructure."""

    def publish(self, channel: str, message: str) -> int:
        """Publish text to a Redis Pub/Sub channel."""

    def lpush(self, key: str, value: str) -> int:
        """Push a durable message onto a Redis List."""

    def xadd(
        self,
        name: str,
        fields: Mapping[str, str | bytes | int | float],
    ) -> str | bytes:
        """Append fields to a Redis Stream and return the generated entry ID."""

    def rpush(self, key: str, value: str) -> int:
        """Append a serialized event to a Redis List."""

    def lrange(self, key: str, start: int, end: int) -> list[str | bytes]:
        """Read a range of serialized list values."""

    def set(
        self,
        key: str,
        value: str,
        *,
        nx: bool,
        ex: int,
    ) -> bool | None:
        """Conditionally set a value with a TTL."""

    def expire(self, key: str, time: int) -> bool:
        """Set a key expiration time in seconds."""

    def pubsub(self) -> "RedisPubSub":
        """Create a Redis Pub/Sub consumer."""


class RedisPubSub(Protocol):
    """The Redis Pub/Sub listener operations used by ``RedisEventBus``."""

    def subscribe(self, *channels: str) -> None:
        """Subscribe to one or more channels."""

    def listen(self) -> Iterator[Mapping[str, object]]:
        """Yield transport messages until the listener is closed."""

    def close(self) -> None:
        """Close the Pub/Sub listener."""


class InMemoryEventBus:
    """Synchronous event bus for tests and single-process development."""

    def __init__(self) -> None:
        """Initialize empty notification handlers and durable queues."""
        self.published_events: list[Event] = []
        self.queues: dict[str, list[Event]] = defaultdict(list)
        self.streams: dict[
            str, list[tuple[str, dict[str, str | bytes | int | float]]]
        ] = defaultdict(list)
        self._handlers: dict[str, list[Callable[[Event], None]]] = defaultdict(list)

    def publish(self, event: Event) -> None:
        """Publish an event and synchronously notify registered local handlers."""
        self.published_events.append(event)
        for handler in self._handlers[event.event_type]:
            handler(event)

    def enqueue(self, queue_name: str, event: Event) -> None:
        """Append an event to an in-memory durable-task queue."""
        self.queues[_queue_key(queue_name)].append(event)

    def xadd(
        self,
        stream_name: str,
        fields: Mapping[str, str | bytes | int | float],
    ) -> str:
        """Append fields to an in-memory stream and return a synthetic entry ID."""
        entries = self.streams[stream_name]
        entry_id = f"{len(entries) + 1}-0"
        entries.append((entry_id, dict(fields)))
        return entry_id

    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Event], None],
    ) -> None:
        """Register a local handler for one exact event type."""
        Event.validate_event_type(event_type)
        self._handlers[event_type].append(handler)


class RedisEventBus:
    """Redis transport implementing notification and durable-task event flows."""

    def __init__(self, redis_client: RedisClient) -> None:
        """Initialize the bus with an already-configured Redis client."""
        self._redis = redis_client
        self._handlers: dict[str, list[Callable[[Event], None]]] = defaultdict(list)
        self._listener_thread: threading.Thread | None = None
        self._listener_stop = threading.Event()
        self._pubsub: RedisPubSub | None = None

    def publish(self, event: Event) -> None:
        """Publish a notification on ``event:<event_type>``."""
        self._redis.publish(f"event:{event.event_type}", event.to_json())

    def xadd(
        self,
        stream_name: str,
        fields: Mapping[str, str | bytes | int | float],
    ) -> str | bytes:
        """Append fields to a Redis Stream and return the generated entry ID."""
        return self._redis.xadd(stream_name, fields)

    def enqueue(self, queue_name: str, event: Event) -> None:
        """Persist a task event in ``queue:<queue_name>``."""
        self._redis.lpush(_queue_key(queue_name), event.to_json())

    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Event], None],
    ) -> None:
        """Register a handler for use by the Redis listener integration."""
        Event.validate_event_type(event_type)
        self._handlers[event_type].append(handler)
        # If we are already listening on Redis, keep the subscription up-to-date.
        # Otherwise, start the background listener immediately so a newly registered
        # consumer does not miss messages that arrive before the app explicitly calls
        # start_listener().
        if self._listener_thread is None or not self._listener_thread.is_alive():
            try:
                self.start_listener()
            except RuntimeError:
                # No handlers were registered before this call because we just added one,
                # so this should not happen. Keep it resilient for defensive usage.
                pass

    def dispatch(self, serialized_event: str | bytes) -> None:
        """Dispatch one Redis-delivered event to local registered handlers."""
        event = Event.from_json(serialized_event)
        for handler in self._handlers[event.event_type]:
            try:
                handler(event)
            except Exception:
                logger.exception(
                    "Event handler failed for event_type=%s trace_id=%s",
                    event.event_type,
                    event.trace_id,
                )

    def start_listener(self) -> None:
        """Start a daemon listener for the event types registered locally."""
        if self._listener_thread is not None and self._listener_thread.is_alive():
            return
        if not self._handlers:
            raise RuntimeError("No event handlers are registered.")

        channels = [f"event:{event_type}" for event_type in self._handlers]
        self._listener_stop.clear()
        self._pubsub = self._redis.pubsub()
        self._pubsub.subscribe(*channels)
        self._listener_thread = threading.Thread(
            target=self._listen,
            name="hermes-redis-event-listener",
            daemon=True,
        )
        self._listener_thread.start()

    def stop_listener(self) -> None:
        """Stop the Redis listener without blocking application shutdown."""
        self._listener_stop.set()
        if self._pubsub is not None:
            self._pubsub.close()
            self._pubsub = None
        if self._listener_thread is not None:
            self._listener_thread.join(timeout=1)
            self._listener_thread = None

    def _listen(self) -> None:
        """Consume Redis message events until the listener is stopped."""
        if self._pubsub is None:
            return
        try:
            for message in self._pubsub.listen():
                if self._listener_stop.is_set():
                    return
                if message.get("type") != "message":
                    continue
                payload = message.get("data")
                if not isinstance(payload, (str, bytes)):
                    logger.warning("Ignored Redis event with non-text payload.")
                    continue
                self.dispatch(payload)
        except Exception:
            if not self._listener_stop.is_set():
                logger.exception("Redis event listener stopped unexpectedly.")


class InMemoryEventRecordStore:
    """Natural-day deduplication store with fallback event lookup."""

    def __init__(self) -> None:
        """Initialize empty deduplication and event-history collections."""
        self._events: dict[tuple[str, date], list[Event]] = defaultdict(list)
        self._keys: set[tuple[str, date, str]] = set()

    def record_once(
        self,
        market: str,
        trading_date: date,
        event: Event,
    ) -> bool:
        """Record a market event exactly once for its natural calendar day."""
        key = (market, trading_date, event.event_type)
        if key in self._keys:
            return False
        self._keys.add(key)
        self._events[(market, trading_date)].append(event)
        return True

    def events_for(
        self,
        market: str,
        trading_date: date,
    ) -> list[Event]:
        """Return a copy of market events recorded for the requested date."""
        return list(self._events[(market, trading_date)])


class RedisEventRecordStore:
    """Redis-backed natural-day idempotency and fallback event history."""

    _TTL_SECONDS = 7 * 24 * 60 * 60

    def __init__(self, redis_client: RedisClient) -> None:
        """Initialize the Redis-backed event record store."""
        self._redis = redis_client

    def record_once(
        self,
        market: str,
        trading_date: date,
        event: Event,
    ) -> bool:
        """Store one event only when it was not emitted earlier that day."""
        deduplication_key = (
            f"market-event:dedup:{market}:{trading_date.isoformat()}:"
            f"{event.event_type}"
        )
        if not self._redis.set(
            deduplication_key,
            event.trace_id,
            nx=True,
            ex=self._TTL_SECONDS,
        ):
            return False

        history_key = _history_key(market, trading_date)
        self._redis.rpush(history_key, event.to_json())
        self._redis.expire(history_key, self._TTL_SECONDS)
        return True

    def events_for(
        self,
        market: str,
        trading_date: date,
    ) -> list[Event]:
        """Read retained events to let restarted modules compensate for Pub/Sub."""
        return [
            Event.from_json(serialized_event)
            for serialized_event in self._redis.lrange(
                _history_key(market, trading_date),
                0,
                -1,
            )
        ]


def _queue_key(queue_name: str) -> str:
    """Return a validated Redis task queue key."""
    if not isinstance(queue_name, str) or not queue_name.strip():
        raise ValueError("queue_name must be a non-empty string.")
    return f"queue:{queue_name.strip()}"


def _history_key(market: str, trading_date: date) -> str:
    """Build the history key used for a market's calendar date."""
    return f"market-event:history:{market}:{trading_date.isoformat()}"
