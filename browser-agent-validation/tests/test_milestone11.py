from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.audit.interfaces import AuditStore
from app.audit.store import LocalAuditStore, make_audit_event
from app.models.base import AuditEvent, RiskLevel, TrustDecision, ValidationResult


# ── helpers ───────────────────────────────────────────────────────────────────


def _vr(**kwargs) -> ValidationResult:
    defaults = dict(
        decision=TrustDecision.ALLOW,
        confidence=85.0,
        risk_level=RiskLevel.LOW,
        policy_score=90.0,
        violations=[],
    )
    defaults.update(kwargs)
    return ValidationResult(**defaults)


def _event(**kwargs) -> AuditEvent:
    defaults = dict(
        execution_id="test-exec-001",
        timestamp=datetime.now(timezone.utc).isoformat(),
        decision=TrustDecision.ALLOW,
        confidence=85.0,
        risk=RiskLevel.LOW,
        latency_ms=123.4,
        violations=[],
        metadata={},
    )
    defaults.update(kwargs)
    return AuditEvent(**defaults)


# ── LocalAuditStore — init ────────────────────────────────────────────────────


class TestLocalAuditStoreInit:
    def test_default_path(self):
        from pathlib import Path
        store = LocalAuditStore()
        assert store.path == Path("audit.jsonl")

    def test_custom_path(self, tmp_path):
        p = tmp_path / "my_audit.jsonl"
        store = LocalAuditStore(p)
        assert store.path == p

    def test_custom_path_string(self, tmp_path):
        from pathlib import Path
        p = str(tmp_path / "audit.jsonl")
        store = LocalAuditStore(p)
        assert store.path == Path(p)

    def test_path_property_returns_path_object(self, tmp_path):
        from pathlib import Path
        store = LocalAuditStore(tmp_path / "a.jsonl")
        assert isinstance(store.path, Path)


# ── LocalAuditStore — append ──────────────────────────────────────────────────


class TestLocalAuditStoreAppend:
    def test_append_creates_file(self, tmp_path):
        store = LocalAuditStore(tmp_path / "audit.jsonl")
        assert not store.path.exists()
        store.append(_event())
        assert store.path.exists()

    def test_append_single_event_readable(self, tmp_path):
        store = LocalAuditStore(tmp_path / "audit.jsonl")
        store.append(_event())
        assert len(store.read_all()) == 1

    def test_append_multiple_events(self, tmp_path):
        store = LocalAuditStore(tmp_path / "audit.jsonl")
        for i in range(3):
            store.append(_event(execution_id=f"exec-{i}"))
        assert len(store.read_all()) == 3

    def test_append_preserves_order(self, tmp_path):
        store = LocalAuditStore(tmp_path / "audit.jsonl")
        for i in range(5):
            store.append(_event(execution_id=f"exec-{i:03}"))
        ids = [e.execution_id for e in store.read_all()]
        assert ids == [f"exec-{i:03}" for i in range(5)]

    def test_append_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "nested" / "dir" / "audit.jsonl"
        store = LocalAuditStore(p)
        store.append(_event())
        assert p.exists()

    def test_jsonl_one_json_per_line(self, tmp_path):
        store = LocalAuditStore(tmp_path / "audit.jsonl")
        store.append(_event(execution_id="a"))
        store.append(_event(execution_id="b"))
        lines = [l for l in store.path.read_text().splitlines() if l.strip()]
        assert len(lines) == 2

    def test_each_line_is_valid_json(self, tmp_path):
        store = LocalAuditStore(tmp_path / "audit.jsonl")
        store.append(_event())
        lines = [l for l in store.path.read_text().splitlines() if l.strip()]
        for line in lines:
            data = json.loads(line)
            assert "execution_id" in data

    def test_append_is_incremental_not_overwrite(self, tmp_path):
        store = LocalAuditStore(tmp_path / "audit.jsonl")
        store.append(_event(execution_id="first"))
        store.append(_event(execution_id="second"))
        events = store.read_all()
        assert events[0].execution_id == "first"
        assert events[1].execution_id == "second"


# ── LocalAuditStore — read_all ────────────────────────────────────────────────


