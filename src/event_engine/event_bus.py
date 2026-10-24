"""Redis Stream event transport with legacy Pub/Sub and List compatibility."""

import json
import math
import threading
from collections import defaultdict
from collections.abc import Callable, Iterator, Mapping
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Protocol

from basic_utils.logging import get_logger

from .event import Event
from .event_format_error import EventFormatError


logger = get_logger(__name__)
_STREAM_NAME = "ChannelA"
_DEAD_LETTER_STREAM = f"{_STREAM_NAME}:dead-letter"
_EXPIRATION_STREAMS_KEY = "hermes:event-expiration-streams"
_APPEND_WITH_EXPIRY_SCRIPT = """
local entry_id = redis.call('XADD', KEYS[1], '*', unpack(ARGV, 2))
redis.call('ZADD', KEYS[2], ARGV[1], entry_id)
redis.call('SADD', KEYS[3], KEYS[1])
return entry_id
"""
_DELETE_EXPIRED_SCRIPT = """
local deleted_total = 0
local stream_names = redis.call('SMEMBERS', KEYS[1])
for _, stream_name in ipairs(stream_names) do
    local index_key = stream_name .. ':expiration-index'
    local entry_ids = redis.call(
        'ZRANGEBYSCORE', index_key, '-inf', ARGV[1], 'LIMIT', 0, ARGV[2]
    )
    if #entry_ids > 0 then
        local groups = redis.pcall('XINFO', 'GROUPS', stream_name)
        if type(groups) == 'table' and groups.err == nil then
            for _, group_info in ipairs(groups) do
                local group_name = nil
                for index = 1, #group_info, 2 do
                    if group_info[index] == 'name' then
                        group_name = group_info[index + 1]
                        break
                    end
                end
                if group_name ~= nil then
                    redis.pcall('XACK', stream_name, group_name, unpack(entry_ids))
                end
            end
        end
        deleted_total = deleted_total + redis.call(
            'XDEL', stream_name, unpack(entry_ids)
        )
        redis.call('ZREM', index_key, unpack(entry_ids))
    end
end
return deleted_total
"""
_EXPIRATION_POLL_INTERVAL_SECONDS = 1
_EXPIRATION_BATCH_SIZE = 100

StreamFields = Mapping[str, str | bytes | int | float]
StreamMessageFields = Mapping[str | bytes, str | bytes | int | float]
StreamEntries = list[
    tuple[str | bytes, list[tuple[str | bytes, StreamMessageFields]]]
]


class EventBus(Protocol):
    """Transport contract used by producers and consumers of Hermes events."""

    @property
    def stream_name(self) -> str:
        """Return the Redis Stream used by this module's event bus."""

    def publish(self, event: Event) -> None:
        """不推荐：通过旧式通知通道发布事件，仅为兼容保留。"""

    def publish_stream(self, event: Event) -> str | bytes:
        """Append an event to this event bus's configured Redis Stream."""

    def xadd(
        self,
        stream_name: str,
        fields: StreamFields,
    ) -> str | bytes:
        """Append fields to a named stream and return the generated entry ID."""

    def enqueue(self, queue_name: str, event: Event) -> None:
        """不推荐：通过旧式 Redis List 队列追加任务，仅为兼容保留。"""

    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Event], None],
    ) -> None:
        """不推荐：通过旧式 Pub/Sub 注册处理器，仅为兼容保留。"""


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

    def ping(self) -> bool:
        """Check Redis connectivity."""

    def publish(self, channel: str, message: str) -> int:
        """不推荐：向旧式 Redis Pub/Sub 通道发布文本，仅为兼容保留。"""

    def lpush(self, key: str, value: str) -> int:
        """不推荐：向旧式 Redis List 队列写入消息，仅为兼容保留。"""

    def xadd(
        self,
        name: str,
        fields: StreamFields,
    ) -> str | bytes:
        """Append fields to a Redis Stream and return the generated entry ID."""

    def xgroup_create(
        self,
        name: str,
        groupname: str,
        *,
        id: str,
        mkstream: bool,
    ) -> str | bytes:
        """Create a consumer group for a Redis Stream."""

    def xreadgroup(
        self,
        groupname: str,
        consumername: str,
        streams: Mapping[str, str],
        *,
        count: int | None = None,
        block: int | None = None,
    ) -> StreamEntries | None:
        """Read new or pending entries from a Redis Stream consumer group."""

    def xack(self, name: str, groupname: str, *ids: str | bytes) -> int:
        """Acknowledge processed entries in a Redis Stream consumer group."""

    def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: str | bytes | int | float,
    ) -> object:
        """Execute an atomic Redis Lua script."""

    def rpush(self, key: str, value: str) -> int:
        """不推荐：向旧式 Redis List 队列追加事件，仅为兼容保留。"""

    def lrange(self, key: str, start: int, end: int) -> list[str | bytes]:
        """不推荐：读取旧式 Redis List 队列，仅为兼容保留。"""

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
        """不推荐：创建旧式 Redis Pub/Sub 消费者，仅为兼容保留。"""

    def close(self) -> None:
        """Close the Redis client."""


