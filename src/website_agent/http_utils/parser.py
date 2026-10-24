from __future__ import annotations

import json
from typing import Any

from bs4 import BeautifulSoup
from requests import Response


class DataEngineError(RuntimeError):
    """Raised when a response payload cannot be parsed into the Hermes row model."""


class HtmlParser:
    """Static HTML/JSON parser utilities for website scrapers."""

    @staticmethod
    def _detect_encoding(raw: bytes) -> str:
        for candidate in ("utf-8", "gbk", "gb2312", "gb18030", "latin-1"):
            try:
                raw.decode(candidate)
                return candidate
            except UnicodeDecodeError:
                continue
        return "utf-8"

    @staticmethod
    def to_text(resp: Response) -> str:
        raw = resp.content or b""
        encoding = resp.encoding or HtmlParser._detect_encoding(raw)
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            return raw.decode("utf-8", errors="replace")

    @staticmethod
    def select(html: str, selector: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        return [node.get_text(" ", strip=True) for node in soup.select(selector)]

    @staticmethod
    def parse_json(text: str) -> dict[str, Any]:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:  # pragma: no cover - error path
            raise DataEngineError(f"Invalid JSON payload: {text[:120]!r}") from exc
        if not isinstance(payload, dict):
            raise DataEngineError("JSON payload must be a dictionary.")
        return payload

    @staticmethod
    def clean_number(s: str) -> float:
        value = str(s or "").strip()
        if not value:
            return 0.0
        value = value.replace(",", "")
        unit_map = {"亿": 1e8, "万": 1e4, "千": 1e3, "百": 1e2}
        multiplier = 1.0
        for suffix, factor in unit_map.items():
            if value.endswith(suffix):
                multiplier = factor
                value = value[: -len(suffix)]
                break
        try:
            return float(value) * multiplier
        except ValueError:
            return float(value.replace("%", "")) if value else 0.0


__all__ = ["HtmlParser", "DataEngineError"]
