"""Scheduler-callable events for synchronizing external data."""

import csv
from collections.abc import Mapping
from datetime import date
import logging
from pathlib import Path
import re

from agent.sites.site_bse_module import BseSiteClient
from agent.sites.site_eastmoney_market_module import EastmoneyMarketSiteClient
from agent.sites.site_eastmoney_module import EastmoneySiteClient
from agent.sites.site_sse_module import SSE_STOCK_LIST_API_URL, SseSiteClient
from agent.sites.site_szse_module import SZSE_STOCK_LIST_API_URL, SzseSiteClient
from data_engine.mysql_table import StockIndex
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)

_STOCK_DATA_OUTPUT_COLUMNS = (
    "stock_code",
    "stock_name",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "amplitude",
    "change_percent",
    "price_change",
    "turnover_rate",
)
_MARKET_PRICE_OUTPUT_COLUMNS = (
    "instrument_type",
    "instrument_code",
    "instrument_name",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "amplitude",
    "change_percent",
    "price_change",
    "turnover_rate",
)


def event_update_stock_index(exchange: str = "ALL") -> None:
    """Fetch exchange stock listings and atomically upsert stock_index.

    Args:
        exchange: ``ALL`` for all supported exchanges, or ``SH``, ``SZ``,
            ``BZ``, ``US``, and ``HK`` for Shanghai, Shenzhen, Beijing, United
            States, and Hong Kong respectively.
    """
    sse_stock_list_url = SSE_STOCK_LIST_API_URL
    sse_stock_list_referer = "https://www.sse.com.cn/assortment/stock/list/share/"
    szse_stock_list_url = SZSE_STOCK_LIST_API_URL
    szse_stock_list_referer = "https://www.szse.cn/index/index.html"
    bse_stock_list_url = "https://www.bse.cn/nq/listedcompany.html"
    client_options = {
        "base_headers": {
            "User-Agent": "Mozilla/5.0 Hermes stock-index updater",
        },
        "timeout": 30.0,
    }

    if not isinstance(exchange, str):
        raise ValueError("exchange must be ALL, SH, SZ, BZ, US, or HK.")
    exchange_code = exchange.strip().upper()
    result_list = []
    if exchange_code == "ALL":
        with SseSiteClient(
            base_headers={
                **client_options["base_headers"],
                "Referer": sse_stock_list_referer,
            },
            timeout=client_options["timeout"],
        ) as site_client:
            result_list.extend(site_client.fetch_stock_list(sse_stock_list_url))
        with SzseSiteClient(
            base_headers={
                **client_options["base_headers"],
                "Referer": szse_stock_list_referer,
            },
            timeout=client_options["timeout"],
        ) as site_client:
            result_list.extend(site_client.fetch_stock_list(szse_stock_list_url))
        with BseSiteClient(
            base_headers={
                **client_options["base_headers"],
                "Referer": bse_stock_list_url,
            },
            timeout=client_options["timeout"],
        ) as site_client:
            result_list.extend(site_client.fetch_stock_list(bse_stock_list_url))
        with EastmoneySiteClient(
            base_headers={
                **client_options["base_headers"],
                "Referer": "https://quote.eastmoney.com/",
            },
            timeout=client_options["timeout"],
        ) as site_client:
            result_list.extend(site_client.fetch_stock_list("US"))
            result_list.extend(site_client.fetch_stock_list("HK"))
    elif exchange_code == "SH":
        with SseSiteClient(
            base_headers={
                **client_options["base_headers"],
                "Referer": sse_stock_list_referer,
            },
            timeout=client_options["timeout"],
        ) as site_client:
            result_list = site_client.fetch_stock_list(sse_stock_list_url)
    elif exchange_code == "SZ":
        with SzseSiteClient(
            base_headers={
                **client_options["base_headers"],
                "Referer": szse_stock_list_referer,
            },
            timeout=client_options["timeout"],
        ) as site_client:
            result_list = site_client.fetch_stock_list(szse_stock_list_url)
    elif exchange_code == "BZ":
        with BseSiteClient(
            base_headers={
                **client_options["base_headers"],
                "Referer": bse_stock_list_url,
            },
            timeout=client_options["timeout"],
        ) as site_client:
            result_list = site_client.fetch_stock_list(bse_stock_list_url)
    elif exchange_code in {"US", "HK"}:
        with EastmoneySiteClient(
            base_headers={
                **client_options["base_headers"],
                "Referer": "https://quote.eastmoney.com/",
            },
            timeout=client_options["timeout"],
        ) as site_client:
            result_list = site_client.fetch_stock_list(exchange_code)
    else:
        raise ValueError(
            f"Unsupported exchange: {exchange}. Use ALL, SH, SZ, BZ, US, or HK."
        )

    if not result_list:
        raise RuntimeError(
            f"{exchange_code} returned no stock records; stock_index was not changed."
        )

    stock_index = StockIndex(None, None, None, None)
    table_name = stock_index.Meta.db_table
    update_stock_index_sql = (
        f"INSERT INTO `{table_name}` "
        "(`stock_code`, `short_name`, `stock_name`, `publish_date`, `update_date`) "
        "VALUES (%s, %s, %s, %s, %s) "
        "ON DUPLICATE KEY UPDATE "
        "`short_name` = VALUES(`short_name`), "
        "`stock_name` = VALUES(`stock_name`), "
        "`publish_date` = VALUES(`publish_date`), "
        "`update_date` = VALUES(`update_date`)"
    )
    update_date = date.today().isoformat()
    try:
        stock_index.create_table()
        with stock_index.transaction():
            for result_record in result_list:
                stock_index.execute(
                    update_stock_index_sql,
                    _normalize_stock_index_row(result_record, update_date),
                    commit=False,
                )
    finally:
        stock_index.close()

    logger.info(
        f"Updated stock_index with {len(result_list)} {exchange_code} stock records."
    )


