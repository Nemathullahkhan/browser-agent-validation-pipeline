from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.models.base import BrowserResult, RiskLevel, TrustDecision, ValidationResult
from app.review.interfaces import ReviewQueueBase
from app.review.models import ReviewItem, ReviewStatus
from app.review.queue import ReviewQueue


# ── helpers ───────────────────────────────────────────────────────────────────


def _vr(**kwargs) -> ValidationResult:
    defaults = dict(
        decision=TrustDecision.HUMAN_REVIEW,
        confidence=55.0,
        risk_level=RiskLevel.CRITICAL,
        policy_score=0.0,
        violations=["Critical risk — escalated"],
        reason="Critical risk level — escalated for human review",
    )
    defaults.update(kwargs)
    return ValidationResult(**defaults)


def _result() -> BrowserResult:
    return BrowserResult(
        summary="Some agent output here for review purposes.",
        sources=["Source A"],
        urls=["https://example.com"],
        latency_ms=500.0,
    )


# ── ReviewStatus ──────────────────────────────────────────────────────────────


class TestReviewStatus:
    def test_pending_value(self):
        assert ReviewStatus.PENDING == "pending"

    def test_approved_value(self):
        assert ReviewStatus.APPROVED == "approved"

    def test_rejected_value(self):
        assert ReviewStatus.REJECTED == "rejected"

    def test_is_str_enum(self):
        assert isinstance(ReviewStatus.PENDING, str)


# ── ReviewItem ────────────────────────────────────────────────────────────────


class TestReviewItem:
    def test_construction(self):
        item = ReviewItem(
            item_id="abc-123",
            timestamp="2026-07-17T10:00:00+00:00",
            query="test query",
            validation=_vr(),
        )
        assert item.item_id == "abc-123"
        assert item.query == "test query"

    def test_default_status_pending(self):
        item = ReviewItem(item_id="x", timestamp="t", query="q", validation=_vr())
        assert item.status == ReviewStatus.PENDING

    def test_default_reviewer_note_empty(self):
        item = ReviewItem(item_id="x", timestamp="t", query="q", validation=_vr())
        assert item.reviewer_note == ""

    def test_default_reviewed_at_none(self):
        item = ReviewItem(item_id="x", timestamp="t", query="q", validation=_vr())
        assert item.reviewed_at is None

    def test_result_optional_none_by_default(self):
        item = ReviewItem(item_id="x", timestamp="t", query="q", validation=_vr())
        assert item.result is None

    def test_result_can_be_set(self):
        item = ReviewItem(item_id="x", timestamp="t", query="q", validation=_vr(), result=_result())
        assert item.result is not None
        assert item.result.sources == ["Source A"]

    def test_validation_preserved(self):
        vr = _vr(confidence=55.0)
        item = ReviewItem(item_id="x", timestamp="t", query="q", validation=vr)
        assert item.validation.confidence == pytest.approx(55.0)

    def test_serialization(self):
        item = ReviewItem(item_id="x", timestamp="t", query="q", validation=_vr(), status=ReviewStatus.APPROVED)
        data = item.model_dump()
        assert data["status"] == "approved"
        assert data["item_id"] == "x"


# ── ReviewQueue — init ────────────────────────────────────────────────────────


