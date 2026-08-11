"""Raw Eastmoney financial-statement field inspection."""

import json
from pathlib import Path

from .fetcher_em import REPORT_TYPES


def probe_stock(
    stock_code: str,
    raw_directory: Path | str = Path("data/raw"),
) -> dict[str, list[str]]:
    """Return available field names for each locally cached report."""
    result_directory = Path(raw_directory)
    fields = {}
    for report_type in REPORT_TYPES:
        result_path = result_directory / f"{stock_code}_{report_type}.json"
        if not result_path.is_file():
            raise FileNotFoundError(result_path)
        records = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(records, list) or not records or not isinstance(records[0], dict):
            raise ValueError(f"{result_path} must contain a non-empty object array.")
        fields[report_type] = sorted(records[0])
    return fields
