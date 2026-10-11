"""Shenzhen Stock Exchange site client."""

from typing import Dict, List

from .site_sse_module import SseSiteClient


class SzseSiteClient(SseSiteClient):
    """Fetch and normalize Shenzhen Stock Exchange listing records."""

    def fetch_stock_list(self, url: str) -> List[Dict]:
        """Download a Shenzhen stock list and mark each record as ``SZ``."""
        result_list = super().fetch_stock_list(url)
        for result_record in result_list:
            result_record["exchange"] = "SZ"
        return result_list
