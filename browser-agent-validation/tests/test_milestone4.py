from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest
from rich.panel import Panel
from rich.table import Table

from app.execution.engine import ExecutionEngine
from app.execution.interfaces import ExecutionContext
from app.execution.timeline import AGENT_STEPS, TimelineRenderer, _make_bar
from app.models.base import ExecutionEvent, ExecutionStatus, ExecutionTrace
from app.ui.live_timeline import LiveTimeline


# ---------------------------------------------------------------------------
# Engine callbacks
# ---------------------------------------------------------------------------

class TestEngineCallbacks:
    def test_on_step_start_fires_before_body(self):
        started: list[str] = []

        def on_start(event: ExecutionEvent) -> None:
            started.append(event.step)

        engine = ExecutionEngine(on_step_start=on_start)
        ctx = ExecutionContext(execution_id="cb-1", query="q")

        with engine.step(ctx, "search"):
            assert "search" in started  # fired before body

    def test_on_step_end_fires_after_body(self):
        ended: list[str] = []

        def on_end(event: ExecutionEvent) -> None:
            ended.append(event.step)

        engine = ExecutionEngine(on_step_end=on_end)
        ctx = ExecutionContext(execution_id="cb-2", query="q")

        with engine.step(ctx, "search"):
            assert ended == []  # not yet

        assert "search" in ended  # now done

    def test_on_step_end_receives_duration(self):
        received: list[ExecutionEvent] = []

        engine = ExecutionEngine(on_step_end=received.append)
        ctx = ExecutionContext(execution_id="cb-3", query="q")

        with engine.step(ctx, "reasoning"):
            time.sleep(0.01)

        assert received[0].duration_ms >= 10

    def test_on_step_end_fires_even_on_failure(self):
        ended: list[ExecutionEvent] = []

        engine = ExecutionEngine(on_step_end=ended.append)
        ctx = ExecutionContext(execution_id="cb-4", query="q")

        with pytest.raises(RuntimeError):
            with engine.step(ctx, "browser"):
                raise RuntimeError("fail")

        assert ended[0].status == ExecutionStatus.FAILED

    def test_no_callback_runs_without_error(self):
        engine = ExecutionEngine()
        ctx = ExecutionContext(execution_id="cb-5", query="q")
        with engine.step(ctx, "planning"):
            pass
        trace = engine.finalize(ctx)
        assert trace.status == ExecutionStatus.SUCCESS


# ---------------------------------------------------------------------------
# TimelineRenderer
# ---------------------------------------------------------------------------

def _sample_trace(ms_list: list[float] | None = None) -> ExecutionTrace:
    durations = ms_list or [1, 3452, 1309, 75, 65815, 0]
    events = []
    for name, ms in zip(AGENT_STEPS, durations):
        e = ExecutionEvent(
            step=name,
            status=ExecutionStatus.SUCCESS,
            start_time=time.time(),
            end_time=time.time() + ms / 1000,
            duration_ms=ms,
        )
        events.append(e)
    return ExecutionTrace(
        execution_id="sample",
        query="test",
        events=events,
        total_duration_ms=sum(durations),
        status=ExecutionStatus.SUCCESS,
    )


class TestTimelineRenderer:
    def test_render_table_returns_rich_table(self):
        renderer = TimelineRenderer()
        trace = _sample_trace()
        table = renderer.render_table(trace.events)
        assert isinstance(table, Table)

    def test_render_panel_returns_panel(self):
        renderer = TimelineRenderer()
        trace = _sample_trace()
        panel = renderer.render_panel(trace)
        assert isinstance(panel, Panel)

    def test_render_panel_green_on_success(self):
        renderer = TimelineRenderer()
        trace = _sample_trace()
        panel = renderer.render_panel(trace)
        assert panel.border_style == "green"

    def test_render_panel_red_on_failure(self):
        renderer = TimelineRenderer()
        trace = _sample_trace()
        trace.status = ExecutionStatus.FAILED
        panel = renderer.render_panel(trace)
        assert panel.border_style == "red"

    def test_all_six_steps_in_table(self):
        renderer = TimelineRenderer()
        trace = _sample_trace()
        table = renderer.render_table(trace.events)
        # Table rows = 6 steps + 2 total rows (blank + total)
        assert table.row_count == len(AGENT_STEPS) + 2

    def test_missing_steps_shown_as_pending(self):
        renderer = TimelineRenderer()
        partial = [ExecutionEvent(
            step="planning",
            status=ExecutionStatus.SUCCESS,
            start_time=time.time(),
            duration_ms=1.0,
        )]
        table = renderer.render_table(partial, step_order=AGENT_STEPS)
        # Should still show all 6 steps
        assert table.row_count == len(AGENT_STEPS) + 2

    def test_render_step_detail_returns_table(self):
        renderer = TimelineRenderer()
        trace = _sample_trace()
        table = renderer.render_step_detail(trace)
        assert isinstance(table, Table)
        assert table.row_count == len(AGENT_STEPS)

    def test_failed_step_shows_error(self):
        renderer = TimelineRenderer()
        events = [ExecutionEvent(
            step="search",
            status=ExecutionStatus.FAILED,
            start_time=time.time(),
            duration_ms=100.0,
            error="Connection refused",
        )]
        trace = ExecutionTrace(
            execution_id="err", query="q", events=events,
            status=ExecutionStatus.FAILED, total_duration_ms=100.0,
        )
        table = renderer.render_step_detail(trace)
        assert isinstance(table, Table)