def record_stock_data(
    output_path: str | Path = "tests/output/stock_data_pending_rows.tsv",
) -> int:
    """Export current daily stock data for every indexed stock to a TSV file.

    This review-stage event reads ``stock_index`` from MySQL, fetches each
    stock's latest adjusted daily K-line from Eastmoney, and writes normalized
    records locally. It deliberately does not write stock data to MySQL.

    Args:
        output_path: Destination TSV file for records pending database review.

    Returns:
        The number of stock-data records written.

    Raises:
        RuntimeError: ``stock_index`` is empty or no stock data can be fetched.
        ValueError: ``output_path`` is not a file path.
    """
    result_stocks = _load_stock_index_records()
    if not result_stocks:
        raise RuntimeError("stock_index is empty; no stock data can be recorded.")

    result_rows: list[dict[str, str]] = []
    client_options = {
        "base_headers": {
            "User-Agent": "Mozilla/5.0 Hermes stock-data recorder",
            "Referer": "https://quote.eastmoney.com/",
        },
        "timeout": 30.0,
    }
    with EastmoneySiteClient(**client_options) as site_client:
        for result_stock in result_stocks:
            try:
                result_rows.append(
                    site_client.fetch_latest_daily_kline(
                        result_stock["stock_code"],
                        result_stock["stock_name"],
                    )
                )
            except (RequestException, ValueError) as exc:
                logger.warning(
                    "Could not fetch Eastmoney data for %s: %s",
                    result_stock["stock_code"],
                    exc,
                )

    if not result_rows:
        raise RuntimeError("Eastmoney returned no stock data for stock_index.")

    _write_stock_data_rows(Path(output_path), result_rows)
    logger.info(
        "Exported %d of %d Eastmoney stock-data records to %s.",
        len(result_rows),
        len(result_stocks),
        output_path,
    )
    return len(result_rows)


def record_stock_data_range(
    start_date: date,
    end_date: date,
    output_path: str | Path = "tests/output/stock_data_range_pending_rows.tsv",
) -> int:
    """Export daily stock data for every indexed stock within a date range.

    Args:
        start_date: Inclusive first date to request from Eastmoney.
        end_date: Inclusive final date to request from Eastmoney.
        output_path: Destination TSV file for records pending database review.

    Returns:
        The number of stock-data rows written.
    """
    if not isinstance(start_date, date) or not isinstance(end_date, date):
        raise ValueError("start_date and end_date must be date instances.")
    if start_date > end_date:
        raise ValueError("start_date must not be after end_date.")

    result_stocks = _load_stock_index_records()
    if not result_stocks:
        raise RuntimeError("stock_index is empty; no stock data can be recorded.")

    result_rows: list[dict[str, str]] = []
    with EastmoneySiteClient(
        base_headers={
            "User-Agent": "Mozilla/5.0 Hermes stock-data recorder",
            "Referer": "https://quote.eastmoney.com/",
        },
        timeout=30.0,
    ) as site_client:
        for result_stock in result_stocks:
            try:
                result_rows.extend(
                    site_client.fetch_daily_kline_range(
                        result_stock["stock_code"],
                        result_stock["stock_name"],
                        start_date,
                        end_date,
                    )
                )
            except (RequestException, ValueError) as exc:
                logger.warning(
                    "Could not fetch Eastmoney range data for %s: %s",
                    result_stock["stock_code"],
                    exc,
                )

    if not result_rows:
        raise RuntimeError("Eastmoney returned no stock data for stock_index.")

    _write_stock_data_rows(Path(output_path), result_rows)
    logger.info(
        "Exported %d Eastmoney stock-data rows from %s to %s.",
        len(result_rows),
        start_date,
        output_path,
    )
    return len(result_rows)


def record_gold_price_data(
    output_path: str | Path = "tests/output/gold_price_pending_rows.tsv",
) -> int:
    """Export the latest Eastmoney gold/US-dollar daily price to TSV."""
    with EastmoneyMarketSiteClient(
        base_headers={
            "User-Agent": "Mozilla/5.0 Hermes market-price recorder",
            "Referer": "https://quote.eastmoney.com/",
        },
        timeout=30.0,
    ) as site_client:
        result_rows = site_client.fetch_gold_daily_prices()
    _write_market_price_rows(Path(output_path), result_rows)
    return len(result_rows)


