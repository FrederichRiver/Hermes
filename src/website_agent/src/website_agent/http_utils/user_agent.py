"""User-Agent identifiers used by Hermes HTTP clients."""

DEFAULT_USER_AGENT = "Hermes/1.0 (automated HTTP client)"
DATA_AGENT_USER_AGENT = "Hermes-DataAgent/1.0 (automated data client)"
SSE_USER_AGENT = "Hermes SiteSSE/1.0 (automated market-data client)"
SINA_USER_AGENT = "Hermes SiteSina/1.0 (automated market-data client)"
SZSE_USER_AGENT = "Hermes SiteSZSE/1.0 (automated market-data client)"
BSE_USER_AGENT = "Hermes SiteBSE/1.0 (automated market-data client)"
STOCK_INDEX_USER_AGENT = "Hermes/1.0 (automated stock-index updater)"
STOCK_DATA_USER_AGENT = "Hermes/1.0 (automated stock-data recorder)"
MARKET_PRICE_USER_AGENT = "Hermes/1.0 (automated market-price recorder)"

DEFAULT_USER_AGENTS = (DEFAULT_USER_AGENT,)

__all__ = [
    "BSE_USER_AGENT",
    "DATA_AGENT_USER_AGENT",
    "DEFAULT_USER_AGENT",
    "DEFAULT_USER_AGENTS",
    "MARKET_PRICE_USER_AGENT",
    "SSE_USER_AGENT",
    "SINA_USER_AGENT",
    "STOCK_DATA_USER_AGENT",
    "STOCK_INDEX_USER_AGENT",
    "SZSE_USER_AGENT",
]
