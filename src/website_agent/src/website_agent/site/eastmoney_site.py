from __future__ import annotations

from typing import Any

from website_agent.http_utils.client import RequestSpec
from website_agent.site.base import BaseSite


class EastMoneySite(BaseSite):
    """Minimal concrete site adapter for Eastmoney-style data."""

    name = "eastmoney"
    priority = 10

    def supports(self, task_type: str) -> bool:
        return task_type in {"daily_bar", "symbol_list"}

    def rate_limit(self) -> float:
        return 2.0

    def build_request(self, task: Any) -> RequestSpec:
        params = dict(task.params)
        url = "https://push2.eastmoney.com/api/qt/stock/get"
        if task.task_type == "daily_bar":
            params.setdefault("secid", "1.600000")
            params.setdefault("fields1", "f1,f2,f3,f4,f5,f6")
            params.setdefault("fields2", "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61")
            params.setdefault("klt", "101")
            params.setdefault("fqt", "1")
            params.setdefault("end", "20500101")
            params.setdefault("lmt", "1")
        else:
            url = "https://push2.eastmoney.com/api/qt/clist/get"
            params.setdefault("pn", "1")
            params.setdefault("pz", "100")
            params.setdefault("po", "1")
            params.setdefault("np", "1")
            params.setdefault("fltt", "2")
            params.setdefault("invt", "2")
            params.setdefault("fid", "f3")
            params.setdefault("fs", "m:105")
        return RequestSpec(method="GET", url=url, params=params, headers={"User-Agent": "Hermes-WebsiteAgent/1.0"})

    def parse(self, response: Any) -> list[dict[str, Any]]:
        try:
            payload = response.json()
        except Exception:
            return []
        if not isinstance(payload, dict):
            return []
        data = payload.get("data", {})
        if isinstance(data, dict):
            rows = data.get("klines") or data.get("diff") or []
            if isinstance(rows, list):
                return [{"source": self.name, "value": row} for row in rows]
        return [{"source": self.name, "value": payload}]


__all__ = ["EastMoneySite"]
