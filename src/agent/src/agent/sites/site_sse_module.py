"""Shanghai Stock Exchange (SSE) site scraper utilities.

This module provides a small site client for fetching the SSE listing page
and producing a normalized list of securities suitable for database storage.
The parser prefers a DOM-based extraction (BeautifulSoup) and falls back to
a regex-based heuristic when structure differs.
"""

from typing import List, Dict, Optional
import json
import logging
import re

from bs4 import BeautifulSoup


def _looks_like_stock_name(value: str) -> bool:
    """Return True when a parsed value looks like a real stock name."""
    if not value:
        return False

    text = value.strip()
    if not text or len(text) < 2:
        return False

    if re.fullmatch(r"[\d\-\.]+", text):
        return False

    if re.fullmatch(r"[A-Za-z0-9]+", text):
        return False

    if re.match(r"^(?:[0-9]{6}|[0-9]{8}|[0-9]{4})$", text):
        return False

    if text.startswith("http") or text.startswith("//"):
        return False

    if "©" in text or "ICP" in text or "备案" in text or "网站" in text:
        return False

    return True

from agent.http_connect import HttpConnect

logger = logging.getLogger("agent.sites.sse")

SSE_STOCK_LIST_API_URL = "https://query.sse.com.cn/sseQuery/commonQuery.do"
SSE_INDEX_LIST_API_URL = "https://query.sse.com.cn/commonSoaQuery.do"
SSE_FUND_LIST_API_URL = SSE_INDEX_LIST_API_URL
SSE_STOCK_TYPES = ("1", "2", "8")
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
_SSE_STOCK_LIST_PARAMETERS = {
    "jsonCallBack": "callback",
    "isPagination": "true",
    "sqlId": "COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L",
    "REG_PROVINCE": "",
    "CSRC_CODE": "",
    "STOCK_CODE": "",
    "COMPANY_STATUS": "2,4,5,7,8",
    "type": "inParams",
    "pageHelp.cacheSize": "1",
    "pageHelp.beginPage": "1",
    "pageHelp.pageSize": "10",
}
_SSE_INDEX_LIST_PARAMETERS = {
    "jsonCallBack": "callback",
    "isPagination": "true",
    "sqlId": "DB_SZZSLB_ZSLB",
    "pageHelp.cacheSize": "1",
    "pageHelp.beginPage": "1",
    "pageHelp.pageSize": "100",
}
_SSE_FUND_LIST_PARAMETERS = {
    "jsonCallBack": "callback",
    "isPagination": "true",
    "sqlId": "FUND_LIST",
    "fundType": "00",
    "pageHelp.cacheSize": "1",
    "pageHelp.beginPage": "1",
    "pageHelp.pageSize": "100",
}


def parse_sse_share_list(text: str) -> List[Dict]:
    """Parse SSE share-listing HTML into items.

    Strategy:
    - Try to parse table rows or list items using BeautifulSoup.
    - If DOM parsing finds nothing, fallback to a regex that looks for
      a 6-digit code and a nearby name.

    Returns a list of dicts with keys: `code`, `name`, `exchange`, `list_date`.
    """
    items: List[Dict] = []
    if not text:
        return items

    try:
        soup = BeautifulSoup(text, 'html.parser')
        # common pattern: table rows containing code and name cells
        rows = soup.select('table tr')
        for r in rows:
            cols = [c.get_text(strip=True) for c in r.find_all(['td', 'th'])]
            if not cols:
                continue
            # find a 6-digit code in the row text
            joined = ' '.join(cols)
            m = re.search(r"\b(\d{6})\b", joined)
            if m:
                code = m.group(1)
                # prefer the column immediately after the code if present
                name = None
                for i, c in enumerate(cols):
                    if code in c:
                        if i + 1 < len(cols):
                            name = cols[i + 1]
                        break
                name = name or cols[0]
                items.append({'code': code, 'name': name, 'exchange': 'SH', 'list_date': None})

        # If nothing found via table rows, try anchor/text list patterns
        if not items:
            anchors = soup.find_all('a')
            for a in anchors:
                txt = a.get_text(strip=True)
                m = re.match(r"^(\d{6})\s*[-–—]?\s*(.+)$", txt)
                if m:
                    items.append({'code': m.group(1), 'name': m.group(2), 'exchange': 'SH', 'list_date': None})
    except Exception:
        logger.debug('BeautifulSoup parsing failed, falling back to regex', exc_info=True)

    return items


def _parse_sse_stock_list_response(text: str) -> tuple[List[Dict], int]:
    """Parse the SSE JSONP stock-list response into normalized records."""
    match = re.fullmatch(r"\s*[\w$]+\((.*)\)\s*;?\s*", text, flags=re.DOTALL)
    if not match:
        raise ValueError("SSE stock-list response is not valid JSONP.")

    response = json.loads(match.group(1))
    if not isinstance(response, dict) or response.get("success") == "false":
        raise RuntimeError(f"SSE stock-list query failed: {response!r}")

    page_help = response.get("pageHelp")
    if not isinstance(page_help, dict):
        raise ValueError("SSE stock-list response does not contain pageHelp.")
    rows = page_help.get("data")
    if not isinstance(rows, list):
        raise ValueError("SSE stock-list response does not contain stock rows.")

    records = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        stock_type = row.get("STOCK_TYPE")
        code = row.get("B_STOCK_CODE") if stock_type == "2" else row.get("A_STOCK_CODE")
        name = row.get("SEC_NAME_CN")
        if not isinstance(code, str) or not re.fullmatch(r"\d{6}", code):
            continue
        if not isinstance(name, str) or not _looks_like_stock_name(name):
            continue
        list_date = row.get("LIST_DATE")
        if isinstance(list_date, str) and re.fullmatch(r"\d{8}", list_date):
            list_date = f"{list_date[:4]}-{list_date[4:6]}-{list_date[6:]}"
        elif list_date == "-":
            list_date = None
        records.append(
            {
                "code": code,
                "name": name,
                "exchange": "SH",
                "list_date": list_date,
            }
        )
    page_count = page_help.get("pageCount", 1)
    if not isinstance(page_count, int) or page_count < 1:
        raise ValueError("SSE stock-list response has an invalid page count.")
    return records, page_count


