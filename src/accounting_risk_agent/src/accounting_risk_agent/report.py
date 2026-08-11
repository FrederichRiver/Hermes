"""Financial metrics report persistence."""

from pathlib import Path

import pandas as pd


def save_report(
    metrics: pd.DataFrame,
    stock_code: str,
    processed_directory: Path | str = Path("data/processed"),
) -> tuple[Path, Path]:
    """Write financial metrics to UTF-8 CSV and Excel workbooks."""
    result_directory = Path(processed_directory)
    result_directory.mkdir(parents=True, exist_ok=True)
    csv_path = result_directory / f"{stock_code}_financial_metrics.csv"
    excel_path = result_directory / f"{stock_code}_financial_metrics.xlsx"
    metrics.to_csv(csv_path, index=False, encoding="utf-8-sig")
    metrics.to_excel(excel_path, index=False)
    return csv_path, excel_path
