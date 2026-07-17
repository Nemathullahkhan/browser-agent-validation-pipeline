from __future__ import annotations

from pathlib import Path

from app.execution.graph import WorkflowGraph, WorkflowNode
from app.models.base import ExecutionStatus

# Mermaid fill colours per status
_STATUS_FILL: dict[ExecutionStatus, str] = {
    ExecutionStatus.SUCCESS: "#22c55e",   # green-500
    ExecutionStatus.FAILED:  "#ef4444",   # red-500
    ExecutionStatus.RUNNING: "#f59e0b",   # amber-500
    ExecutionStatus.PENDING: "#94a3b8",   # slate-400
    ExecutionStatus.BLOCKED: "#6b7280",   # gray-500
}
_TERMINAL_FILL = "#3b82f6"   # blue-500
_TEXT_COLOUR   = "#ffffff"


def to_mermaid(graph: WorkflowGraph) -> str:
    """Generate Mermaid flowchart TD syntax from a WorkflowGraph."""
    lines: list[str] = [
        "flowchart TD",
        f"    %% {graph.title}",
        "",
    ]

    # Node declarations
    for node in graph.nodes:
        nid   = _safe_id(node.id)
        label = _node_label(node)
        if node.node_type == "terminal":
            lines.append(f'    {nid}(["{label}"])')
        else:
            lines.append(f'    {nid}["{label}"]')

    lines.append("")

    # Edges
    for edge in graph.edges:
        src = _safe_id(edge.from_id)
        dst = _safe_id(edge.to_id)
        if edge.label:
            lines.append(f"    {src} -->|{edge.label}| {dst}")
        else:
            lines.append(f"    {src} --> {dst}")

    lines.append("")

    # Style declarations
    for node in graph.nodes:
        nid = _safe_id(node.id)
        if node.node_type == "terminal":
            fill = _TERMINAL_FILL
        elif node.status:
            fill = _STATUS_FILL.get(node.status, "#94a3b8")
        else:
            fill = "#475569"   # slate-600 (unannotated process node)

        lines.append(
            f"    style {nid} fill:{fill},color:{_TEXT_COLOUR},stroke:{fill}"
        )

    # Duration comments
    lines.append("")
    for node in graph.nodes:
        if node.status and node.duration_ms is not None:
            icon = "✓" if node.status == ExecutionStatus.SUCCESS else "✗"
            lines.append(f"    %% {node.label}: {icon} {node.duration_ms:,.0f} ms")

    return "\n".join(lines) + "\n"


def save_mermaid(graph: WorkflowGraph, path: str | Path = "workflow.mmd") -> Path:
    p = Path(path)
    p.write_text(to_mermaid(graph), encoding="utf-8")
    return p


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_id(node_id: str) -> str:
    return node_id.replace("-", "_").replace(" ", "_")


def _node_label(node: WorkflowNode) -> str:
    if node.status and node.duration_ms is not None:
        icon = "✓" if node.status == ExecutionStatus.SUCCESS else "✗"
        return f"{node.label}\\n{icon} {node.duration_ms:,.0f} ms"
    return node.label
