from __future__ import annotations

from typing import Iterable

from website_agent.website.agent import BaseSite


class SiteRegistry:
    """Keep site adapters in a simple registry that can be plugged into WebsiteAgent."""

    def __init__(self) -> None:
        self._sites: dict[str, BaseSite] = {}

    def register(self, site: BaseSite) -> None:
        self._sites[site.name] = site

    def register_many(self, sites: Iterable[BaseSite]) -> None:
        for site in sites:
            self.register(site)

    def get(self, name: str) -> BaseSite | None:
        return self._sites.get(name)

    def values(self) -> list[BaseSite]:
        return list(self._sites.values())

    def __iter__(self):
        return iter(self._sites.values())


__all__ = ["SiteRegistry"]
