"""Shanghai Stock Exchange (SSE) site scraper utilities.

This module provides a small site client for fetching the SSE listing page
and producing a normalized list of securities suitable for database storage.
The parser prefers a DOM-based extraction (BeautifulSoup) and falls back to
a regex-based heuristic when structure differs.
"""

import json
import re
import time
from typing import Any, Dict, List

from bs4 import BeautifulSoup

from website_agent.http_utils.client import HttpClient
from website_agent.http_utils.user_agent import SSE_USER_AGENT
from website_agent.website.agent import BaseSite
from utils.logging import get_logger


logger = get_logger(__name__)

SSE_STOCK_LIST_API_URL = "https://query.sse.com.cn/sseQuery/commonQuery.do"
SSE_INDEX_LIST_API_URL = "https://query.sse.com.cn/commonSoaQuery.do"
SSE_FUND_LIST_API_URL = SSE_INDEX_LIST_API_URL
SSE_INDEX_OVERVIEW_API_URL = "https://query.sse.com.cn/commonQuery.do"
SSE_INDEX_OVERVIEW_SQL_ID = "COMMON_SSE_SJ_SZZS_ZDZSJYBBXXX"
SSE_STOCK_TYPES = ("1", "2", "8")
SSE_STOCK_LIST_PAGE_SIZE = 25
SSE_FUND_SUBCLASSES = (
    "01",
    "02",
    "03",
    "04",
    "05",
    "06",
    "07",
    "08",
    "09",
    "10",
    "11",
    "12",
    "31",
)
SSE_STOCK_LIST_PARAMETERS = {
    "isPagination": "true",
    "sqlId": "COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L",
    "REG_PROVINCE": "",
    "CSRC_CODE": "",
    "STOCK_CODE": "",
    "COMPANY_STATUS": "2,4,5,7,8",
    "type": "inParams",
    "pageHelp.cacheSize": "1",
    "pageHelp.beginPage": "1",
    "pageHelp.pageSize": str(SSE_STOCK_LIST_PAGE_SIZE),
}
SSE_INDEX_LIST_PARAMETERS = {
    "jsonCallBack": "callback",
    "isPagination": "true",
    "sqlId": "DB_SZZSLB_ZSLB",
    "pageHelp.cacheSize": "1",
    "pageHelp.beginPage": "1",
    "pageHelp.pageSize": "100",
}
SSE_FUND_LIST_PARAMETERS = {
    "jsonCallBack": "callback",
    "isPagination": "true",
    "sqlId": "FUND_LIST",
    "fundType": "00",
    "pageHelp.cacheSize": "1",
    "pageHelp.beginPage": "1",
    "pageHelp.pageSize": "100",
}


