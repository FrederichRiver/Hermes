"""Eastmoney stock-list and daily stock-data client.

The client retrieves overseas stock listings and the latest daily K-line for
one indexed stock, normalizing Eastmoney's compact responses into explicit
field names.
"""

from collections.abc import Mapping
from datetime import date
import json
import re

from agent.http_connect import HttpConnect


EASTMONEY_STOCK_KLINE_API_URL = (
    "https://push2his.eastmoney.com/api/qt/stock/kline/get"
)
EASTMONEY_STOCK_LIST_API_URL = "https://push2.eastmoney.com/api/qt/clist/get"
EASTMONEY_US_STOCK_LIST_FILTER = "m:105,m:106,m:107"
EASTMONEY_HK_STOCK_LIST_FILTER = "m:128+t:3,m:128+t:4,m:128+t:1,m:128+t:2"
_EASTMONEY_FIELDS = (
    "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
)
_EXCHANGE_MARKETS = {
    "SH": "1",
    "SZ": "0",
    "BZ": "0",
}
_LIST_FILTERS = {
    "US": EASTMONEY_US_STOCK_LIST_FILTER,
    "HK": EASTMONEY_HK_STOCK_LIST_FILTER,
}
_LIST_PAGE_SIZE = 100


def parse_eastmoney_daily_kline(
    text: str,
    stock_code: str,
    stock_name: str,
) -> dict[str, str]:
    """Parse an Eastmoney latest-daily-K-line response.

    Args:
        text: JSON response body returned by Eastmoney.
        stock_code: Indexed exchange-prefixed stock code, such as ``SH600000``.
        stock_name: Stock name from ``stock_index``.

    Returns:
        A normalized latest daily bar, including code, name, OHLC, volume, and
        turnover fields.

    Raises:
        ValueError: The response is invalid or does not contain a daily bar.
    """
    return parse_eastmoney_daily_klines(text, stock_code, stock_name)[-1]


