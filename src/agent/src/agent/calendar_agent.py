"""CalendarAgent — lightweight calendar service.

This module provides a small, dependency-free in-memory CalendarAgent suitable for
tests and as a minimal production starting point.

Features:
- Load market holiday data from JSON files under ``data/calendar/<market>.json``.
- In-memory query API: ``is_trading_day``, ``get_holidays``, ``next_trading_day``,
  ``previous_trading_day``, ``list_special_events``.
- Simple in-process subscriber callbacks for update notifications.

The implementation follows project coding guidelines (typed public API, Google-style
docstrings, structured logging, and safe file updates).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import json
import logging
from typing import Callable, Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "calendar"

class ApplicationError(Exception):
    """Base application exception for CalendarAgent-related errors."""


class NotFoundError(ApplicationError):
    """Raised when requested market data cannot be found."""


class TransientError(ApplicationError):
    """Raised for transient external errors (e.g. network timeouts)."""

class CalendarAgent:
    """In-memory calendar service backed by JSON files.

    Args:
        data_dir: Optional path to calendar JSON files. Defaults to
            ``src/data/calendar`` inside the repository.
    """

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.data_dir: Path = Path(data_dir) if data_dir else DATA_DIR
        self.markets: Dict[str, Dict[str, Any]] = {}
        self.subscribers: List[Tuple[Callable[[Dict[str, Any]], None], Dict[str, Any]]] = []

    def load_market(self, market: str) -> None:
        """Load market calendar JSON into memory.

        Raises:
            NotFoundError: If the JSON file does not exist.
            ValueError: If the JSON content is invalid.
        """
        path = self.data_dir / f"{market}.json"
        if not path.exists():
            raise NotFoundError(f"Market data for '{market}' not found at {path}")
        try:
            with path.open("r", encoding="utf-8") as f:
                self.markets[market] = json.load(f)
        except json.JSONDecodeError as exc:
            logger.exception("Failed to parse calendar JSON for market=%s at %s", market, path)
            raise ValueError("invalid calendar JSON") from exc

    def ensure_market(self, market: str) -> None:
        """Ensure market data is loaded into memory.

        This is a convenience wrapper that lazy-loads JSON data on first use.
        """
        if market not in self.markets:
            self.load_market(market)

    def is_trading_day(self, market: str, dt: date) -> bool:
        """Return True when ``dt`` is a trading day for ``market``.

        Rules:
        - If the date appears in the market `holidays` map, honor the ``trading`` flag
          when present (``True`` means trading allowed, ``False`` means holiday).
        - Otherwise, default to weekdays (Mon-Fri) as trading days.
        """
        self.ensure_market(market)
        key = dt.isoformat()
        holidays = self.markets[market].get("holidays", {})
        if key in holidays:
            trading_flag = holidays[key].get("trading")
            if isinstance(trading_flag, bool):
                return trading_flag
        return dt.weekday() < 5

    def get_holidays(self, market: str, year: int) -> List[Dict]:
        self.ensure_market(market)
        holidays = self.markets[market].get("holidays", {})
        out = []
        for d, meta in holidays.items():
            if d.startswith(str(year)):
                entry = {"date": d, **meta}
                out.append(entry)
        return sorted(out, key=lambda x: x["date"])

    def _move_trading_day(self, market: str, dt: date, step: int) -> date:
        """Move forward/backward ``n`` trading days from ``dt``.

        Args:
            market: market key.
            dt: starting date (exclusive).
            step: positive for next, negative for previous.

        Returns:
            The target date after moving ``abs(step)`` trading days.
        """
        direction = 1 if step > 0 else -1
        remaining = abs(step)
        current = dt
        while remaining > 0:
            current = current + timedelta(days=direction)
            if self.is_trading_day(market, current):
                remaining -= 1
        return current

    def next_trading_day(self, market: str, dt: date, n: int = 1) -> date:
        self.ensure_market(market)
        return self._move_trading_day(market, dt, n)

    def previous_trading_day(self, market: str, dt: date, n: int = 1) -> date:
        self.ensure_market(market)
        return self._move_trading_day(market, dt, -n)

    def list_special_events(self, market: str, start: date, end: date) -> List[Dict[str, Any]]:
        """List special calendar events for ``market`` between ``start`` and ``end``.

        Dates are inclusive. Returned entries are dicts containing at least a
        ``date`` ISO string and attached metadata from the source JSON.
        """
        self.ensure_market(market)
        holidays = self.markets[market].get("holidays", {})
        out: List[Dict[str, Any]] = []
        for d, meta in holidays.items():
            try:
                parsed = date.fromisoformat(d)
            except ValueError:
                logger.warning("Ignoring invalid date format in holidays: %s", d)
                continue
            if start <= parsed <= end:
                out.append({"date": d, **(meta or {})})
        return sorted(out, key=lambda x: x["date"])

    def subscribe(self, callback: Callable[[Dict[str, Any]], None], filters: Optional[Dict[str, Any]] = None) -> None:
        """Register a callback to be notified on calendar updates.

        The callback will receive a single ``event`` dict. ``filters`` is reserved
        for future use and is stored alongside the callback.
        """
        self.subscribers.append((callback, filters or {}))

    def _notify_subscribers(self, event: Dict[str, Any]) -> None:
        """Notify subscribers about an event.

        Exceptions raised by subscribers are logged but do not interrupt the
        notification loop.
        """
        for cb, _flt in self.subscribers:
            try:
                cb(event)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("Subscriber callback failed: %s", exc)

    def update_market_data(self, market: str, data: Dict[str, Any], source: Optional[str] = None) -> None:
        """Atomically update market calendar data and persist to disk.

        The on-disk file is replaced atomically (write to a temp file then
        rename). After successful write the in-memory cache is updated and
        subscribers are notified.
        """
        path = self.data_dir / f"{market}.json"
        tmp = path.with_suffix(".json.tmp")
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            tmp.replace(path)
        except OSError as exc:
            logger.exception("Failed to persist calendar data for market=%s: %s", market, exc)
            raise TransientError("failed to persist calendar data") from exc
        # update memory and notify
        self.markets[market] = data
        meta = {"market": market, "source": source, "updated_at": datetime.utcnow().isoformat()}
        self._notify_subscribers({"type": "calendar.updated", "meta": meta})


if __name__ == "__main__":  # pragma: no cover - manual run helper
    ca = CalendarAgent()
    try:
        ca.load_market("china")
    except NotFoundError:
        logger.info("No sample data found for 'china'. Create data/calendar/china.json to try.")
    except Exception:
        logger.exception("Unexpected error loading sample calendar data")
    else:
        today = date.today()
        logger.info("today %s is trading day? %s", today, ca.is_trading_day("china", today))
