from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Any, Generator

from app.models.base import ExecutionEvent, ExecutionTrace


class ExecutionContext:
    def __init__(self, execution_id: str, query: str) -> None:
        self.execution_id = execution_id
        self.query = query
        self.trace = ExecutionTrace(execution_id=execution_id, query=query)

    def emit(self, event: ExecutionEvent) -> None:
        self.trace.events.append(event)


class StepContext:
    """Passed into each `with engine.step(...)` block to record I/O metadata."""

    def __init__(self, event: ExecutionEvent) -> None:
        self._event = event

    def set_inputs(self, **kwargs: Any) -> None:
        self._event.inputs = _safe_serialize(kwargs)

    def set_outputs(self, **kwargs: Any) -> None:
        self._event.outputs = _safe_serialize(kwargs)


class ExecutionEngineBase(ABC):
    @abstractmethod
    @contextmanager
    def step(self, ctx: ExecutionContext, step_name: str) -> Generator[StepContext, None, None]:
        ...

    @abstractmethod
    def finalize(self, ctx: ExecutionContext) -> ExecutionTrace:
        ...


def _safe_serialize(data: dict[str, Any]) -> dict[str, Any]:
    """Serialize values to JSON-safe primitives, truncating large blobs."""
    out: dict[str, Any] = {}
    for k, v in data.items():
        if isinstance(v, (str, int, float, bool, type(None))):
            out[k] = v[:500] if isinstance(v, str) and len(v) > 500 else v
        elif isinstance(v, (list, tuple)):
            out[k] = [_truncate(item) for item in v[:20]]
        elif isinstance(v, dict):
            out[k] = {dk: _truncate(dv) for dk, dv in list(v.items())[:10]}
        else:
            out[k] = repr(v)[:200]
    return out


def _truncate(value: Any) -> Any:
    if isinstance(value, str) and len(value) > 200:
        return value[:200] + "…"
    return value