class RedisPubSub(Protocol):
    """不推荐：旧式 Redis Pub/Sub 监听接口，仅为兼容保留。"""

    def subscribe(self, *channels: str) -> None:
        """不推荐：订阅旧式 Redis Pub/Sub 通道，仅为兼容保留。"""

    def listen(self) -> Iterator[Mapping[str, object]]:
        """Yield transport messages until the listener is closed."""

    def close(self) -> None:
        """Close the Pub/Sub listener."""


class InMemoryEventBus:
    """Synchronous event bus for tests and single-process development."""

    def __init__(self, *, stream_name: str = _STREAM_NAME) -> None:
        """Initialize in-memory event storage for a named module Stream.

        Args:
            stream_name: Stream name used by ``publish_stream``.
        """
        self.stream_name = _validate_stream_name(stream_name)
        self.published_events: list[Event] = []
        self.queues: dict[str, list[Event]] = defaultdict(list)
        self.streams: dict[
            str, list[tuple[str, dict[str, str | bytes | int | float]]]
        ] = defaultdict(list)
        self._stream_counters: dict[str, int] = defaultdict(int)
        self._handlers: dict[str, list[Callable[[Event], None]]] = defaultdict(list)
        self._expiration_stop = threading.Event()
        self._expiration_lock = threading.RLock()
        self._expiration_thread: threading.Thread | None = None

    def publish(self, event: Event) -> None:
        """不推荐：同步执行本地通知处理器，仅为旧代码兼容保留。"""
        self.published_events.append(event)
        for handler in self._handlers[event.event_type]:
            handler(event)

    def enqueue(self, queue_name: str, event: Event) -> None:
        """不推荐：追加到旧式内存任务队列，仅为兼容保留。"""
        self.queues[_queue_key(queue_name)].append(event)

    def xadd(
        self,
        stream_name: str,
        fields: StreamFields,
    ) -> str:
        """Append fields to an in-memory stream and return a synthetic entry ID."""
        stream_name = _validate_stream_name(stream_name)
        has_expiration = _expiration_timestamp(fields) is not None
        with self._expiration_lock:
            entries = self.streams[stream_name]
            self._stream_counters[stream_name] += 1
            entry_id = f"{self._stream_counters[stream_name]}-0"
            entries.append((entry_id, dict(fields)))
        if has_expiration:
            self._ensure_expiration_worker()
        return entry_id

    def publish_stream(self, event: Event) -> str:
        """Append an event to this module's in-memory Stream."""
        return self.xadd(self.stream_name, event.to_envelope())

    def close(self) -> None:
        """Stop the in-memory expiration cleaner."""
        self._expiration_stop.set()
        if self._expiration_thread is not None:
            self._expiration_thread.join(timeout=2)
            self._expiration_thread = None

    def _ensure_expiration_worker(self) -> None:
        with self._expiration_lock:
            if (
                self._expiration_thread is not None
                and self._expiration_thread.is_alive()
            ):
                return
            self._expiration_stop.clear()
            self._expiration_thread = threading.Thread(
                target=self._clean_expired_entries,
                name=f"hermes-memory-expiry-{self.stream_name}",
                daemon=True,
            )
            self._expiration_thread.start()

    def _clean_expired_entries(self) -> None:
        while not self._expiration_stop.wait(_EXPIRATION_POLL_INTERVAL_SECONDS):
            now_ms = _now_ms()
            with self._expiration_lock:
                for stream_name, entries in self.streams.items():
                    self.streams[stream_name] = [
                        (entry_id, fields)
                        for entry_id, fields in entries
                        if (
                            (expires_at := _expiration_timestamp(fields)) is None
                            or expires_at > now_ms
                        )
                    ]

    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Event], None],
    ) -> None:
        """不推荐：注册旧式本地通知处理器，仅为兼容保留。"""
        Event.validate_event_type(event_type)
        self._handlers[event_type].append(handler)


