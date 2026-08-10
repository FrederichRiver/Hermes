"""Beijing Stock Exchange site client."""

from typing import Dict, List

from .site_sse_module import SseSiteClient


class BseSiteClient(SseSiteClient):
    """Fetch and normalize Beijing Stock Exchange listing records."""

    def fetch_stock_list(self, url: str) -> List[Dict]:
        """Download a Beijing stock list and mark each record as ``BZ``."""
        result_list = super().fetch_stock_list(url)
        for result_record in result_list:
            result_record["exchange"] = "BZ"
        return result_list
