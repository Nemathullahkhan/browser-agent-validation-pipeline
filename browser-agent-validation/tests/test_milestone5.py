from __future__ import annotations

import time

import pytest
from rich.panel import Panel

from app.execution.graph import (
    WorkflowEdge,
    WorkflowGraph,
    WorkflowNode,
    annotate_from_trace,
    browser_agent_graph,
)
from app.execution.mermaid import _safe_id, to_mermaid
from app.models.base import ExecutionEvent, ExecutionStatus, ExecutionTrace
from app.ui.graph_renderer import GraphRenderer, _topo_order


# ---------------------------------------------------------------------------
# WorkflowNode / WorkflowGraph model
# ---------------------------------------------------------------------------

class TestWorkflowNode:
    def test_defaults(self):
        node = WorkflowNode(id="a", label="Step A")
        assert node.node_type == "process"
        assert node.status is None
        assert node.duration_ms is None
        assert node.step_name is None

    def test_terminal_type(self):
        node = WorkflowNode(id="start", label="Start", node_type="terminal")
        assert node.node_type == "terminal"

    def test_status_field(self):
        node = WorkflowNode(id="s", label="S", status=ExecutionStatus.SUCCESS, duration_ms=42.0)
        assert node.status == ExecutionStatus.SUCCESS
        assert node.duration_ms == 42.0


class TestWorkflowGraph:
    def test_browser_agent_graph_has_seven_nodes(self):
        g = browser_agent_graph()
        assert len(g.nodes) == 7

    def test_browser_agent_graph_has_six_edges(self):
        g = browser_agent_graph()
        assert len(g.edges) == 6

    def test_first_and_last_are_terminals(self):
        g = browser_agent_graph()
        assert g.nodes[0].node_type == "terminal"
        assert g.nodes[-1].node_type == "terminal"

    def test_all_process_nodes_have_step_name(self):
        g = browser_agent_graph()
        for node in g.nodes:
            if node.node_type == "process":
                assert node.step_name is not None

    def test_edges_form_linear_chain(self):
        g = browser_agent_graph()
        from_ids = {e.from_id for e in g.edges}
        to_ids   = {e.to_id   for e in g.edges}
        # Every node except first appears as a destination
        non_sources = {n.id for n in g.nodes} - from_ids
        assert len(non_sources) == 1  # only the last node has no outgoing edge


class TestAnnotateFromTrace:
    def _trace_with_steps(self, steps: list[tuple[str, float]]) -> ExecutionTrace:
        events = [
            ExecutionEvent(
                step=name,
                status=ExecutionStatus.SUCCESS,
                start_time=time.time(),
                duration_ms=ms,
            )
            for name, ms in steps
        ]
        return ExecutionTrace(
            execution_id="t1", query="q",
            events=events, status=ExecutionStatus.SUCCESS,
            total_duration_ms=sum(ms for _, ms in steps),
        )

    def test_annotates_matching_nodes(self):
        g = browser_agent_graph()
        trace = self._trace_with_steps([("search", 3452.0), ("reasoning", 65000.0)])
        annotated = annotate_from_trace(g, trace)

        search_node = next(n for n in annotated.nodes if n.step_name == "search")
        assert search_node.status == ExecutionStatus.SUCCESS
        assert search_node.duration_ms == 3452.0

    def test_unannotated_nodes_unchanged(self):
        g = browser_agent_graph()
        trace = self._trace_with_steps([("search", 100.0)])
        annotated = annotate_from_trace(g, trace)

        planning_node = next(n for n in annotated.nodes if n.step_name == "planning")
        assert planning_node.status is None

    def test_terminal_nodes_always_unannotated(self):
        g = browser_agent_graph()
        trace = self._trace_with_steps([("planning", 1.0)])
        annotated = annotate_from_trace(g, trace)

        terminals = [n for n in annotated.nodes if n.node_type == "terminal"]
        assert all(n.status is None for n in terminals)

    def test_returns_new_graph_not_mutated(self):
        g = browser_agent_graph()
        original_statuses = [n.status for n in g.nodes]
        trace = self._trace_with_steps([("search", 100.0)])
        _ = annotate_from_trace(g, trace)
        assert [n.status for n in g.nodes] == original_statuses


# ---------------------------------------------------------------------------
# Graph renderer
# ---------------------------------------------------------------------------

