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
