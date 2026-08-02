# DataAgent 数据Agent基础实现
import os
import logging
from typing import List


class DataAgent:
    def fetch_data(self, source: str, params: dict):
        """从指定数据源抓取数据"""
        pass

    def clean_data(self, raw_data):
        """数据清洗、标准化"""
        pass

    def publish_event(self, event_type: str, data: dict):
        """发布数据事件，驱动其他Agent"""
        pass


# Module-level synchronous scraper functions for scheduler to call
from agents.http_connect import HttpConnect
from utils.parser import (
    extract_codes_from_text,
    parse_sse_html,
    parse_szse_html,
    parse_sse_json,
    parse_szse_json,
)

logger = logging.getLogger("src.data_agent")
# default http client for site scrapers
_client = HttpConnect(base_headers={"User-Agent": "Hermes-DataAgent/1.0"}, timeout=15.0, max_retries=3, backoff_factor=0.5)

# Best-effort list pages for exchanges (may need adjustment if site structure changes)
_SSE_LIST_URL = "http://www.sse.com.cn/assortment/stock/list/share/"
_SZSE_LIST_URL = "http://www.szse.cn/market/stock/list/index.html"

# Candidate public API endpoints (best-effort). These may require specific headers
# (e.g., Referer) or query parameters; keep them as candidates and try each.
_SSE_API_ENDPOINTS = [
    "http://query.sse.com.cn/security/stock/getStockListData.json",
    "https://query.sse.com.cn/security/stock/getStockListData.json",
]

_SZSE_API_ENDPOINTS = [
    "http://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=1110",
    "https://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=1110",
]


def _write_codes_atomic(codes: List[str], output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    tmp = output_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for code in codes:
            f.write(f"{code}\n")
    os.replace(tmp, output_path)


def _fetch_and_write(url: str, prefix: str, output_path: str) -> int:
    try:
        text = _client.get(url)
        # prefer specialized parsers for known exchanges, fallback to generic regex
        if prefix == "SH":
            codes = parse_sse_html(text)
        elif prefix == "SZ":
            codes = parse_szse_html(text)
        else:
            codes = extract_codes_from_text(text, prefix)
        if not codes:
            # fallback to generic regex
            codes = extract_codes_from_text(text, prefix)
        if not codes:
            logger.warning("No codes extracted from %s", url)
        else:
            _write_codes_atomic(codes, output_path)
            logger.info("Wrote %d codes to %s", len(codes), output_path)
        return len(codes)
    except Exception as e:
        logger.exception("Failed fetching codes from %s: %s", url, e)
        raise


def fetch_sse_codes(output_path: str = "src/data/codes/shanghai.txt") -> int:
    """Fetch codes from Shanghai Stock Exchange and save to `output_path`.

    Returns number of codes written.
    """
    # Try API endpoints first
    for api in _SSE_API_ENDPOINTS:
        try:
            data = _client.get_json(api)
            codes = parse_sse_json(data)
            if codes:
                _write_codes_atomic(codes, output_path)
                logger.info("Wrote %d codes to %s via SSE API %s", len(codes), output_path, api)
                return len(codes)
        except Exception:
            logger.debug("SSE API endpoint failed: %s", api)
    # Fallback to HTML scraping
    return _fetch_and_write(_SSE_LIST_URL, "SH", output_path)


def fetch_szse_codes(output_path: str = "src/data/codes/shenzhen.txt") -> int:
    """Fetch codes from Shenzhen Stock Exchange and save to `output_path`.

    Returns number of codes written.
    """
    # Try API endpoints first
    for api in _SZSE_API_ENDPOINTS:
        try:
            data = _client.get_json(api)
            codes = parse_szse_json(data)
            if codes:
                _write_codes_atomic(codes, output_path)
                logger.info("Wrote %d codes to %s via SZSE API %s", len(codes), output_path, api)
                return len(codes)
        except Exception:
            logger.debug("SZSE API endpoint failed: %s", api)
    # Fallback to HTML scraping
    return _fetch_and_write(_SZSE_LIST_URL, "SZ", output_path)
