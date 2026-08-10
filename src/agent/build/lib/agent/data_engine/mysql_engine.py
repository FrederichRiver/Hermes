"""DatabaseEngine implementation for MySQL using PyMySQL.

Implements a `DatabaseEngine` class per docs/QTS-SDD/DatabaseEngine.
Designed for synchronous use and easy unit testing (conn/cursor can be mocked).
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Any, Callable
import logging

logger = logging.getLogger("agent.data_engine.mysql")


class DBConnectionError(Exception):
    pass


class DBOperationError(Exception):
    pass


@dataclass
class MySQLConfig:
    host: str = 'mysql'
    port: int = 3306
    user: str = 'root'
    password: str = ''
    database: str = 'hermes'
    charset: str = 'utf8mb4'
    cursorclass: Optional[Any] = None  # default to pymysql.cursors.DictCursor when connecting
    connect_timeout: int = 10
    log_sql: bool = False


class DatabaseEngine:
    """Core DatabaseEngine providing connection, CRUD and higher-level ops.

    Lazy-connect: connection established on first need. Use as context manager
    to ensure proper close: `with DatabaseEngine(cfg) as db:`
    """

    def __init__(self, cfg: MySQLConfig):
        self.cfg = cfg
        self.conn = None
        self._pymysql = None

    # ------------------ connection & context ------------------
    def connect(self):
        if self.conn:
            return
        try:
            import pymysql
            import pymysql.cursors
        except Exception as e:
            logger.exception('PyMySQL import failed')
            raise DBConnectionError('PyMySQL is required') from e

        self._pymysql = pymysql
        cursorclass = self.cfg.cursorclass or pymysql.cursors.DictCursor
        try:
            self.conn = pymysql.connect(host=self.cfg.host, port=self.cfg.port,
                                        user=self.cfg.user, password=self.cfg.password,
                                        database=self.cfg.database, charset=self.cfg.charset,
                                        cursorclass=cursorclass, connect_timeout=self.cfg.connect_timeout,
                                        autocommit=False)
        except Exception as e:
            logger.exception('Failed to connect to MySQL')
            raise DBConnectionError('Could not connect to DB') from e

    def close(self):
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                logger.exception('Error closing DB connection')
            finally:
                self.conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc:
            try:
                self.rollback()
            except Exception:
                pass
        else:
            try:
                self.commit()
            except Exception:
                pass
        self.close()

    # ------------------ transaction control ------------------
    def begin(self):
        self.connect()
        try:
            self.conn.begin()
        except Exception as e:
            logger.exception('begin transaction failed')
            raise DBOperationError from e

    def commit(self):
        if not self.conn:
            return
        try:
            self.conn.commit()
        except Exception as e:
            logger.exception('commit failed')
            raise DBOperationError from e

    def rollback(self):
        if not self.conn:
            return
        try:
            self.conn.rollback()
        except Exception as e:
            logger.exception('rollback failed')
            raise DBOperationError from e

    # ------------------ low-level execute ------------------
    def execute_raw(self, sql: str, params: Optional[tuple] = None) -> Any:
        """Execute raw SQL with parameters and return cursor or result.

        Note: SQL template may be logged (without params) when cfg.log_sql is True.
        """
        self.connect()
        if self.cfg.log_sql:
            logger.info(f'Executing SQL: {sql}')
        try:
            cur = self.conn.cursor()
            cur.execute(sql, params or ())
            return cur
        except Exception as e:
            logger.exception('execute_raw failed')
            raise DBOperationError from e

    # ------------------ basic CRUD ------------------
    def insert(self, table: str, data: Dict) -> int:
        self.connect()
        keys = ','.join(f'`{k}`' for k in data.keys())
        placeholders = ','.join(['%s'] * len(data))
        sql = f"INSERT INTO `{table}` ({keys}) VALUES ({placeholders})"
        params = tuple(data.values())
        cur = self.execute_raw(sql, params)
        affected = cur.rowcount
        try:
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return affected

    def get(self, table: str, where: Optional[Dict] = None, columns: Optional[List[str]] = None,
            limit: Optional[int] = None, order_by: Optional[str] = None) -> List[Dict]:
        self.connect()
        cols = ','.join(columns) if columns else '*'
        sql = f"SELECT {cols} FROM `{table}`"
        params: List[Any] = []
        if where:
            clauses = [f"`{k}`=%s" for k in where.keys()]
            sql += ' WHERE ' + ' AND '.join(clauses)
            params.extend(where.values())
        if order_by:
            sql += f' ORDER BY {order_by}'
        if limit:
            sql += f' LIMIT {int(limit)}'
        cur = self.execute_raw(sql, tuple(params))
        return cur.fetchall()

    def update(self, table: str, data: Dict, where: Dict) -> int:
        self.connect()
        set_clause = ','.join(f"`{k}`=%s" for k in data.keys())
        where_clause = ' AND '.join(f"`{k}`=%s" for k in where.keys())
        sql = f"UPDATE `{table}` SET {set_clause} WHERE {where_clause}"
        params = tuple(list(data.values()) + list(where.values()))
        cur = self.execute_raw(sql, params)
        affected = cur.rowcount
        try:
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return affected

    def delete(self, table: str, where: Dict) -> int:
        self.connect()
        where_clause = ' AND '.join(f"`{k}`=%s" for k in where.keys())
        sql = f"DELETE FROM `{table}` WHERE {where_clause}"
        params = tuple(where.values())
        cur = self.execute_raw(sql, params)
        affected = cur.rowcount
        try:
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return affected

    # ------------------ higher-level operations ------------------
    def bulk_insert(self, table: str, rows: List[Dict], batch_size: int = 1000) -> int:
        if not rows:
            return 0
        self.connect()
        total = 0
        keys = list(rows[0].keys())
        cols = ','.join(f'`{k}`' for k in keys)
        placeholders = ','.join(['%s'] * len(keys))
        sql = f"INSERT INTO `{table}` ({cols}) VALUES ({placeholders})"
        cur = self.conn.cursor()
        try:
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i+batch_size]
                params = [tuple(r[k] for k in keys) for r in batch]
                cur.executemany(sql, params)
                total += cur.rowcount
            self.conn.commit()
            return total
        except Exception as e:
            self.conn.rollback()
            logger.exception('bulk_insert failed')
            raise DBOperationError from e

    def upsert(self, table: str, data: Dict, conflict_keys: List[str]) -> int:
        # build insert ... on duplicate key update
        self.connect()
        keys = list(data.keys())
        cols = ','.join(f'`{k}`' for k in keys)
        placeholders = ','.join(['%s'] * len(keys))
        update_clause = ','.join(f"`{k}`=VALUES(`{k}`)" for k in keys if k not in conflict_keys)
        sql = f"INSERT INTO `{table}` ({cols}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {update_clause}"
        params = tuple(data[k] for k in keys)
        cur = self.execute_raw(sql, params)
        affected = cur.rowcount
        try:
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return affected

    def paginate(self, table: str, where: Optional[Dict] = None, page: int = 1, page_size: int = 50, order_by: Optional[str] = None) -> Dict:
        offset = (page - 1) * page_size
        items = self.get(table, where=where, limit=page_size, order_by=order_by)
        # total count
        sql = f"SELECT COUNT(1) as cnt FROM `{table}`"
        params = []
        if where:
            clauses = [f"`{k}`=%s" for k in where.keys()]
            sql += ' WHERE ' + ' AND '.join(clauses)
            params = list(where.values())
        cur = self.execute_raw(sql, tuple(params))
        total = cur.fetchone().get('cnt', 0)
        return {'items': items, 'total': total, 'page': page, 'page_size': page_size}

    def transactional(self, func: Callable):
        """Run callable within a transaction. If func raises, rollback."""
        self.connect()
        try:
            self.begin()
            res = func(self)
            self.commit()
            return res
        except Exception:
            self.rollback()
            raise

    def copy_to_table(self, src_table: str, dst_table: str, columns: List[str], chunk_size: int = 1000):
        cols = ','.join(f'`{c}`' for c in columns)
        offset = 0
        total = 0
        while True:
            sql = f"SELECT {cols} FROM `{src_table}` LIMIT {chunk_size} OFFSET {offset}"
            cur = self.execute_raw(sql)
            rows = cur.fetchall()
            if not rows:
                break
            self.bulk_insert(dst_table, rows, batch_size=chunk_size)
            total += len(rows)
            offset += chunk_size
        return total

    def execute_migration(self, sql_statements: List[str]):
        self.connect()
        try:
            self.begin()
            cur = self.conn.cursor()
            for s in sql_statements:
                cur.execute(s)
            self.commit()
        except Exception as e:
            self.rollback()
            logger.exception('execute_migration failed')
            raise DBOperationError from e


class MySQLEngine:
    """Backward-compatible thin wrapper providing a simple upsert helper."""

    def __init__(self, cfg: MySQLConfig):
        self.db = DatabaseEngine(cfg)

    def upsert_sse_stocks(self, records: List[Dict]) -> int:
        return self.db.bulk_insert('sse_stocks', records) if records else 0

    def close(self):
        self.db.close()