def _parse_sse_index_list_response(text: str) -> tuple[List[Dict], int]:
    """Parse an SSE index-list JSONP response into normalized records."""
    response = _parse_sse_jsonp_response(text, "index")
    page_help = _get_sse_page_help(response, "index")
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
                "list_date": _normalize_sse_list_date(row.get("launchDay")),
            }
        )
    return records, _get_sse_page_count(page_help, "index")


def _parse_sse_fund_list_response(text: str) -> tuple[List[Dict], int]:
    """Parse an SSE fund-list JSONP response into normalized records."""
    response = _parse_sse_jsonp_response(text, "fund")
    page_help = _get_sse_page_help(response, "fund")
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
                "list_date": _normalize_sse_list_date(row.get("listingDate")),
            }
        )
    return records, _get_sse_page_count(page_help, "fund")


def _parse_sse_jsonp_response(text: str, security_type: str) -> Dict:
    """Decode and validate an SSE JSONP response."""
    match = re.fullmatch(r"\s*[\w$]+\((.*)\)\s*;?\s*", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"SSE {security_type}-list response is not valid JSONP.")
    response = json.loads(match.group(1))
    if not isinstance(response, dict) or response.get("success") == "false":
        raise RuntimeError(f"SSE {security_type}-list query failed: {response!r}")
    return response


def _get_sse_page_help(response: Dict, security_type: str) -> Dict:
    """Get the paginated result metadata from an SSE response."""
    page_help = response.get("pageHelp")
    if not isinstance(page_help, dict):
        raise ValueError(
            f"SSE {security_type}-list response does not contain pageHelp."
        )
    return page_help


def _get_sse_page_count(page_help: Dict, security_type: str) -> int:
    """Validate and return an SSE response page count."""
    page_count = page_help.get("pageCount", 1)
    if not isinstance(page_count, int) or page_count < 0:
        raise ValueError(
            f"SSE {security_type}-list response has an invalid page count."
        )
    return page_count


def _normalize_sse_list_date(value: object) -> str | None:
    """Normalize an optional SSE listing or launch date to ISO format."""
    if value is None or value in ("", "-"):
        return None
    if not isinstance(value, str):
        raise ValueError(f"Invalid SSE list date: {value!r}")
    if re.fullmatch(r"\d{8}", value):
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value
    raise ValueError(f"Invalid SSE list date: {value!r}")



class SseSiteClient(HttpConnect):
    """Site client for Shanghai Stock Exchange pages, built on HttpConnect.

    Provides a convenience method `fetch_stock_list()` that fetches the public
    listing page and returns a cleaned list suitable for database insertion.
    """

    def __init__(self, *args, **kwargs):
        """Create an SSE site client.

        URL is provided to each fetch method rather than at construction time,
        because different fetch functions may target different pages or APIs.
        """
        super().__init__(*args, **kwargs)

    def fetch_stock_list(self, url: str) -> List[Dict]:
        """Download SSE stock listings and return extracted records.

        Args:
            url: The SSE stock-list API URL or a static listing page URL.

        Returns:
            A list of records (dict) with keys: `code`, `name`, `exchange`,
            `list_date` (may be None). Codes are 6-digit strings.
        """
        if url == SSE_STOCK_LIST_API_URL:
            raw = []
            for stock_type in SSE_STOCK_TYPES:
                page_number = 1
                while True:
                    response = self.get(
                        url,
                        params={
                            **_SSE_STOCK_LIST_PARAMETERS,
                            "STOCK_TYPE": stock_type,
                            "pageHelp.beginPage": str(page_number),
                            "pageHelp.endPage": str(page_number),
                            "pageHelp.pageNo": str(page_number),
                        },
                    )
                    text = response.text if response is not None else ""
                    page_records, page_count = _parse_sse_stock_list_response(text)
                    raw.extend(page_records)
                    if page_number >= page_count:
                        break
                    page_number += 1
        else:
            response = self.get(url)
            text = response.text if response is not None else ""
            raw = parse_sse_share_list(text)
        records: List[Dict] = []
        for it in raw:
            code = (it.get('code') or '').strip()
            name = (it.get('name') or '').strip()
            if not code or not code.isdigit():
                continue
            if not _looks_like_stock_name(name):
                logger.debug('Skipping non-stock-name value for code %s: %r', code, name)
                continue
            records.append({'code': code, 'name': name, 'exchange': it.get('exchange', 'SH'), 'list_date': it.get('list_date')})
        logger.info(f'SseSiteClient fetched {len(records)} records from {url}')
        return records

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
            _SSE_INDEX_LIST_PARAMETERS,
            _parse_sse_index_list_response,
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
                    **_SSE_FUND_LIST_PARAMETERS,
                    "subClass": subclass,
                },
                _parse_sse_fund_list_response,
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
            response = self.get(
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
