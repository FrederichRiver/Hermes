"""Event-driven persistence orchestration for data-engine tables."""

from collections.abc import Callable, Mapping

from event_engine.event import Event
from event_engine.event_bus import EventBus
from utils.logging import get_logger

from .mysql_meta import MySQLDB
from .stock_tables import StockDailyBarEntity, StockIndexEntity


logger = get_logger(__name__)


class DataAgent:
    """Route data events to database and table operations."""

    STOCK_LIST_EVENT = "data.task.finished"
    STOCK_LIST_REQUEST_EVENT = "data.fetch.requested"
    STOCK_LIST_TASK = "symbol_list"
    STOCK_LIST_SOURCE = "sse"
    STOCK_DATABASE = "stock_data"
    STOCK_INDEX_TABLE = "stock_index"
    HISTORICAL_KLINE_TASK = "historical_kline"
    SINA_SOURCE = "sina"
    STOCK_DAILY_TABLE = "stock_daily"

    def __init__(
        self,
        event_bus: EventBus,
        mysql_dbs: Mapping[str, MySQLDB],
        *,
        stock_db_name: str = STOCK_DATABASE,
    ) -> None:
        if not callable(getattr(event_bus, "subscribe", None)):
            raise TypeError("event_bus must provide subscribe(event_type, handler).")
        if not isinstance(mysql_dbs, Mapping) or not mysql_dbs:
            raise ValueError("mysql_dbs must contain at least one MySQLDB.")
        if stock_db_name not in mysql_dbs:
            raise ValueError(
                f"Stock database {stock_db_name!r} is not present in mysql_dbs."
            )
        if any(not isinstance(database, MySQLDB) for database in mysql_dbs.values()):
            raise TypeError("Every mysql_dbs value must be a MySQLDB instance.")

        self.event_bus = event_bus
        self.mysql_dbs = dict(mysql_dbs)
        self.stock_db_name = stock_db_name
        self.event_handlers: dict[str, Callable[[Event], None]] = {}
        self._closed = False

        stock_db = self.mysql_dbs[stock_db_name]
        if self.STOCK_INDEX_TABLE not in stock_db.tables:
            stock_db.register_table(
                self.STOCK_INDEX_TABLE,
                StockIndexEntity(stock_db),
            )
        stock_table = stock_db.table(self.STOCK_INDEX_TABLE)
        if not callable(getattr(stock_table, "upsert_sse_stocks", None)):
            raise TypeError(
                f"Table {self.STOCK_INDEX_TABLE!r} must provide upsert_sse_stocks()."
            )
        if self.STOCK_DAILY_TABLE not in stock_db.tables:
            stock_db.register_table(
                self.STOCK_DAILY_TABLE,
                StockDailyBarEntity(stock_db),
            )
        daily_table = stock_db.table(self.STOCK_DAILY_TABLE)
        if not callable(getattr(daily_table, "upsert_sina_bars", None)):
            raise TypeError(
                f"Table {self.STOCK_DAILY_TABLE!r} must provide upsert_sina_bars()."
            )

        self.register_event(self.STOCK_LIST_EVENT, self._on_task_finished)
        self.register_event(
            self.STOCK_LIST_REQUEST_EVENT,
            self._on_stock_list_requested,
        )

    def register_event(
        self,
        event_type: str,
        handler: Callable[[Event], None],
    ) -> None:
        """Register an event handler and subscribe the agent to its event type."""
        if not isinstance(event_type, str) or not event_type.strip():
            raise ValueError("event_type must be a non-empty string.")
        if not callable(handler):
            raise TypeError("handler must be callable.")
        if event_type in self.event_handlers:
            raise ValueError(f"Event handler already registered for {event_type!r}.")

        self.event_handlers[event_type] = handler
        self.event_bus.subscribe(event_type, self._dispatch_event)

    def _dispatch_event(self, event: Event) -> None:
        if self._closed:
            return
        handler = self.event_handlers.get(event.event_type)
        if handler is not None:
            handler(event)

    def _on_task_finished(self, event: Event) -> None:
        event_data = event.event_data
        if not isinstance(event_data, dict):
            raise ValueError("data.task.finished requires dictionary event_data.")
        task_type = event_data.get("task_type")
        source = event_data.get("source")
        if task_type == self.STOCK_LIST_TASK and source == self.STOCK_LIST_SOURCE:
            rows = event_data.get("rows")
            if not isinstance(rows, list):
                raise ValueError("SSE symbol-list completion requires a rows list.")

            stock_db = self.mysql_dbs[self.stock_db_name]
            stock_table = stock_db.table(self.STOCK_INDEX_TABLE)
            stock_table.upsert_sse_stocks(rows)
            return
        if task_type != self.HISTORICAL_KLINE_TASK or source != self.SINA_SOURCE:
            return
        rows = event_data.get("rows")
        if not isinstance(rows, list):
            raise ValueError("Sina historical K-line completion requires a rows list.")

        stock_db = self.mysql_dbs[self.stock_db_name]
        daily_table = stock_db.table(self.STOCK_DAILY_TABLE)
        affected_rows = daily_table.upsert_sina_bars(rows)
        logger.info(
            f"Received {len(rows)} Sina daily bars; upserted {affected_rows} rows."
        )

    def _on_stock_list_requested(self, event: Event) -> None:
        event_data = event.event_data
        task = event_data.get("task") if isinstance(event_data, dict) else None
        if not isinstance(task, dict):
            raise ValueError("data.fetch.requested requires a task object.")
        if task.get("task_type") != self.STOCK_LIST_TASK:
            return

        from website_agent.website.site_sse import SiteSSE

        with SiteSSE() as site:
            rows = site.fetch_stock_code()

        stock_db = self.mysql_dbs[self.stock_db_name]
        stock_table = stock_db.table(self.STOCK_INDEX_TABLE)
        affected_rows = stock_table.upsert_sse_stocks(rows)
        logger.info(
            f"Fetched {len(rows)} SSE stock records; upserted {affected_rows} rows."
        )

    def close(self) -> None:
        """Close all distinct managed database connections."""
        if self._closed:
            return
        self._closed = True
        closed_databases: set[int] = set()
        for database in self.mysql_dbs.values():
            if id(database) not in closed_databases:
                database.close()
                closed_databases.add(id(database))


__all__ = ["DataAgent"]
