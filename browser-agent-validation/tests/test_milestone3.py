from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.browser_agent.agent import BrowserAgent
from app.browser_agent.interfaces import Summarizer
from app.browser_agent.planner import QueryPlanner
from app.execution.engine import ExecutionEngine
from app.execution.interfaces import ExecutionContext, StepContext
from app.execution.tracer import format_timeline, load_trace, save_trace
from app.models.base import ExecutionStatus, ExecutionTrace


# ---------------------------------------------------------------------------
# ExecutionEngine
# ---------------------------------------------------------------------------

class TestExecutionEngine:
    def test_step_records_success(self):
        engine = ExecutionEngine()
        ctx = ExecutionContext(execution_id="test-1", query="q")

        with engine.step(ctx, "search") as step:
            step.set_inputs(query="q")
            step.set_outputs(results_count=5)

        assert len(ctx.trace.events) == 1
        event = ctx.trace.events[0]
        assert event.step == "search"
        assert event.status == ExecutionStatus.SUCCESS
        assert event.inputs["query"] == "q"
        assert event.outputs["results_count"] == 5
        assert event.duration_ms is not None
        assert event.duration_ms >= 0

    def test_step_records_failure(self):
        engine = ExecutionEngine()
        ctx = ExecutionContext(execution_id="test-2", query="q")

        with pytest.raises(ValueError):
            with engine.step(ctx, "search") as step:
                step.set_inputs(query="q")
                raise ValueError("search failed")

        event = ctx.trace.events[0]
        assert event.status == ExecutionStatus.FAILED
        assert event.error == "search failed"

    def test_step_records_timing(self):
        engine = ExecutionEngine()
        ctx = ExecutionContext(execution_id="test-3", query="q")

        with engine.step(ctx, "slow_step") as step:
            time.sleep(0.01)

        event = ctx.trace.events[0]
        assert event.end_time is not None
        assert event.duration_ms >= 10  # at least 10 ms

    def test_finalize_sums_durations(self):
        engine = ExecutionEngine()
        ctx = ExecutionContext(execution_id="test-4", query="q")

        with engine.step(ctx, "a") as step:
            pass
        with engine.step(ctx, "b") as step:
            pass

        trace = engine.finalize(ctx)
        assert trace.total_duration_ms >= 0
        assert trace.status == ExecutionStatus.SUCCESS

    def test_finalize_marks_failed_if_any_step_failed(self):
        engine = ExecutionEngine()
        ctx = ExecutionContext(execution_id="test-5", query="q")

        with engine.step(ctx, "a"):
            pass

        with pytest.raises(RuntimeError):
            with engine.step(ctx, "b"):
                raise RuntimeError("oops")

        trace = engine.finalize(ctx)
        assert trace.status == ExecutionStatus.FAILED

    def test_multiple_steps_all_recorded(self):
        engine = ExecutionEngine()
        ctx = ExecutionContext(execution_id="test-6", query="q")

        steps = ["planning", "search", "browser", "extraction", "reasoning", "response"]
        for name in steps:
            with engine.step(ctx, name):
                pass

        assert len(ctx.trace.events) == 6
        assert [e.step for e in ctx.trace.events] == steps


# ---------------------------------------------------------------------------
# StepContext serialisation
# ---------------------------------------------------------------------------

class TestStepContext:
    def test_truncates_long_strings(self):
        from app.models.base import ExecutionEvent
        event = ExecutionEvent(step="x", status=ExecutionStatus.RUNNING, start_time=time.time())
        step_ctx = StepContext(event)
        step_ctx.set_inputs(big="A" * 1000)
        assert len(event.inputs["big"]) <= 503  # 500 + "…"

    def test_handles_list_values(self):
        from app.models.base import ExecutionEvent
        event = ExecutionEvent(step="x", status=ExecutionStatus.RUNNING, start_time=time.time())
        step_ctx = StepContext(event)
        step_ctx.set_outputs(urls=["http://a.com", "http://b.com"])
        assert event.outputs["urls"] == ["http://a.com", "http://b.com"]


# ---------------------------------------------------------------------------
# Tracer
# ---------------------------------------------------------------------------

