"""Eastmoney financial-statement API client with local JSON caching."""

from collections.abc import Callable
import json
from pathlib import Path
import re
import time

import requests


EASTMONEY_FINANCIAL_API_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
REPORT_TYPES = {
    "balance_sheet": "RPT_DMSK_FN_BALANCE",
    "income_statement": "RPT_DMSK_FN_INCOME",
    "cash_flow": "RPT_DMSK_FN_CASHFLOW",
}
_HEADERS = {
    "User-Agent": "Mozilla/5.0 Hermes accounting-risk-agent",
    "Referer": "https://data.eastmoney.com/",
}


def fetch_financial_report(
    stock_code: str,
    report_type: str,
    raw_directory: Path | str = Path("data/raw"),
    *,
    force_update: bool = False,
    session: requests.Session | None = None,
    request_interval: float = 0.5,
    sleeper: Callable[[float], None] = time.sleep,
) -> Path:
    """Fetch one statement from Eastmoney and persist its raw records as JSON."""
    _validate_stock_code(stock_code)
    report_name = REPORT_TYPES.get(report_type)
    if report_name is None:
        raise ValueError(f"Unsupported financial report type: {report_type!r}")
    if request_interval < 0:
        raise ValueError("request_interval must not be negative.")

    result_directory = Path(raw_directory)
    result_directory.mkdir(parents=True, exist_ok=True)
    result_path = result_directory / f"{stock_code}_{report_type}.json"
    if result_path.exists() and not force_update:
        return result_path

    result_session = session or requests.Session()
    response = result_session.get(
        EASTMONEY_FINANCIAL_API_URL,
        params={
            "reportName": report_name,
            "columns": "ALL",
            "filter": f'(SECURITY_CODE="{stock_code}")',
            "pageSize": "500",
            "pageNumber": "1",
            "sortColumns": "REPORT_DATE",
            "sortTypes": "-1",
            "source": "WEB",
            "client": "WEB",
        },
        headers=_HEADERS,
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not payload.get("success"):
        raise RuntimeError(f"Eastmoney financial API failed for {stock_code}.")
    result = payload.get("result")
    records = result.get("data") if isinstance(result, dict) else None
    if not isinstance(records, list) or not records:
        raise RuntimeError(f"Eastmoney returned no {report_type} data for {stock_code}.")

    temporary_path = result_path.with_name(f"{result_path.name}.tmp")
    try:
        temporary_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(result_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    sleeper(request_interval)
    return result_path


def fetch_all_reports(
    stock_code: str,
    raw_directory: Path | str = Path("data/raw"),
    **kwargs: object,
) -> dict[str, Path]:
    """Fetch balance sheet, income statement, and cash-flow statement."""
    return {
        report_type: fetch_financial_report(
            stock_code,
            report_type,
            raw_directory,
            **kwargs,
        )
        for report_type in REPORT_TYPES
    }


def _validate_stock_code(stock_code: str) -> None:
    """Validate a mainland six-digit stock code."""
    if not isinstance(stock_code, str) or re.fullmatch(r"\d{6}", stock_code) is None:
        raise ValueError("stock_code must be a six-digit string.")
