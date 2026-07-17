from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models.base import ExecutionStatus, ExecutionTrace

NodeType = Literal["terminal", "process"]


class WorkflowNode(BaseModel):
    id: str
    label: str
    description: str = ""
    step_name: str | None = None  # maps to ExecutionTrace step
    node_type: NodeType = "process"
    # Populated by annotate_from_trace():
    status: ExecutionStatus | None = None
    duration_ms: float | None = None
    inputs: dict = Field(default_factory=dict)
    outputs: dict = Field(default_factory=dict)


class WorkflowEdge(BaseModel):
    from_id: str
    to_id: str
    label: str = ""


class WorkflowGraph(BaseModel):
    title: str
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]


# ---------------------------------------------------------------------------
# Browser Agent canonical graph
# ---------------------------------------------------------------------------

def browser_agent_graph() -> WorkflowGraph:
    nodes = [
        WorkflowNode(
            id="user", label="User Query",
            description="Natural language research question",
            node_type="terminal",
        ),
        WorkflowNode(
            id="planning", label="Planning",
            description="Expand query into search terms",
            step_name="planning",
        ),
        WorkflowNode(
            id="search", label="Search",
            description="DuckDuckGo — top URLs",
            step_name="search",
        ),
        WorkflowNode(
            id="browser", label="Browser",
            description="HTTP fetch each URL",
            step_name="browser",
        ),
        WorkflowNode(
            id="extraction", label="Extraction",
            description="Trafilatura — readable text",
            step_name="extraction",
        ),
        WorkflowNode(
            id="reasoning", label="Reasoning",
            description="Ollama LLM summarization",
            step_name="reasoning",
        ),
        WorkflowNode(
            id="summary", label="Summary",
            description="Structured BrowserResult",
            node_type="terminal",
        ),
    ]
    edges = [
        WorkflowEdge(from_id="user",       to_id="planning"),
        WorkflowEdge(from_id="planning",   to_id="search"),
        WorkflowEdge(from_id="search",     to_id="browser"),
        WorkflowEdge(from_id="browser",    to_id="extraction"),
        WorkflowEdge(from_id="extraction", to_id="reasoning"),
        WorkflowEdge(from_id="reasoning",  to_id="summary"),
    ]
    return WorkflowGraph(title="Browser Agent Workflow", nodes=nodes, edges=edges)


def annotate_from_trace(graph: WorkflowGraph, trace: ExecutionTrace) -> WorkflowGraph:
    """Return a new graph with status/duration/IO overlaid from a completed trace."""
    by_step = {e.step: e for e in trace.events}
    updated: list[WorkflowNode] = []
    for node in graph.nodes:
        if node.step_name and node.step_name in by_step:
            event = by_step[node.step_name]
            updated.append(node.model_copy(update={
                "status":      event.status,
                "duration_ms": event.duration_ms,
                "inputs":      event.inputs,
                "outputs":     event.outputs,
            }))
        else:
            updated.append(node)
    return graph.model_copy(update={"nodes": updated})
