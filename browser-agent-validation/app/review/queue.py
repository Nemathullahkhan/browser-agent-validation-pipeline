from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.models.base import BrowserResult, ValidationResult
from app.review.interfaces import ReviewQueueBase
from app.review.models import ReviewItem, ReviewStatus


class ReviewQueue(ReviewQueueBase):
    """Append-then-rewrite JSONL queue for HUMAN_REVIEW escalations."""

    def __init__(self, path: str | Path = "review_queue.jsonl") -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def enqueue(
        self,
        query: str,
        validation: ValidationResult,
        result: BrowserResult | None = None,
    ) -> ReviewItem:
        item = ReviewItem(
            item_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            query=query,
            result=result,
            validation=validation,
        )
        self._append(item)
        return item

    def read_all(self) -> list[ReviewItem]:
        if not self._path.exists():
            return []
        items: list[ReviewItem] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                items.append(ReviewItem.model_validate_json(line))
        return items

    def list_pending(self) -> list[ReviewItem]:
        return [i for i in self.read_all() if i.status == ReviewStatus.PENDING]

    def approve(self, item_id: str, note: str = "") -> ReviewItem:
        return self._update(item_id, ReviewStatus.APPROVED, note)

    def reject(self, item_id: str, note: str = "") -> ReviewItem:
        return self._update(item_id, ReviewStatus.REJECTED, note)

    def clear(self) -> None:
        if self._path.exists():
            self._path.unlink()

    # ── internals ─────────────────────────────────────────────────────────────

    def _append(self, item: ReviewItem) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(item.model_dump_json() + "\n")

    def _update(self, item_id: str, status: ReviewStatus, note: str) -> ReviewItem:
        items = self.read_all()
        updated: ReviewItem | None = None
        for i, item in enumerate(items):
            if item.item_id == item_id:
                items[i] = item.model_copy(update={
                    "status": status,
                    "reviewer_note": note,
                    "reviewed_at": datetime.now(timezone.utc).isoformat(),
                })
                updated = items[i]
                break
        if updated is None:
            raise KeyError(f"Review item not found: {item_id}")
        self._rewrite(items)
        return updated

    def _rewrite(self, items: list[ReviewItem]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as f:
            for item in items:
                f.write(item.model_dump_json() + "\n")
