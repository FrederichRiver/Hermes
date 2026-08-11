"""Financial statement loading and normalization."""

import json
from pathlib import Path

import pandas as pd


FIELD_MAP = {
    "balance_sheet": {
        "report_date": "REPORT_DATE",
        "cash": "CURRENCY_FUNDS",
        "accounts_receivable": "ACCOUNTS_RECEIVABLE",
        "inventory": "INVENTORY",
        "total_current_assets": "TOTAL_CURRENT_ASSETS",
        "fixed_assets": "FIXED_ASSETS",
        "intangible_assets": "INTANGIBLE_ASSETS",
        "total_assets": "TOTAL_ASSETS",
        "short_term_loans": "SHORT_TERM_LOANS",
        "total_current_liabilities": "TOTAL_CURRENT_LIABILITIES",
        "total_liabilities": "TOTAL_LIABILITIES",
        "total_equity": "TOTAL_EQUITY",
    },
    "income_statement": {
        "report_date": "REPORT_DATE",
        "revenue": "TOTAL_OPERATE_INCOME",
        "operating_cost": "OPERATE_COST",
        "sales_expense": "SALE_EXPENSE",
        "admin_expense": "MANAGE_EXPENSE",
        "rd_expense": "RESEARCH_EXPENSE",
        "financial_expense": "FINANCE_EXPENSE",
        "operating_profit": "OPERATE_PROFIT",
        "total_profit": "TOTAL_PROFIT",
        "net_profit": "NETPROFIT",
    },
    "cash_flow": {
        "report_date": "REPORT_DATE",
        "operating_cash_flow": "OPERATE_CASH_FLOW",
        "investing_cash_flow": "INVEST_CASH_FLOW",
        "financing_cash_flow": "FINANCE_CASH_FLOW",
        "capex": "CONSTRUCT_INTANGIBLE_ASSET_OTHER",
    },
}


def load_financial_statements(
    stock_code: str,
    raw_directory: Path | str = Path("data/raw"),
) -> pd.DataFrame:
    """Load and merge locally cached Eastmoney financial statements by date."""
    result_directory = Path(raw_directory)
    statements = []
    for report_type in FIELD_MAP:
        result_path = result_directory / f"{stock_code}_{report_type}.json"
        if not result_path.is_file():
            raise FileNotFoundError(result_path)
        records = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(records, list) or not records:
            raise ValueError(f"{result_path} must contain a non-empty record array.")
        statements.append(normalize_statement(records, report_type))

    result_frame = statements[0]
    for statement in statements[1:]:
        result_frame = result_frame.merge(statement, on="report_date", how="outer")
    result_frame["report_date"] = pd.to_datetime(result_frame["report_date"])
    return result_frame.sort_values("report_date").reset_index(drop=True)


def normalize_statement(records: list[dict[str, object]], report_type: str) -> pd.DataFrame:
    """Normalize one Eastmoney statement record collection to canonical fields."""
    field_map = FIELD_MAP.get(report_type)
    if field_map is None:
        raise ValueError(f"Unsupported financial report type: {report_type!r}")
    frame = pd.DataFrame(records)
    normalized = pd.DataFrame()
    for output_name, source_name in field_map.items():
        normalized[output_name] = (
            frame[source_name] if source_name in frame else pd.NA
        )
    normalized["report_date"] = pd.to_datetime(normalized["report_date"]).dt.date
    for column in normalized.columns:
        if column != "report_date":
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    return normalized.drop_duplicates("report_date", keep="first")