class TestGraphRenderer:
    def test_render_returns_panel(self):
        renderer = GraphRenderer()
        panel = renderer.render(browser_agent_graph())
        assert isinstance(panel, Panel)

    def test_render_annotated_returns_panel(self):
        from app.execution.graph import annotate_from_trace
        g = browser_agent_graph()
        events = [ExecutionEvent(
            step="search", status=ExecutionStatus.SUCCESS,
            start_time=time.time(), duration_ms=3452.0,
        )]
        trace = ExecutionTrace(
            execution_id="x", query="q", events=events,
            status=ExecutionStatus.SUCCESS, total_duration_ms=3452.0,
        )
        annotated = annotate_from_trace(g, trace)
        renderer = GraphRenderer()
        panel = renderer.render(annotated)
        assert isinstance(panel, Panel)

    def test_topo_order_follows_edges(self):
        g = browser_agent_graph()
        ordered = _topo_order(g)
        ids = [n.id for n in ordered]
        assert ids[0] == "user"
        assert ids[-1] == "summary"
        # planning must come before search
        assert ids.index("planning") < ids.index("search")
        assert ids.index("search") < ids.index("browser")

    def test_topo_order_includes_all_nodes(self):
        g = browser_agent_graph()
        ordered = _topo_order(g)
        assert len(ordered) == len(g.nodes)

    def test_custom_graph_renders(self):
        g = WorkflowGraph(
            title="Test",
            nodes=[
                WorkflowNode(id="a", label="A", node_type="terminal"),
                WorkflowNode(id="b", label="B"),
                WorkflowNode(id="c", label="C", node_type="terminal"),
            ],
            edges=[
                WorkflowEdge(from_id="a", to_id="b"),
                WorkflowEdge(from_id="b", to_id="c"),
            ],
        )
        renderer = GraphRenderer()
        panel = renderer.render(g)
        assert isinstance(panel, Panel)


# ---------------------------------------------------------------------------
# Mermaid generator
# ---------------------------------------------------------------------------

class TestMermaidGenerator:
    def test_output_starts_with_flowchart(self):
        g = browser_agent_graph()
        mmd = to_mermaid(g)
        assert mmd.startswith("flowchart TD")

    def test_all_node_ids_present(self):
        g = browser_agent_graph()
        mmd = to_mermaid(g)
        for node in g.nodes:
            assert _safe_id(node.id) in mmd

    def test_edges_present(self):
        g = browser_agent_graph()
        mmd = to_mermaid(g)
        assert "-->" in mmd

    def test_terminal_nodes_use_rounded_shape(self):
        g = browser_agent_graph()
        mmd = to_mermaid(g)
        # Terminals use ([...]) syntax in Mermaid
        assert "([" in mmd

    def test_style_declarations_present(self):
        g = browser_agent_graph()
        mmd = to_mermaid(g)
        assert "style" in mmd

    def test_annotated_graph_includes_duration_comments(self):
        g = browser_agent_graph()
        events = [ExecutionEvent(
            step="search", status=ExecutionStatus.SUCCESS,
            start_time=time.time(), duration_ms=3452.0,
        )]
        trace = ExecutionTrace(
            execution_id="x", query="q", events=events,
            status=ExecutionStatus.SUCCESS, total_duration_ms=3452.0,
        )
        annotated = annotate_from_trace(g, trace)
        mmd = to_mermaid(annotated)
        assert "3,452" in mmd or "3452" in mmd

    def test_annotated_node_uses_status_fill(self):
        g = browser_agent_graph()
        events = [ExecutionEvent(
            step="search", status=ExecutionStatus.SUCCESS,
            start_time=time.time(), duration_ms=100.0,
        )]
        trace = ExecutionTrace(
            execution_id="x", query="q", events=events,
            status=ExecutionStatus.SUCCESS, total_duration_ms=100.0,
        )
        annotated = annotate_from_trace(g, trace)
        mmd = to_mermaid(annotated)
        assert "#22c55e" in mmd  # green-500 for SUCCESS

    def test_save_mermaid_writes_file(self, tmp_path):
        from app.execution.mermaid import save_mermaid
        g = browser_agent_graph()
        p = save_mermaid(g, tmp_path / "test.mmd")
        assert p.exists()
        content = p.read_text()
        assert "flowchart TD" in content

    def test_safe_id_replaces_hyphens(self):
        assert _safe_id("my-node") == "my_node"

    def test_safe_id_replaces_spaces(self):
        assert _safe_id("my node") == "my_node"
