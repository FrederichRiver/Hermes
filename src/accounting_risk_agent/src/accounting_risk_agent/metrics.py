"""Core accounting financial-ratio calculation."""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class FinancialMetrics:
    """Calculate twenty core accounting metrics from normalized statements."""

    stock_code: str
    statements: pd.DataFrame

    def compute_all(self) -> pd.DataFrame:
        """Return normalized statements enriched with twenty core metrics."""
        result = self.statements.copy().sort_values("report_date").reset_index(drop=True)

        def divide(numerator: str, denominator: str) -> pd.Series:
            values = result[numerator] / result[denominator].replace(0, np.nan)
            return values.replace([np.inf, -np.inf], np.nan)

        result["current_ratio"] = divide("total_current_assets", "total_current_liabilities")
        result["quick_ratio"] = (
            (result["total_current_assets"] - result["inventory"])
            / result["total_current_liabilities"].replace(0, np.nan)
        )
        result["cash_ratio"] = divide("cash", "total_current_liabilities")
        result["debt_to_asset_ratio"] = divide("total_liabilities", "total_assets")
        result["equity_multiplier"] = divide("total_assets", "total_equity")
        result["tangible_asset_debt_ratio"] = result["total_liabilities"] / (
            result["total_assets"] - result["intangible_assets"]
        ).replace(0, np.nan)
        result["debt_to_equity_ratio"] = divide("total_liabilities", "total_equity")

        result["gross_margin"] = (
            result["revenue"] - result["operating_cost"]
        ) / result["revenue"].replace(0, np.nan)
        result["operating_margin"] = divide("operating_profit", "revenue")
        result["net_margin"] = divide("net_profit", "revenue")
        result["roe"] = divide("net_profit", "total_equity")
        result["roa"] = divide("net_profit", "total_assets")

        result["operating_cash_to_net_profit"] = divide(
            "operating_cash_flow",
            "net_profit",
        )
        result["operating_cash_to_revenue"] = divide("operating_cash_flow", "revenue")
        result["free_cash_flow"] = result["operating_cash_flow"] - result["capex"]

        result["revenue_qoq_growth"] = result["revenue"].pct_change(fill_method=None)
        result["net_profit_qoq_growth"] = result["net_profit"].pct_change(fill_method=None)

        result["current_assets_ratio"] = divide("total_current_assets", "total_assets")
        result["receivables_to_revenue"] = divide("accounts_receivable", "revenue")
        result["inventory_ratio"] = divide("inventory", "total_assets")
        return result.sort_values("report_date", ascending=False).reset_index(drop=True)
