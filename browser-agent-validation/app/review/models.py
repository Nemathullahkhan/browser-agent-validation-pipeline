from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.models.base import BrowserResult, ValidationResult


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewItem(BaseModel):
    item_id: str
    timestamp: str
    query: str
    result: BrowserResult | None = None
    validation: ValidationResult
    status: ReviewStatus = ReviewStatus.PENDING
    reviewer_note: str = ""
    reviewed_at: str | None = None
