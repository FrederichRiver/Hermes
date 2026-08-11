"""Shenzhen Stock Exchange stock-list client."""

import json
import re
from typing import Dict, List

from agent.http_connect import HttpConnect


SZSE_STOCK_LIST_API_URL = "https://www.szse.cn/api/report/ShowReport/data"
SZSE_INDEX_LIST_API_URL = SZSE_STOCK_LIST_API_URL
SZSE_FUND_LIST_API_URL = SZSE_STOCK_LIST_API_URL
_SZSE_STOCK_LIST_PARAMETERS = {
    "SHOWTYPE": "JSON",
    "CATALOGID": "1110",
}
_SZSE_INDEX_LIST_PARAMETERS = {
    "SHOWTYPE": "JSON",
    "CATALOGID": "1812_zs",
    "TABKEY": "tab1",
}
_SZSE_FUND_LIST_PARAMETERS = {
    "SHOWTYPE": "JSON",
    "CATALOGID": "fund_lof",
    "TABKEY": "tab1",
}
_SZSE_STOCK_LIST_TABS = ("tab1", "tab2")
_CODE_NAME_DATE_FIELDS = (
    ("agdm", "agjc", "agssrq"),
    ("bgdm", "bgjc", "bgssrq"),
)


def _normalize_list_date(value: object) -> str | None:
    """Normalize an optional SZSE listing date to ISO format."""
    if value is None or value in ("", "-"):
        return None
    if not isinstance(value, str):
        raise ValueError(f"Invalid SZSE listing date: {value!r}")
    if re.fullmatch(r"\d{8}", value):
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value
    raise ValueError(f"Invalid SZSE listing date: {value!r}")


def _strip_html(value: str) -> str:
    """Return the visible text of a SZSE report field."""
    return re.sub(r"<[^>]+>", "", value).strip()


def _parse_szse_stock_list_response(
    text: str,
    tab_key: str,
) -> tuple[List[Dict], int]:
    """Parse the SZSE stock-list report into normalized records."""
    payload = json.loads(text)
    report_sections = payload if isinstance(payload, list) else [payload]
    records = []
    page_count = None

    for section in report_sections:
        if not isinstance(section, dict):
            continue
        metadata = section.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("tabkey") != tab_key:
            continue
        rows = section.get("data")
        if not isinstance(rows, list):
            continue
        reported_page_count = metadata.get("pagecount")
        if not isinstance(reported_page_count, int) or reported_page_count < 1:
            raise ValueError(f"SZSE {tab_key} response has an invalid page count.")
        page_count = reported_page_count
        for row in rows:
            if not isinstance(row, dict):
                continue
            for code_field, name_field, date_field in _CODE_NAME_DATE_FIELDS:
                code = row.get(code_field)
                name = row.get(name_field)
                if code in (None, "", "-"):
                    continue
                if not isinstance(code, str) or not re.fullmatch(r"\d{6}", code):
                    raise ValueError(f"Invalid SZSE stock code: {code!r}")
                if not isinstance(name, str) or not name.strip():
                    raise ValueError(f"Missing SZSE stock name for code {code}.")
                stock_name = _strip_html(name)
                if not stock_name:
                    raise ValueError(f"Missing SZSE stock name for code {code}.")
                records.append(
                    {
                        "code": code,
                        "name": stock_name,
                        "exchange": "SZ",
                        "list_date": _normalize_list_date(row.get(date_field)),
                    }
                )
    if page_count is None:
        raise ValueError(f"SZSE stock-list response does not contain {tab_key}.")
    return records, page_count


def _parse_szse_index_list_response(text: str) -> tuple[List[Dict], int]:
    """Parse the SZSE index-list report into normalized records."""
    return _parse_szse_security_list_response(
        text,
        security_type="index",
        code_field="zsdm",
        name_field="zsmc",
        date_field="qsrnew",
    )


def _parse_szse_fund_list_response(text: str) -> tuple[List[Dict], int]:
    """Parse the SZSE LOF fund-list report into normalized records."""
    return _parse_szse_security_list_response(
        text,
        security_type="fund",
        code_field="sys_key",
        name_field="kzjcurl",
        date_field=None,
    )