class RedisEventBus:
    """Redis Stream event bus with a JSON-backed module registration table."""

    STREAM_NAME = _STREAM_NAME
    DEAD_LETTER_STREAM = _DEAD_LETTER_STREAM
    _READ_BATCH_SIZE = 100
    _READ_BLOCK_MILLISECONDS = 1000

    def __init__(
        self,
        redis_client: RedisClient,
        *,
        stream_name: str = _STREAM_NAME,
        consumer_group: str | None = None,
        registration_file: str | Path | None = None,
        poll_interval: float = 60,
    ) -> None:
        """Initialize a Redis event bus and its optional Stream consumer settings.

        Args:
            redis_client: Configured Redis client owned by this bus.
            stream_name: Redis Stream used by this module's event bus.
            consumer_group: Module-specific consumer group. Required by ``start()``.
            registration_file: UTF-8 JSON mapping event types to handler keys.
            poll_interval: Registration-file polling interval in seconds.

        Raises:
            ValueError: If the consumer group or polling interval is invalid.
        """
        if consumer_group is not None and (
            not isinstance(consumer_group, str) or not consumer_group.strip()
        ):
            raise ValueError("consumer_group must be a non-empty string.")
        if isinstance(poll_interval, bool) or not isinstance(
            poll_interval,
            (int, float),
        ):
            raise ValueError("poll_interval must be a positive number of seconds.")
        if not math.isfinite(poll_interval) or poll_interval <= 0:
            raise ValueError("poll_interval must be a positive number of seconds.")

        self.stream_name = _validate_stream_name(stream_name)
        self.dead_letter_stream = f"{self.stream_name}:dead-letter"
        self.STREAM_NAME = self.stream_name
        self.DEAD_LETTER_STREAM = self.dead_letter_stream
        self._redis = redis_client
        self._consumer_group = consumer_group
        self._registration_file = (
            Path(registration_file) if registration_file is not None else None
        )
        self._poll_interval = float(poll_interval)
        self._handlers: dict[str, list[Callable[[Event], None]]] = defaultdict(list)
        self._declared_handlers: dict[str, Callable[[Event], None]] = {}
        self._registry: dict[str, str] = {}
        self._registry_lock = threading.RLock()
        self._listener_thread: threading.Thread | None = None
        self._listener_stop = threading.Event()
        self._pubsub: RedisPubSub | None = None
        self._stream_thread: threading.Thread | None = None
        self._registry_thread: threading.Thread | None = None
        self._stream_stop = threading.Event()
        self._expiration_stop = threading.Event()
        self._expiration_lock = threading.Lock()
        self._expiration_thread: threading.Thread | None = None

    def ping(self) -> bool:
        """Check connectivity through the underlying Redis client."""
        connected = self._redis.ping()
        self._ensure_expiration_worker()
        return connected

    def close(self) -> None:
        """Stop all bus workers and close the underlying Redis client."""
        try:
            self.stop()
        finally:
            self._expiration_stop.set()
            if self._expiration_thread is not None:
                self._expiration_thread.join(timeout=2)
                if self._expiration_thread.is_alive():
                    logger.error(
                        f"Event bus expiration worker for {self.stream_name!r} "
                        "did not stop in time."
                    )
            self._redis.close()

    def publish(self, event: Event) -> None:
        """不推荐：通过 Redis Pub/Sub 发布事件，仅为旧代码兼容保留。"""
        self._redis.publish(f"event:{event.event_type}", event.to_json())

    def publish_stream(self, event: Event) -> str | bytes:
        """Append an event envelope to this module's configured Stream."""
        return self.xadd(self.stream_name, event.to_envelope())

    def xadd(
        self,
        stream_name: str,
        fields: StreamFields,
    ) -> str | bytes:
        """Append fields to a Redis Stream and return the generated entry ID.

        Events containing ``expires_at`` are atomically indexed for expiration
        cleanup along with the Stream append.
        """
        stream_name = _validate_stream_name(stream_name)
        expires_at = _expiration_timestamp(fields)
        if expires_at is None:
            return self._redis.xadd(stream_name, fields)

        self._ensure_expiration_worker()
        script_args: list[str | bytes | int | float] = [str(expires_at)]
        for field_name, value in fields.items():
            script_args.extend((field_name, value))
        entry_id = self._redis.eval(
            _APPEND_WITH_EXPIRY_SCRIPT,
            3,
            stream_name,
            _expiration_index_key(stream_name),
            _EXPIRATION_STREAMS_KEY,
            *script_args,
        )
        if not isinstance(entry_id, (str, bytes)):
            raise RuntimeError(
                "Redis returned an invalid Stream entry ID after atomic append."
            )
        return entry_id

    def enqueue(self, queue_name: str, event: Event) -> None:
        """不推荐：通过 Redis List 持久化任务，仅为旧代码兼容保留。"""
        self._redis.lpush(_queue_key(queue_name), event.to_json())

    def register_handler(
        self,
        handler_key: str,
        handler: Callable[[Event], None],
    ) -> None:
        """Declare a callable that a JSON event registration may reference.

        Args:
            handler_key: Stable key referenced by the registration JSON.
            handler: Function called for matching events.

        Raises:
            TypeError: If the handler is not callable.
            ValueError: If the key is empty or already registered.
        """
        if not isinstance(handler_key, str) or not handler_key.strip():
            raise ValueError("handler_key must be a non-empty string.")
        if not callable(handler):
            raise TypeError("handler must be callable.")
        with self._registry_lock:
            if handler_key in self._declared_handlers:
                raise ValueError(f"Handler key {handler_key!r} is already registered.")
            self._declared_handlers[handler_key] = handler

    def start(self) -> None:
        """Start the Stream consumer and periodic JSON registration reload.

        Raises:
            RuntimeError: If the consumer group or registration file is missing.
        """
        if not self._consumer_group:
            raise RuntimeError("consumer_group must be set before starting the bus.")
        if self._registration_file is None:
            raise RuntimeError("registration_file must be set before starting the bus.")
        self._ensure_expiration_worker()
        if (
            self._stream_thread is not None
            and self._stream_thread.is_alive()
        ):
            return

        self._reload_registry()
        try:
            self._redis.xgroup_create(
                self.stream_name,
                self._consumer_group,
                id="0",
                mkstream=True,
            )
        except Exception as error:
            if "BUSYGROUP" not in str(error):
                raise
            logger.debug(
                f"Redis consumer group {self._consumer_group!r} already exists."
            )

        self._stream_stop.clear()
        self._registry_thread = threading.Thread(
            target=self._poll_registry,
            name=f"hermes-registry-{self._consumer_group}",
            daemon=True,
        )
        self._stream_thread = threading.Thread(
            target=self._consume_stream,
            name=f"hermes-stream-{self._consumer_group}",
            daemon=True,
        )
        started_threads: list[threading.Thread] = []
        try:
            for thread in (self._registry_thread, self._stream_thread):
                thread.start()
                started_threads.append(thread)
        except Exception:
            self._stream_stop.set()
            for thread in started_threads:
                thread.join(timeout=2)
            self._stream_thread = None
            self._registry_thread = None
            raise

    def stop(self) -> None:
        """Stop the Stream consumer, registry poller, and legacy listener."""
        self._stream_stop.set()
        current_thread = threading.current_thread()
        for thread in (self._stream_thread, self._registry_thread):
            if thread is not None and thread is not current_thread:
                thread.join(timeout=2)
                if thread.is_alive():
                    logger.error(
                        f"Event bus worker {thread.name!r} did not stop in time."
                    )
        if self._stream_thread is not None and not self._stream_thread.is_alive():
            self._stream_thread = None
        if (
            self._registry_thread is not None
            and not self._registry_thread.is_alive()
        ):
            self._registry_thread = None
        self.stop_listener()

    def _ensure_expiration_worker(self) -> None:
        with self._expiration_lock:
            if (
                self._expiration_thread is not None
                and self._expiration_thread.is_alive()
            ):
                return
            self._expiration_stop.clear()
            self._expiration_thread = threading.Thread(
                target=self._clean_expired_entries,
                name=f"hermes-expiry-{self.stream_name}",
                daemon=True,
            )
            self._expiration_thread.start()

    def _clean_expired_entries(self) -> None:
        while not self._expiration_stop.wait(
            _EXPIRATION_POLL_INTERVAL_SECONDS
        ):
            try:
                deleted_total = 0
                while not self._expiration_stop.is_set():
                    deleted = self._redis.eval(
                        _DELETE_EXPIRED_SCRIPT,
                        1,
                        _EXPIRATION_STREAMS_KEY,
                        _now_ms(),
                        _EXPIRATION_BATCH_SIZE,
                    )
                    if not isinstance(deleted, int):
                        raise RuntimeError(
                            "Redis returned an invalid expired-entry count."
                        )
                    deleted_total += deleted
                    if deleted < _EXPIRATION_BATCH_SIZE:
                        break
                if deleted_total > 0:
                    logger.debug(
                        f"Deleted {deleted_total} expired event(s) from "
                        "registered event streams."
                    )
            except Exception:
                if not self._expiration_stop.is_set():
                    logger.exception(
                        f"Failed to delete expired events from "
                        f"Stream {self.stream_name!r}; retrying."
                    )

    def _reload_registry(self) -> None:
        """Replace the in-memory event map after successfully validating JSON."""
        if self._registration_file is None:
            return
        try:
            registration_data = json.loads(
                self._registration_file.read_text(encoding="utf-8")
            )
            if not isinstance(registration_data, dict):
                raise ValueError("Event registration JSON must be an object.")

            registry: dict[str, str] = {}
            for event_type, handler_key in registration_data.items():
                Event.validate_event_type(event_type)
                if not isinstance(handler_key, str) or not handler_key.strip():
                    raise ValueError(
                        f"Handler key for event {event_type!r} must be a "
                        "non-empty string."
                    )
                registry[event_type] = handler_key
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            logger.exception(
                f"Failed to load event registration file {self._registration_file}."
            )
            return

        with self._registry_lock:
            self._registry = registry

    def _poll_registry(self) -> None:
        """Periodically reload event registrations until the bus stops."""
        while not self._stream_stop.wait(self._poll_interval):
            self._reload_registry()

    def _consume_stream(self) -> None:
        """Read, dispatch, and acknowledge events from this module's group."""
        if self._consumer_group is None:
            return
        while not self._stream_stop.is_set():
            try:
                entries = self._read_group_entries("0")
                entries.extend(self._read_group_entries(">"))

                has_failed_handler = False
                for entry_id, fields in entries:
                    if self._stream_stop.is_set():
                        return
                    if self._dispatch_stream_entry(entry_id, fields):
                        acknowledged = self._redis.xack(
                            self.stream_name,
                            self._consumer_group,
                            entry_id,
                        )
                        if acknowledged == 0:
                            logger.warning(
                                f"Redis did not acknowledge Stream entry {entry_id!r}."
                            )
                    else:
                        has_failed_handler = True

                if has_failed_handler:
                    self._stream_stop.wait(1)
            except Exception:
                if not self._stream_stop.is_set():
                    logger.exception(
                        f"Redis Stream consumer for group "
                        f"{self._consumer_group!r} failed; retrying."
                    )
                    self._stream_stop.wait(1)

    def _read_group_entries(
        self,
        last_id: str,
    ) -> list[tuple[str | bytes, StreamMessageFields]]:
        """Read pending or new entries for this consumer group."""
        if self._consumer_group is None:
            return []
        batches = self._redis.xreadgroup(
            self._consumer_group,
            self._consumer_group,
            {self.stream_name: last_id},
            count=self._READ_BATCH_SIZE,
            block=self._READ_BLOCK_MILLISECONDS if last_id == ">" else None,
        )
        return [
            (entry_id, fields)
            for _, stream_entries in batches or []
            for entry_id, fields in stream_entries
        ]

    def _dispatch_stream_entry(
        self,
        entry_id: str | bytes,
        fields: StreamMessageFields,
    ) -> bool:
        """Dispatch one entry and return whether it may be acknowledged."""
        try:
            event = Event.from_envelope(_decode_stream_fields(fields))
        except (UnicodeDecodeError, TypeError, EventFormatError) as error:
            self._write_dead_letter(entry_id, fields, error)
            logger.error(
                f"Invalid Event in Redis Stream entry {entry_id!r}; "
                f"copied to {self.dead_letter_stream!r}; "
                f"format_error={type(error).__name__}."
            )
            return True

        if event.expires_at is not None and event.expires_at <= _now_ms():
            logger.info(
                f"Skipped expired event {event.event_id!r} from "
                f"Stream {self.stream_name!r}."
            )
            return True

        with self._registry_lock:
            handler_key = self._registry.get(event.event_type)
            handler = (
                self._declared_handlers.get(handler_key)
                if handler_key is not None
                else None
            )

        if handler_key is None:
            return True
        if handler is None:
            logger.error(
                f"No declared handler for key {handler_key!r} registered for "
                f"event_type={event.event_type!r}."
            )
            return True

        try:
            handler(event)
        except Exception:
            logger.exception(
                f"Event handler {handler_key!r} failed for "
                f"event_type={event.event_type!r}; entry remains pending."
            )
            return False
        return True

    def _write_dead_letter(
        self,
        entry_id: str | bytes,
        fields: StreamMessageFields,
        error: Exception,
    ) -> None:
        """Copy an invalid event to the dead-letter stream before acknowledging."""
        dead_letter_fields: dict[str, str | bytes | int | float] = {}
        for field_key, value in fields.items():
            normalized_key = (
                field_key.decode("utf-8", errors="replace")
                if isinstance(field_key, bytes)
                else field_key
            )
            dead_letter_fields[normalized_key] = value
        dead_letter_fields["original_stream_id"] = _decode_stream_value(entry_id)
        dead_letter_fields["error"] = type(error).__name__
        try:
            self._redis.xadd(self.dead_letter_stream, dead_letter_fields)
        except Exception:
            logger.exception(
                f"Failed to copy invalid Stream entry {entry_id!r} to dead-letter."
            )
            raise

    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Event], None],
    ) -> None:
        """不推荐：注册旧式 Redis Pub/Sub 处理器，仅为兼容保留。"""
        Event.validate_event_type(event_type)
        handlers = self._handlers[event_type]
        handlers.append(handler)
        # If we are already listening on Redis, keep the subscription up-to-date.
        # Otherwise, start the background listener immediately so a newly registered
        # consumer does not miss messages that arrive before the app explicitly calls
        # start_listener().
        try:
            if (
                self._listener_thread is not None
                and self._listener_thread.is_alive()
            ):
                if self._pubsub is None:
                    raise RuntimeError(
                        "Redis event listener has no Pub/Sub connection."
                    )
                self._pubsub.subscribe(f"event:{event_type}")
            else:
                self.start_listener()
        except Exception:
            handlers.pop()
            if not handlers:
                del self._handlers[event_type]
            raise

    def dispatch(self, serialized_event: str | bytes) -> None:
        """不推荐：分发旧式 Redis Pub/Sub 事件，仅为兼容保留。"""
        event = Event.from_json(serialized_event)
        if event.expires_at is not None and event.expires_at <= _now_ms():
            logger.info(
                f"Skipped expired event {event.event_id!r} from Pub/Sub."
            )
            return
        for handler in self._handlers[event.event_type]:
            try:
                handler(event)
            except Exception:
                logger.exception(
                    f"Event handler failed for event_type={event.event_type} "
                    f"trace_id={event.trace_id}"
                )

    def start_listener(self) -> None:
        """不推荐：启动旧式 Pub/Sub 监听器，仅为兼容保留。"""
        if self._listener_thread is not None and self._listener_thread.is_alive():
            return
        if not self._handlers:
            raise RuntimeError("No event handlers are registered.")

        channels = [f"event:{event_type}" for event_type in self._handlers]
        self._listener_stop.clear()
        pubsub = self._redis.pubsub()
        try:
            pubsub.subscribe(*channels)
        except Exception:
            try:
                pubsub.close()
            except Exception:
                logger.exception(
                    "Failed to close Redis Pub/Sub after subscribe failure."
                )
            raise

        listener_thread = threading.Thread(
            target=self._listen,
            name="hermes-redis-event-listener",
            daemon=True,
        )
        self._pubsub = pubsub
        self._listener_thread = listener_thread
        try:
            listener_thread.start()
        except Exception:
            self._pubsub = None
            self._listener_thread = None
            try:
                pubsub.close()
            except Exception:
                logger.exception(
                    "Failed to close Redis Pub/Sub after listener startup failure."
                )
            raise

    def stop_listener(self) -> None:
        """不推荐：停止旧式 Pub/Sub 监听器，仅为兼容保留。"""
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
        now_ms = _now_ms()
        return [
            event
            for event in self._events[(market, trading_date)]
            if event.expires_at is None or event.expires_at > now_ms
        ]


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
        now_ms = _now_ms()
        return [
            event
            for serialized_event in self._redis.lrange(
                _history_key(market, trading_date),
                0,
                -1,
            )
            if (
                (event := Event.from_json(serialized_event)).expires_at is None
                or event.expires_at > now_ms
            )
        ]


