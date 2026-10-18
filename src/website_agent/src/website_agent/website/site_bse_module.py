"""Beijing Stock Exchange site client."""

from typing import Any, Dict, List

from website_agent.http_utils.client import HttpClient

from .site_sse_module import SseSiteClient


class BseSiteClient(SseSiteClient):
    """Fetch and normalize Beijing Stock Exchange listing records."""

    name = "bse"
    priority = 30

    def __init__(
        self,
        config: Any | None = None,
        http_clients: dict[str, HttpClient] | None = None,
        **client_options: Any,
    ) -> None:
        client_options.setdefault(
            "base_headers",
            {
                "User-Agent": "Mozilla/5.0 Hermes BSE stock-list fetcher",
                "Referer": "https://www.bse.cn/nq/listedcompany.html",
            },
        )
        super().__init__(config, http_clients, **client_options)

    def request_url(self, task: Any) -> str:
        url = task.params.get("url", "https://www.bse.cn/nq/listedcompany.html")
        if not isinstance(url, str) or not url:
            raise ValueError("BSE stock-list task requires a valid URL.")
        return url

    def fetch_stock_list(self, url: str) -> List[Dict]:
        """Download a Beijing stock list and mark each record as ``BZ``."""
        result_list = super().fetch_stock_list(url)
        for result_record in result_list:
            result_record["exchange"] = "BZ"
        return result_list
