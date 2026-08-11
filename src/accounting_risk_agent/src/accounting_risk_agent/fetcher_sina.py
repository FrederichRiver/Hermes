"""Sina Finance HTML fallback for annual financial statements."""

from pathlib import Path
import re

import pandas as pd


SINA_URLS = {
    "balance_sheet": (
        "http://money.finance.sina.com.cn/corp/go.php/"
        "vFD_BalanceSheet/stockid/{code}/ctrl/{year}/displaytype/4.phtml"
    ),
    "income_statement": (
        "http://money.finance.sina.com.cn/corp/go.php/"
        "vFD_ProfitStatement/stockid/{code}/ctrl/{year}/displaytype/4.phtml"
    ),
    "cash_flow": (
        "http://money.finance.sina.com.cn/corp/go.php/"
        "vFD_CashFlow/stockid/{code}/ctrl/{year}/displaytype/4.phtml"
    ),
}


def fetch_from_sina(
    stock_code: str,
    year: int,
    raw_directory: Path | str = Path("data/raw"),
) -> dict[str, Path]:
    """Fetch one annual set of Sina statement tables as local CSV files."""
    if not isinstance(stock_code, str) or re.fullmatch(r"\d{6}", stock_code) is None:
        raise ValueError("stock_code must be a six-digit string.")
    if not isinstance(year, int) or year < 1990:
        raise ValueError("year must be a valid reporting year.")

    result_directory = Path(raw_directory)
    result_directory.mkdir(parents=True, exist_ok=True)
    result_paths = {}
    for report_type, url_template in SINA_URLS.items():
        tables = pd.read_html(url_template.format(code=stock_code, year=year))
        if not tables:
            raise RuntimeError(f"Sina returned no {report_type} table for {stock_code}.")
        result_path = result_directory / f"{stock_code}_{report_type}_sina.csv"
        tables[0].to_csv(result_path, index=False, encoding="utf-8-sig")
        result_paths[report_type] = result_path
    return result_paths
