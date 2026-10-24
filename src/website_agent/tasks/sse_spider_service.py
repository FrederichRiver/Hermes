#!/opt/application/venv/bin/python3
"""SSE spider service

Fetches SSE listings periodically and publishes events to a Redis-backed EventBus.
This module is written to be importable and runnable as a simple service entrypoint.

Configuration via environment variables:
- SSE_FETCH_INTERVAL_SECONDS (default 3600)
- REDIS_URL (default redis://redis:6379/0)
- REDIS_STREAM_NAME (default market:listings:sse)

The service registers SiteSSE with WebsiteAgent, fetches the SSE list in
response to a task, then publishes the completed result to Redis Pub/Sub and a
durable stream.
"""
from __future__ import annotations

import os
import time

from event_service import create_redis_event_bus
from event_engine.event import Event
from basic_utils.logging import configure_logging, get_logger
from website_agent.website.agent import WebsiteAgent
from website_agent.website.site_sse import SiteSSE

logger = get_logger(__name__)

FETCH_INTERVAL = int(os.environ.get("SSE_FETCH_INTERVAL_SECONDS", "3600"))
_DEFAULT_REDIS_URL = "redis://redis:6379/0"
REDIS_STREAM = os.environ.get("REDIS_STREAM_NAME", "market:listings:sse")


def records_to_events(records) -> list[Event]:
    events = []
    for r in records:
        code = r.get("code")
        name = r.get("name")
        meta = {k: v for k, v in r.items() if k not in ("code", "name")}
        ev = Event.create("market.listing.sse", source="sse_spider", event_data={"code": code, "name": name, "meta": meta})
        events.append(ev)
    return events


def publish_records_to_redis(records, redis_client_url: str, stream_name: str) -> int:
    event_bus = create_redis_event_bus(
        redis_client_url,
        stream_name=stream_name,
    )
    count = 0
    try:
        event_bus.ping()
        for ev in records_to_events(records):
            # Publish pubsub notification
            try:
                event_bus.publish(ev)
            except Exception:
                logger.exception(f"Failed to publish pubsub for event {ev.event_id}")
            # Append to stream for durable consumers
            try:
                event_bus.xadd(stream_name, ev.to_envelope())
            except Exception:
                logger.exception(
                    f"Failed to xadd event {ev.event_id} to stream {stream_name}"
                )
            count += 1
    finally:
        event_bus.close()
    return count


def run_once_and_publish() -> int:
    event_bus = create_redis_event_bus(
        default_url=_DEFAULT_REDIS_URL,
        stream_name=REDIS_STREAM,
    )
    published_rows = 0
    agent: WebsiteAgent | None = None

    def publish_event(event: Event) -> None:
        nonlocal published_rows
        event_bus.publish(event)
        event_bus.xadd(
            REDIS_STREAM,
            event.to_envelope(),
        )
        if event.event_type == "data.task.finished":
            published_rows = int(event.event_data.get("rows_count", 0))

    try:
        event_bus.ping()
        agent = WebsiteAgent(publisher=publish_event)
        agent.register(SiteSSE())
        request_event = Event.create(
            "data.fetch.requested",
            "sse_spider",
            {
                "task": {
                    "task_type": "symbol_list",
                    "params": {},
                }
            },
        )
        agent.on_fetch_requested(request_event)
    finally:
        try:
            if agent is not None:
                agent.close()
        finally:
            event_bus.close()

    logger.info(f"Published {published_rows} SSE stock records to Redis")
    return published_rows


def main_loop():
    logger.info(
        f"Starting SSE spider service. stream={REDIS_STREAM} "
        f"interval={FETCH_INTERVAL}"
    )
    while True:
        try:
            run_once_and_publish()
        except Exception:
            logger.exception("SSE spider run failed")
        time.sleep(FETCH_INTERVAL)


if __name__ == "__main__":
    configure_logging()
    main_loop()
