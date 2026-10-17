from dataclasses import asdict, fields
from collections.abc import Mapping, Sequence
from datetime import date
import logging
import re
from typing import Any, Dict, List, Type

from .mysql_meta import MySQLMeta
from .models import FundNav, StockDailyBar, StockIndexRecord, SymbolInfo
from .mysql_table import StockIndex

logger = logging.getLogger(__name__)


class MySQLTableWrapper:
    """Composition-based table wrapper that uses MySQLMeta for DB operations.

    Provides: insert, bulk_insert, select, update, delete. Works from a dataclass model.
    """

    def __init__(self, table_name: str, model: Type[Any], meta: MySQLMeta):
        self._meta = meta
        self._table_name = table_name
        self._model = model
        # derive columns from dataclass fields (exclude id)
        self._columns = [f.name for f in fields(model) if f.name != "id"]

    @property
    def table_name(self) -> str:
        return self._table_name

    @property
    def model(self) -> Type[Any]:
        return self._model

    def _row_to_dict(self, row: Any) -> Dict[str, Any]:
        d = asdict(row)
        # remove id if None
        return {k: v for k, v in d.items() if k in self._columns}

    def bulk_insert(self, rows: List[Any]) -> int:
        if not rows:
            return 0
        cols = ", ".join(f"`{c}`" for c in self._columns)
        placeholders = ", ".join(["%s"] * len(self._columns))
        sql = f"INSERT INTO `{self._table_name}` ({cols}) VALUES ({placeholders})"
        total = 0
        with self._meta.transaction():
            for r in rows:
                d = self._row_to_dict(r)
                params = tuple(d[c] for c in self._columns)
                cnt = self._meta.execute(sql, params, commit=False)
                total += max(0, cnt)
        return total

    def insert(self, row: Any) -> int:
        return self.bulk_insert([row])

    def select(self, **conds) -> List[Any]:
        if conds:
            for k in conds.keys():
                if k not in self._columns:
                    raise ValueError(f"Condition field not in columns: {k}")
            where = " AND ".join(f"`{k}`=%s" for k in conds.keys())
            sql = f"SELECT * FROM `{self._table_name}` WHERE {where}"
            params = tuple(conds[k] for k in conds.keys())
        else:
            sql = f"SELECT * FROM `{self._table_name}`"
            params = ()
        rows = self._meta.query(sql, params)
        result = []
        for r in rows:
            # Convert dates if necessary left as-is; assume DB driver returns proper types
            result.append(self._model(**r))
        return result

    def update(self, row: Any, **conds) -> int:
        if not conds:
            raise ValueError("Update requires conds to locate rows")
        for k in conds.keys():
            if k not in self._columns and k != "id":
                raise ValueError(f"Condition field not allowed: {k}")
        d = self._row_to_dict(row)
        set_clause = ", ".join(f"`{k}`=%s" for k in d.keys())
        where = " AND ".join(f"`{k}`=%s" for k in conds.keys())
        sql = f"UPDATE `{self._table_name}` SET {set_clause} WHERE {where}"
        params = tuple(d[k] for k in d.keys()) + tuple(conds[k] for k in conds.keys())
        return self._meta.execute(sql, params)

    def delete(self, **conds) -> int:
        if not conds:
            raise ValueError("Delete requires conds")
        for k in conds.keys():
            if k not in self._columns and k != "id":
                raise ValueError(f"Condition field not allowed: {k}")
        where = " AND ".join(f"`{k}`=%s" for k in conds.keys())
        sql = f"DELETE FROM `{self._table_name}` WHERE {where}"
        params = tuple(conds[k] for k in conds.keys())
        return self._meta.execute(sql, params)


