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
from .site_registry import SiteRegistry
from .site_sse_module import (
    SSE_FUND_LIST_API_URL,
    SSE_INDEX_LIST_API_URL,
    SSE_STOCK_LIST_API_URL,
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
    "parse_sse_share_list",
    "SSE_FUND_LIST_API_URL",
    "SSE_INDEX_LIST_API_URL",
    "SSE_STOCK_LIST_API_URL",
    "SiteRegistry",
    "SseSiteClient",
    "SZSE_FUND_LIST_API_URL",
    "SZSE_INDEX_LIST_API_URL",
    "SZSE_STOCK_LIST_API_URL",
    "SzseSiteClient",
    "WebsiteAgent",
]
