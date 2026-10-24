"""WebsiteAgent package."""

from .agent import BaseSite, CircuitState, FetchTask, WebsiteAgent
from .eastmoney_site import (
    EASTMONEY_HK_STOCK_LIST_FILTER,
    EASTMONEY_STOCK_KLINE_API_URL,
    EASTMONEY_STOCK_LIST_API_URL,
    EASTMONEY_US_STOCK_LIST_FILTER,
    EastMoneySite,
    EastmoneySiteClient,
    parse_eastmoney_daily_kline,
    parse_eastmoney_daily_klines,
)
from .site_bse_module import BseSiteClient
from .site_eastmoney_market_module import (
    EastmoneyMarketSiteClient,
    parse_eastmoney_market_daily_klines,
)
from ..http_utils.user_agent import SINA_USER_AGENT
from .site_sina import (
    SINA_STOCK_KLINE_API_URL,
    SINA_STOCK_KLINE_MAX_ROWS,
    SiteSina,
    parse_sina_daily_klines,
)
from .site_sse import (
    SSE_FUND_LIST_API_URL,
    SSE_INDEX_LIST_API_URL,
    SSE_INDEX_OVERVIEW_API_URL,
    SSE_INDEX_OVERVIEW_SQL_ID,
    SSE_STOCK_LIST_API_URL,
    SSEStockCode,
    SiteSSE,
    SseSiteClient,
    parse_sse_share_list,
)
from .site_szse_module import (
    SZSE_FUND_LIST_API_URL,
    SZSE_INDEX_LIST_API_URL,
    SZSE_STOCK_LIST_API_URL,
    SzseSiteClient,
)

__all__ = [
    "BaseSite",
    "BseSiteClient",
    "CircuitState",
    "EastMoneySite",
    "EastmoneyMarketSiteClient",
    "EastmoneySiteClient",
    "EASTMONEY_HK_STOCK_LIST_FILTER",
    "EASTMONEY_STOCK_KLINE_API_URL",
    "EASTMONEY_STOCK_LIST_API_URL",
    "EASTMONEY_US_STOCK_LIST_FILTER",
    "FetchTask",
    "parse_eastmoney_daily_kline",
    "parse_eastmoney_daily_klines",
    "parse_eastmoney_market_daily_klines",
    "parse_sina_daily_klines",
    "parse_sse_share_list",
    "SINA_STOCK_KLINE_API_URL",
    "SINA_STOCK_KLINE_MAX_ROWS",
    "SINA_USER_AGENT",
    "SSE_FUND_LIST_API_URL",
    "SSE_INDEX_LIST_API_URL",
    "SSE_INDEX_OVERVIEW_API_URL",
    "SSE_INDEX_OVERVIEW_SQL_ID",
    "SSE_STOCK_LIST_API_URL",
    "SSEStockCode",
    "SiteSSE",
    "SiteSina",
    "SseSiteClient",
    "SZSE_FUND_LIST_API_URL",
    "SZSE_INDEX_LIST_API_URL",
    "SZSE_STOCK_LIST_API_URL",
    "SzseSiteClient",
    "WebsiteAgent",
]
