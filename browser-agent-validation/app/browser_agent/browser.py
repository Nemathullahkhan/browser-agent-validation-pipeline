from __future__ import annotations

import logging

import requests
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


class RequestsBrowserTool:
    def __init__(self, timeout: int = 10, max_size_bytes: int = 500_000) -> None:
        self._timeout = timeout
        self._max_size_bytes = max_size_bytes

    def fetch(self, url: str, timeout: int | None = None) -> str:
        """Fetch a URL and return raw HTML. Returns empty string on failure."""
        try:
            resp = requests.get(
                url,
                headers=_HEADERS,
                timeout=timeout or self._timeout,
                stream=True,
            )
            resp.raise_for_status()

            content_type = resp.headers.get("Content-Type", "")
            if "text" not in content_type and "html" not in content_type:
                logger.debug("Skipping non-text URL %s (Content-Type: %s)", url, content_type)
                return ""

            chunks: list[bytes] = []
            total = 0
            for chunk in resp.iter_content(chunk_size=8192):
                chunks.append(chunk)
                total += len(chunk)
                if total >= self._max_size_bytes:
                    logger.debug("Truncating response from %s at %d bytes", url, total)
                    break

            html = b"".join(chunks).decode("utf-8", errors="replace")
            logger.info("Fetched %d bytes from %s", len(html), url)
            return html

        except RequestException as exc:
            logger.warning("Failed to fetch %s: %s", url, exc)
            return ""
        except Exception as exc:
            logger.error("Unexpected error fetching %s: %s", url, exc)
            return ""
