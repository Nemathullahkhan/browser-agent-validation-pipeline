from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.base import BrowserResult, ExecutionTrace


class ComparisonRunner(ABC):
    @abstractmethod
    def run_without_trust(self, query: str) -> tuple[BrowserResult, ExecutionTrace]:
        ...

    @abstractmethod
    def run_with_trust(self, query: str) -> tuple[BrowserResult, ExecutionTrace]:
        ...

    @abstractmethod
    def compare(self, query: str) -> dict:
        ...
