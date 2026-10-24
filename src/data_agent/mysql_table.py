"""Application-level MySQL table declarations."""

from .mysql_meta import MySQLTable


class StockIndex(MySQLTable):
    """Declarative schema for the ``stock_index`` table."""

    class Meta:
        """Schema defined in ``docs/QTS-SDD/Server.md``."""

        db_table = "stock_index"
        fields = {
            "stock_code": "VARCHAR(10) NOT NULL",
            "short_name": "VARCHAR(10) NOT NULL",
            "stock_name": "VARCHAR(20) NOT NULL",
            "publish_date": "DATE",
            "update_date": "DATE",
        }
        primary_key = ("stock_code",)


class StockDaily(MySQLTable):
    """Declarative schema for normalized daily stock bars."""

    class Meta:
        """Schema for the ``stock_daily`` history table."""

        db_table = "stock_daily"
        fields = {
            "symbol": "VARCHAR(10) NOT NULL",
            "trade_date": "DATE NOT NULL",
            "open": "DECIMAL(18,6) NOT NULL",
            "high": "DECIMAL(18,6) NOT NULL",
            "low": "DECIMAL(18,6) NOT NULL",
            "close": "DECIMAL(18,6) NOT NULL",
            "volume": "BIGINT UNSIGNED NOT NULL",
            "amount": "DECIMAL(24,2) NOT NULL",
            "adj_factor": "DECIMAL(20,10) NOT NULL DEFAULT 1.0",
        }
        primary_key = ("symbol", "trade_date")


class StockDataTemplate(MySQLTable):
    """Declarative schema for the ``stock_data_template`` table."""

    class Meta:
        """Schema defined in ``docs/QTS-SDD/Server.md``."""

        db_table = "stock_data_template"
        fields = {
            "stock_name": "VARCHAR(20) NOT NULL",
            "update_date": "DATE NOT NULL",
            "open": "DECIMAL(8,2) NOT NULL",
            "high": "DECIMAL(8,2) NOT NULL",
            "low": "DECIMAL(8,2) NOT NULL",
            "close": "DECIMAL(8,2) NOT NULL",
            "volume": "DECIMAL(12,2) NOT NULL",
        }
        primary_key = ("update_date",)
