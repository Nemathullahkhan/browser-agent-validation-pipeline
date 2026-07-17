from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.base import BrowserResult, ValidationResult
from app.review.models import ReviewItem


class ReviewQueueBase(ABC):
    @abstractmethod
    def enqueue(
        self,
        query: str,
        validation: ValidationResult,
        result: BrowserResult | None = None,
    ) -> ReviewItem: ...

    @abstractmethod
    def read_all(self) -> list[ReviewItem]: ...

    @abstractmethod
    def list_pending(self) -> list[ReviewItem]: ...

    @abstractmethod
    def approve(self, item_id: str, note: str = "") -> ReviewItem: ...

    @abstractmethod
    def reject(self, item_id: str, note: str = "") -> ReviewItem: ...
