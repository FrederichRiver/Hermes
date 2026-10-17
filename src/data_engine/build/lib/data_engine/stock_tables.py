from typing import List, Type, Any, Dict
from dataclasses import asdict, fields
from datetime import date

from .mysql_meta import MySQLMeta
from .models import StockDailyBar, FundNav, SymbolInfo


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


def make_default_tables(meta: MySQLMeta) -> dict:
    return {
        "stock_daily": MySQLTableWrapper("stock_daily", StockDailyBar, meta),
        "fund_nav": MySQLTableWrapper("fund_nav", FundNav, meta),
        "symbol_info": MySQLTableWrapper("symbol_info", SymbolInfo, meta),
    }