class StockIndexEntity(MySQLTableWrapper):
    """Persist normalized exchange listing JSON in the ``stock_index`` table."""

    def __init__(self, meta: MySQLMeta) -> None:
        super().__init__(StockIndex.Meta.db_table, StockIndexRecord, meta)

    def upsert_sse_stocks(
        self,
        records: Sequence[Mapping[str, object]],
        update_date: date | None = None,
    ) -> int:
        """Validate, normalize, and atomically upsert exchange listing records.

        Args:
            records: JSON objects with ``code``, ``name``, and optional
                ``exchange``, ``short_name``, and ``list_date`` fields.
            update_date: Date to store in the ``update_date`` column. Defaults
                to the current local date.

        Returns:
            The total affected row count reported by MySQL.

        Raises:
            ValueError: A record contains invalid listing data.
        """
        effective_update_date = update_date or date.today()
        normalized_records = [
            self.normalize_sse_record(record, effective_update_date)
            for record in records
        ]
        if not normalized_records:
            return 0

        columns = self._columns
        placeholders = ", ".join(["%s"] * len(columns))
        column_sql = ", ".join(f"`{column}`" for column in columns)
        update_sql = ", ".join(
            f"`{column}` = VALUES(`{column}`)"
            for column in columns
            if column != "stock_code"
        )
        sql = (
            f"INSERT INTO `{self._table_name}` ({column_sql}) "
            f"VALUES ({placeholders}) "
            f"ON DUPLICATE KEY UPDATE {update_sql}"
        )

        affected_rows = 0
        with self._meta.transaction():
            for row in normalized_records:
                row_values = self._row_to_dict(row)
                params = tuple(row_values[column] for column in columns)
                affected_rows += max(
                    0,
                    self._meta.execute(sql, params, commit=False),
                )
        return affected_rows

    @staticmethod
    def normalize_sse_record(
        record: Mapping[str, object],
        update_date: date,
    ) -> StockIndexRecord:
        """Convert one exchange listing JSON object to the stock-index model."""
        if not isinstance(record, Mapping):
            raise ValueError("Each stock listing must be a JSON object.")

        code = record.get("code")
        exchange = record.get("exchange", "SH")
        supported_exchanges = {"SH", "SZ", "BZ", "US", "HK"}
        if not isinstance(exchange, str) or exchange.strip().upper() not in supported_exchanges:
            raise ValueError(f"Invalid stock exchange: {exchange!r}")
        exchange_code = exchange.strip().upper()
        if not isinstance(code, str) or not StockIndexEntity._is_valid_code(
            code,
            exchange_code,
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
            logger.warning("Truncating short_name for %s to 10 characters.", stock_code)
            short_name = short_name[:10]
        if len(stock_name) > 20:
            logger.warning("Truncating stock_name for %s to 20 characters.", stock_code)
            stock_name = stock_name[:20]

        return StockIndexRecord(
            stock_code=stock_code,
            short_name=short_name,
            stock_name=stock_name,
            publish_date=StockIndexEntity._normalize_publish_date(
                record.get("list_date")
            ),
            update_date=update_date,
        )

    @staticmethod
    def _is_valid_code(code: str, exchange: str) -> bool:
        if exchange in {"SH", "SZ", "BZ"}:
            return re.fullmatch(r"\d{6}", code) is not None
        if exchange == "US":
            return re.fullmatch(r"[A-Za-z][A-Za-z0-9.-]{0,7}", code) is not None
        return re.fullmatch(r"\d{5}", code) is not None

    @staticmethod
    def _normalize_publish_date(value: object) -> date | None:
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            raise ValueError(f"Invalid SSE listing date: {value!r}")

        try:
            return date.fromisoformat(value[:10])
        except ValueError as exc:
            raise ValueError(f"Invalid SSE listing date: {value!r}") from exc


def make_default_tables(meta: MySQLMeta) -> dict[str, MySQLTableWrapper]:
    return {
        "stock_daily": MySQLTableWrapper("stock_daily", StockDailyBar, meta),
        "fund_nav": MySQLTableWrapper("fund_nav", FundNav, meta),
        "symbol_info": MySQLTableWrapper("symbol_info", SymbolInfo, meta),
        "stock_index": StockIndexEntity(meta),
    }