def _parse_szse_security_list_response(
    text: str,
    security_type: str,
    code_field: str,
    name_field: str,
    date_field: str | None,
) -> tuple[List[Dict], int]:
    """Parse one tabular SZSE report into normalized security records."""
    payload = json.loads(text)
    report_sections = payload if isinstance(payload, list) else [payload]
    records = []
    page_count = None

    for section in report_sections:
        if not isinstance(section, dict):
            continue
        metadata = section.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("tabkey") != "tab1":
            continue
        rows = section.get("data")
        if not isinstance(rows, list):
            continue
        reported_page_count = metadata.get("pagecount")
        if not isinstance(reported_page_count, int) or reported_page_count < 1:
            raise ValueError(
                f"SZSE {security_type}-list response has an invalid page count."
            )
        page_count = reported_page_count
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = _strip_html_value(row.get(code_field))
            name = _strip_html_value(row.get(name_field))
            if not re.fullmatch(r"\d{6}", code):
                raise ValueError(f"Invalid SZSE {security_type} code: {code!r}")
            if not name:
                raise ValueError(
                    f"Missing SZSE {security_type} name for code {code}."
                )
            records.append(
                {
                    "code": code,
                    "name": name,
                    "exchange": "SZ",
                    "list_date": (
                        _normalize_list_date(row.get(date_field))
                        if date_field is not None
                        else None
                    ),
                }
            )
    if page_count is None:
        raise ValueError(
            f"SZSE {security_type}-list response does not contain tab1."
        )
    return records, page_count


def _strip_html_value(value: object) -> str:
    """Extract visible text from an optional SZSE report value."""
    if not isinstance(value, str):
        return ""
    return _strip_html(value)


class SzseSiteClient(HttpConnect):
    """Fetch and normalize Shenzhen Stock Exchange listing records."""

    def fetch_stock_list(self, url: str = SZSE_STOCK_LIST_API_URL) -> List[Dict]:
        """Download SZSE stock listings from its official report API.

        Args:
            url: The SZSE stock-list report API endpoint.

        Returns:
            Normalized A-share and B-share listing records with ``SZ`` as the
            exchange code.
        """
        records = []
        for tab_key in _SZSE_STOCK_LIST_TABS:
            page_number = 1
            while True:
                response = self.get(
                    url,
                    params={
                        **_SZSE_STOCK_LIST_PARAMETERS,
                        "TABKEY": tab_key,
                        f"{tab_key}PAGENO": str(page_number),
                    },
                )
                page_records, page_count = _parse_szse_stock_list_response(
                    response.text,
                    tab_key,
                )
                records.extend(page_records)
                if page_number >= page_count:
                    break
                page_number += 1
        return records

    def fetch_index_list(
        self,
        url: str = SZSE_INDEX_LIST_API_URL,
    ) -> List[Dict]:
        """Download the official SZSE index list.

        Args:
            url: The SZSE index-list report API endpoint.

        Returns:
            Normalized index records with ``SZ`` as the exchange code.
        """
        return self._fetch_paginated_list(
            url,
            _SZSE_INDEX_LIST_PARAMETERS,
            _parse_szse_index_list_response,
            "PAGENO",
        )

    def fetch_fund_list(
        self,
        url: str = SZSE_FUND_LIST_API_URL,
    ) -> List[Dict]:
        """Download the official SZSE LOF fund list.

        Args:
            url: The SZSE fund-list report API endpoint.

        Returns:
            Normalized fund records with ``SZ`` as the exchange code.
        """
        return self._fetch_paginated_list(
            url,
            _SZSE_FUND_LIST_PARAMETERS,
            _parse_szse_fund_list_response,
            "tab1PAGENO",
        )

    def _fetch_paginated_list(
        self,
        url: str,
        base_parameters: Dict,
        parser,
        page_parameter: str,
    ) -> List[Dict]:
        """Fetch all report pages for one SZSE security list."""
        records = []
        page_number = 1
        while True:
            response = self.get(
                url,
                params={
                    **base_parameters,
                    page_parameter: str(page_number),
                },
            )
            page_records, page_count = parser(response.text)
            records.extend(page_records)
            if page_number >= page_count:
                return records
            page_number += 1
