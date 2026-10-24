"""新浪财经个股历史日K抓取适配器。"""

from collections.abc import Mapping
from datetime import date
import json
import math
import re
from typing import Any

from website_agent.http_utils.client import HttpClient
from website_agent.http_utils.user_agent import SINA_USER_AGENT
from website_agent.website.agent import BaseSite


SINA_STOCK_KLINE_API_URL = (
    "https://quotes.sina.cn/cn/api/json_v2.php/"
    "CN_MarketData.getKLineData"
)
SINA_STOCK_KLINE_MAX_ROWS = 1023
_SINA_SYMBOL_PATTERN = re.compile(r"^(SH|SZ)(\d{6})$", re.IGNORECASE)
_TRADE_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _normalize_date(value: object, field_name: str) -> date:
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not _TRADE_DATE_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must use YYYY-MM-DD format.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}: {value!r}.") from exc


def _normalize_symbol(value: object) -> tuple[str, str]:
    if not isinstance(value, str):
        raise ValueError("symbol must be an exchange-prefixed stock code.")
    match = _SINA_SYMBOL_PATTERN.fullmatch(value.strip())
    if match is None:
        raise ValueError(
            f"Invalid Sina stock symbol {value!r}; expected SH600000 or SZ000001."
        )
    normalized = f"{match.group(1).upper()}{match.group(2)}"
    return normalized, f"{match.group(1).lower()}{match.group(2)}"


def _parse_number(value: object, field_name: str, symbol: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"Sina returned an invalid {field_name} for {symbol}.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Sina returned an invalid {field_name} for {symbol}."
        ) from exc
    if not math.isfinite(number):
        raise ValueError(f"Sina returned a non-finite {field_name} for {symbol}.")
    return number


def parse_sina_daily_klines(
    text: str,
    symbol: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, str | int | float]]:
    """校验新浪日K响应，并返回请求日期范围内的标准化记录。"""
    normalized_symbol, _ = _normalize_symbol(symbol)
    try:
        response = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Sina K-line response is not valid JSON.") from exc
    if not isinstance(response, list) or not response:
        raise ValueError(f"Sina returned no daily K-lines for {normalized_symbol}.")
    if len(response) > SINA_STOCK_KLINE_MAX_ROWS:
        raise ValueError(
            f"Sina returned more than {SINA_STOCK_KLINE_MAX_ROWS} daily K-lines."
        )

    parsed_records: list[dict[str, str | int | float]] = []
    for row in response:
        if not isinstance(row, Mapping):
            raise ValueError(
                f"Sina returned an invalid daily K-line for {normalized_symbol}."
            )
        raw_trade_date = row.get("day")
        if (
            not isinstance(raw_trade_date, str)
            or not _TRADE_DATE_PATTERN.fullmatch(raw_trade_date)
        ):
            raise ValueError(
                f"Sina returned an invalid trade date for {normalized_symbol}."
            )
        try:
            trade_date = date.fromisoformat(raw_trade_date)
        except ValueError as exc:
            raise ValueError(
                f"Sina returned an invalid trade date for {normalized_symbol}."
            ) from exc

        open_price = _parse_number(row.get("open"), "open price", normalized_symbol)
        high_price = _parse_number(row.get("high"), "high price", normalized_symbol)
        low_price = _parse_number(row.get("low"), "low price", normalized_symbol)
        close_price = _parse_number(row.get("close"), "close price", normalized_symbol)
        volume = _parse_number(row.get("volume"), "volume", normalized_symbol)
        amount = _parse_number(row.get("amount"), "amount", normalized_symbol)
        if volume < 0 or not volume.is_integer():
            raise ValueError(f"Sina returned an invalid volume for {normalized_symbol}.")
        if min(open_price, high_price, low_price, close_price, amount) < 0:
            raise ValueError(
                f"Sina returned a negative market value for {normalized_symbol}."
            )
        if (
            low_price > high_price
            or low_price > min(open_price, close_price)
            or high_price < max(open_price, close_price)
        ):
            raise ValueError(
                f"Sina returned inconsistent OHLC values for {normalized_symbol}."
            )

        parsed_records.append(
            {
                "symbol": normalized_symbol,
                "trade_date": trade_date.isoformat(),
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": int(volume),
                "amount": amount,
                "adj_factor": 1.0,
            }
        )

    earliest_available_date = min(
        date.fromisoformat(str(row["trade_date"])) for row in parsed_records
    )
    if (
        len(parsed_records) == SINA_STOCK_KLINE_MAX_ROWS
        and start_date < earliest_available_date
    ):
        raise ValueError(
            f"Sina history for {normalized_symbol} starts at "
            f"{earliest_available_date.isoformat()}, after requested start date "
            f"{start_date.isoformat()}."
        )
    records = [
        row
        for row in parsed_records
        if start_date
        <= date.fromisoformat(str(row["trade_date"]))
        <= end_date
    ]
    if not records:
        raise ValueError(
            f"Sina returned no daily K-lines for {normalized_symbol} "
            f"between {start_date.isoformat()} and {end_date.isoformat()}."
        )
    return sorted(records, key=lambda row: str(row["trade_date"]))


class SiteSina(BaseSite):
    """新浪财经个股历史日K站点客户端。"""

    name = "sina"
    priority = 20

    def __init__(
        self,
        config: Any | None = None,
        http_clients: list[HttpClient] | None = None,
        **http_options: Any,
    ) -> None:
        if http_clients is None:
            http_options.setdefault("user_agents", [SINA_USER_AGENT])
            http_options.setdefault("rate", self.rate_limit())
        super().__init__(config, http_clients, **http_options)

    def supports(self, task_type: str) -> bool:
        return task_type == "historical_kline"

    def rate_limit(self) -> float:
        return 1.0

    def request_url(self, task: Any) -> str:
        if not self.supports(task.task_type):
            raise ValueError(f"Unsupported Sina task type: {task.task_type!r}")
        return SINA_STOCK_KLINE_API_URL

    def fetch(self, task: Any) -> list[dict[str, Any]]:
        if not self.supports(task.task_type):
            raise ValueError(f"Unsupported Sina task type: {task.task_type!r}")
        if not isinstance(task.params, Mapping):
            raise ValueError("Sina historical K-line task params must be an object.")

        symbol, sina_symbol = _normalize_symbol(task.params.get("symbol"))
        start_date = _normalize_date(task.params.get("start_date"), "start_date")
        end_date = _normalize_date(task.params.get("end_date"), "end_date")
        if start_date > end_date:
            raise ValueError("start_date must not be later than end_date.")

        response = self._http_clients[0].get(
            SINA_STOCK_KLINE_API_URL,
            params={
                "symbol": sina_symbol,
                "scale": "240",
                "ma": "no",
                "datalen": str(SINA_STOCK_KLINE_MAX_ROWS),
            },
        )
        return parse_sina_daily_klines(
            response.text,
            symbol,
            start_date,
            end_date,
        )


__all__ = [
    "SINA_STOCK_KLINE_API_URL",
    "SINA_STOCK_KLINE_MAX_ROWS",
    "SiteSina",
    "parse_sina_daily_klines",
]