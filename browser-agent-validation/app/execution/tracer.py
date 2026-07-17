from __future__ import annotations

import json
from pathlib import Path

from app.models.base import ExecutionStatus, ExecutionTrace

_STEP_ICONS = {
    ExecutionStatus.SUCCESS: "✓",
    ExecutionStatus.FAILED: "✗",
    ExecutionStatus.RUNNING: "…",
    ExecutionStatus.PENDING: "○",
    ExecutionStatus.BLOCKED: "⊘",
}


def save_trace(trace: ExecutionTrace, path: str | Path = "trace.json") -> Path:
    p = Path(path)
    p.write_text(trace.model_dump_json(indent=2), encoding="utf-8")
    return p


def load_trace(path: str | Path = "trace.json") -> ExecutionTrace:
    p = Path(path)
    return ExecutionTrace.model_validate_json(p.read_text(encoding="utf-8"))


def format_timeline(trace: ExecutionTrace) -> list[str]:
    """Return lines describing each step — suitable for Rich or plain printing."""
    lines: list[str] = []
    for event in trace.events:
        icon = _STEP_ICONS.get(event.status, "?")
        dur = f"{event.duration_ms:.0f} ms" if event.duration_ms is not None else "—"
        name = event.step.replace("_", " ").title()
        suffix = f"  [{event.error}]" if event.error else ""
        lines.append(f"{icon}  {name:<16} {dur:>8}{suffix}")

    if trace.total_duration_ms is not None:
        lines.append("")
        lines.append(f"   {'Total':<16} {trace.total_duration_ms:.0f} ms")

    return lines
