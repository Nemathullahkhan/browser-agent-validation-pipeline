from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.audit.interfaces import AuditStore
from app.models.base import AuditEvent, ValidationResult


class LocalAuditStore(AuditStore):
    """Append-only JSONL audit store persisted to a local file."""

    def __init__(self, path: str | Path = "audit.jsonl") -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, event: AuditEvent) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")

    def read_all(self) -> list[AuditEvent]:
        if not self._path.exists():
            return []
        events: list[AuditEvent] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                events.append(AuditEvent.model_validate_json(line))
        return events

    def clear(self) -> None:
        if self._path.exists():
            self._path.unlink()


def make_audit_event(
    execution_id: str,
    validation: ValidationResult,
    latency_ms: float,
    metadata: dict | None = None,
) -> AuditEvent:
    return AuditEvent(
        execution_id=execution_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        decision=validation.decision,
        confidence=validation.confidence,
        risk=validation.risk_level,
        latency_ms=latency_ms,
        violations=list(validation.violations),
        metadata=metadata or {},
    )
