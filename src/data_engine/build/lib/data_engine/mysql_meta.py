import contextlib
import typing
import logging
import os
import re
import pymysql

logger = logging.getLogger(__name__)


class MySQLMeta:
        """Lightweight MySQL connection manager and helper utilities.

        This class centralises connection handling so callers (services, agents,
        crawlers) don't need repeated boilerplate to connect/close/perform
        statements. It exposes:

        - `connect()` / `close()`: manage a single persistent connection.
        - `cursor()` context manager: get a cursor that will be closed after use.
        - `execute()` / `query()`: convenience wrappers around cursor execution.
        - `transaction()` context manager: commit on success, rollback on error.

        Usage patterns:

        - Simple query: ``db = MySQLMeta(...); rows = db.query(sql, params)``
        - Transaction block:
            ``with db.transaction(): db.execute(...); db.execute(...)``
        - Context-manager convenience (recommended):
            ``with MySQLMeta(...).connect() as conn: ...``

        Notes and design choices:
        - The underlying driver used is PyMySQL (cursor returns dict rows).
        - The class keeps a single connection in ``self._conn`` for reuse by subsequent
            calls. Callers should call ``close()`` when the object is no longer needed
            (e.g. application shutdown) to release sockets.
        - For high-concurrency applications consider using a connection pool
            (not implemented here) or SQLAlchemy's engine.

        Thread-safety: this class is NOT thread-safe. Do not share instances
        across threads without external synchronization.
        """

        def __init__(self, host: typing.Optional[str], port: typing.Optional[int], user: typing.Optional[str], password: typing.Optional[str], database: typing.Optional[str] = None, charset: str = "utf8mb4"):
                """Initialise connection configuration but do not connect immediately.

                Parameters
                - host, port, user, password: connection credentials.
                - database: optional default database name.
                - charset: client charset; default utf8mb4 to support full Unicode.
                """
                # Allow credentials to be provided via environment variables as a
                # secure alternative to hardcoding. Environment variable names used
                # (in order of precedence):
                #   - HOST: MYSQL_HOST
                #   - PORT: MYSQL_PORT
                #   - USER: MYSQL_USER
                #   - PASSWORD: MYSQL_PASSWORD or DB_PASSWORD
                #   - DATABASE: MYSQL_DB or MYSQL_DATABASE
                host = host or os.getenv("MYSQL_HOST") or os.getenv("DB_HOST") or "127.0.0.1"
                port = int(port) if port is not None else int(os.getenv("MYSQL_PORT", os.getenv("DB_PORT", 3306)))
                user = user or os.getenv("MYSQL_USER") or os.getenv("DB_USER")
                password = password or os.getenv("MYSQL_PASSWORD") or os.getenv("DB_PASSWORD")
                database = database or os.getenv("MYSQL_DB") or os.getenv("MYSQL_DATABASE") or os.getenv("DB_NAME")

                self._cfg = dict(host=host, port=port, user=user, password=password, db=database, charset=charset, cursorclass=pymysql.cursors.DictCursor)
                self._conn: typing.Optional[pymysql.connections.Connection] = None

        def connect(self):
            """Open and return a live connection.

            If a connection already exists and is open, it will be returned.
            The connection is stored on the instance for reuse by subsequent
            calls. Any connection errors from PyMySQL are propagated to callers
            so they can decide how to handle retries.
            """
            if self._conn and getattr(self._conn, "open", False):
                return self._conn
            logger.debug("Opening MySQL connection to %s:%s db=%s", self._cfg.get("host"), self._cfg.get("port"), self._cfg.get("db"))
            self._conn = pymysql.connect(**self._cfg)
            return self._conn

        def close(self):
            """Close and clear the stored connection (no-op if already closed)."""
            if self._conn:
                try:
                    logger.debug("Closing MySQL connection")
                    self._conn.close()
                finally:
                    self._conn = None

        @contextlib.contextmanager
        def cursor(self):
            """Yield a cursor and ensure it's closed after use.

            Yields a PyMySQL cursor that returns dict rows. The caller should
            not commit/rollback directly when using this helper; prefer
            ``execute``/``query`` or the ``transaction`` context manager.
            """
            conn = self.connect()
            cur = conn.cursor()
            try:
                yield cur
            finally:
                try:
                    cur.close()
                except Exception:
                    logger.exception("Error closing cursor")

        def execute(self, sql: str, params: typing.Optional[typing.Tuple] = None, commit: bool = True) -> int:
            """Execute a statement and optionally commit.

            Returns the statement's affected rowcount. Parameters should be a
            sequence matching the statement's placeholders. By default the
            method commits after execution; set ``commit=False`` when executing
            multiple statements inside a transaction (use ``transaction()``).
            """
            with self.cursor() as cur:
                logger.debug("Executing SQL: %s params=%s", sql, params)
                cur.execute(sql, params or ())
                if commit:
                    self._conn.commit()
                return cur.rowcount

        def query(self, sql: str, params: typing.Optional[typing.Tuple] = None) -> typing.List[dict]:
            """Execute a SELECT-style query and return list of dict rows."""
            with self.cursor() as cur:
                logger.debug("Querying SQL: %s params=%s", sql, params)
                cur.execute(sql, params or ())
                return cur.fetchall()

        @contextlib.contextmanager
        def transaction(self):
            """Transaction context manager. Commits on success, rolls back on exception."""
            conn = self.connect()
            try:
                logger.debug("Begin transaction")
                yield
                conn.commit()
                logger.debug("Transaction committed")
            except Exception:
                logger.exception("Transaction failed, rolling back")
                conn.rollback()
                raise

        # Make MySQLMeta usable as a context manager directly for simple usage
        def __enter__(self):
            return self.connect()

        def __exit__(self, exc_type, exc, tb):
            # On context exit we close the underlying connection
            try:
                if exc:
                    logger.debug("Context manager exiting with exception, closing connection")
            finally:
                self.close()


