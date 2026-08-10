"""Scheduler-callable events for synchronizing external data."""

from collections.abc import Mapping
from datetime import date
import logging
import re

from agent.sites.site_bse_module import BseSiteClient
from agent.sites.site_sse_module import SseSiteClient
from agent.sites.site_szse_module import SzseSiteClient
from data_engine.mysql_table import StockIndex

logger = logging.getLogger(__name__)


def event_update_stock_index(exchange: str = "ALL") -> None:
    """Fetch exchange stock listings and atomically upsert stock_index.

    Args:
        exchange: ``ALL`` for all supported exchanges, or ``SH``, ``SZ``, and
            ``BZ`` for Shanghai, Shenzhen, and Beijing respectively.
    """
    sse_stock_list_url = "https://www.sse.com.cn/assortment/stock/list/share/"
    szse_stock_list_url = "https://www.szse.cn/market/product/stock/list/index.html"
    bse_stock_list_url = "https://www.bse.cn/nq/listedcompany.html"
    client_options = {
        "base_headers": {
            "User-Agent": "Mozilla/5.0 Hermes stock-index updater",
        },
        "timeout": 30.0,
    }

    if not isinstance(exchange, str):
        raise ValueError("exchange must be ALL, SH, SZ, or BZ.")
    exchange_code = exchange.strip().upper()
    result_list = []
    if exchange_code == "ALL":
        with SseSiteClient(
            base_headers={
                **client_options["base_headers"],
                "Referer": sse_stock_list_url,
            },
            timeout=client_options["timeout"],
        ) as site_client:
            result_list.extend(site_client.fetch_stock_list(sse_stock_list_url))
        with SzseSiteClient(
            base_headers={
                **client_options["base_headers"],
                "Referer": szse_stock_list_url,
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
    elif exchange_code == "SH":
        with SseSiteClient(
            base_headers={
                **client_options["base_headers"],
                "Referer": sse_stock_list_url,
            },
            timeout=client_options["timeout"],
        ) as site_client:
            result_list = site_client.fetch_stock_list(sse_stock_list_url)
    elif exchange_code == "SZ":
        with SzseSiteClient(
            base_headers={
                **client_options["base_headers"],
                "Referer": szse_stock_list_url,
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
    else:
        raise ValueError(f"Unsupported exchange: {exchange}. Use ALL, SH, SZ, or BZ.")

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


def _normalize_stock_index_row(
    record: Mapping[str, object],
    update_date: str,
) -> tuple[str, str, str, str | None, str]:
    """Convert an SSE listing record to the stock_index table column order."""
    code = record.get("code")
    if not isinstance(code, str) or not re.fullmatch(r"\d{6}", code):
        raise ValueError(f"Invalid SSE stock code: {code!r}")

    name = record.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Missing SSE stock name for code {code}.")
    stock_name = name.strip()

    exchange = record.get("exchange", "SH")
    if not isinstance(exchange, str) or not exchange.strip():
        raise ValueError(f"Invalid SSE exchange for code {code}: {exchange!r}")
    stock_code = f"{exchange.strip().upper()}{code}"

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