def parse_eastmoney_daily_klines(
    text: str,
    stock_code: str,
    stock_name: str,
) -> list[dict[str, str]]:
    """Parse all daily K-lines returned by Eastmoney for one indexed stock."""
    try:
        response = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Eastmoney response is not valid JSON.") from exc

    if not isinstance(response, Mapping):
        raise ValueError("Eastmoney response must be a JSON object.")
    result_data = response.get("data")
    if not isinstance(result_data, Mapping):
        raise ValueError(f"Eastmoney returned no data for {stock_code}.")
    result_klines = result_data.get("klines")
    if not isinstance(result_klines, list) or not result_klines:
        raise ValueError(f"Eastmoney returned no daily K-line for {stock_code}.")

    records = []
    for result_kline in result_klines:
        if not isinstance(result_kline, str):
            raise ValueError(f"Eastmoney returned an invalid K-line for {stock_code}.")
        values = result_kline.split(",")
        if len(values) != 11:
            raise ValueError(f"Eastmoney returned an incomplete K-line for {stock_code}.")
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
                f"Eastmoney returned an invalid trade date for {stock_code}."
            )
        records.append(
            {
                "stock_code": stock_code,
                "stock_name": stock_name,
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


class EastmoneySiteClient(HttpConnect):
    """Fetch stock listings and normalized daily stock data from Eastmoney."""

    def fetch_stock_list(self, exchange: str) -> list[dict[str, str | None]]:
        """Fetch all Eastmoney stock codes for the requested overseas exchange.

        Args:
            exchange: ``US`` for United States stocks or ``HK`` for Hong Kong
                stocks.

        Returns:
            Normalized stock-index records with ``code``, ``name``,
            ``exchange``, and ``list_date`` keys.

        Raises:
            ValueError: The exchange is unsupported or Eastmoney returns an
                invalid listing response.
        """
        if not isinstance(exchange, str):
            raise ValueError("exchange must be US or HK.")
        result_exchange = exchange.strip().upper()
        result_filter = _LIST_FILTERS.get(result_exchange)
        if result_filter is None:
            raise ValueError(f"Unsupported Eastmoney listing exchange: {exchange!r}")

        result_records: list[dict[str, str | None]] = []
        result_page_number = 1
        result_page_count: int | None = None
        while result_page_count is None or result_page_number <= result_page_count:
            response = self.get(
                EASTMONEY_STOCK_LIST_API_URL,
                params={
                    "pn": str(result_page_number),
                    "pz": str(_LIST_PAGE_SIZE),
                    "po": "1",
                    "np": "1",
                    "fltt": "2",
                    "invt": "2",
                    "fid": "f3",
                    "fs": result_filter,
                    "fields": "f12,f14",
                },
            )
            result_page, result_total = _parse_eastmoney_stock_list_response(
                response.text,
                result_exchange,
            )
            if result_page_count is None:
                result_page_count = max(
                    1,
                    (result_total + _LIST_PAGE_SIZE - 1) // _LIST_PAGE_SIZE,
                )
            result_records.extend(result_page)
            result_page_number += 1
        return result_records

    def fetch_us_stock_list(self) -> list[dict[str, str | None]]:
        """Fetch all United States stock codes available from Eastmoney."""
        return self.fetch_stock_list("US")

    def fetch_hk_stock_list(self) -> list[dict[str, str | None]]:
        """Fetch all Hong Kong stock codes available from Eastmoney."""
        return self.fetch_stock_list("HK")

    def fetch_latest_daily_kline(
        self,
        stock_code: str,
        stock_name: str,
    ) -> dict[str, str]:
        """Fetch the latest daily K-line for one exchange-prefixed stock code.

        Args:
            stock_code: Indexed code in ``SH600000``, ``SZ000001``, or
                ``BZ430047`` form.
            stock_name: Stock name to include in the normalized result.

        Returns:
            A normalized latest daily K-line record.

        Raises:
            ValueError: The indexed code is invalid or Eastmoney has no data.
        """
        result_secid = _to_eastmoney_security_id(stock_code)
        response = self.get(
            EASTMONEY_STOCK_KLINE_API_URL,
            params={
                "secid": result_secid,
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": _EASTMONEY_FIELDS,
                "klt": "101",
                "fqt": "1",
                "end": "20500101",
                "lmt": "1",
            },
        )
        return parse_eastmoney_daily_kline(response.text, stock_code, stock_name)

    def fetch_daily_kline_range(
        self,
        stock_code: str,
        stock_name: str,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, str]]:
        """Fetch adjusted daily K-lines for one stock over an inclusive range."""
        if not isinstance(start_date, date) or not isinstance(end_date, date):
            raise ValueError("start_date and end_date must be date instances.")
        if start_date > end_date:
            raise ValueError("start_date must not be after end_date.")

        result_secid = _to_eastmoney_security_id(stock_code)
        response = self.get(
            EASTMONEY_STOCK_KLINE_API_URL,
            params={
                "secid": result_secid,
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": _EASTMONEY_FIELDS,
                "klt": "101",
                "fqt": "1",
                "beg": start_date.strftime("%Y%m%d"),
                "end": end_date.strftime("%Y%m%d"),
                "lmt": "10000",
            },
        )
        return parse_eastmoney_daily_klines(response.text, stock_code, stock_name)


def _parse_eastmoney_stock_list_response(
    text: str,
    exchange: str,
) -> tuple[list[dict[str, str | None]], int]:
    """Parse one page of Eastmoney's overseas stock-list response."""
    try:
        response = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Eastmoney stock-list response is not valid JSON.") from exc

    if not isinstance(response, Mapping) or response.get("rc") != 0:
        raise ValueError(f"Eastmoney stock-list request failed: {response!r}")
    result_data = response.get("data")
    if not isinstance(result_data, Mapping):
        raise ValueError("Eastmoney stock-list response does not contain data.")
    result_total = result_data.get("total")
    result_rows = result_data.get("diff")
    if not isinstance(result_total, int) or result_total < 0:
        raise ValueError("Eastmoney stock-list response has an invalid total.")
    if not isinstance(result_rows, list):
        raise ValueError("Eastmoney stock-list response does not contain rows.")

    result_records: list[dict[str, str | None]] = []
    for result_row in result_rows:
        if not isinstance(result_row, Mapping):
            continue
        code = result_row.get("f12")
        name = result_row.get("f14")
        if (
            not isinstance(code, str)
            or not isinstance(name, str)
            or not name.strip()
            or not _is_valid_overseas_stock_code(code, exchange)
        ):
            continue
        result_records.append(
            {
                "code": code.upper(),
                "name": name.strip(),
                "exchange": exchange,
                "list_date": None,
            }
        )
    return result_records, result_total


def _is_valid_overseas_stock_code(code: str, exchange: str) -> bool:
    """Validate an Eastmoney US or Hong Kong stock code."""
    if exchange == "US":
        return re.fullmatch(r"[A-Za-z][A-Za-z0-9.-]{0,7}", code) is not None
    return re.fullmatch(r"\d{5}", code) is not None


def _to_eastmoney_security_id(stock_code: str) -> str:
    """Convert an indexed stock code to Eastmoney's ``market.code`` form."""
    if not isinstance(stock_code, str):
        raise ValueError("stock_code must be an exchange-prefixed string.")
    result_match = re.fullmatch(r"(SH|SZ|BZ)(\d{6})", stock_code.upper())
    if result_match is None:
        raise ValueError(f"Invalid indexed stock code: {stock_code!r}")
    exchange, code = result_match.groups()
    return f"{_EXCHANGE_MARKETS[exchange]}.{code}"
