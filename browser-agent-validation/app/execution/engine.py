from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Callable, Generator

from app.execution.interfaces import ExecutionContext, ExecutionEngineBase, StepContext
from app.models.base import ExecutionEvent, ExecutionStatus, ExecutionTrace

StepCallback = Callable[[ExecutionEvent], None]


class ExecutionEngine(ExecutionEngineBase):
    """Records timing and I/O for every named step; fires optional callbacks."""

    def __init__(
        self,
        on_step_start: StepCallback | None = None,
        on_step_end: StepCallback | None = None,
    ) -> None:
        self._on_step_start = on_step_start
        self._on_step_end = on_step_end

    @contextmanager
    def step(self, ctx: ExecutionContext, step_name: str) -> Generator[StepContext, None, None]:
        event = ExecutionEvent(
            step=step_name,
            status=ExecutionStatus.RUNNING,
            start_time=time.time(),
        )
        if self._on_step_start:
            self._on_step_start(event)

        step_ctx = StepContext(event)
        try:
            yield step_ctx
            event.status = ExecutionStatus.SUCCESS
        except Exception as exc:
            event.status = ExecutionStatus.FAILED
            event.error = str(exc)
            raise
        finally:
            event.end_time = time.time()
            event.duration_ms = (event.end_time - event.start_time) * 1000
            ctx.emit(event)
            if self._on_step_end:
                self._on_step_end(event)

    def finalize(self, ctx: ExecutionContext) -> ExecutionTrace:
        failed = [e for e in ctx.trace.events if e.status == ExecutionStatus.FAILED]
        ctx.trace.status = ExecutionStatus.FAILED if failed else ExecutionStatus.SUCCESS
        ctx.trace.total_duration_ms = sum(e.duration_ms or 0.0 for e in ctx.trace.events)
        return ctx.trace
