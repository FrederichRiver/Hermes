"""Beijing Stock Exchange site client."""

from typing import Any, Dict, List

from website_agent.http_utils.client import HttpClient
from website_agent.http_utils.user_agent import BSE_USER_AGENT

from .site_sse import SiteSSE


class BseSiteClient(SiteSSE):
    """Fetch and normalize Beijing Stock Exchange listing records."""

    name = "bse"
    priority = 30

    def __init__(
        self,
        config: Any | None = None,
        http_clients: list[HttpClient] | None = None,
        **client_options: Any,
    ) -> None:
        client_options.setdefault(
            "base_headers",
            {
                "User-Agent": BSE_USER_AGENT,
                "Referer": "https://www.bse.cn/nq/listedcompany.html",
            },
        )
        super().__init__(config, http_clients, **client_options)

    def request_url(self, task: Any) -> str:
        url = task.params.get("url", "https://www.bse.cn/nq/listedcompany.html")
        if not isinstance(url, str) or not url:
            raise ValueError("BSE stock-list task requires a valid URL.")
        return url

    def supports(self, task_type: str) -> bool:
        return task_type in {"symbol_list", "stock_list"}

    def _fetch_stock_list_from_url(self, url: str) -> List[Dict]:
        """Download a Beijing stock list and mark each record as ``BZ``."""
        result_list = super()._fetch_stock_list_from_url(url)
        for result_record in result_list:
            result_record["exchange"] = "BZ"
        return result_list
