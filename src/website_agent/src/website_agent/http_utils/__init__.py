"""Shared HTTP utilities for the Hermes WebsiteAgent."""

from .client import HttpClient, HttpFatalError, HttpRetryableError
from .parser import DataEngineError, HtmlParser
from .robots import RobotsChecker
from .user_agent import (
    BSE_USER_AGENT,
    DATA_AGENT_USER_AGENT,
    DEFAULT_USER_AGENT,
    DEFAULT_USER_AGENTS,
    MARKET_PRICE_USER_AGENT,
    SSE_USER_AGENT,
    STOCK_DATA_USER_AGENT,
    STOCK_INDEX_USER_AGENT,
    SZSE_USER_AGENT,
)

__all__ = [
    "BSE_USER_AGENT",
    "DATA_AGENT_USER_AGENT",
    "DEFAULT_USER_AGENT",
    "DEFAULT_USER_AGENTS",
    "HttpClient",
    "HttpFatalError",
    "HttpRetryableError",
    "DataEngineError",
    "HtmlParser",
    "MARKET_PRICE_USER_AGENT",
    "RobotsChecker",
    "SSE_USER_AGENT",
    "STOCK_DATA_USER_AGENT",
    "STOCK_INDEX_USER_AGENT",
    "SZSE_USER_AGENT",
]