def _queue_key(queue_name: str) -> str:
    """Return a validated Redis task queue key."""
    if not isinstance(queue_name, str) or not queue_name.strip():
        raise ValueError("queue_name must be a non-empty string.")
    return f"queue:{queue_name.strip()}"


def _validate_stream_name(stream_name: str) -> str:
    """Validate and return a Redis Stream name."""
    if not isinstance(stream_name, str) or not stream_name.strip():
        raise ValueError("stream_name must be a non-empty string.")
    return stream_name.strip()


def _expiration_index_key(stream_name: str) -> str:
    """Build the sorted-set key used to schedule Stream entry expiration."""
    return f"{stream_name}:expiration-index"


def _expiration_timestamp(
    fields: Mapping[str | bytes, str | bytes | int | float],
) -> int | None:
    """Read and validate an optional UTC expiration timestamp from Stream fields."""
    raw_expiration = next(
        (
            value
            for key, value in fields.items()
            if _decode_stream_key(key) == "expires_at"
        ),
        None,
    )
    if raw_expiration is None:
        return None
    try:
        expires_at = int(_decode_stream_value(raw_expiration))
    except (TypeError, ValueError) as error:
        raise ValueError(
            "expires_at must be a valid millisecond Unix timestamp."
        ) from error
    if expires_at <= 0 or expires_at > 10_000_000_000_000:
        raise ValueError("expires_at must be a valid millisecond Unix timestamp.")
    return expires_at


def _now_ms() -> int:
    """Return the current UTC time as a Unix timestamp in milliseconds."""
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _decode_stream_fields(fields: StreamMessageFields) -> dict[str, str]:
    """Decode Redis Stream field names and values to the Event wire format."""
    return {
        _decode_stream_key(key): _decode_stream_value(value)
        for key, value in fields.items()
    }


def _decode_stream_key(value: str | bytes) -> str:
    """Decode one Redis Stream field name."""
    return value.decode("utf-8") if isinstance(value, bytes) else value


def _decode_stream_value(value: str | bytes | int | float) -> str:
    """Decode or stringify one Redis Stream field value."""
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def _history_key(market: str, trading_date: date) -> str:
    """Build the history key used for a market's calendar date."""
    return f"market-event:history:{market}:{trading_date.isoformat()}"
