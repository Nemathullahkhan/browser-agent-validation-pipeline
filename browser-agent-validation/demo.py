from __future__ import annotations

import logging

import typer
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

logging.basicConfig(level=logging.WARNING)

app = typer.Typer(help="Browser Agent + AgentTrust Demo")
console = Console()

MENU = """
[bold cyan]1.[/bold cyan] Execute Browser Agent          [dim]python demo.py run "query"[/dim]
[bold cyan]2.[/bold cyan] Execute Browser Agent + AgentTrust  [dim]milestone 6[/dim]
[bold cyan]3.[/bold cyan] Compare Executions             [dim]milestone 8[/dim]
[bold cyan]4.[/bold cyan] View Execution Trace           [dim]python demo.py trace[/dim]
[bold cyan]5.[/bold cyan] View Workflow Diagram          [dim]python demo.py workflow[/dim]
[bold cyan]6.[/bold cyan] View Metrics Dashboard         [dim]milestone 9[/dim]
[bold cyan]7.[/bold cyan] Run Failure Scenarios          [dim]milestone 10[/dim]
[bold cyan]8.[/bold cyan] Exit
"""


@app.command()
def main() -> None:
    """Show the main menu."""
    console.print(
        Panel(
            Text("Browser Agent Demo Initialized", style="bold green", justify="center"),
            title="[bold white]Browser Agent + AgentTrust[/bold white]",
            subtitle="[dim]Governance Demo[/dim]",
            border_style="cyan",
            padding=(1, 4),
        )
    )
    console.print(Panel(MENU, title="[bold white]Main Menu[/bold white]", border_style="dim"))
    console.print("[dim]Run [bold]python demo.py run \"your query\"[/bold] to start.[/dim]")


@app.command()
def run(
    query: str = typer.Argument(..., help="Research query for the Browser Agent"),
    model: str = typer.Option("llama3.1", "--model", "-m", help="Ollama model to use"),
    max_results: int = typer.Option(5, "--max-results", "-n", help="Max search results"),
    show_detail: bool = typer.Option(False, "--detail", "-d", help="Show per-step I/O detail"),
) -> None:
    """Execute the Browser Agent on a query and display results."""
    from app.browser_agent.agent import create_browser_agent
    from app.execution.engine import ExecutionEngine
    from app.execution.graph import annotate_from_trace, browser_agent_graph
    from app.execution.mermaid import save_mermaid
    from app.execution.timeline import TimelineRenderer
    from app.ui.live_timeline import LiveTimeline

    console.print()
    console.print(
        Panel(
            f"[bold white]{query}[/bold white]",
            title="[bold cyan]Browser Agent[/bold cyan]",
            subtitle=f"[dim]model: {model}[/dim]",
            border_style="cyan",
        )
    )
    console.print()

    live_tl = LiveTimeline()
    engine = ExecutionEngine(
        on_step_start=live_tl.on_step_start,
        on_step_end=live_tl.on_step_end,
    )
    agent = create_browser_agent(model=model, max_results=max_results, engine=engine)

    with Live(live_tl.render(), console=console, refresh_per_second=8, transient=True) as live:
        live_tl.attach(live)
        result = agent.run(query)

    # -- Final timeline --
    renderer = TimelineRenderer()
    if agent.last_trace:
        console.print()
        console.print(renderer.render_panel(agent.last_trace))
        if show_detail:
            console.print()
            console.print(renderer.render_step_detail(agent.last_trace))

        # Auto-generate annotated workflow diagram
        graph = annotate_from_trace(browser_agent_graph(), agent.last_trace)
        mmd_path = save_mermaid(graph, "workflow.mmd")

    # -- Summary --
    console.print()
    console.print(
        Panel(
            Markdown(result.summary),
            title="[bold green]Summary[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
    )

    # -- Sources table --
    if result.sources:
        table = Table(title="Sources", border_style="dim", show_lines=False)
        table.add_column("#", style="dim", width=3)
        table.add_column("Title", style="white")
        table.add_column("URL", style="cyan")
        for i, (title, url) in enumerate(zip(result.sources, result.urls), 1):
            table.add_row(str(i), title[:60], url[:80])
        console.print(table)

    # -- Footer --
    meta = result.metadata
    console.print(
        f"\n[dim]Total: [bold]{result.latency_ms:,.0f} ms[/bold]  |  "
        f"Sources: [bold]{meta.get('urls_fetched', 0)}[/bold]  |  "
        f"Context: [bold]{meta.get('context_chars', 0):,} chars[/bold]  |  "
        f"Trace → [bold]trace.json[/bold]  |  Diagram → [bold]workflow.mmd[/bold][/dim]"
    )


@app.command()
def trace(
    path: str = typer.Option("trace.json", "--path", "-p", help="Path to trace.json"),
    detail: bool = typer.Option(False, "--detail", "-d", help="Show per-step I/O detail"),
) -> None:
    """Load and display a saved execution trace."""
    from pathlib import Path

    from app.execution.timeline import TimelineRenderer
    from app.execution.tracer import load_trace
    from app.models.base import ExecutionStatus

    p = Path(path)
    if not p.exists():
        console.print(f"[red]Trace file not found: {path}[/red]")
        raise typer.Exit(1)

    t = load_trace(p)
    renderer = TimelineRenderer()

    status_color = "green" if t.status == ExecutionStatus.SUCCESS else "red"
    total_str = f"{t.total_duration_ms:,.0f} ms" if t.total_duration_ms else "—"
    console.print()
    console.print(
        Panel(
            f"[bold]Query:[/bold]  {t.query}\n"
            f"[bold]ID:[/bold]     {t.execution_id}\n"
            f"[bold]Status:[/bold] [{status_color}]{t.status.value}[/{status_color}]  "
            f"[bold]Total:[/bold] {total_str}",
            title="[bold white]Execution Trace[/bold white]",
            border_style="blue",
        )
    )
    console.print()
    console.print(renderer.render_panel(t))
    if detail:
        console.print()
        console.print(renderer.render_step_detail(t))


@app.command()
def workflow(
    trace_path: str = typer.Option("", "--trace", "-t", help="Overlay a trace.json onto the diagram"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save workflow.mmd"),
    out: str = typer.Option("workflow.mmd", "--out", "-o", help="Output path for .mmd file"),
) -> None:
    """Show the Browser Agent workflow diagram and generate workflow.mmd."""
    from pathlib import Path

    from app.execution.graph import annotate_from_trace, browser_agent_graph
    from app.execution.mermaid import save_mermaid, to_mermaid
    from app.execution.tracer import load_trace
    from app.ui.graph_renderer import GraphRenderer

    graph = browser_agent_graph()

    # Overlay trace data if provided
    if trace_path:
        tp = Path(trace_path)
        if tp.exists():
            t = load_trace(tp)
            graph = annotate_from_trace(graph, t)
            console.print(f"\n[dim]Annotated from: {tp}[/dim]")
        else:
            console.print(f"[yellow]Trace not found: {trace_path} — showing plain diagram[/yellow]")

    renderer = GraphRenderer()
    console.print()
    console.print(renderer.render(graph))

    if save:
        p = save_mermaid(graph, out)
        console.print(f"\n[dim]Mermaid diagram saved → [bold]{p}[/bold][/dim]")
        console.print("[dim]Render at: https://mermaid.live or embed in any Markdown.[/dim]")


if __name__ == "__main__":
    app()
