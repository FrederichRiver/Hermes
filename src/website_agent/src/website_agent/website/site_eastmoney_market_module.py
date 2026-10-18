"""Eastmoney gold and foreign-exchange daily price client."""

from collections.abc import Mapping
from datetime import date
import json
import re
from typing import Any

from website_agent.http_utils.client import HttpClient
from website_agent.website.agent import BaseSite


EASTMONEY_MARKET_KLINE_API_URL = (
    "https://push2his.eastmoney.com/api/qt/stock/kline/get"
)
_EASTMONEY_MARKET_FIELDS = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
_GOLD_SECURITY_IDS = {"XAU": "122.XAU"}
_FOREX_SECURITY_IDS = {
    "USDCNH": "133.USDCNH",
    "EURUSD": "133.EURUSD",
    "USDJPY": "133.USDJPY",
}


def parse_eastmoney_market_daily_klines(
    text: str,
    instrument_type: str,
    instrument_code: str,
) -> list[dict[str, str]]:
    """Parse Eastmoney daily K-lines for a gold or foreign-exchange instrument."""
    try:
        response = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Eastmoney response is not valid JSON.") from exc

    if not isinstance(response, Mapping):
        raise ValueError("Eastmoney response must be a JSON object.")
    result_data = response.get("data")
    if not isinstance(result_data, Mapping):
        raise ValueError(f"Eastmoney returned no data for {instrument_code}.")
    result_name = result_data.get("name")
    result_klines = result_data.get("klines")
    if not isinstance(result_name, str) or not result_name:
        raise ValueError(f"Eastmoney returned no name for {instrument_code}.")
    if not isinstance(result_klines, list) or not result_klines:
        raise ValueError(f"Eastmoney returned no daily K-line for {instrument_code}.")

    records = []
    for result_kline in result_klines:
        if not isinstance(result_kline, str):
            raise ValueError(f"Eastmoney returned an invalid K-line for {instrument_code}.")
        values = result_kline.split(",")
        if len(values) != 11:
            raise ValueError(f"Eastmoney returned an incomplete K-line for {instrument_code}.")
        (
            trade_date,
            open_price,
            close_price,
            high_price,
            low_price,
            volume,
            amount,
            amplitude,
            change_percent,
            price_change,
            turnover_rate,
        ) = values
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", trade_date):
            raise ValueError(
                f"Eastmoney returned an invalid trade date for {instrument_code}."
            )
        records.append(
            {
                "instrument_type": instrument_type,
                "instrument_code": instrument_code,
                "instrument_name": result_name,
                "trade_date": trade_date,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": volume,
                "amount": amount,
                "amplitude": amplitude,
                "change_percent": change_percent,
                "price_change": price_change,
                "turnover_rate": turnover_rate,
            }
        )
    return records


class EastmoneyMarketSiteClient(BaseSite):
    """Fetch normalized daily gold and foreign-exchange prices from Eastmoney."""

    name = "eastmoney-market"
    priority = 50

    def __init__(
        self,
        config: Any | None = None,
        http_clients: dict[str, HttpClient] | None = None,
        **client_options: Any,
    ) -> None:
        super().__init__(config, http_clients, **client_options)

    def supports(self, task_type: str) -> bool:
        return task_type in {"gold_daily", "forex_daily"}

    def request_url(self, task: Any) -> str:
        if task.task_type not in {"gold_daily", "forex_daily"}:
            raise ValueError(f"Unsupported market task type: {task.task_type!r}")
        return EASTMONEY_MARKET_KLINE_API_URL

    def fetch(self, task: Any) -> list[dict[str, str]]:
        params = task.params
        start_date = _coerce_task_date(params.get("start_date"), "start_date")
        end_date = _coerce_task_date(params.get("end_date"), "end_date")
        if task.task_type == "gold_daily":
            return self.fetch_gold_daily_prices(
                symbol=params.get("symbol", "XAU"),
                start_date=start_date,
                end_date=end_date,
            )
        if task.task_type == "forex_daily":
            return self.fetch_forex_daily_prices(
                currency_pair=params.get("currency_pair", "USDCNH"),
                start_date=start_date,
                end_date=end_date,
            )
        raise ValueError(f"Unsupported market task type: {task.task_type!r}")

    def fetch_gold_daily_prices(
        self,
        symbol: str = "XAU",
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict[str, str]]:
        """Fetch gold/US-dollar daily prices for an optional inclusive range."""
        normalized_symbol = symbol.upper()
        security_id = _GOLD_SECURITY_IDS.get(normalized_symbol)
        if security_id is None:
            raise ValueError(f"Unsupported Eastmoney gold symbol: {symbol!r}")
        return self._fetch_daily_prices(
            security_id,
            "gold",
            normalized_symbol,
            start_date,
            end_date,
        )

    def fetch_forex_daily_prices(
        self,
        currency_pair: str = "USDCNH",
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict[str, str]]:
        """Fetch foreign-exchange daily prices for an optional inclusive range."""
        normalized_pair = currency_pair.upper()
        security_id = _FOREX_SECURITY_IDS.get(normalized_pair)
        if security_id is None:
            raise ValueError(
                f"Unsupported Eastmoney foreign-exchange pair: {currency_pair!r}"
            )
        return self._fetch_daily_prices(
            security_id,
            "forex",
            normalized_pair,
            start_date,
            end_date,
        )

    def _fetch_daily_prices(
        self,
        security_id: str,
        instrument_type: str,
        instrument_code: str,
        start_date: date | None,
        end_date: date | None,
    ) -> list[dict[str, str]]:
        """Fetch and parse daily prices for a configured Eastmoney security."""
        if (start_date is None) != (end_date is None):
            raise ValueError("start_date and end_date must be provided together.")
        if start_date is not None:
            if not isinstance(start_date, date) or not isinstance(end_date, date):
                raise ValueError("start_date and end_date must be date instances.")
            if start_date > end_date:
                raise ValueError("start_date must not be after end_date.")

        parameters = {
            "secid": security_id,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": _EASTMONEY_MARKET_FIELDS,
            "klt": "101",
            "fqt": "1",
            "end": "20500101",
            "lmt": "1" if start_date is None else "10000",
        }
        if start_date is not None:
            parameters["beg"] = start_date.strftime("%Y%m%d")
            parameters["end"] = end_date.strftime("%Y%m%d")

        response = self.get(EASTMONEY_MARKET_KLINE_API_URL, params=parameters)
        return parse_eastmoney_market_daily_klines(
            response.text,
            instrument_type,
            instrument_code,
        )


def _coerce_task_date(value: Any, name: str) -> date | None:
    if value is None or isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{name} must be an ISO date.") from exc
    raise ValueError(f"{name} must be a date or ISO date string.")
