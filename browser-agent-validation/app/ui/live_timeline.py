from __future__ import annotations

import time
from typing import TYPE_CHECKING

from rich.panel import Panel

from app.execution.timeline import AGENT_STEPS, TimelineRenderer
from app.models.base import ExecutionEvent, ExecutionStatus, ExecutionTrace

if TYPE_CHECKING:
    from rich.live import Live


class LiveTimeline:
    """
    Tracks step state during a BrowserAgent run and provides a renderable
    Rich panel that updates as each step starts and finishes.

    Usage
    -----
    live_tl = LiveTimeline()
    engine  = ExecutionEngine(
        on_step_start=live_tl.on_step_start,
        on_step_end=live_tl.on_step_end,
    )
    with Live(live_tl.render(), ...) as live:
        live_tl.attach(live)
        agent.run(query)
    """

    def __init__(self, step_order: list[str] | None = None) -> None:
        self._step_order = step_order or AGENT_STEPS
        self._events: dict[str, ExecutionEvent] = {}
        self._live: Live | None = None
        self._renderer = TimelineRenderer()
        self._start_time = time.time()

    def attach(self, live: Live) -> None:
        self._live = live

    # ── Callbacks fired by ExecutionEngine ───────────────────────────────────

    def on_step_start(self, event: ExecutionEvent) -> None:
        self._events[event.step] = event
        self._refresh()

    def on_step_end(self, event: ExecutionEvent) -> None:
        self._events[event.step] = event
        self._refresh()

    # ── Rendering ────────────────────────────────────────────────────────────

    def render(self) -> Panel:
        """Build a renderable from the current tracked state."""
        snapshot_events = list(self._events.values())
        fake_trace = ExecutionTrace(
            execution_id="live",
            query="",
            events=snapshot_events,
            total_duration_ms=sum(e.duration_ms or 0.0 for e in snapshot_events),
            status=self._current_status(snapshot_events),
        )
        running_step = next(
            (e.step for e in snapshot_events if e.status == ExecutionStatus.RUNNING),
            None,
        )
        subtitle = f"[yellow]Running: {running_step}[/yellow]" if running_step else ""
        table = self._renderer.render_table(
            snapshot_events, step_order=self._step_order
        )
        return Panel(
            table,
            title="[bold white]Execution Timeline[/bold white]",
            subtitle=subtitle,
            border_style="blue",
            padding=(0, 2),
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.update(self.render())

    @staticmethod
    def _current_status(events: list[ExecutionEvent]) -> ExecutionStatus:
        if any(e.status == ExecutionStatus.FAILED for e in events):
            return ExecutionStatus.FAILED
        if any(e.status == ExecutionStatus.RUNNING for e in events):
            return ExecutionStatus.RUNNING
        return ExecutionStatus.PENDING