class TestReviewQueueInit:
    def test_default_path(self):
        from pathlib import Path
        q = ReviewQueue()
        assert q.path == Path("review_queue.jsonl")

    def test_custom_path(self, tmp_path):
        p = tmp_path / "queue.jsonl"
        q = ReviewQueue(p)
        assert q.path == p

    def test_custom_path_string(self, tmp_path):
        from pathlib import Path
        p = str(tmp_path / "queue.jsonl")
        q = ReviewQueue(p)
        assert q.path == Path(p)

    def test_is_review_queue_base(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        assert isinstance(q, ReviewQueueBase)

    def test_interface_is_abstract(self):
        with pytest.raises(TypeError):
            ReviewQueueBase()  # type: ignore[abstract]


# ── ReviewQueue — enqueue ─────────────────────────────────────────────────────


class TestReviewQueueEnqueue:
    def test_enqueue_creates_file(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        assert not q.path.exists()
        q.enqueue("query", _vr())
        assert q.path.exists()

    def test_enqueue_returns_review_item(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        item = q.enqueue("my query", _vr())
        assert isinstance(item, ReviewItem)

    def test_enqueue_status_pending(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        item = q.enqueue("query", _vr())
        assert item.status == ReviewStatus.PENDING

    def test_enqueue_query_preserved(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        item = q.enqueue("what is AI?", _vr())
        assert item.query == "what is AI?"

    def test_enqueue_validation_preserved(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        vr = _vr(confidence=62.0)
        item = q.enqueue("q", vr)
        assert item.validation.confidence == pytest.approx(62.0)

    def test_enqueue_with_result(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        item = q.enqueue("q", _vr(), result=_result())
        assert item.result is not None

    def test_enqueue_without_result(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        item = q.enqueue("q", _vr())
        assert item.result is None

    def test_enqueue_item_id_is_uuid(self, tmp_path):
        import uuid
        q = ReviewQueue(tmp_path / "q.jsonl")
        item = q.enqueue("q", _vr())
        assert uuid.UUID(item.item_id)  # valid UUID

    def test_enqueue_ids_are_unique(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        ids = {q.enqueue("q", _vr()).item_id for _ in range(5)}
        assert len(ids) == 5

    def test_enqueue_timestamp_is_utc(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        item = q.enqueue("q", _vr())
        ts = item.timestamp
        assert "Z" in ts or "+00:00" in ts

    def test_enqueue_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "nested" / "dir" / "q.jsonl"
        q = ReviewQueue(p)
        q.enqueue("q", _vr())
        assert p.exists()


# ── ReviewQueue — read_all / list_pending ─────────────────────────────────────


class TestReviewQueueRead:
    def test_read_all_nonexistent_returns_empty(self, tmp_path):
        q = ReviewQueue(tmp_path / "missing.jsonl")
        assert q.read_all() == []

    def test_read_all_single_item(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        q.enqueue("q", _vr())
        assert len(q.read_all()) == 1

    def test_read_all_multiple_items(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        for i in range(4):
            q.enqueue(f"query {i}", _vr())
        assert len(q.read_all()) == 4

    def test_read_all_preserves_order(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        q.enqueue("first", _vr())
        q.enqueue("second", _vr())
        items = q.read_all()
        assert items[0].query == "first"
        assert items[1].query == "second"

    def test_read_all_returns_review_items(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        q.enqueue("q", _vr())
        assert all(isinstance(i, ReviewItem) for i in q.read_all())

    def test_list_pending_returns_only_pending(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        q.enqueue("q1", _vr())
        item2 = q.enqueue("q2", _vr())
        q.approve(item2.item_id)
        pending = q.list_pending()
        assert len(pending) == 1
        assert pending[0].query == "q1"

    def test_list_pending_empty_when_all_resolved(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        item = q.enqueue("q", _vr())
        q.reject(item.item_id)
        assert q.list_pending() == []

    def test_jsonl_one_json_per_line(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        q.enqueue("a", _vr())
        q.enqueue("b", _vr())
        lines = [l for l in q.path.read_text().splitlines() if l.strip()]
        assert len(lines) == 2
        for line in lines:
            data = json.loads(line)
            assert "item_id" in data


# ── ReviewQueue — approve / reject ────────────────────────────────────────────


class TestReviewQueueApproveReject:
    def test_approve_changes_status(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        item = q.enqueue("q", _vr())
        updated = q.approve(item.item_id)
        assert updated.status == ReviewStatus.APPROVED

    def test_approve_sets_reviewed_at(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        item = q.enqueue("q", _vr())
        before = datetime.now(timezone.utc)
        updated = q.approve(item.item_id)
        after = datetime.now(timezone.utc)
        reviewed = datetime.fromisoformat(updated.reviewed_at.replace("Z", "+00:00"))
        assert before <= reviewed <= after

    def test_approve_stores_note(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        item = q.enqueue("q", _vr())
        updated = q.approve(item.item_id, note="Looks clean")
        assert updated.reviewer_note == "Looks clean"

    def test_reject_changes_status(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        item = q.enqueue("q", _vr())
        updated = q.reject(item.item_id)
        assert updated.status == ReviewStatus.REJECTED

    def test_reject_stores_note(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        item = q.enqueue("q", _vr())
        updated = q.reject(item.item_id, note="PII confirmed")
        assert updated.reviewer_note == "PII confirmed"

    def test_approve_persisted_to_file(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        item = q.enqueue("q", _vr())
        q.approve(item.item_id, note="ok")
        reloaded = q.read_all()
        assert reloaded[0].status == ReviewStatus.APPROVED
        assert reloaded[0].reviewer_note == "ok"

    def test_reject_persisted_to_file(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        item = q.enqueue("q", _vr())
        q.reject(item.item_id, note="bad")
        reloaded = q.read_all()
        assert reloaded[0].status == ReviewStatus.REJECTED

    def test_approve_nonexistent_raises_key_error(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        with pytest.raises(KeyError):
            q.approve("nonexistent-id")

    def test_reject_nonexistent_raises_key_error(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        with pytest.raises(KeyError):
            q.reject("nonexistent-id")

    def test_approve_only_changes_target_item(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        item1 = q.enqueue("q1", _vr())
        item2 = q.enqueue("q2", _vr())
        q.approve(item1.item_id)
        items = q.read_all()
        assert items[0].status == ReviewStatus.APPROVED
        assert items[1].status == ReviewStatus.PENDING

    def test_default_note_is_empty(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        item = q.enqueue("q", _vr())
        updated = q.approve(item.item_id)
        assert updated.reviewer_note == ""


# ── ReviewQueue — clear ───────────────────────────────────────────────────────


class TestReviewQueueClear:
    def test_clear_removes_file(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        q.enqueue("q", _vr())
        q.clear()
        assert not q.path.exists()

    def test_clear_nonexistent_is_noop(self, tmp_path):
        q = ReviewQueue(tmp_path / "missing.jsonl")
        q.clear()  # must not raise

    def test_read_all_after_clear_empty(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        q.enqueue("q", _vr())
        q.clear()
        assert q.read_all() == []

    def test_enqueue_after_clear_works(self, tmp_path):
        q = ReviewQueue(tmp_path / "q.jsonl")
        q.enqueue("first", _vr())
        q.clear()
        q.enqueue("second", _vr())
        items = q.read_all()
        assert len(items) == 1
        assert items[0].query == "second"
