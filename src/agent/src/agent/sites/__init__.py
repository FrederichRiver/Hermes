"""Site-specific scrapers for DataAgent"""
from .site_bse_module import BseSiteClient
from .site_eastmoney_module import (
    EASTMONEY_HK_STOCK_LIST_FILTER,
    EASTMONEY_STOCK_LIST_API_URL,
    EASTMONEY_US_STOCK_LIST_FILTER,
    EastmoneySiteClient,
)
from .site_eastmoney_market_module import EastmoneyMarketSiteClient
from .site_sse_module import (
    SSE_FUND_LIST_API_URL,
    SSE_INDEX_LIST_API_URL,
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
    'BseSiteClient',
    'EastmoneySiteClient',
    'EastmoneyMarketSiteClient',
    'EASTMONEY_HK_STOCK_LIST_FILTER',
    'EASTMONEY_STOCK_LIST_API_URL',
    'EASTMONEY_US_STOCK_LIST_FILTER',
    'SSE_FUND_LIST_API_URL',
    'SSE_INDEX_LIST_API_URL',
    'SseSiteClient',
    'SZSE_FUND_LIST_API_URL',
    'SZSE_INDEX_LIST_API_URL',
    'SzseSiteClient',
    'SZSE_STOCK_LIST_API_URL',
    'parse_sse_share_list',
]
