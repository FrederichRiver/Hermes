"""Week-one accounting-risk analysis entry point."""

from pathlib import Path

from .fetcher_em import fetch_all_reports
from .loader import load_financial_statements
from .metrics import FinancialMetrics
from .report import save_report


def analyze(
    stock_code: str,
    data_directory: Path | str = Path("data"),
) -> tuple[Path, Path]:
    """Fetch statements, calculate metrics, and save local reports."""
    result_directory = Path(data_directory)
    fetch_all_reports(stock_code, result_directory / "raw")
    statements = load_financial_statements(stock_code, result_directory / "raw")
    metrics = FinancialMetrics(stock_code, statements).compute_all()
    return save_report(metrics, stock_code, result_directory / "processed")