def record_forex_price_data(
    currency_pair: str = "USDCNH",
    output_path: str | Path = "tests/output/forex_price_pending_rows.tsv",
) -> int:
    """Export the latest Eastmoney foreign-exchange daily price to TSV."""
    with EastmoneyMarketSiteClient(
        base_headers={
            "User-Agent": "Mozilla/5.0 Hermes market-price recorder",
            "Referer": "https://quote.eastmoney.com/",
        },
        timeout=30.0,
    ) as site_client:
        result_rows = site_client.fetch_forex_daily_prices(currency_pair)
    _write_market_price_rows(Path(output_path), result_rows)
    return len(result_rows)


def _load_stock_index_records() -> list[dict[str, str]]:
    """Read stock codes and names from ``stock_index`` without modifying it."""
    stock_index = StockIndex(None, None, None, None)
    table_name = stock_index.Meta.db_table
    try:
        result_records = stock_index.query(
            f"SELECT `stock_code`, `stock_name` FROM `{table_name}` "
            "ORDER BY `stock_code`"
        )
    finally:
        stock_index.close()

    result_stocks: list[dict[str, str]] = []
    for result_record in result_records:
        if not isinstance(result_record, Mapping):
            raise ValueError("stock_index returned a non-mapping row.")
        stock_code = result_record.get("stock_code")
        stock_name = result_record.get("stock_name")
        if not isinstance(stock_code, str) or not isinstance(stock_name, str):
            raise ValueError("stock_index rows must contain string code and name.")
        result_stocks.append(
            {
                "stock_code": stock_code,
                "stock_name": stock_name,
            }
        )
    return result_stocks


def _write_stock_data_rows(
    output_path: Path,
    rows: list[dict[str, str]],
) -> None:
    """Atomically write normalized stock-data rows as UTF-8 TSV."""
    if output_path.name == "":
        raise ValueError("output_path must identify a file.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f"{output_path.name}.tmp")
    try:
        with temporary_path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output,
                fieldnames=_STOCK_DATA_OUTPUT_COLUMNS,
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
        temporary_path.replace(output_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _write_market_price_rows(
    output_path: Path,
    rows: list[dict[str, str]],
) -> None:
    """Atomically write normalized gold or foreign-exchange rows as TSV."""
    if not rows:
        raise RuntimeError("Eastmoney returned no market-price data.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f"{output_path.name}.tmp")
    try:
        with temporary_path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output,
                fieldnames=_MARKET_PRICE_OUTPUT_COLUMNS,
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
        temporary_path.replace(output_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _normalize_stock_index_row(
    record: Mapping[str, object],
    update_date: str,
) -> tuple[str, str, str, str | None, str]:
    """Convert an exchange listing record to the stock_index table column order."""
    code = record.get("code")
    exchange = record.get("exchange", "SH")
    if not isinstance(exchange, str) or exchange.strip().upper() not in {
        "SH",
        "SZ",
        "BZ",
        "US",
        "HK",
    }:
        raise ValueError(f"Invalid stock exchange: {exchange!r}")
    exchange_code = exchange.strip().upper()
    if (
        not isinstance(code, str)
        or not _is_valid_stock_index_code(code, exchange_code)
    ):
        raise ValueError(f"Invalid {exchange_code} stock code: {code!r}")

    name = record.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Missing SSE stock name for code {code}.")
    stock_name = name.strip()

    stock_code = f"{exchange_code}{code.upper()}"

    short_name = record.get("short_name", stock_name)
    if not isinstance(short_name, str) or not short_name.strip():
        short_name = stock_name
    short_name = short_name.strip()

    if len(short_name) > 10:
        logger.warning(f"Truncating short_name for {stock_code} to 10 characters.")
        short_name = short_name[:10]
    if len(stock_name) > 20:
        logger.warning(f"Truncating stock_name for {stock_code} to 20 characters.")
        stock_name = stock_name[:20]

    return (
        stock_code,
        short_name,
        stock_name,
        _normalize_publish_date(record.get("list_date")),
        update_date,
    )


def _is_valid_stock_index_code(code: str, exchange: str) -> bool:
    """Validate a source stock code for its exchange namespace."""
    if exchange in {"SH", "SZ", "BZ"}:
        return re.fullmatch(r"\d{6}", code) is not None
    if exchange == "US":
        return re.fullmatch(r"[A-Za-z][A-Za-z0-9.-]{0,7}", code) is not None
    return re.fullmatch(r"\d{5}", code) is not None


def _normalize_publish_date(value: object) -> str | None:
    """Normalize an optional SSE listing date to the MySQL DATE representation."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"Invalid SSE listing date: {value!r}")

    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError as exc:
        raise ValueError(f"Invalid SSE listing date: {value!r}") from exc
