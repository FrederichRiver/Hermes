"""Typed row models for the data engine."""

from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class StockIndexRecord:
    """One normalized security listing stored in ``stock_index``."""

    stock_code: str
    short_name: str
    stock_name: str
    publish_date: date | None = None
    update_date: date | None = None


@dataclass(slots=True)
class SymbolInfo:
    """Basic information for one listed security."""

    symbol: str
    name: str
    market: str
    asset_type: str
    list_date: date
    delist_date: date | None = None


@dataclass(slots=True)
class StockDailyBar:
    """Daily market data for one security."""

    symbol: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: float
    adj_factor: float = 1.0


@dataclass(slots=True)
class FundNav:
    """Net asset value for one fund on one date."""

    symbol: str
    nav_date: date
    unit_nav: float
    accum_nav: float | None = None