class MySQLTable(MySQLMeta):
    """Base class for entity tables and their schema operations."""

    def create_table(self, table_sql: typing.Optional[str] = None):
        """Create a table from SQL or from the subclass's nested ``Meta`` class.

        A declarative table subclass can define its schema as follows::

            class StockTable(MySQLTable):
                class Meta:
                    db_table = "stocks"
                    fields = {
                        "id": "INT AUTO_INCREMENT PRIMARY KEY",
                        "code": "VARCHAR(64) NOT NULL",
                    }
                    indexes = {"idx_stocks_code": ("code",)}
                    engine = "InnoDB"
                    charset = "utf8mb4"

            StockTable(...).create_table()

        ``table_sql`` remains supported for callers that need a complete custom
        ``CREATE TABLE`` statement.

        Args:
            table_sql: Complete ``CREATE TABLE`` statement. When omitted, generate
                it from the nested ``Meta`` declaration.

        Returns:
            The affected row count returned by MySQL.

        Raises:
            ValueError: The nested ``Meta`` declaration is missing or invalid.
        """
        return self.execute(table_sql or self._build_create_table_sql())

    def _build_create_table_sql(self) -> str:
        """Build a ``CREATE TABLE`` statement from the nested ``Meta`` class."""
        meta = getattr(self, "Meta", None)
        if meta is None:
            raise ValueError(
                "create_table() without SQL requires a nested Meta class."
            )

        table_name = self._meta_table_name(meta)
        fields = getattr(meta, "fields", None)
        if not isinstance(fields, dict) or not fields:
            raise ValueError("Meta.fields must be a non-empty dictionary.")

        definitions = [
            f"{self._quote_identifier(name)} {self._field_definition(definition)}"
            for name, definition in fields.items()
        ]
        definitions.extend(self._primary_key_definition(meta))
        definitions.extend(self._unique_together_definitions(meta))
        definitions.extend(self._index_definitions(meta))

        if_not_exists = getattr(meta, "if_not_exists", True)
        if not isinstance(if_not_exists, bool):
            raise ValueError("Meta.if_not_exists must be a boolean.")
        existence_clause = "IF NOT EXISTS " if if_not_exists else ""
        return (
            f"CREATE TABLE {existence_clause}{self._quote_identifier(table_name)} "
            f"({', '.join(definitions)}){self._table_options(meta)}"
        )

    @staticmethod
    def _meta_table_name(meta: type) -> str:
        """Return the table name declared by a nested ``Meta`` class."""
        table_name = getattr(meta, "db_table", None)
        if not isinstance(table_name, str):
            raise ValueError("Meta.db_table must be a table name string.")
        return table_name

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        """Quote a valid MySQL identifier."""
        if not isinstance(identifier, str) or not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_$]*", identifier
        ):
            raise ValueError(f"Invalid MySQL identifier: {identifier!r}")
        return f"`{identifier}`"

    @staticmethod
    def _field_definition(definition: typing.Any) -> str:
        """Validate and return a field SQL definition."""
        if not isinstance(definition, str) or not definition.strip():
            raise ValueError("Each Meta.fields value must be a non-empty SQL string.")
        if ";" in definition or "\x00" in definition:
            raise ValueError("Field definitions cannot contain statement delimiters.")
        return definition.strip()

    def _primary_key_definition(self, meta: type) -> typing.List[str]:
        """Build an optional composite primary-key constraint."""
        primary_key = getattr(meta, "primary_key", None)
        if primary_key is None:
            return []
        return [f"PRIMARY KEY ({self._quote_identifiers(primary_key)})"]

    def _unique_together_definitions(self, meta: type) -> typing.List[str]:
        """Build composite unique constraints declared by ``Meta``."""
        unique_together = getattr(meta, "unique_together", ())
        if not isinstance(unique_together, (list, tuple)):
            raise ValueError("Meta.unique_together must be a sequence of field groups.")
        return [
            f"UNIQUE ({self._quote_identifiers(fields)})"
            for fields in unique_together
        ]

    def _index_definitions(self, meta: type) -> typing.List[str]:
        """Build indexes declared by an ``{index_name: fields}`` mapping."""
        indexes = getattr(meta, "indexes", {})
        if not isinstance(indexes, dict):
            raise ValueError("Meta.indexes must be a dictionary of index fields.")
        return [
            f"INDEX {self._quote_identifier(name)} "
            f"({self._quote_identifiers(fields)})"
            for name, fields in indexes.items()
        ]

    def _quote_identifiers(self, identifiers: typing.Any) -> str:
        """Quote a non-empty sequence of field names."""
        if (
            not isinstance(identifiers, (list, tuple))
            or not identifiers
        ):
            raise ValueError("Field groups must be non-empty lists or tuples.")
        return ", ".join(self._quote_identifier(name) for name in identifiers)

    @staticmethod
    def _table_options(meta: type) -> str:
        """Build supported MySQL storage options from ``Meta``."""
        options = []
        for attribute, sql_name in (
            ("engine", "ENGINE"),
            ("charset", "DEFAULT CHARSET"),
            ("collation", "COLLATE"),
        ):
            value = getattr(meta, attribute, None)
            if value is None:
                continue
            if not isinstance(value, str) or not re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_$]*", value
            ):
                raise ValueError(
                    f"Meta.{attribute} must be a valid MySQL identifier."
                )
            options.append(f"{sql_name}={value}")
        return f" {' '.join(options)}" if options else ""

    def drop_table(
        self,
        table_name: typing.Optional[str] = None,
        if_exists: bool = True,
    ):
        """Drop this entity table or an explicitly supplied table."""
        if table_name is None:
            meta = getattr(self, "Meta", None)
            if meta is None:
                raise ValueError(
                    "drop_table() without a table name requires a nested Meta class."
                )
            table_name = self._meta_table_name(meta)
        sql = (
            f"DROP TABLE {'IF EXISTS ' if if_exists else ''}"
            f"{self._quote_identifier(table_name)}"
        )
        return self.execute(sql)

    def alter_table(self, alteration: str):
        """Apply an ``ALTER TABLE`` clause to this entity table.

        Args:
            alteration: The clause after the table name, such as
                ``"ADD COLUMN `industry` VARCHAR(64)"``.

        Returns:
            The affected row count returned by MySQL.

        Raises:
            ValueError: The table declaration or alteration clause is invalid.
        """
        if not isinstance(alteration, str) or not alteration.strip():
            raise ValueError("alteration must be a non-empty SQL clause.")
        if ";" in alteration or "\x00" in alteration:
            raise ValueError("alteration cannot contain statement delimiters.")

        meta = getattr(self, "Meta", None)
        if meta is None:
            raise ValueError("alter_table() requires a nested Meta class.")
        table_name = self._meta_table_name(meta)
        sql = f"ALTER TABLE {self._quote_identifier(table_name)} {alteration.strip()}"
        return self.execute(sql)