class TestLocalAuditStoreReadAll:
    def test_nonexistent_returns_empty(self, tmp_path):
        store = LocalAuditStore(tmp_path / "missing.jsonl")
        assert store.read_all() == []

    def test_roundtrip_execution_id(self, tmp_path):
        store = LocalAuditStore(tmp_path / "audit.jsonl")
        store.append(_event(execution_id="my-exec-id"))
        assert store.read_all()[0].execution_id == "my-exec-id"

    def test_roundtrip_decision(self, tmp_path):
        store = LocalAuditStore(tmp_path / "audit.jsonl")
        store.append(_event(decision=TrustDecision.BLOCK))
        assert store.read_all()[0].decision == TrustDecision.BLOCK

    def test_roundtrip_confidence(self, tmp_path):
        store = LocalAuditStore(tmp_path / "audit.jsonl")
        store.append(_event(confidence=72.5))
        assert store.read_all()[0].confidence == pytest.approx(72.5)

    def test_roundtrip_risk(self, tmp_path):
        store = LocalAuditStore(tmp_path / "audit.jsonl")
        store.append(_event(risk=RiskLevel.CRITICAL))
        assert store.read_all()[0].risk == RiskLevel.CRITICAL

    def test_roundtrip_latency(self, tmp_path):
        store = LocalAuditStore(tmp_path / "audit.jsonl")
        store.append(_event(latency_ms=456.78))
        assert store.read_all()[0].latency_ms == pytest.approx(456.78)

    def test_roundtrip_violations(self, tmp_path):
        store = LocalAuditStore(tmp_path / "audit.jsonl")
        store.append(_event(violations=["injection detected", "low confidence"]))
        assert store.read_all()[0].violations == ["injection detected", "low confidence"]

    def test_roundtrip_metadata(self, tmp_path):
        store = LocalAuditStore(tmp_path / "audit.jsonl")
        store.append(_event(metadata={"mode": "governed", "stage": "output"}))
        assert store.read_all()[0].metadata == {"mode": "governed", "stage": "output"}

    def test_returns_audit_event_instances(self, tmp_path):
        store = LocalAuditStore(tmp_path / "audit.jsonl")
        store.append(_event())
        assert all(isinstance(e, AuditEvent) for e in store.read_all())

    def test_roundtrip_timestamp(self, tmp_path):
        ts = datetime.now(timezone.utc).isoformat()
        store = LocalAuditStore(tmp_path / "audit.jsonl")
        store.append(_event(timestamp=ts))
        assert store.read_all()[0].timestamp == ts


# ── LocalAuditStore — clear ───────────────────────────────────────────────────


class TestLocalAuditStoreClear:
    def test_clear_removes_file(self, tmp_path):
        store = LocalAuditStore(tmp_path / "audit.jsonl")
        store.append(_event())
        store.clear()
        assert not store.path.exists()

    def test_clear_nonexistent_is_noop(self, tmp_path):
        store = LocalAuditStore(tmp_path / "missing.jsonl")
        store.clear()  # must not raise

    def test_read_all_after_clear_empty(self, tmp_path):
        store = LocalAuditStore(tmp_path / "audit.jsonl")
        store.append(_event())
        store.clear()
        assert store.read_all() == []

    def test_clear_then_append_works(self, tmp_path):
        store = LocalAuditStore(tmp_path / "audit.jsonl")
        store.append(_event(execution_id="first"))
        store.clear()
        store.append(_event(execution_id="second"))
        events = store.read_all()
        assert len(events) == 1
        assert events[0].execution_id == "second"


# ── make_audit_event ──────────────────────────────────────────────────────────


