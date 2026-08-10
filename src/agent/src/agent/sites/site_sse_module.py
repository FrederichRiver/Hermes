"""Shanghai Stock Exchange (SSE) site scraper utilities.

This module provides a small site client for fetching the SSE listing page
and producing a normalized list of securities suitable for database storage.
The parser prefers a DOM-based extraction (BeautifulSoup) and falls back to
a regex-based heuristic when structure differs.
"""

from typing import List, Dict, Optional
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

    # Regex fallback: look for 6-digit code and nearby CJK/word characters
    if not items:
        pattern = re.compile(r"(\d{6})[\s\S]{0,60}?([\u4e00-\u9fff\w\-。·]{2,30})")
        for m in pattern.finditer(text):
            code = m.group(1)
            name = m.group(2).strip()
            items.append({'code': code, 'name': name, 'exchange': 'SH', 'list_date': None})

    return items



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
        """Download the SSE listing page at `url` and return extracted records.

        Args:
            url: The full URL of the SSE page to fetch.

        Returns:
            A list of records (dict) with keys: `code`, `name`, `exchange`,
            `list_date` (may be None). Codes are 6-digit strings.
        """
        resp = self.get(url)
        text = resp.text if resp is not None else ''
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
