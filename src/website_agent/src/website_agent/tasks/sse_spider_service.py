"""SSE spider service

Fetches SSE listings periodically and publishes events to a Redis-backed EventBus.
This module is written to be importable and runnable as a simple service entrypoint.

Configuration via environment variables:
- SSE_FETCH_INTERVAL_SECONDS (default 3600)
- REDIS_URL (default redis://redis:6379/0)
- REDIS_STREAM_NAME (default market:listings:sse)

The service uses the existing SseSiteClient to fetch records and publishes each
record as an Event onto RedisEventBus.xadd (stream) and also publishes Pub/Sub
notifications via publish for consumers.
"""
from __future__ import annotations

import os
import time
import json
import logging
from typing import Iterable

from website_agent.website.site_sse_module import SseSiteClient
from event_engine.event import Event
from event_engine.event_bus import RedisEventBus

# Lazy import redis to avoid hard requirement during unit tests
try:
    import redis
except Exception:  # pragma: no cover - runtime dependency
    redis = None

logger = logging.getLogger("sse_spider_service")

SSE_LIST_URL = os.environ.get("SSE_LIST_URL", "https://query.sse.com.cn/sseQuery/commonQuery.do")
FETCH_INTERVAL = int(os.environ.get("SSE_FETCH_INTERVAL_SECONDS", "3600"))
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
REDIS_STREAM = os.environ.get("REDIS_STREAM_NAME", "market:listings:sse")


class RedisClientWrapper:
    """Minimal redis client adapter matching RedisClient protocol used by RedisEventBus."""

    def __init__(self, url: str):
        if redis is None:
            raise RuntimeError("redis package is required for RedisEventBus. Install redis-py.")
        self._client = redis.from_url(url, decode_responses=False)

    def publish(self, channel: str, message: str) -> int:
        return self._client.publish(channel, message)

    def lpush(self, key: str, value: str) -> int:
        return self._client.lpush(key, value)

    def xadd(self, name: str, fields):
        # redis-py's xadd accepts mapping of bytes/str
        return self._client.xadd(name, fields)

    def rpush(self, key: str, value: str) -> int:
        return self._client.rpush(key, value)

    def lrange(self, key: str, start: int, end: int):
        return self._client.lrange(key, start, end)

    def set(self, key: str, value: str, *, nx: bool, ex: int):
        return self._client.set(key, value, nx=nx, ex=ex)

    def expire(self, key: str, time: int) -> bool:
        return self._client.expire(key, time)

    def pubsub(self):
        return self._client.pubsub()


def records_to_events(records: Iterable[dict]) -> Iterable[Event]:
    for r in records:
        code = r.get("code")
        name = r.get("name")
        meta = {k: v for k, v in r.items() if k not in ("code", "name")}
        ev = Event.create("market.listing.sse", source="sse_spider", event_data={"code": code, "name": name, "meta": meta})
        yield ev


def publish_records_to_redis(records: Iterable[dict], redis_client_url: str, stream_name: str) -> int:
    client = RedisClientWrapper(redis_client_url)
    bus = RedisEventBus(client)
    count = 0
    for ev in records_to_events(records):
        # Publish pubsub notification
        try:
            bus.publish(ev)
        except Exception:
            logger.exception("Failed to publish pubsub for event %s", ev.event_id)
        # Append to stream for durable consumers
        try:
            fields = {
                "event_id": ev.event_id,
                "event_type": ev.event_type,
                "source": ev.source,
                "timestamp": str(ev.timestamp),
                "event_data": json.dumps(ev.event_data, ensure_ascii=False),
            }
            client.xadd(stream_name, fields)
        except Exception:
            logger.exception("Failed to xadd event %s to stream %s", ev.event_id, stream_name)
        count += 1
    return count


def run_once_and_publish() -> int:
    client = SseSiteClient()
    records = client.fetch_stock_list(SSE_LIST_URL)
    logger.info("Fetched %d records from SSE", len(records))
    published = publish_records_to_redis(records, REDIS_URL, REDIS_STREAM)
    logger.info("Published %d records to Redis", published)
    return published


def main_loop():
    logger.info("Starting SSE spider service. Redis=%s stream=%s interval=%s", REDIS_URL, REDIS_STREAM, FETCH_INTERVAL)
    while True:
        try:
            run_once_and_publish()
        except Exception:
            logger.exception("SSE spider run failed")
        time.sleep(FETCH_INTERVAL)


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    main_loop()
