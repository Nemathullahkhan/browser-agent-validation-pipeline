from __future__ import annotations

import logging

import trafilatura
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class TrafilaturaExtractor:
    """Extract clean readable text from HTML using trafilatura, with BS4 as fallback."""

    def __init__(self, max_chars: int = 3000) -> None:
        self._max_chars = max_chars

    def extract(self, html: str, url: str = "") -> str:
        if not html:
            return ""

        text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_recall=True,
        )

        if not text:
            text = self._bs4_fallback(html)

        if text:
            text = text.strip()
            if len(text) > self._max_chars:
                text = text[: self._max_chars] + "…"
            logger.debug("Extracted %d chars from %s", len(text), url or "unknown")
        else:
            logger.debug("No text extracted from %s", url or "unknown")

        return text or ""

    def _bs4_fallback(self, html: str) -> str:
        try:
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            return soup.get_text(separator=" ", strip=True)
        except Exception as exc:
            logger.warning("BS4 fallback extraction failed: %s", exc)
            return ""
