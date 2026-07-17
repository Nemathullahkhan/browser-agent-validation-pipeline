from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.models.base import BrowserResult, ValidationResult


class TrustMiddleware(ABC):
    @abstractmethod
    def validate(self, query: str, result: BrowserResult) -> ValidationResult:
        ...

    @abstractmethod
    def wrap(self, query: str, result: BrowserResult) -> BrowserResult:
        ...


class PolicyEngine(ABC):
    @abstractmethod
    def evaluate(self, output: dict[str, Any]) -> tuple[float, list[str]]:
        ...


class AuditLogger(ABC):
    @abstractmethod
    def log(self, event: dict[str, Any]) -> None:
        ...