class TestMakeBar:
    def test_full_bar(self):
        bar = _make_bar(1.0, ExecutionStatus.SUCCESS)
        assert "█" in bar.plain

    def test_empty_bar_for_zero(self):
        bar = _make_bar(0.0, ExecutionStatus.PENDING)
        assert "█" not in bar.plain

    def test_partial_bar(self):
        bar = _make_bar(0.5, ExecutionStatus.SUCCESS)
        # Should have some filled and some empty chars
        assert len(bar.plain) == 20


# ---------------------------------------------------------------------------
# LiveTimeline
# ---------------------------------------------------------------------------

class TestLiveTimeline:
    def test_render_returns_panel(self):
        lt = LiveTimeline()
        panel = lt.render()
        assert isinstance(panel, Panel)

    def test_on_step_start_records_running(self):
        lt = LiveTimeline()
        event = ExecutionEvent(
            step="search",
            status=ExecutionStatus.RUNNING,
            start_time=time.time(),
        )
        lt.on_step_start(event)
        assert "search" in lt._events
        assert lt._events["search"].status == ExecutionStatus.RUNNING

    def test_on_step_end_updates_status(self):
        lt = LiveTimeline()
        event = ExecutionEvent(
            step="search",
            status=ExecutionStatus.RUNNING,
            start_time=time.time(),
        )
        lt.on_step_start(event)
        event.status = ExecutionStatus.SUCCESS
        event.duration_ms = 100.0
        lt.on_step_end(event)
        assert lt._events["search"].status == ExecutionStatus.SUCCESS

    def test_attach_triggers_live_update(self):
        lt = LiveTimeline()
        mock_live = MagicMock()
        lt.attach(mock_live)

        event = ExecutionEvent(
            step="planning",
            status=ExecutionStatus.RUNNING,
            start_time=time.time(),
        )
        lt.on_step_start(event)
        mock_live.update.assert_called()

    def test_render_shows_pending_steps(self):
        lt = LiveTimeline()
        panel = lt.render()
        # With no events yet, should still render (pending state)
        assert isinstance(panel, Panel)

    def test_render_with_partial_progress(self):
        lt = LiveTimeline()
        events = [
            ExecutionEvent(step="planning", status=ExecutionStatus.SUCCESS,
                           start_time=time.time(), duration_ms=1.0),
            ExecutionEvent(step="search",   status=ExecutionStatus.RUNNING,
                           start_time=time.time()),
        ]
        for e in events:
            lt._events[e.step] = e
        panel = lt.render()
        assert isinstance(panel, Panel)

    def test_end_to_end_with_engine(self):
        """LiveTimeline receives all 6 step events from a real ExecutionEngine run."""
        lt = LiveTimeline()
        engine = ExecutionEngine(
            on_step_start=lt.on_step_start,
            on_step_end=lt.on_step_end,
        )
        ctx = ExecutionContext(execution_id="live-test", query="q")

        for step_name in AGENT_STEPS:
            with engine.step(ctx, step_name):
                pass

        # All 6 steps should be in lt._events and all SUCCESS
        assert set(lt._events.keys()) == set(AGENT_STEPS)
        assert all(e.status == ExecutionStatus.SUCCESS for e in lt._events.values())
