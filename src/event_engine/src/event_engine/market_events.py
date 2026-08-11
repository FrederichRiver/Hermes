"""Calendar-aware market event generation and natural-day idempotency."""

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Protocol
from zoneinfo import ZoneInfo

from .event_bus import EventBus, EventRecordStore
from .quant_event import QuantEvent


class TradingCalendar(Protocol):
    """The calendar interface required by ``MarketEventGenerator``."""

    def is_trading_day(self, market: str, dt: date) -> bool:
        """Return whether a date is tradable for a market."""


class CronScheduler(Protocol):
    """The minimal APScheduler API used to register market clock jobs."""

    def add_job(
        self,
        func: object,
        *,
        trigger: str,
        day_of_week: str,
        hour: int,
        minute: int,
        id: str,
        name: str,
        replace_existing: bool,
        coalesce: bool,
        max_instances: int,
    ) -> object:
        """Register a cron job."""


@dataclass(frozen=True, slots=True)
class MarketEventSchedule:
    """The required execution time and trading-day behavior for an event."""

    event_type: str
    scheduled_time: time
    friday_only: bool = False


CN_MARKET_EVENT_SCHEDULE = (
    MarketEventSchedule("market.pre_open", time(9, 15)),
    MarketEventSchedule("market.open", time(9, 30)),
    MarketEventSchedule("market.midday_close", time(11, 30)),
    MarketEventSchedule("market.midday_open", time(13, 0)),
    MarketEventSchedule("market.close", time(15, 0)),
    MarketEventSchedule("market.after_hours", time(15, 5)),
    MarketEventSchedule("system.nightly_batch_start", time(18, 0)),
    MarketEventSchedule("system.weekly_report", time(20, 0), friday_only=True),
)


class MarketEventGenerator:
    """Generate required market events through an event bus.

    The generator is intentionally independent of APScheduler and Redis
    implementations. A scheduler invokes ``emit_due_events`` while injected
    bus and record-store implementations provide production Redis behavior or
    deterministic test behavior.
    """

    def __init__(
        self,
        event_bus: EventBus,
        event_store: EventRecordStore,
        trading_calendar: TradingCalendar,
        *,
        market: str = "CN",
        calendar_market: str = "china",
        timezone_name: str = "Asia/Shanghai",
        source: str = "market_event_generator",
    ) -> None:
        """Initialize a market event generator for one market timezone."""
        if not isinstance(market, str) or not market:
            raise ValueError("market must be a non-empty string.")
        if not isinstance(calendar_market, str) or not calendar_market:
            raise ValueError("calendar_market must be a non-empty string.")
        if not isinstance(source, str) or not source:
            raise ValueError("source must be a non-empty string.")
        self._event_bus = event_bus
        self._event_store = event_store
        self._trading_calendar = trading_calendar
        self._market = market
        self._calendar_market = calendar_market
        self._timezone = ZoneInfo(timezone_name)
        self._source = source

    def emit_due_events(self, now: datetime | None = None) -> list[QuantEvent]:
        """Generate the calendar events due in the local minute of ``now``.

        Args:
            now: Optional instant to evaluate. Naive values are interpreted in
                the generator's market timezone.

        Returns:
            Newly emitted events. Events emitted earlier on the same natural
            day are omitted by the event store.
        """
        result_now = self._localize(now)
        result_date = result_now.date()
        if not self._trading_calendar.is_trading_day(
            self._calendar_market,
            result_date,
        ):
            return []

        result_events: list[QuantEvent] = []
        for schedule in CN_MARKET_EVENT_SCHEDULE:
            if schedule.scheduled_time != result_now.time().replace(
                second=0,
                microsecond=0,
            ):
                continue
            if schedule.friday_only and result_date.weekday() != 4:
                continue
            result_event = QuantEvent.create(
                schedule.event_type,
                {
                    "market": self._market,
                    "trading_date": result_date.isoformat(),
                    "scheduled_at": result_now.isoformat(),
                },
                self._source,
            )
            if self._event_store.record_once(
                self._market,
                result_date,
                result_event,
            ):
                self._event_bus.publish(result_event)
                result_events.append(result_event)
        return result_events

    def emitted_events(self, trading_date: date | None = None) -> list[QuantEvent]:
        """Return emitted events for today or an explicitly requested local date."""
        result_date = trading_date or datetime.now(self._timezone).date()
        return self._event_store.events_for(self._market, result_date)

    def register_jobs(self, scheduler: CronScheduler) -> None:
        """Register all required market clock events with an APScheduler instance.

        Each scheduled invocation calls ``emit_due_events``. The generator
        itself verifies the local time, trading calendar, and natural-day
        deduplication, so an APScheduler misfire cannot create duplicate events.
        """
        for schedule in CN_MARKET_EVENT_SCHEDULE:
            scheduler.add_job(
                self.emit_due_events,
                trigger="cron",
                day_of_week="fri" if schedule.friday_only else "mon-fri",
                hour=schedule.scheduled_time.hour,
                minute=schedule.scheduled_time.minute,
                id=f"market-event:{self._market}:{schedule.event_type}",
                name=schedule.event_type,
                replace_existing=True,
                coalesce=True,
                max_instances=1,
            )

    def _localize(self, now: datetime | None) -> datetime:
        """Convert an instant to the market timezone."""
        if now is None:
            return datetime.now(self._timezone)
        if now.tzinfo is None:
            return now.replace(tzinfo=self._timezone)
        return now.astimezone(self._timezone)