class TestMakeAuditEvent:
    def test_returns_audit_event(self):
        event = make_audit_event("exec-1", _vr(), 100.0)
        assert isinstance(event, AuditEvent)

    def test_execution_id_preserved(self):
        event = make_audit_event("my-unique-id", _vr(), 0.0)
        assert event.execution_id == "my-unique-id"

    def test_decision_preserved(self):
        event = make_audit_event("e", _vr(decision=TrustDecision.BLOCK), 0.0)
        assert event.decision == TrustDecision.BLOCK

    def test_confidence_preserved(self):
        event = make_audit_event("e", _vr(confidence=67.3), 0.0)
        assert event.confidence == pytest.approx(67.3)

    def test_risk_preserved(self):
        event = make_audit_event("e", _vr(risk_level=RiskLevel.HIGH), 0.0)
        assert event.risk == RiskLevel.HIGH

    def test_latency_preserved(self):
        event = make_audit_event("e", _vr(), 999.9)
        assert event.latency_ms == pytest.approx(999.9)

    def test_violations_copied(self):
        event = make_audit_event("e", _vr(violations=["v1", "v2"]), 0.0)
        assert event.violations == ["v1", "v2"]

    def test_violations_is_independent_copy(self):
        vr = _vr(violations=["v1"])
        event = make_audit_event("e", vr, 0.0)
        event.violations.append("extra")
        assert "extra" not in vr.violations

    def test_metadata_default_empty(self):
        event = make_audit_event("e", _vr(), 0.0)
        assert event.metadata == {}

    def test_metadata_preserved(self):
        event = make_audit_event("e", _vr(), 0.0, metadata={"k": "v"})
        assert event.metadata == {"k": "v"}

    def test_timestamp_is_string(self):
        event = make_audit_event("e", _vr(), 0.0)
        assert isinstance(event.timestamp, str)

    def test_timestamp_has_utc_indicator(self):
        event = make_audit_event("e", _vr(), 0.0)
        ts = event.timestamp
        assert "Z" in ts or "+00:00" in ts

    def test_timestamp_is_recent(self):
        before = datetime.now(timezone.utc)
        event = make_audit_event("e", _vr(), 0.0)
        after = datetime.now(timezone.utc)
        ts = datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))
        assert before <= ts <= after

    def test_zero_latency_allowed(self):
        event = make_audit_event("e", _vr(), 0.0)
        assert event.latency_ms == 0.0

    def test_empty_violations_list(self):
        event = make_audit_event("e", _vr(violations=[]), 0.0)
        assert event.violations == []


# ── AuditStore interface ──────────────────────────────────────────────────────


class TestAuditStoreInterface:
    def test_is_abstract(self):
        with pytest.raises(TypeError):
            AuditStore()  # type: ignore[abstract]

    def test_local_store_is_audit_store(self, tmp_path):
        store = LocalAuditStore(tmp_path / "a.jsonl")
        assert isinstance(store, AuditStore)

    def test_interface_has_append(self):
        assert callable(getattr(AuditStore, "append", None))

    def test_interface_has_read_all(self):
        assert callable(getattr(AuditStore, "read_all", None))

    def test_local_store_has_clear(self, tmp_path):
        store = LocalAuditStore(tmp_path / "a.jsonl")
        assert callable(store.clear)


# ── Integration: make_audit_event → store roundtrip ──────────────────────────


class TestMakeAndStoreRoundtrip:
    def test_event_from_allow_vr(self, tmp_path):
        store = LocalAuditStore(tmp_path / "audit.jsonl")
        vr = _vr(decision=TrustDecision.ALLOW, confidence=91.0, risk_level=RiskLevel.LOW)
        event = make_audit_event("exec-allow", vr, 250.0)
        store.append(event)
        recovered = store.read_all()[0]
        assert recovered.execution_id == "exec-allow"
        assert recovered.decision == TrustDecision.ALLOW
        assert recovered.confidence == pytest.approx(91.0)

    def test_event_from_block_vr(self, tmp_path):
        store = LocalAuditStore(tmp_path / "audit.jsonl")
        vr = _vr(
            decision=TrustDecision.BLOCK,
            confidence=30.0,
            risk_level=RiskLevel.CRITICAL,
            violations=["SSN detected"],
        )
        event = make_audit_event("exec-block", vr, 0.0)
        store.append(event)
        recovered = store.read_all()[0]
        assert recovered.decision == TrustDecision.BLOCK
        assert recovered.risk == RiskLevel.CRITICAL
        assert "SSN detected" in recovered.violations

    def test_multiple_events_different_decisions(self, tmp_path):
        store = LocalAuditStore(tmp_path / "audit.jsonl")
        store.append(make_audit_event("e1", _vr(decision=TrustDecision.ALLOW), 100.0))
        store.append(make_audit_event("e2", _vr(decision=TrustDecision.BLOCK), 0.0))
        store.append(make_audit_event("e3", _vr(decision=TrustDecision.ALLOW), 200.0))
        events = store.read_all()
        assert len(events) == 3
        assert events[0].decision == TrustDecision.ALLOW
        assert events[1].decision == TrustDecision.BLOCK
        assert events[2].decision == TrustDecision.ALLOW
