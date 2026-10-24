"""Shared application support for HTTP, logging, and market data parsing."""

from . import http_client, logging, parser
from .http_client import SimpleHttpClient
from .logging import configure_logging, get_logger
from .parser import (
    extract_codes_from_text,
    normalize_code,
    parse_sse_html,
    parse_sse_json,
    parse_sse_stock_info_json,
    parse_szse_html,
    parse_szse_json,
)

__all__ = [
    "SimpleHttpClient",
    "configure_logging",
    "extract_codes_from_text",
    "get_logger",
    "http_client",
    "logging",
    "normalize_code",
    "parse_sse_html",
    "parse_sse_json",
    "parse_sse_stock_info_json",
    "parse_szse_html",
    "parse_szse_json",
    "parser",
]
