#!/opt/application/venv/bin/python3
"""Simple long-running fetcher service that periodically fetches SZSE list
and publishes events to a Redis-backed EventBus.

Usage: python run_fetcher.py --redis redis://redis:6379/0 --interval 3600
"""
import time
import argparse
import os
from urllib.parse import urlparse

import redis
from utils.logging import configure_logging, get_logger
from website_agent.website.site_szse_module import SzseSiteClient
from event_engine.event_engine import EventEngine
from event_engine.event_engine import EventEngine as EE
from event_engine.event_engine import Event
from event_engine.event_engine import EventEngine
from event_engine.event_bus import RedisEventBus, RedisEventRecordStore

logger = get_logger(__name__)


def make_redis_client(redis_url: str):
    parsed = urlparse(redis_url)
    return redis.Redis(
        host=parsed.hostname,
        port=parsed.port or 6379,
        db=int((parsed.path or "/0").lstrip("/")),
        username=os.environ["REDIS_USERNAME"],
        password=os.environ["REDIS_PASSWORD"],
    )


def run_forever(redis_url: str, interval: int):
    r = make_redis_client(redis_url)
    bus = RedisEventBus(r)
    store = RedisEventRecordStore(r)
    engine = EventEngine(bus)

    client = SzseSiteClient()
    while True:
        try:
            logger.info("Starting SZSE fetch...")
            records = client.fetch_and_publish(engine)
            logger.info(f"Fetched {len(records)} records")
        except Exception:
            logger.exception("Fetch failed")
        time.sleep(interval)


if __name__ == "__main__":
    configure_logging()
    ap = argparse.ArgumentParser()
    ap.add_argument("--redis", default="redis://localhost:6379/0")
    ap.add_argument("--interval", type=int, default=3600)
    args = ap.parse_args()
    run_forever(args.redis, args.interval)
