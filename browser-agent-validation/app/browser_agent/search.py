from __future__ import annotations

import logging
from typing import Any

from ddgs import DDGS
from ddgs.exceptions import DDGSException

logger = logging.getLogger(__name__)


class DuckDuckGoSearchTool:
    def __init__(self, region: str = "us-en", safesearch: str = "moderate", timeout: int = 10) -> None:
        self._region = region
        self._safesearch = safesearch
        self._timeout = timeout

    def search(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        """Return list of {title, url, snippet} dicts for the query."""
        try:
            with DDGS(timeout=self._timeout) as ddgs:
                raw = ddgs.text(
                    query,
                    region=self._region,
                    safesearch=self._safesearch,
                    max_results=max_results,
                )
            results = []
            for item in raw or []:
                results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("href", ""),
                        "snippet": item.get("body", ""),
                    }
                )
            logger.info("Search returned %d results for: %s", len(results), query)
            return results
        except DDGSException as exc:
            logger.warning("DDGS search failed: %s", exc)
            return []
        except Exception as exc:
            logger.error("Unexpected search error: %s", exc)
            return []
