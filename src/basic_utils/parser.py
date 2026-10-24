import re
from typing import List
try:
    from bs4 import BeautifulSoup
    _HAS_BS4 = True
except Exception:
    _HAS_BS4 = False


def extract_codes_from_text(text: str, prefix: str) -> List[str]:
    """Extract unique 6-digit codes from arbitrary text and add a prefix.

    This is a simple, robust extractor intended as a fallback generic parser.
    It finds all 6-digit sequences and returns them prefixed (e.g. 'SH600000').
    """
    codes = re.findall(r"\b\d{6}\b", text or "")
    seen = set()
    results = []
    for c in codes:
        if c in seen:
            continue
        seen.add(c)
        results.append(f"{prefix}{c}")
    # deterministic order
    results = sorted(results)
    return results


def normalize_code(code: str, prefix: str) -> str:
    """Normalize an arbitrary code string to a 6-digit code with prefix.

    Examples:
        normalize_code('6001', 'SH') -> 'SH006001'
    """
    digits = re.sub(r"\D", "", code or "")
    digits = digits.zfill(6)
    return f"{prefix}{digits}"


def _parse_html_generic(html: str, prefix: str) -> List[str]:
    """Parse HTML using BeautifulSoup if available, otherwise fallback to regex.

    The implementation tries to extract 6-digit sequences from common tags
    (td, a, span, li) to avoid matching unrelated numbers in scripts.
    """
    if _HAS_BS4:
        soup = BeautifulSoup(html or "", "html.parser")
        candidates = []
        for tag in soup.find_all(["td", "a", "span", "li"]):
            text = tag.get_text(separator=" ", strip=True)
            for c in re.findall(r"\b\d{6}\b", text):
                candidates.append(f"{prefix}{c}")
        if candidates:
            # preserve order but unique
            seen = set()
            out = []
            for c in candidates:
                if c not in seen:
                    seen.add(c)
                    out.append(c)
            return sorted(out)
        # fallback to whole-text regex
    return extract_codes_from_text(html, prefix)


def parse_sse_html(html: str) -> List[str]:
    """Parse Shanghai Stock Exchange listing HTML and return prefixed codes.

    This is a best-effort parser that relies on table/list patterns commonly
    used on exchange pages. It falls back to a generic regex-based extractor.
    """
    return _parse_html_generic(html, "SH")


def parse_szse_html(html: str) -> List[str]:
    """Parse Shenzhen Stock Exchange listing HTML and return prefixed codes."""
    return _parse_html_generic(html, "SZ")


def _extract_codes_from_json(obj, prefix: str) -> List[str]:
    """Recursively search JSON-like structures for 6-digit codes and prefix them."""
    found = []
    if obj is None:
        return found
    if isinstance(obj, str):
        for c in re.findall(r"\b\d{6}\b", obj):
            found.append(f"{prefix}{c}")
        return found
    if isinstance(obj, (int,)):
        s = str(obj)
        if re.fullmatch(r"\d{6}", s):
            return [f"{prefix}{s}"]
        return []
    if isinstance(obj, dict):
        for v in obj.values():
            found.extend(_extract_codes_from_json(v, prefix))
        return found
    if isinstance(obj, (list, tuple)):
        for item in obj:
            found.extend(_extract_codes_from_json(item, prefix))
        return found
    # other types
    return found


def parse_sse_json(data) -> List[str]:
    """Parse SSE JSON response for codes and return 'SH' prefixed codes."""
    return sorted(set(_extract_codes_from_json(data, "SH")))


def parse_sse_stock_info_json(data) -> List[dict]:
    """Parse SSE JSON response for stock code, name, and issue_date."""
    # SSE JSON structure usually looks like:
    # { "result": [ { "COMPANY_CODE": "600000", "COMPANY_ABBR": "浦发银行", "LISTING_DATE": "1999-11-10", ... }, ... ] }
    # Let's extract them.
    results = []
    if not isinstance(data, dict):
        return results
    
    # Try different possible key patterns for result list
    items = data.get("result", data.get("pageHelp", {}).get("data", []))
    if not isinstance(items, list):
        return results

    for item in items:
        if not isinstance(item, dict):
            continue
        # Extract code (typically COMPANY_CODE or A_STOCK_CODE)
        code = item.get("COMPANY_CODE") or item.get("A_STOCK_CODE") or item.get("stockCode")
        if not code:
            continue
        
        # Extract name (COMPANY_ABBR or SECURITY_ABBR_A or stockAbbr)
        name = item.get("COMPANY_ABBR") or item.get("SECURITY_ABBR_A") or item.get("stockAbbr") or ""
        
        # Extract issue listing date (LISTING_DATE or LISTING_DATE_A)
        issue_date = item.get("LISTING_DATE") or item.get("LISTING_DATE_A") or item.get("listingDate")
        
        results.append({
            "code": f"SH{code}",
            "name": name,
            "issue_date": issue_date if issue_date and issue_date != "-" else None
        })
    return results


def parse_szse_json(data) -> List[str]:
    """Parse SZSE JSON response for codes and return 'SZ' prefixed codes."""
    return sorted(set(_extract_codes_from_json(data, "SZ")))