class SiteSSE(BaseSite):
    """上海证券交易所数据抓取器，通过组合持有的 HttpClient 发送请求。"""

    name = "sse"
    priority = 10
    url = {
        "symbol_list": SSE_STOCK_LIST_API_URL,
        "stock_list": SSE_STOCK_LIST_API_URL,
        "index_list": SSE_INDEX_LIST_API_URL,
        "fund_list": SSE_FUND_LIST_API_URL,
        "sh_index": SSE_INDEX_OVERVIEW_API_URL,
    }

    def __init__(
        self,
        config: Any | None = None,
        **client_options: Any,
    ) -> None:
        self._site_http_clients: list[HttpClient] = [
            SSEStockCode(**client_options)
        ]
        super().__init__(config, self._site_http_clients)

    @classmethod
    def _parse_share_list(cls, text: str) -> list[dict[str, Any]]:
        if not text:
            return []

        records = []
        soup = BeautifulSoup(text, "html.parser")
        for row in soup.select("table tr"):
            columns = [
                cell.get_text(strip=True)
                for cell in row.find_all(["td", "th"])
            ]
            if not columns:
                continue
            joined_text = " ".join(columns)
            match = re.search(r"\b(\d{6})\b", joined_text)
            if match is None:
                continue
            code = match.group(1)
            name = next(
                (
                    columns[index + 1]
                    for index, column in enumerate(columns[:-1])
                    if code in column
                ),
                columns[0],
            )
            records.append(
                {
                    "code": code,
                    "name": name,
                    "exchange": "SH",
                    "list_date": None,
                }
            )

        if records:
            return records
        for anchor in soup.find_all("a"):
            match = re.match(
                r"^(\d{6})\s*[-–—]?\s*(.+)$",
                anchor.get_text(strip=True),
            )
            if match is not None:
                records.append(
                    {
                        "code": match.group(1),
                        "name": match.group(2),
                        "exchange": "SH",
                        "list_date": None,
                    }
                )
        return records

    @classmethod
    def _parse_stock_list_response(
        cls,
        text: str,
    ) -> tuple[list[dict[str, Any]], int]:
        response = cls._parse_jsonp_response(text, "stock")
        page_help = cls._get_page_help(response, "stock")
        rows = page_help.get("data")
        if not isinstance(rows, list):
            raise ValueError("SSE stock-list response does not contain stock rows.")

        records = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            stock_type = row.get("STOCK_TYPE")
            code = (
                row.get("B_STOCK_CODE")
                if str(stock_type) == "2"
                else row.get("A_STOCK_CODE")
            )
            name = row.get("SEC_NAME_CN")
            if not isinstance(code, str) or not re.fullmatch(r"\d{6}", code):
                continue
            if not isinstance(name, str) or not name.strip():
                continue
            records.append(
                {
                    "code": code,
                    "name": name.strip(),
                    "exchange": "SH",
                    "list_date": cls._normalize_list_date(row.get("LIST_DATE")),
                }
            )
        page_count = cls._get_page_count(page_help, "stock")
        if page_count < 1:
            raise ValueError("SSE stock-list response has an invalid page count.")
        return records, page_count

    @classmethod
    def _parse_index_list_response(
        cls,
        text: str,
    ) -> tuple[list[dict[str, Any]], int]:
        response = cls._parse_jsonp_response(text, "index")
        page_help = cls._get_page_help(response, "index")
        rows = page_help.get("data")
        if not isinstance(rows, list):
            raise ValueError("SSE index-list response does not contain index rows.")

        records = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = row.get("indexCode")
            name = row.get("indexName")
            if code in (None, "", "-"):
                continue
            if not isinstance(code, str) or not re.fullmatch(r"[A-Z0-9]{6}", code):
                raise ValueError(f"Invalid SSE index code: {code!r}")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"Missing SSE index name for code {code}.")
            records.append(
                {
                    "code": code,
                    "name": name.strip(),
                    "exchange": "SH",
                    "list_date": cls._normalize_list_date(row.get("launchDay")),
                }
            )
        return records, cls._get_page_count(page_help, "index")

    @classmethod
    def _parse_fund_list_response(
        cls,
        text: str,
    ) -> tuple[list[dict[str, Any]], int]:
        response = cls._parse_jsonp_response(text, "fund")
        page_help = cls._get_page_help(response, "fund")
        rows = page_help.get("data")
        if not isinstance(rows, list):
            raise ValueError("SSE fund-list response does not contain fund rows.")

        records = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = row.get("fundCode")
            name = row.get("fundAbbr")
            if not isinstance(code, str) or not re.fullmatch(r"\d{6}", code):
                raise ValueError(f"Invalid SSE fund code: {code!r}")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"Missing SSE fund name for code {code}.")
            records.append(
                {
                    "code": code,
                    "name": name.strip(),
                    "exchange": "SH",
                    "list_date": cls._normalize_list_date(
                        row.get("listingDate")
                    ),
                }
            )
        return records, cls._get_page_count(page_help, "fund")

    @staticmethod
    def _parse_jsonp_response(text: str, security_type: str) -> dict[str, Any]:
        match = re.fullmatch(
            r"\s*(?:[\w$]+\s*)?\((.*)\)\s*;?\s*",
            text,
            flags=re.DOTALL,
        )
        if match is None:
            raise ValueError(
                f"SSE {security_type}-list response is not valid JSONP."
            )
        response = json.loads(match.group(1))
        if not isinstance(response, dict) or response.get("success") == "false":
            raise RuntimeError(
                f"SSE {security_type}-list query failed: {response!r}"
            )
        return response

    @staticmethod
    def _get_page_help(
        response: dict[str, Any],
        security_type: str,
    ) -> dict[str, Any]:
        page_help = response.get("pageHelp")
        if not isinstance(page_help, dict):
            raise ValueError(
                f"SSE {security_type}-list response does not contain pageHelp."
            )
        return page_help

    @staticmethod
    def _get_page_count(
        page_help: dict[str, Any],
        security_type: str,
    ) -> int:
        page_count = page_help.get("pageCount", 1)
        if not isinstance(page_count, int) or page_count < 0:
            raise ValueError(
                f"SSE {security_type}-list response has an invalid page count."
            )
        return page_count

    @staticmethod
    def _normalize_list_date(value: object) -> str | None:
        if value is None or value in ("", "-"):
            return None
        if not isinstance(value, str):
            raise ValueError(f"Invalid SSE list date: {value!r}")
        if re.fullmatch(r"\d{8}", value):
            return f"{value[:4]}-{value[4:6]}-{value[6:]}"
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return value
        raise ValueError(f"Invalid SSE list date: {value!r}")

    @classmethod
    def _normalize_stock_records(
        cls,
        records: list[dict[str, Any]],
    ) -> list[dict[str, str | None]]:
        normalized_records = []
        for record in records:
            code = record.get("code")
            name = record.get("name")
            if not isinstance(code, str) or not code.strip().isdigit():
                continue
            if not isinstance(name, str) or not name.strip():
                continue
            normalized_records.append(
                {
                    "code": code.strip(),
                    "name": name.strip(),
                    "exchange": str(record.get("exchange", "SH")),
                    "list_date": record.get("list_date"),
                }
            )
        return normalized_records

    def fetch_symbol_list(self, task: Any) -> List[Dict]:
        """Fetch the symbol-list task independently from the other crawlers."""
        try:
            url = task.params.get("url", self.url[task.task_type])
        except KeyError as exc:
            raise ValueError(
                f"Unsupported SSE task type: {task.task_type!r}"
            ) from exc
        if not isinstance(url, str) or not url:
            raise ValueError("SSE task requires a valid URL.")
        if url == SSE_STOCK_LIST_API_URL:
            return self.fetch_stock_code()
        return self._fetch_stock_list_from_url(url)

    def fetch_stock_list(self, task: Any) -> List[Dict]:
        """Fetch the stock-list task independently from the other crawlers."""
        try:
            url = task.params.get("url", self.url[task.task_type])
        except KeyError as exc:
            raise ValueError(
                f"Unsupported SSE task type: {task.task_type!r}"
            ) from exc
        if not isinstance(url, str) or not url:
            raise ValueError("SSE task requires a valid URL.")
        if url == SSE_STOCK_LIST_API_URL:
            return self.fetch_stock_code()
        return self._fetch_stock_list_from_url(url)

    def fetch_index_list_task(self, task: Any) -> List[Dict]:
        """Fetch the index-list task using its configured endpoint."""
        try:
            url = task.params.get("url", self.url[task.task_type])
        except KeyError as exc:
            raise ValueError(
                f"Unsupported SSE task type: {task.task_type!r}"
            ) from exc
        if not isinstance(url, str) or not url:
            raise ValueError("SSE task requires a valid URL.")
        return self.fetch_index_list(url)

    def fetch_fund_list_task(self, task: Any) -> List[Dict]:
        """Fetch the fund-list task using its configured endpoint."""
        try:
            url = task.params.get("url", self.url[task.task_type])
        except KeyError as exc:
            raise ValueError(
                f"Unsupported SSE task type: {task.task_type!r}"
            ) from exc
        if not isinstance(url, str) or not url:
            raise ValueError("SSE task requires a valid URL.")
        return self.fetch_fund_list(url)

    def fetch_stock_code(self) -> list[dict[str, str | None]]:
        """Fetch all SSE stock listings as JSON-compatible records.

        Returns:
            A list of JSON-compatible stock records. Each item contains
            ``code``, ``name``, ``exchange``, and ``list_date``.
        """
        return self._site_http_clients[0].fetch_stock_code()

    def fetch_sh_index(self) -> list[dict[str, Any]]:
        """Fetch the SSE index overview through the owned HTTP client."""
        return self._site_http_clients[0].fetch_sh_index()

    def _fetch_stock_list_from_url(self, url: str) -> list[dict[str, str | None]]:
        """Fetch the supplied static listing URL for exchange subclasses."""
        response = self._http_clients[0].get(url)
        raw_records = self._parse_share_list(response.text)
        result_records = self._normalize_stock_records(raw_records)
        logger.info(f"SiteSSE parsed {len(result_records)} records from {url}.")
        return result_records

    def fetch_index_list(
        self,
        url: str = SSE_INDEX_LIST_API_URL,
    ) -> List[Dict]:
        """Download the official SSE index list.

        Args:
            url: The SSE index-list API endpoint.

        Returns:
            Normalized index records with ``SH`` as the exchange code.
        """
        return self._fetch_paginated_list(
            url,
            SSE_INDEX_LIST_PARAMETERS,
            self._parse_index_list_response,
        )

    def fetch_fund_list(
        self,
        url: str = SSE_FUND_LIST_API_URL,
    ) -> List[Dict]:
        """Download the official SSE ETF fund lists.

        Args:
            url: The SSE fund-list API endpoint.

        Returns:
            Deduplicated normalized ETF fund records with ``SH`` as the
            exchange code.
        """
        records_by_code = {}
        for subclass in SSE_FUND_SUBCLASSES:
            for record in self._fetch_paginated_list(
                url,
                {
                    **SSE_FUND_LIST_PARAMETERS,
                    "subClass": subclass,
                },
                self._parse_fund_list_response,
            ):
                records_by_code[record["code"]] = record
        return list(records_by_code.values())

    def _fetch_paginated_list(
        self,
        url: str,
        base_parameters: Dict,
        parser,
    ) -> List[Dict]:
        """Fetch all pages from one SSE list endpoint."""
        records = []
        page_number = 1
        while True:
            response = self._http_clients[0].get(
                url,
                params={
                    **base_parameters,
                    "pageHelp.beginPage": str(page_number),
                    "pageHelp.endPage": str(page_number),
                    "pageHelp.pageNo": str(page_number),
                },
            )
            page_records, page_count = parser(response.text)
            records.extend(page_records)
            if page_number >= page_count:
                return records
            page_number += 1


