from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol

from app.models.base import BrowserResult


class SearchTool(Protocol):
    def search(self, query: str, max_results: int = 5) -> list[dict]:
        ...


class BrowserTool(Protocol):
    def fetch(self, url: str, timeout: int = 10) -> str:
        ...


class Extractor(Protocol):
    def extract(self, html: str, url: str = "") -> str:
        ...


class Summarizer(ABC):
    @abstractmethod
    def summarize(self, query: str, context: str, sources: list[str]) -> str:
        ...


class BrowserAgentBase(ABC):
    @abstractmethod
    def run(self, query: str) -> BrowserResult:
        ...
