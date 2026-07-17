from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.base import AuditEvent


class AuditStore(ABC):
    @abstractmethod
    def append(self, event: AuditEvent) -> None:
        ...

    @abstractmethod
    def read_all(self) -> list[AuditEvent]:
        ...
