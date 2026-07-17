from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class MetricsEngine(ABC):
    @abstractmethod
    def record(self, key: str, value: float | int, tags: dict[str, str] | None = None) -> None:
        ...

    @abstractmethod
    def summary(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def export(self, path: str) -> None:
        ...
