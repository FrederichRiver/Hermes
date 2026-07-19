# Hermes Quant Trading System (application package)
# Allow using PyMySQL as a drop-in replacement for MySQLdb when installed
try:
	import pymysql
	pymysql.install_as_MySQLdb()
except Exception:
	# If PyMySQL is not installed, fall back to system MySQLdb (mysqlclient)
	pass
