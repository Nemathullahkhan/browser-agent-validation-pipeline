from __future__ import annotations

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from app.models.base import ExecutionEvent, ExecutionStatus, ExecutionTrace

# Canonical step order for the Browser Agent pipeline
AGENT_STEPS = ["planning", "search", "browser", "extraction", "reasoning", "response"]

_BAR_WIDTH = 20
_BAR_CHAR = "█"
_BAR_EMPTY = " "

_STATUS_ICON: dict[ExecutionStatus, str] = {
    ExecutionStatus.SUCCESS: "✓",
    ExecutionStatus.FAILED:  "✗",
    ExecutionStatus.RUNNING: "⟳",
    ExecutionStatus.PENDING: "○",
    ExecutionStatus.BLOCKED: "⊘",
}

_STATUS_STYLE: dict[ExecutionStatus, str] = {
    ExecutionStatus.SUCCESS: "bold green",
    ExecutionStatus.FAILED:  "bold red",
    ExecutionStatus.RUNNING: "bold yellow",
    ExecutionStatus.PENDING: "dim",
    ExecutionStatus.BLOCKED: "dim red",
}

_BAR_STYLE: dict[ExecutionStatus, str] = {
    ExecutionStatus.SUCCESS: "green",
    ExecutionStatus.FAILED:  "red",
    ExecutionStatus.RUNNING: "yellow",
    ExecutionStatus.PENDING: "dim",
    ExecutionStatus.BLOCKED: "dim",
}


def _make_bar(fraction: float, status: ExecutionStatus) -> Text:
    filled = max(1, round(fraction * _BAR_WIDTH)) if fraction > 0 else 0
    empty  = _BAR_WIDTH - filled
    bar = Text()
    bar.append(_BAR_CHAR * filled, style=_BAR_STYLE.get(status, ""))
    bar.append(_BAR_EMPTY * empty, style="")
    return bar


class TimelineRenderer:
    """Renders a completed or partial ExecutionTrace as a Rich panel."""

    def render_table(
        self,
        events: list[ExecutionEvent],
        step_order: list[str] | None = None,
        *,
        show_io: bool = False,
    ) -> Table:
        order = step_order or AGENT_STEPS
        by_name = {e.step: e for e in events}
        max_ms = max((e.duration_ms or 0.0 for e in events), default=1.0) or 1.0

        table = Table(box=None, show_header=False, padding=(0, 1))
        table.add_column("icon",     width=2,          no_wrap=True)
        table.add_column("step",     width=12,         no_wrap=True)
        table.add_column("bar",      width=_BAR_WIDTH,  no_wrap=True)
        table.add_column("duration", width=9,  justify="right", no_wrap=True)
        table.add_column("pct",      width=4,  justify="right", no_wrap=True)

        total_ms = sum(e.duration_ms or 0.0 for e in events)

        for name in order:
            event = by_name.get(name)
            if event is None:
                icon_txt  = Text(_STATUS_ICON[ExecutionStatus.PENDING], style="dim")
                step_txt  = Text(name.replace("_", " ").title(), style="dim")
                bar_txt   = Text(_BAR_EMPTY * _BAR_WIDTH, style="dim")
                dur_txt   = Text("—", style="dim", justify="right")
                pct_txt   = Text("", style="dim")
            else:
                status    = event.status
                style     = _STATUS_STYLE.get(status, "")
                dur_ms    = event.duration_ms or 0.0
                fraction  = dur_ms / max_ms
                pct       = (dur_ms / total_ms * 100) if total_ms > 0 else 0

                icon_txt  = Text(_STATUS_ICON.get(status, "?"), style=style)
                step_txt  = Text(name.replace("_", " ").title(), style="white")
                bar_txt   = _make_bar(fraction, status)
                dur_txt   = Text(f"{dur_ms:,.0f} ms", style=style, justify="right")
                pct_txt   = Text(f"{pct:.0f}%", style="dim", justify="right")

            table.add_row(icon_txt, step_txt, bar_txt, dur_txt, pct_txt)

        # Total row
        if events:
            table.add_row(Text(""), Text(""), Text(""), Text(""), Text(""))
            total_txt = Text(f"{total_ms:,.0f} ms", style="bold white", justify="right")
            table.add_row(Text(""), Text("Total", style="bold dim"), Text(""), total_txt, Text(""))

        return table

    def render_panel(
        self,
        trace: ExecutionTrace,
        title: str = "Execution Timeline",
        *,
        show_io: bool = False,
    ) -> Panel:
        table = self.render_table(trace.events, show_io=show_io)
        status = trace.status
        border = "green" if status == ExecutionStatus.SUCCESS else ("red" if status == ExecutionStatus.FAILED else "blue")
        return Panel(table, title=f"[bold white]{title}[/bold white]", border_style=border, padding=(0, 2))

    def render_step_detail(self, trace: ExecutionTrace) -> Table:
        """Detailed table: step, status, duration, inputs, outputs."""
        table = Table(border_style="dim", show_lines=True)
        table.add_column("Step",     style="cyan",  no_wrap=True)
        table.add_column("Status",   width=8)
        table.add_column("Duration", justify="right", width=9)
        table.add_column("Inputs",   style="dim")
        table.add_column("Outputs",  style="dim")

        for event in trace.events:
            icon  = _STATUS_ICON.get(event.status, "?")
            style = _STATUS_STYLE.get(event.status, "")
            dur   = f"{event.duration_ms:,.0f} ms" if event.duration_ms else "—"
            inputs  = _format_dict(event.inputs)
            outputs = _format_dict(event.outputs)
            err_sfx = f"\n[red]{event.error}[/red]" if event.error else ""
            table.add_row(
                event.step,
                Text(icon, style=style),
                dur,
                inputs + err_sfx,
                outputs,
            )
        return table


def _format_dict(d: dict) -> str:
    if not d:
        return "—"
    parts = []
    for k, v in d.items():
        vs = str(v)
        if len(vs) > 40:
            vs = vs[:40] + "…"
        parts.append(f"{k}: {vs}")
    return "\n".join(parts)