class TestTracer:
    def test_save_and_load_roundtrip(self, tmp_path):
        trace = ExecutionTrace(execution_id="abc", query="test")
        p = tmp_path / "trace.json"
        save_trace(trace, p)
        loaded = load_trace(p)
        assert loaded.execution_id == "abc"
        assert loaded.query == "test"

    def test_save_produces_valid_json(self, tmp_path):
        trace = ExecutionTrace(execution_id="abc", query="test")
        p = tmp_path / "trace.json"
        save_trace(trace, p)
        data = json.loads(p.read_text())
        assert data["execution_id"] == "abc"

    def test_format_timeline_lists_step_names(self):
        engine = ExecutionEngine()
        ctx = ExecutionContext(execution_id="t1", query="q")
        for name in ["planning", "search", "browser"]:
            with engine.step(ctx, name):
                pass
        trace = engine.finalize(ctx)
        lines = format_timeline(trace)
        assert any("Planning" in l for l in lines)
        assert any("Search" in l for l in lines)
        assert any("Browser" in l for l in lines)

    def test_format_timeline_includes_total(self):
        engine = ExecutionEngine()
        ctx = ExecutionContext(execution_id="t2", query="q")
        with engine.step(ctx, "step"):
            pass
        trace = engine.finalize(ctx)
        lines = format_timeline(trace)
        assert any("Total" in l for l in lines)

    def test_format_timeline_shows_failure_icon(self):
        engine = ExecutionEngine()
        ctx = ExecutionContext(execution_id="t3", query="q")
        with pytest.raises(RuntimeError):
            with engine.step(ctx, "broken"):
                raise RuntimeError("fail")
        trace = engine.finalize(ctx)
        lines = format_timeline(trace)
        assert any("✗" in l for l in lines)


# ---------------------------------------------------------------------------
# QueryPlanner
# ---------------------------------------------------------------------------

class TestQueryPlanner:
    def test_returns_plan_dict(self):
        planner = QueryPlanner()
        plan = planner.plan("Summarize MCP updates")
        assert "original_query" in plan
        assert "search_query" in plan
        assert "strategy" in plan

    def test_expands_mcp_abbreviation(self):
        planner = QueryPlanner()
        plan = planner.plan("Latest MCP news")
        assert "Model Context Protocol" in plan["search_query"]

    def test_original_query_preserved(self):
        planner = QueryPlanner()
        query = "What is AI safety?"
        plan = planner.plan(query)
        assert plan["original_query"] == query


# ---------------------------------------------------------------------------
# Refactored BrowserAgent — uses real ExecutionEngine (no network)
# ---------------------------------------------------------------------------

def _make_agent_with_engine(summary="Summary.", search_results=None) -> BrowserAgent:
    mock_search = MagicMock()
    mock_search.search.return_value = (
        search_results
        if search_results is not None
        else [{"title": "Page", "url": "https://example.com", "snippet": "info"}]
    )
    mock_browser = MagicMock()
    mock_browser.fetch.return_value = "<html><body><p>content</p></body></html>"
    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = "Extracted content about MCP."
    mock_summarizer = MagicMock(spec=Summarizer)
    mock_summarizer.summarize.return_value = summary

    return BrowserAgent(
        search_tool=mock_search,
        browser_tool=mock_browser,
        extractor=mock_extractor,
        summarizer=mock_summarizer,
        engine=ExecutionEngine(),
        trace_path="/tmp/test_trace.json",
    )


class TestRefactoredBrowserAgent:
    def test_run_produces_six_step_trace(self):
        agent = _make_agent_with_engine()
        agent.run("MCP updates")
        assert agent.last_trace is not None
        step_names = [e.step for e in agent.last_trace.events]
        assert "planning" in step_names
        assert "search" in step_names
        assert "browser" in step_names
        assert "extraction" in step_names
        assert "reasoning" in step_names
        assert "response" in step_names

    def test_trace_is_saved_to_file(self):
        agent = _make_agent_with_engine()
        agent.run("test query")
        assert Path("/tmp/test_trace.json").exists()

    def test_trace_has_total_duration(self):
        agent = _make_agent_with_engine()
        agent.run("test query")
        assert agent.last_trace.total_duration_ms is not None
        assert agent.last_trace.total_duration_ms >= 0

    def test_trace_status_is_success(self):
        agent = _make_agent_with_engine()
        agent.run("test query")
        assert agent.last_trace.status == ExecutionStatus.SUCCESS

    def test_result_latency_equals_trace_total(self):
        agent = _make_agent_with_engine()
        result = agent.run("test query")
        assert result.latency_ms == agent.last_trace.total_duration_ms

    def test_trace_execution_id_is_unique(self):
        agent = _make_agent_with_engine()
        agent.run("first")
        id1 = agent.last_trace.execution_id
        agent.run("second")
        id2 = agent.last_trace.execution_id
        assert id1 != id2
