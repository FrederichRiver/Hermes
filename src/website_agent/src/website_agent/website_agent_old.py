"""Compatibility imports for the consolidated WebsiteAgent module."""

from website_agent.website.agent import (
    BaseSite,
    CircuitState,
    FetchTask,
    WebsiteAgent,
)

__all__ = ["BaseSite", "CircuitState", "FetchTask", "WebsiteAgent"]
