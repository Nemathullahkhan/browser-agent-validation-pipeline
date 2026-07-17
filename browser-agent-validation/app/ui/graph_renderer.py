from __future__ import annotations

from rich.panel import Panel
from rich.text import Text

from app.execution.graph import WorkflowGraph, WorkflowNode
from app.models.base import ExecutionStatus

# ── Layout constants ──────────────────────────────────────────────────────────
_BOX_W   = 26          # interior width of each node box
_INDENT  = "   "       # left margin
_CENTER  = " " * 12    # connector column offset from left margin

_STATUS_STYLE: dict[ExecutionStatus, str] = {
    ExecutionStatus.SUCCESS: "bold green",
    ExecutionStatus.FAILED:  "bold red",
    ExecutionStatus.RUNNING: "bold yellow",
    ExecutionStatus.PENDING: "dim",
    ExecutionStatus.BLOCKED: "dim red",
}
_STATUS_ICON = {
    ExecutionStatus.SUCCESS: "✓",
    ExecutionStatus.FAILED:  "✗",
    ExecutionStatus.RUNNING: "⟳",
    ExecutionStatus.PENDING: "○",
    ExecutionStatus.BLOCKED: "⊘",
}


class GraphRenderer:
    """Renders a WorkflowGraph as a vertical ASCII flowchart inside a Rich Panel."""

    def render(self, graph: WorkflowGraph) -> Panel:
        t = Text()
        t.append("\n")

        nodes_by_id = {n.id: n for n in graph.nodes}

        # Build ordered list following edge chain from first node
        ordered = _topo_order(graph)

        for i, node in enumerate(ordered):
            _append_node(t, node)

            # Arrow between nodes (skip after last)
            if i < len(ordered) - 1:
                t.append(f"{_INDENT}{_CENTER}│\n", style="dim")
                t.append(f"{_INDENT}{_CENTER}▼\n", style="dim")

        t.append("\n")
        return Panel(
            t,
            title=f"[bold white]{graph.title}[/bold white]",
            border_style="cyan",
            padding=(0, 2),
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _topo_order(graph: WorkflowGraph) -> list[WorkflowNode]:
    """Return nodes in edge-chain order starting from the node with no incoming edges."""
    has_incoming = {e.to_id for e in graph.edges}
    roots = [n for n in graph.nodes if n.id not in has_incoming]
    if not roots:
        return graph.nodes  # fallback

    by_id = {n.id: n for n in graph.nodes}
    next_map: dict[str, str] = {e.from_id: e.to_id for e in graph.edges}

    ordered: list[WorkflowNode] = []
    current_id: str | None = roots[0].id
    seen: set[str] = set()
    while current_id and current_id not in seen:
        seen.add(current_id)
        ordered.append(by_id[current_id])
        current_id = next_map.get(current_id)

    return ordered


def _append_node(t: Text, node: WorkflowNode) -> None:
    status   = node.status
    style    = _STATUS_STYLE.get(status, "white") if status else "white"
    terminal = node.node_type == "terminal"

    top_h    = "═" if terminal else "─"
    side_v   = "║" if terminal else "│"
    tl       = "╔" if terminal else "┌"
    tr       = "╗" if terminal else "┐"
    bl       = "╚" if terminal else "└"
    br       = "╝" if terminal else "┘"

    label    = node.label
    pad      = _BOX_W - len(label) - 2  # 2 spaces padding inside

    # -- Top border --
    t.append(f"{_INDENT}{tl}{top_h * _BOX_W}{tr}\n", style="cyan" if terminal else "white")

    # -- Content line --
    t.append(f"{_INDENT}{side_v} ", style="cyan" if terminal else "white")
    t.append(f"{label}", style=style if status else ("bold cyan" if terminal else "white"))
    t.append(" " * (pad + 1))
    t.append(f"{side_v}", style="cyan" if terminal else "white")

    # -- Inline annotation --
    if status:
        icon = _STATUS_ICON.get(status, "")
        dur  = f"  {icon}  {node.duration_ms:,.0f} ms" if node.duration_ms is not None else f"  {icon}"
        t.append(dur, style=style)
    elif node.description and not terminal:
        desc = node.description[:35] + "…" if len(node.description) > 35 else node.description
        t.append(f"  {desc}", style="dim")

    t.append("\n")

    # -- Bottom border --
    t.append(f"{_INDENT}{bl}{top_h * _BOX_W}{br}\n", style="cyan" if terminal else "white")