def parse_sse_share_list(text: str) -> List[Dict]:
    """Compatibility wrapper for the SiteSSE HTML parser."""
    return SiteSSE._parse_share_list(text)


class SSEStockCode(HttpClient):
    """HTTP client for fetching and parsing SSE stock-code listings."""

    def __init__(self, **client_options: Any) -> None:
        client_options.setdefault("timeout", 30.0)
        client_options.setdefault(
            "base_headers",
            {
                "User-Agent": SSE_USER_AGENT,
                "Referer": "https://www.sse.com.cn/assortment/stock/list/share/",
            },
        )
        super().__init__(**client_options)

    def fetch_sh_index(self) -> list[dict[str, Any]]:
        """Fetch index metrics displayed on SSE's index overview page.

        Returns:
            JSON-compatible index rows with the overview fields:
            ``index_name``, ``index_code``, ``close_point``, ``trade_amount``,
            ``avg_vol``, ``pe_ratio``, and ``trade_date``.

        Raises:
            RuntimeError: The SSE query reports a service-side failure.
            ValueError: The response does not contain valid index data.
        """
        response = self.get(
            SSE_INDEX_OVERVIEW_API_URL,
            params={
                "jsonCallBack": self._create_jsonp_callback(),
                "isPagination": "false",
                "sqlId": SSE_INDEX_OVERVIEW_SQL_ID,
            },
        )
        payload = SiteSSE._parse_jsonp_response(response.text, "index overview")
        result_records = payload.get("result")
        if not isinstance(result_records, list):
            raise ValueError(
                "SSE index overview response does not contain result rows."
            )

        index_records = []
        for result_record in result_records:
            if not isinstance(result_record, dict):
                continue
            index_name = result_record.get("INDEX_ABBR")
            index_code = result_record.get("INDEX_CODE")
            if not isinstance(index_name, str) or not isinstance(index_code, str):
                raise ValueError(
                    f"SSE index overview row has invalid identity fields: "
                    f"{result_record!r}"
                )
            index_records.append(
                {
                    "index_name": index_name,
                    "index_code": index_code,
                    "close_point": result_record.get("CLOSE_POINT"),
                    "trade_amount": result_record.get("TRADE_AMT"),
                    "avg_vol": result_record.get("AVG_VOL"),
                    "pe_ratio": result_record.get("PE_RATIO"),
                    "trade_date": SiteSSE._normalize_list_date(
                        result_record.get("TRADE_DATE")
                    ),
                }
            )
        return index_records

    @staticmethod
    def _create_jsonp_callback() -> str:
        """按 SSE 的 JSONP 约定生成回调函数名。

        算法：
        1. 读取当前 Unix 时间的微秒值，令短时间内的连续请求得到不同后缀。
        2. 对 100,000,000 取模，将后缀限制在 8 位十进制范围。
        3. 左侧补零至 8 位，并添加 SSE 要求的 ``jsonpCallback`` 前缀。

        Returns:
            符合 SSE 接口格式的 JSONP 回调名称。
        """
        # SSE expects a JavaScript-identifier prefix followed by eight digits.
        timestamp_microseconds = time.time_ns() // 1_000
        callback_suffix = timestamp_microseconds % 100_000_000
        return f"jsonpCallback{callback_suffix:08d}"

    def fetch_stock_code(self) -> list[dict[str, str | None]]:
        result_records = []
        for stock_type in SSE_STOCK_TYPES:
            page_number = 1
            while True:
                cache_buster = time.time_ns() // 1_000_000
                response = self.get(
                    SSE_STOCK_LIST_API_URL,
                    params={
                        **SSE_STOCK_LIST_PARAMETERS,
                        "jsonCallBack": self._create_jsonp_callback(),
                        "STOCK_TYPE": stock_type,
                        "pageHelp.beginPage": str(page_number),
                        "pageHelp.endPage": str(page_number),
                        "pageHelp.pageNo": str(page_number),
                        "_": str(cache_buster),
                    },
                )
                page_records, page_count = SiteSSE._parse_stock_list_response(
                    response.text
                )
                result_records.extend(
                    SiteSSE._normalize_stock_records(page_records)
                )
                if page_number >= page_count:
                    break
                page_number += 1

        logger.info(f"SiteSSE fetched {len(result_records)} stock records.")
        return result_records


SseSiteClient = SiteSSE

__all__ = [
    "SSE_FUND_LIST_API_URL",
    "SSE_FUND_SUBCLASSES",
    "SSE_INDEX_LIST_API_URL",
    "SSE_INDEX_LIST_PARAMETERS",
    "SSE_INDEX_OVERVIEW_API_URL",
    "SSE_INDEX_OVERVIEW_SQL_ID",
    "SSE_INDEX_OVERVIEW_API_URL",
    "SSE_INDEX_OVERVIEW_SQL_ID",
    "SSE_STOCK_LIST_API_URL",
    "SSE_STOCK_LIST_PARAMETERS",
    "SSE_STOCK_LIST_PAGE_SIZE",
    "SSE_STOCK_TYPES",
    "SSE_USER_AGENT",
    "SSEStockCode",
    "SiteSSE",
    "SseSiteClient",
    "parse_sse_share_list",
]
