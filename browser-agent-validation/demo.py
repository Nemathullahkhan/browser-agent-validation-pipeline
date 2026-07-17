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
[bold cyan]2.[/bold cyan] Execute Browser Agent + AgentTrust  [dim]python demo.py run-governed "query"[/dim]
[bold cyan]3.[/bold cyan] Compare Executions             [dim]python demo.py compare "query"[/dim]
[bold cyan]4.[/bold cyan] View Execution Trace           [dim]python demo.py trace[/dim]
[bold cyan]5.[/bold cyan] View Workflow Diagram          [dim]python demo.py workflow[/dim]
[bold cyan]6.[/bold cyan] View Metrics Dashboard         [dim]python demo.py metrics[/dim]
[bold cyan]7.[/bold cyan] Run Failure Scenarios          [dim]python demo.py scenarios[/dim]
[bold cyan]8.[/bold cyan] View Audit Log                 [dim]python demo.py audit[/dim]
[bold cyan]9.[/bold cyan] View Policy Config             [dim]python demo.py policy[/dim]
[bold cyan]10.[/bold cyan] Human Review Queue             [dim]python demo.py review[/dim]
[bold cyan]11.[/bold cyan] Generate Session Report        [dim]python demo.py report[/dim]
[bold cyan]12.[/bold cyan] Governance Dashboard           [dim]python demo.py dashboard[/dim]
[bold cyan]13.[/bold cyan] Export Governance Data         [dim]python demo.py export[/dim]
[bold cyan]14.[/bold cyan] Trend Analysis                 [dim]python demo.py trends[/dim]
[bold cyan]15.[/bold cyan] Governance Health Check        [dim]python demo.py health[/dim]
[bold cyan]16.[/bold cyan] Exit
"""


@app.command()
def main() -> None:
    """Interactive main menu — select an option or press Ctrl+C to exit."""
    from rich.prompt import IntPrompt, Prompt

    console.print(
        Panel(
            Text("Browser Agent + AgentTrust", style="bold green", justify="center"),
            title="[bold white]AgentTrust Governance Demo[/bold white]",
            subtitle="[dim]Interactive Menu[/dim]",
            border_style="cyan",
            padding=(1, 4),
        )
    )

    while True:
        console.print(Panel(MENU, title="[bold white]Main Menu[/bold white]", border_style="dim"))
        try:
            choice = IntPrompt.ask("[bold cyan]Select[/bold cyan]", default=9)
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if choice == 16:
            console.print("[dim]Goodbye.[/dim]")
            break

        try:
            if choice == 1:
                q = Prompt.ask("[cyan]Enter query[/cyan]")
                if q.strip():
                    run(query=q, model="llama3.1", max_results=5, show_detail=False)
            elif choice == 2:
                q = Prompt.ask("[cyan]Enter query[/cyan]")
                if q.strip():
                    run_governed(query=q, model="llama3.1", max_results=5, show_detail=False)
            elif choice == 3:
                q = Prompt.ask("[cyan]Enter query[/cyan]")
                if q.strip():
                    compare(query=q, model="llama3.1", max_results=5, save=True)
            elif choice == 4:
                trace(path="trace.json", detail=False)
            elif choice == 5:
                workflow(trace_path="", save=True, out="workflow.mmd")
            elif choice == 6:
                metrics(path="metrics.json")
            elif choice == 7:
                scenarios(scenario_num=0)
            elif choice == 8:
                audit(path="audit.jsonl", clear_log=False, limit=50)
            elif choice == 9:
                policy(path="", validate=False)
            elif choice == 10:
                review(path="review_queue.jsonl", approve_id="", reject_id="", note="", clear_queue=False)
            elif choice == 11:
                report(
                    audit="audit.jsonl", metrics_file="metrics.json",
                    comparison_file="comparison.json", review_file="review_queue.jsonl",
                    out="report.md", title="AgentTrust Session Report",
                )
            elif choice == 12:
                dashboard(
                    audit="audit.jsonl", metrics_file="metrics.json",
                    comparison_file="comparison.json", review_file="review_queue.jsonl",
                )
            elif choice == 13:
                export(
                    audit="audit.jsonl", metrics_file="metrics.json",
                    comparison_file="comparison.json", review_file="review_queue.jsonl",
                    out_dir="exports", fmt="json",
                )
            elif choice == 14:
                trends(audit="audit.jsonl")
            elif choice == 15:
                health(
                    audit="audit.jsonl", metrics_file="metrics.json",
                    review_file="review_queue.jsonl", policy_file="",
                )
            else:
                console.print("[yellow]Please enter 1-16.[/yellow]")
        except typer.Exit:
            pass
        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted.[/dim]")


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

    # -- Metrics --
    if agent.last_trace:
        from app.metrics.engine import LocalMetricsEngine, save_metrics
        _m = LocalMetricsEngine()
        _m.record_trace(agent.last_trace, mode="raw")
        save_metrics(_m)

    # -- Footer --
    meta = result.metadata
    console.print(
        f"\n[dim]Total: [bold]{result.latency_ms:,.0f} ms[/bold]  |  "
        f"Sources: [bold]{meta.get('urls_fetched', 0)}[/bold]  |  "
        f"Context: [bold]{meta.get('context_chars', 0):,} chars[/bold]  |  "
        f"Trace → [bold]trace.json[/bold]  |  Diagram → [bold]workflow.mmd[/bold]  |  "
        f"Metrics → [bold]metrics.json[/bold][/dim]"
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


@app.command(name="run-governed")
def run_governed(
    query: str = typer.Argument(..., help="Research query for the Governed Browser Agent"),
    model: str = typer.Option("llama3.1", "--model", "-m", help="Ollama model to use"),
    max_results: int = typer.Option(5, "--max-results", "-n", help="Max search results"),
    show_detail: bool = typer.Option(False, "--detail", "-d", help="Show per-step I/O detail"),
) -> None:
    """Execute the Browser Agent with AgentTrust governance middleware."""
    from app.agenttrust.exceptions import BlockedError, EscalationError
    from app.agenttrust.governed_agent import GovernedBrowserAgent
    from app.browser_agent.agent import create_browser_agent
    from app.execution.engine import ExecutionEngine
    from app.execution.graph import annotate_from_trace, browser_agent_graph
    from app.execution.mermaid import save_mermaid
    from app.execution.timeline import TimelineRenderer
    from app.models.base import RiskLevel, TrustDecision
    from app.ui.live_timeline import LiveTimeline

    _RISK_COLOR = {
        RiskLevel.LOW: "green",
        RiskLevel.MEDIUM: "yellow",
        RiskLevel.HIGH: "red",
        RiskLevel.CRITICAL: "bold red",
    }
    _DECISION_COLOR = {
        TrustDecision.ALLOW: "green",
        TrustDecision.BLOCK: "red",
        TrustDecision.RETRY: "yellow",
        TrustDecision.HUMAN_REVIEW: "yellow",
    }

    console.print()
    console.print(
        Panel(
            f"[bold white]{query}[/bold white]",
            title="[bold cyan]Browser Agent + AgentTrust[/bold cyan]",
            subtitle=f"[dim]model: {model}  |  governance: enabled[/dim]",
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
    governed = GovernedBrowserAgent(agent)

    result = None
    try:
        with Live(live_tl.render(), console=console, refresh_per_second=8, transient=True) as live:
            live_tl.attach(live)
            result = governed.run(query)

    except BlockedError as exc:
        vr = exc.validation
        stage = vr.metadata.get("stage", "output")
        stage_label = "Stage 1 — Input Validation" if stage == "input" else "Stage 2 — Output Validation"
        console.print()
        console.print(
            Panel(
                f"[bold red]BLOCKED[/bold red]  {exc.reason}\n\n"
                f"[dim]{stage_label}[/dim]\n"
                f"[dim]Confidence:[/dim] [red]{vr.confidence:.0f}/100[/red]   "
                f"[dim]Policy score:[/dim] [red]{vr.policy_score:.0f}/100[/red]   "
                f"[dim]Risk:[/dim] [red]{vr.risk_level.value}[/red]\n"
                + (f"\n[dim]Violations:[/dim]\n" + "\n".join(f"  • {v}" for v in vr.violations) if vr.violations else ""),
                title="[bold red]AgentTrust — Blocked[/bold red]",
                border_style="red",
            )
        )
        import uuid as _uuid
        from app.audit.store import LocalAuditStore as _LAS, make_audit_event as _mae
        _eid = agent.last_trace.execution_id if agent.last_trace else _uuid.uuid4().hex
        _LAS().append(_mae(_eid, exc.validation, 0.0))
        raise typer.Exit(1)

    except EscalationError as exc:
        vr = exc.validation
        import uuid as _uuid
        from app.audit.store import LocalAuditStore as _LAS, make_audit_event as _mae
        from app.review.queue import ReviewQueue as _RQ
        _eid = agent.last_trace.execution_id if agent.last_trace else _uuid.uuid4().hex
        _LAS().append(_mae(_eid, exc.validation, 0.0))
        _item = _RQ().enqueue(query, exc.validation)
        console.print()
        console.print(
            Panel(
                f"[bold yellow]ESCALATED[/bold yellow]  {exc.reason}\n\n"
                f"[dim]Confidence:[/dim] {vr.confidence:.0f}/100   "
                f"[dim]Policy score:[/dim] {vr.policy_score:.0f}/100\n\n"
                f"[dim]Queued for review → [bold]review_queue.jsonl[/bold]  "
                f"ID: [bold]{_item.item_id[:8]}…[/bold][/dim]\n"
                f"[dim]Run [bold]python demo.py review[/bold] to inspect or resolve.[/dim]",
                title="[bold yellow]AgentTrust — Human Review Required[/bold yellow]",
                border_style="yellow",
            )
        )
        raise typer.Exit(1)

    # -- Final timeline --
    renderer = TimelineRenderer()
    if agent.last_trace:
        console.print()
        console.print(renderer.render_panel(agent.last_trace))
        if show_detail:
            console.print()
            console.print(renderer.render_step_detail(agent.last_trace))

        graph = annotate_from_trace(browser_agent_graph(), agent.last_trace)
        save_mermaid(graph, "workflow.mmd")

    # -- AgentTrust governance report (two-stage) --
    def _vr_row(label: str, vr: "ValidationResult") -> str:  # type: ignore[name-defined]
        dc = _DECISION_COLOR.get(vr.decision, "white")
        rc = _RISK_COLOR.get(vr.risk_level, "white")
        checks = vr.metadata.get("checks_passed")
        checks_run = vr.metadata.get("checks_run")
        checks_str = f"  [dim]checks:[/dim] {checks}/{checks_run}" if checks is not None else ""
        return (
            f"[dim]{label}[/dim]\n"
            f"  [{dc}]{vr.decision.value}[/{dc}]"
            f"  [dim]confidence[/dim] [{dc}]{vr.confidence:.0f}/100[/{dc}]"
            f"  [dim]policy[/dim] [{dc}]{vr.policy_score:.0f}/100[/{dc}]"
            f"  [dim]risk[/dim] [{rc}]{vr.risk_level.value}[/{rc}]"
            + checks_str
            + (
                "\n  [dim]violations:[/dim] " + "  ".join(f"[red]{v}[/red]" for v in vr.violations)
                if vr.violations else ""
            )
        )

    input_row = _vr_row("Stage 1 — Input Validation", governed.last_input_validation) if governed.last_input_validation else ""
    output_row = _vr_row("Stage 2 — Output Validation", governed.last_validation) if governed.last_validation else ""

    if input_row or output_row:
        console.print()
        console.print(
            Panel(
                "\n\n".join(filter(None, [input_row, output_row])),
                title="[bold cyan]AgentTrust Governance Report[/bold cyan]",
                border_style="cyan",
            )
        )

    # -- Retry report --
    rr = governed.last_retry_result
    if rr and rr.retried:
        body = f"[yellow]{rr.total_attempts - 1} retry attempt(s)[/yellow] → final: "
        dc = "green" if rr.final_decision == "ALLOW" else "red"
        body += f"[{dc}]{rr.final_decision}[/{dc}]\n\n"
        for a in rr.attempts:
            adc = "green" if a.decision == "ALLOW" else "red"
            delay_str = f"  → waited [dim]{a.delay_ms_after:.0f} ms[/dim]" if a.delay_ms_after > 0 else ""
            body += (
                f"  Attempt {a.attempt}: [{adc}]{a.decision}[/{adc}]"
                f"  [dim]conf:[/dim] {a.confidence:.0f}  [dim]score:[/dim] {a.policy_score:.0f}"
                f"  [dim]risk:[/dim] {a.risk_level}{delay_str}\n"
            )
        console.print()
        console.print(Panel(body.rstrip(), title="[bold yellow]Retry Log[/bold yellow]", border_style="yellow"))

    if result is None:
        raise typer.Exit(1)

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

    # -- Metrics --
    if agent.last_trace:
        from app.metrics.engine import LocalMetricsEngine, save_metrics
        _m = LocalMetricsEngine()
        _m.record_trace(agent.last_trace, mode="governed")
        if governed.last_input_validation:
            _m.record_validation(governed.last_input_validation, prefix="governance.input")
        if governed.last_validation:
            _m.record_validation(governed.last_validation, prefix="governance.output")
        save_metrics(_m)

    # -- Audit --
    _vr_audit = governed.last_validation or governed.last_input_validation
    if _vr_audit:
        import uuid as _uuid
        from app.audit.store import LocalAuditStore as _LAS, make_audit_event as _mae
        _eid = agent.last_trace.execution_id if agent.last_trace else _uuid.uuid4().hex
        _LAS().append(_mae(_eid, _vr_audit, result.latency_ms))

    meta = result.metadata
    console.print(
        f"\n[dim]Total: [bold]{result.latency_ms:,.0f} ms[/bold]  |  "
        f"Sources: [bold]{meta.get('urls_fetched', 0)}[/bold]  |  "
        f"Governance: [bold green]ENABLED[/bold green]  |  "
        f"Trace → [bold]trace.json[/bold]  |  Diagram → [bold]workflow.mmd[/bold]  |  "
        f"Metrics → [bold]metrics.json[/bold]  |  "
        f"Audit → [bold]audit.jsonl[/bold][/dim]"
    )


@app.command()
def compare(
    query: str = typer.Argument(..., help="Research query to run through both modes"),
    model: str = typer.Option("llama3.1", "--model", "-m", help="Ollama model to use"),
    max_results: int = typer.Option(5, "--max-results", "-n", help="Max search results"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save comparison.json"),
) -> None:
    """Run the same query without and with AgentTrust — display side-by-side."""
    from app.agenttrust.exceptions import BlockedError, EscalationError
    from app.agenttrust.governed_agent import GovernedBrowserAgent
    from app.browser_agent.agent import create_browser_agent
    from app.comparison.engine import ComparisonEngine, save_comparison
    from app.execution.engine import ExecutionEngine
    from app.execution.tracer import format_timeline
    from app.models.base import ExecutionStatus, RiskLevel, TrustDecision
    from app.ui.live_timeline import LiveTimeline
    from rich.columns import Columns
    from rich.live import Live

    _RISK_COLOR = {
        RiskLevel.LOW: "green",
        RiskLevel.MEDIUM: "yellow",
        RiskLevel.HIGH: "red",
        RiskLevel.CRITICAL: "bold red",
    }
    _DECISION_COLOR = {
        TrustDecision.ALLOW: "green",
        TrustDecision.BLOCK: "red",
        TrustDecision.RETRY: "yellow",
        TrustDecision.HUMAN_REVIEW: "yellow",
    }

    console.print()
    console.print(
        Panel(
            f"[bold white]{query}[/bold white]",
            title="[bold cyan]Side-by-Side Comparison[/bold cyan]",
            subtitle=f"[dim]model: {model}  |  running both modes[/dim]",
            border_style="cyan",
        )
    )
    console.print()

    # ── Run 1: Raw agent ──────────────────────────────────────────────────────
    console.print("[bold dim]Step 1/2 — Without AgentTrust[/bold dim]")
    live_tl_raw = LiveTimeline()
    engine_raw = ExecutionEngine(
        on_step_start=live_tl_raw.on_step_start,
        on_step_end=live_tl_raw.on_step_end,
    )
    raw_agent = create_browser_agent(
        model=model, max_results=max_results, engine=engine_raw, trace_path="trace_raw.json"
    )

    with Live(live_tl_raw.render(), console=console, refresh_per_second=8, transient=True) as live:
        live_tl_raw.attach(live)
        raw_result = raw_agent.run(query)

    raw_trace = raw_agent.last_trace

    # ── Run 2: Governed agent ─────────────────────────────────────────────────
    console.print()
    console.print("[bold dim]Step 2/2 — With AgentTrust[/bold dim]")
    live_tl_gov = LiveTimeline()
    engine_gov = ExecutionEngine(
        on_step_start=live_tl_gov.on_step_start,
        on_step_end=live_tl_gov.on_step_end,
    )
    inner_agent = create_browser_agent(
        model=model, max_results=max_results, engine=engine_gov, trace_path="trace_governed.json"
    )
    governed = GovernedBrowserAgent(inner_agent)

    governed_result = None
    governed_error = None
    try:
        with Live(live_tl_gov.render(), console=console, refresh_per_second=8, transient=True) as live:
            live_tl_gov.attach(live)
            governed_result = governed.run(query)
    except (BlockedError, EscalationError) as exc:
        governed_error = exc.reason

    governed_trace = inner_agent.last_trace

    # ── Build side-by-side comparison table ───────────────────────────────────
    _STEP_ICONS = {
        ExecutionStatus.SUCCESS: "[green]✓[/green]",
        ExecutionStatus.FAILED: "[red]✗[/red]",
        ExecutionStatus.RUNNING: "[yellow]…[/yellow]",
        ExecutionStatus.PENDING: "○",
        ExecutionStatus.BLOCKED: "[red]⊘[/red]",
    }

    def _step_line(event) -> str:
        icon = _STEP_ICONS.get(event.status, "?")
        dur = f"{event.duration_ms:.0f} ms" if event.duration_ms is not None else "—"
        name = event.step.replace("_", " ").title()
        return f"{icon} {name:<16} [dim]{dur:>8}[/dim]"

    def _gate_line(label: str, vr, decision_color: str) -> str:
        conf = f"{vr.confidence:.0f}" if vr else "—"
        decision = vr.decision.value if vr else "—"
        return (
            f"[cyan]⊙[/cyan] [dim]{label}[/dim]\n"
            f"  [{decision_color}]{decision}[/{decision_color}]"
            f"  [dim]conf:[/dim] [{decision_color}]{conf}/100[/{decision_color}]"
        )

    # Build left column lines (raw)
    left_lines: list[str] = []
    if raw_trace:
        for ev in raw_trace.events:
            left_lines.append(_step_line(ev))
        left_lines.append("")
        total_str = f"{raw_trace.total_duration_ms:,.0f} ms" if raw_trace.total_duration_ms else "—"
        left_lines.append(f"[dim]Total:[/dim] [bold]{total_str}[/bold]")
        left_lines.append(f"[dim]Steps:[/dim] {len(raw_trace.events)}")
        left_lines.append("[red]Governance: DISABLED[/red]")

    # Build right column lines (governed)
    right_lines: list[str] = []
    iv = governed.last_input_validation
    ov = governed.last_validation
    iv_color = _DECISION_COLOR.get(iv.decision, "white") if iv else "white"
    ov_color = _DECISION_COLOR.get(ov.decision, "white") if ov else "white"

    if iv:
        right_lines.append(_gate_line("Input Validation", iv, iv_color))
        right_lines.append("")

    if governed_trace:
        for ev in governed_trace.events:
            right_lines.append(_step_line(ev))
        right_lines.append("")

    if ov:
        right_lines.append(_gate_line("Output Validation", ov, ov_color))
        right_lines.append("")

    if governed_error:
        right_lines.append(f"[red]BLOCKED:[/red] {governed_error}")
    elif governed_result is None:
        right_lines.append("[red]No governed result[/red]")

    if governed_trace and governed_trace.total_duration_ms:
        raw_total = raw_trace.total_duration_ms if raw_trace else 0.0
        gov_total = governed_trace.total_duration_ms or 0.0
        overhead = gov_total - (raw_total or 0.0)
        right_lines.append(f"[dim]Total:[/dim] [bold]{gov_total:,.0f} ms[/bold]")
        steps_label = f"{len(governed_trace.events)} agent steps"
        gate_count = sum(1 for x in [iv, ov] if x)
        right_lines.append(f"[dim]Steps:[/dim] {steps_label} + {gate_count} gates")
        overhead_color = "yellow" if abs(overhead) > 500 else "green"
        right_lines.append(f"[{overhead_color}]Overhead: {overhead:+,.0f} ms[/{overhead_color}]")
        final_decision = ov.decision.value if ov else ("BLOCK" if governed_error else "—")
        dc = _DECISION_COLOR.get(ov.decision, "white") if ov else "red"
        right_lines.append(f"[dim]Decision:[/dim] [{dc}]{final_decision}[/{dc}]")
    elif governed_error:
        right_lines.append("[dim]Total:[/dim] [bold]—[/bold]")
        right_lines.append("[red]Governance: BLOCKED[/red]")

    console.print()
    table = Table(
        title="[bold white]Execution Comparison[/bold white]",
        show_header=True,
        header_style="bold",
        border_style="dim",
        show_lines=True,
    )
    table.add_column("WITHOUT AgentTrust", style="white", min_width=38, no_wrap=False)
    table.add_column("WITH AgentTrust", style="white", min_width=38, no_wrap=False)

    max_rows = max(len(left_lines), len(right_lines))
    left_lines += [""] * (max_rows - len(left_lines))
    right_lines += [""] * (max_rows - len(right_lines))

    for l, r in zip(left_lines, right_lines):
        table.add_row(l, r)

    console.print(table)

    # ── Summary panels ────────────────────────────────────────────────────────
    if governed_result:
        console.print()
        console.print(
            Panel(
                Markdown(governed_result.summary),
                title="[bold green]Governed Summary[/bold green]",
                subtitle="[dim]output approved by AgentTrust[/dim]",
                border_style="green",
                padding=(1, 2),
            )
        )

    # ── Save comparison.json + metrics.json ──────────────────────────────────
    from app.models.base import ComparisonResult as CR
    cr = CR(
        query=query,
        raw_result=raw_result,
        raw_trace=raw_trace or _empty_trace_placeholder(query),
        governed_result=governed_result,
        governed_trace=governed_trace,
        governed_decision=ov.decision.value if ov else None,
        input_validation=iv,
        output_validation=ov,
        governed_error=governed_error,
    )
    if save:
        from app.comparison.engine import save_comparison
        p = save_comparison(cr)
        console.print(f"\n[dim]Comparison saved → [bold]{p}[/bold][/dim]")

    from app.metrics.engine import LocalMetricsEngine, save_metrics
    _m = LocalMetricsEngine()
    _m.record_comparison(cr)
    save_metrics(_m)
    console.print(f"[dim]Metrics saved → [bold]metrics.json[/bold][/dim]")

    # -- Audit --
    _vr_audit = ov or iv
    if _vr_audit:
        import uuid as _uuid
        from app.audit.store import LocalAuditStore as _LAS, make_audit_event as _mae
        _eid = governed_trace.execution_id if governed_trace else _uuid.uuid4().hex
        _LAS().append(_mae(_eid, _vr_audit, cr.governed_latency_ms))
        console.print(f"[dim]Audit saved → [bold]audit.jsonl[/bold][/dim]")


@app.command()
def metrics(
    path: str = typer.Option("metrics.json", "--path", "-p", help="Path to metrics.json"),
) -> None:
    """Display a metrics dashboard from the last recorded run."""
    from pathlib import Path as _Path

    from app.metrics.engine import load_metrics
    from app.execution.timeline import AGENT_STEPS

    p = _Path(path)
    if not p.exists():
        console.print(f"[yellow]No metrics file found at [bold]{path}[/bold].[/yellow]")
        console.print("[dim]Run [bold]python demo.py run[/bold] or [bold]compare[/bold] first.[/dim]")
        raise typer.Exit(0)

    data = load_metrics(p)
    if not data:
        console.print("[yellow]Metrics file is empty.[/yellow]")
        raise typer.Exit(0)

    console.print()
    console.print(
        Panel(
            f"[dim]Source:[/dim] [bold]{path}[/bold]",
            title="[bold white]Metrics Dashboard[/bold white]",
            border_style="cyan",
        )
    )

    # ── Step breakdown ────────────────────────────────────────────────────────
    step_table = Table(show_header=True, header_style="bold dim", border_style="dim")
    step_table.add_column("Step", style="white", min_width=12)
    step_table.add_column("Avg ms", justify="right", min_width=9)
    step_table.add_column("Min ms", justify="right", min_width=9)
    step_table.add_column("Max ms", justify="right", min_width=9)
    step_table.add_column("Runs", justify="right", min_width=5)
    step_table.add_column("Share", min_width=20)

    step_avgs = {}
    for step in AGENT_STEPS:
        key = f"step.{step}.ms"
        if key in data:
            step_avgs[step] = data[key]["avg"]

    max_avg = max(step_avgs.values(), default=1.0) or 1.0
    _BAR = "█"

    for step in AGENT_STEPS:
        key = f"step.{step}.ms"
        if key not in data:
            step_table.add_row(step, "—", "—", "—", "—", "")
            continue
        d = data[key]
        frac = d["avg"] / max_avg
        bar_len = max(1, round(frac * 18))
        bar = f"[cyan]{_BAR * bar_len}[/cyan]"
        step_table.add_row(
            step.replace("_", " ").title(),
            f"{d['avg']:,.0f}",
            f"{d['min']:,.0f}",
            f"{d['max']:,.0f}",
            str(int(d["count"])),
            bar,
        )

    console.print()
    console.print(Panel(step_table, title="[bold white]Step Breakdown[/bold white]", border_style="blue"))

    # ── Latency summary ───────────────────────────────────────────────────────
    if "total_latency_ms" in data:
        lt = data["total_latency_ms"]
        console.print()
        console.print(
            Panel(
                f"  [dim]Avg:[/dim] [bold]{lt['avg']:,.0f} ms[/bold]   "
                f"[dim]Min:[/dim] {lt['min']:,.0f} ms   "
                f"[dim]Max:[/dim] {lt['max']:,.0f} ms   "
                f"[dim]Runs:[/dim] {int(lt['count'])}",
                title="[bold white]Total Latency[/bold white]",
                border_style="blue",
            )
        )

    # ── Governance metrics ────────────────────────────────────────────────────
    gov_keys = [k for k in data if k.startswith("governance.") or k.startswith("run.")]
    if gov_keys:
        gov_table = Table(show_header=True, header_style="bold dim", border_style="dim")
        gov_table.add_column("Metric", style="white", min_width=30)
        gov_table.add_column("Avg", justify="right", min_width=10)
        gov_table.add_column("Last", justify="right", min_width=10)
        gov_table.add_column("Runs", justify="right", min_width=5)

        _FRIENDLY = {
            "governance.output.confidence": "Output Confidence",
            "governance.output.policy_score": "Output Policy Score",
            "governance.output.violations": "Output Violations",
            "governance.output.risk": "Output Risk (0=LOW … 3=CRITICAL)",
            "governance.input.confidence": "Input Confidence",
            "governance.input.policy_score": "Input Policy Score",
            "governance.overhead_ms": "Governance Overhead ms",
            "run.allowed": "Runs Allowed",
            "run.blocked": "Runs Blocked",
        }

        for k in sorted(gov_keys):
            d = data[k]
            label = _FRIENDLY.get(k, k)
            gov_table.add_row(
                label,
                f"{d['avg']:.1f}",
                f"{d['last']:.1f}",
                str(int(d["count"])),
            )

        console.print()
        console.print(
            Panel(gov_table, title="[bold white]Governance Metrics[/bold white]", border_style="cyan")
        )

    console.print(f"\n[dim]Metrics file: [bold]{path}[/bold][/dim]")


@app.command()
def scenarios(
    scenario_num: int = typer.Option(0, "--scenario", "-s", help="Run a specific scenario (1-5); 0 = all"),
) -> None:
    """Run the 5 deterministic failure scenarios — each without and with AgentTrust."""
    from app.scenarios.scenarios import SCENARIOS, run_all_scenarios

    _STAGE = {True: "[cyan]Stage 1 — Input[/cyan]", False: "[yellow]Stage 2 — Output[/yellow]"}

    console.print()
    console.print(
        Panel(
            "[dim]Each scenario runs twice — without governance and with AgentTrust.[/dim]\n"
            "[dim]Without AgentTrust: failures pass through undetected.[/dim]\n"
            "[dim]With AgentTrust:    governance catches and blocks the failure.[/dim]",
            title="[bold white]Failure Scenario Demonstrations[/bold white]",
            border_style="red",
        )
    )

    to_run = (
        [SCENARIOS[scenario_num - 1]] if 1 <= scenario_num <= 5 else SCENARIOS
    )

    results = []
    for i, scenario in enumerate(to_run, 1):
        idx = SCENARIOS.index(scenario) + 1
        console.print()
        console.rule(f"[bold]Scenario {idx}/5 — {scenario.name}[/bold]")

        sr = scenario.run()
        results.append(sr)

        # Header
        console.print(f"[dim]Query:[/dim] [italic]{sr.query}[/italic]")
        console.print(f"[dim]{scenario.description}[/dim]")
        console.print()

        # Without AgentTrust panel
        raw_summary = sr.raw_result.summary[:120] + "…" if len(sr.raw_result.summary) > 120 else sr.raw_result.summary
        raw_body = (
            f"[bold yellow]⚠  Agent executed — failure undetected[/bold yellow]\n\n"
            f"[dim]Result:[/dim] {raw_summary or '[dim](empty)[/dim]'}\n\n"
            f"[red]Governance: DISABLED — output returned as-is[/red]"
        )
        console.print(
            Panel(raw_body, title="[bold white]WITHOUT AgentTrust[/bold white]", border_style="yellow", padding=(0, 2))
        )

        # With AgentTrust panel
        stage_label = _STAGE.get(sr.input_blocked, "[yellow]Stage 2 — Output[/yellow]")
        agent_ran = "[dim]Agent did not run[/dim]" if sr.input_blocked else "[dim]Agent ran — but output was intercepted[/dim]"
        gov_body = (
            f"[bold red]⊘  BLOCKED at {stage_label}[/bold red]\n\n"
            f"[dim]Reason:[/dim] [red]{sr.governance_reason}[/red]\n\n"
            f"{agent_ran}"
        )
        console.print(
            Panel(gov_body, title="[bold white]WITH AgentTrust[/bold white]", border_style="red", padding=(0, 2))
        )

    # Summary table
    if len(results) > 1:
        console.print()
        table = Table(
            title="[bold white]Failure Scenario Summary[/bold white]",
            border_style="dim",
            show_lines=True,
        )
        table.add_column("#", width=3, style="dim")
        table.add_column("Scenario", style="white", min_width=26)
        table.add_column("Without AgentTrust", justify="center", min_width=18)
        table.add_column("With AgentTrust", justify="center", min_width=18)
        table.add_column("Stage Blocked", min_width=14)

        for i, (scenario, sr) in enumerate(zip(to_run, results), 1):
            idx = SCENARIOS.index(scenario) + 1
            raw_cell = "[yellow]PASS (failure undetected)[/yellow]"
            gov_cell = "[bold red]BLOCK[/bold red]" if sr.governed_blocked else f"[green]{sr.governed_decision}[/green]"
            stage = "[cyan]Stage 1 — Input[/cyan]" if sr.input_blocked else "[yellow]Stage 2 — Output[/yellow]"
            table.add_row(str(idx), scenario.name, raw_cell, gov_cell, stage)

        console.print(table)
        passed = sum(1 for r in results if r.governed_blocked)
        console.print(
            f"\n[bold green]AgentTrust blocked {passed}/{len(results)} failure scenarios.[/bold green]  "
            f"[dim]Run [bold]python demo.py scenarios --scenario N[/bold] to inspect one in detail.[/dim]"
        )


@app.command()
def report(
    audit: str = typer.Option("audit.jsonl", "--audit", "-a", help="Path to audit.jsonl"),
    metrics_file: str = typer.Option("metrics.json", "--metrics", "-m", help="Path to metrics.json"),
    comparison_file: str = typer.Option("comparison.json", "--comparison", "-c", help="Path to comparison.json"),
    review_file: str = typer.Option("review_queue.jsonl", "--review", "-r", help="Path to review_queue.jsonl"),
    out: str = typer.Option("report.md", "--out", "-o", help="Output path for report"),
    title: str = typer.Option("AgentTrust Session Report", "--title", help="Report title"),
) -> None:
    """Generate a Markdown session report from all collected data."""
    from pathlib import Path as _Path
    from app.report.generator import ReportGenerator
    from app.report.models import ReportConfig
    from app.report.renderer import MarkdownRenderer

    def _opt(s: str) -> "_Path | None":
        p = _Path(s)
        return p if p.exists() else None

    cfg = ReportConfig(title=title)
    gen = ReportGenerator(cfg)
    rpt = gen.generate(
        audit_path=_opt(audit),
        metrics_path=_opt(metrics_file),
        comparison_path=_opt(comparison_file),
        review_path=_opt(review_file),
    )

    renderer = MarkdownRenderer()
    saved = renderer.save(rpt, _Path(out))

    s = rpt.summary
    table = Table(show_header=True, header_style="bold dim", border_style="dim", show_lines=False)
    table.add_column("Metric", style="white", min_width=22)
    table.add_column("Value", justify="right", min_width=12)
    total = s.total_governed_runs
    pct = lambda n: f"({n / total * 100:.0f}%)" if total else ""
    table.add_row("Governed runs", str(total))
    table.add_row("Allowed", f"{s.allowed} {pct(s.allowed)}")
    table.add_row("Blocked", f"{s.blocked} {pct(s.blocked)}")
    table.add_row("Escalated", f"{s.escalated} {pct(s.escalated)}")
    table.add_row("Avg confidence", f"{s.avg_confidence:.1f}/100")
    table.add_row("Avg latency", f"{s.avg_latency_ms:,.0f} ms")
    table.add_row("Total violations", str(s.violation_count))
    table.add_row("Most common risk", s.most_common_risk)

    console.print()
    console.print(Panel(table, title="[bold white]Session Report Summary[/bold white]", border_style="green"))

    sources = []
    if rpt.audit_events:
        sources.append(f"[bold]{len(rpt.audit_events)}[/bold] audit events")
    if rpt.metrics:
        sources.append(f"[bold]{len(rpt.metrics)}[/bold] metrics keys")
    if rpt.comparison:
        sources.append("[bold]1[/bold] comparison run")
    if rpt.review_items:
        sources.append(f"[bold]{len(rpt.review_items)}[/bold] review items")

    console.print(
        f"\n[dim]Data: {', '.join(sources) or 'none found'}[/dim]\n"
        f"[dim]Report saved → [bold]{saved}[/bold][/dim]"
    )


@app.command()
def dashboard(
    audit: str = typer.Option("audit.jsonl", "--audit", "-a", help="Path to audit.jsonl"),
    metrics_file: str = typer.Option("metrics.json", "--metrics", "-m", help="Path to metrics.json"),
    comparison_file: str = typer.Option("comparison.json", "--comparison", "-c", help="Path to comparison.json"),
    review_file: str = typer.Option("review_queue.jsonl", "--review", "-r", help="Path to review_queue.jsonl"),
) -> None:
    """Display a live governance dashboard snapshot."""
    from pathlib import Path as _Path
    from app.dashboard.collector import DashboardCollector
    from app.dashboard.models import DashboardConfig
    from app.dashboard.renderer import DashboardRenderer

    def _opt(s: str) -> "_Path | None":
        p = _Path(s)
        return p if p.exists() else None

    cfg = DashboardConfig()
    collector = DashboardCollector(cfg)
    state = collector.collect(
        audit_path=_opt(audit),
        metrics_path=_opt(metrics_file),
        comparison_path=_opt(comparison_file),
        review_path=_opt(review_file),
    )

    # ── KPI table ─────────────────────────────────────────────────────────────
    kpi_table = Table(show_header=True, header_style="bold dim", border_style="dim", show_lines=False)
    kpi_table.add_column("KPI", style="white", min_width=22)
    kpi_table.add_column("Value", justify="right", min_width=14)
    total = state.total_governed_runs
    pct = lambda n: f"({n / total * 100:.0f}%)" if total else ""
    kpi_table.add_row("Governed runs", str(total))
    kpi_table.add_row("Allowed", f"[green]{state.allowed}[/green] {pct(state.allowed)}")
    kpi_table.add_row("Blocked", f"[red]{state.blocked}[/red] {pct(state.blocked)}")
    kpi_table.add_row("Escalated", f"[yellow]{state.escalated}[/yellow] {pct(state.escalated)}")
    kpi_table.add_row("Pending review", f"[yellow]{state.pending_review}[/yellow]")
    kpi_table.add_row("Avg confidence", f"{state.avg_confidence:.1f}/100")
    kpi_table.add_row("Avg latency", f"{state.avg_latency_ms:,.0f} ms")
    kpi_table.add_row("Total violations", str(state.violation_count))
    kpi_table.add_row("Most common risk", state.most_common_risk)
    kpi_table.add_row("Comparison data", "Yes" if state.has_comparison else "No")

    ts = state.collected_at[:19].replace("T", " ")
    console.print()
    console.print(Panel(
        kpi_table,
        title=f"[bold white]{cfg.title}[/bold white]",
        subtitle=f"[dim]as of {ts} UTC[/dim]",
        border_style="cyan",
    ))

    # ── Recent audit events ────────────────────────────────────────────────────
    if state.recent_events:
        evt_table = Table(show_header=True, header_style="bold dim", border_style="dim", show_lines=False)
        evt_table.add_column("Timestamp", style="dim", min_width=19)
        evt_table.add_column("Decision", min_width=12)
        evt_table.add_column("Confidence", justify="right", min_width=10)
        evt_table.add_column("Risk", min_width=8)
        for e in state.recent_events:
            ev_ts = e.timestamp[:19].replace("T", " ")
            dec_style = "green" if e.decision.value == "ALLOW" else ("red" if e.decision.value == "BLOCK" else "yellow")
            evt_table.add_row(ev_ts, f"[{dec_style}]{e.decision.value}[/{dec_style}]",
                              f"{e.confidence:.0f}", e.risk.value)
        console.print(Panel(evt_table, title="[bold white]Recent Audit Events[/bold white]", border_style="dim"))

    # ── Pending review items ───────────────────────────────────────────────────
    if state.pending_review_items:
        rv_table = Table(show_header=True, header_style="bold dim", border_style="dim", show_lines=False)
        rv_table.add_column("ID", style="dim", min_width=10)
        rv_table.add_column("Query", min_width=40)
        rv_table.add_column("Status", min_width=10)
        for item in state.pending_review_items:
            q = item.query[:50] + ("…" if len(item.query) > 50 else "")
            rv_table.add_row(f"{item.item_id[:8]}…", q, f"[yellow]{item.status.value}[/yellow]")
        console.print(Panel(rv_table, title="[bold white]Pending Review[/bold white]", border_style="yellow"))

    # ── Alert evaluation ───────────────────────────────────────────────────────
    from app.alerts.defaults import default_rules
    from app.alerts.engine import AlertEngine
    from app.alerts.models import AlertSeverity

    alerts = AlertEngine(default_rules()).evaluate(state)
    if alerts:
        _sev_style = {
            AlertSeverity.CRITICAL: "bold red",
            AlertSeverity.WARNING: "yellow",
            AlertSeverity.INFO: "cyan",
        }
        al_table = Table(show_header=True, header_style="bold dim", border_style="dim", show_lines=False)
        al_table.add_column("Severity", min_width=10)
        al_table.add_column("Rule", min_width=26)
        al_table.add_column("Metric", min_width=18)
        al_table.add_column("Value", justify="right", min_width=8)
        al_table.add_column("Threshold", justify="right", min_width=10)
        for a in alerts:
            sty = _sev_style.get(a.severity, "white")
            al_table.add_row(
                f"[{sty}]{a.severity.value.upper()}[/{sty}]",
                a.rule_name, a.metric,
                f"{a.actual_value:.1f}", f"{a.threshold:.1f}",
            )
        border = "red" if any(a.severity == AlertSeverity.CRITICAL for a in alerts) else "yellow"
        console.print(Panel(al_table, title=f"[bold white]Alerts ({len(alerts)})[/bold white]", border_style=border))

    if not state.recent_events and not state.pending_review_items and total == 0:
        console.print("\n[dim]No governance data found. Run some queries first.[/dim]\n")


@app.command()
def export(
    audit: str = typer.Option("audit.jsonl", "--audit", "-a", help="Path to audit.jsonl"),
    metrics_file: str = typer.Option("metrics.json", "--metrics", "-m", help="Path to metrics.json"),
    comparison_file: str = typer.Option("comparison.json", "--comparison", "-c", help="Path to comparison.json"),
    review_file: str = typer.Option("review_queue.jsonl", "--review", "-r", help="Path to review_queue.jsonl"),
    out_dir: str = typer.Option("exports", "--out", "-o", help="Output directory"),
    fmt: str = typer.Option("json", "--format", "-f", help="Export format: json or csv"),
) -> None:
    """Export governance data to JSON or CSV files."""
    from pathlib import Path as _Path
    from app.dashboard.collector import DashboardCollector
    from app.export.exporter import DataExporter
    from app.export.models import ExportConfig, ExportFormat

    def _opt(s: str) -> "_Path | None":
        p = _Path(s)
        return p if p.exists() else None

    try:
        export_fmt = ExportFormat(fmt.lower())
    except ValueError:
        console.print(f"[red]Unknown format '{fmt}'. Use 'json' or 'csv'.[/red]")
        raise typer.Exit(1)

    state = DashboardCollector().collect(
        audit_path=_opt(audit),
        metrics_path=_opt(metrics_file),
        comparison_path=_opt(comparison_file),
        review_path=_opt(review_file),
    )

    cfg = ExportConfig(format=export_fmt)
    manifest = DataExporter(cfg).export_all(state, out_dir)

    table = Table(show_header=True, header_style="bold dim", border_style="dim", show_lines=False)
    table.add_column("Dataset", style="white", min_width=12)
    table.add_column("File", style="cyan")
    for name, path in manifest.files.items():
        table.add_row(name, path)

    console.print()
    console.print(Panel(
        table,
        title=f"[bold white]Export Complete ({export_fmt.value.upper()})[/bold white]",
        subtitle=f"[dim]{manifest.total_records} records | {len(manifest.files)} files → {out_dir}[/dim]",
        border_style="green",
    ))
    if not manifest.files:
        console.print("\n[dim]No data to export. Run some queries first.[/dim]\n")


@app.command()
def trends(
    audit: str = typer.Option("audit.jsonl", "--audit", "-a", help="Path to audit.jsonl"),
) -> None:
    """Analyze governance trends across audit events."""
    from pathlib import Path as _Path
    from app.audit.store import LocalAuditStore
    from app.trends.analyzer import TrendAnalyzer
    from app.trends.models import TrendDirection

    p = _Path(audit)
    if not p.exists():
        console.print(f"\n[dim]No audit log found at {audit}. Run some governed queries first.[/dim]\n")
        return

    events = LocalAuditStore(p).read_all()
    if not events:
        console.print("\n[dim]Audit log is empty.[/dim]\n")
        return

    report = TrendAnalyzer().analyze(events)

    _dir_style = {
        TrendDirection.IMPROVING: "[green]▲ IMPROVING[/green]",
        TrendDirection.DEGRADING: "[red]▼ DEGRADING[/red]",
        TrendDirection.STABLE: "[dim]→ STABLE[/dim]",
    }

    table = Table(show_header=True, header_style="bold dim", border_style="dim", show_lines=False)
    table.add_column("Metric", style="white", min_width=20)
    table.add_column("Direction", min_width=15)
    table.add_column("First", justify="right", min_width=10)
    table.add_column("Last", justify="right", min_width=10)
    table.add_column("Change", justify="right", min_width=10)

    for metric, trend in report.trends.items():
        sign = "+" if trend.change_pct >= 0 else ""
        table.add_row(
            metric,
            _dir_style[trend.direction],
            f"{trend.first_value:.1f}",
            f"{trend.last_value:.1f}",
            f"{sign}{trend.change_pct:.1f}%",
        )

    console.print()
    console.print(Panel(
        table,
        title="[bold white]Governance Trend Analysis[/bold white]",
        subtitle=f"[dim]{report.event_count} events analyzed[/dim]",
        border_style="cyan",
    ))
    if not report.trends:
        console.print("[dim]  Not enough data for trend analysis (need at least 2 events).[/dim]\n")


@app.command()
def health(
    audit: str = typer.Option("audit.jsonl", "--audit", "-a", help="Path to audit.jsonl"),
    metrics_file: str = typer.Option("metrics.json", "--metrics", "-m", help="Path to metrics.json"),
    review_file: str = typer.Option("review_queue.jsonl", "--review", "-r", help="Path to review_queue.jsonl"),
    policy_file: str = typer.Option("", "--policy", "-p", help="Path to policy YAML (blank = default)"),
) -> None:
    """Run a governance pipeline health check."""
    from pathlib import Path as _Path
    from app.health.checker import HealthChecker
    from app.health.models import HealthStatus

    def _opt(s: str) -> "_Path | None":
        if not s:
            return None
        p = _Path(s)
        return p if p.exists() else p  # pass through — checker handles missing

    checker = HealthChecker()
    report = checker.check(
        audit_path=_opt(audit),
        metrics_path=_opt(metrics_file),
        review_path=_opt(review_file),
        policy_path=_opt(policy_file),
    )

    _status_style = {
        HealthStatus.HEALTHY: "[green]✓ HEALTHY[/green]",
        HealthStatus.DEGRADED: "[red]✗ DEGRADED[/red]",
        HealthStatus.UNKNOWN: "[dim]? UNKNOWN[/dim]",
    }
    _border = {
        HealthStatus.HEALTHY: "green",
        HealthStatus.DEGRADED: "red",
        HealthStatus.UNKNOWN: "dim",
    }

    table = Table(show_header=True, header_style="bold dim", border_style="dim", show_lines=False)
    table.add_column("Component", style="white", min_width=18)
    table.add_column("Status", min_width=14)
    table.add_column("Message")
    for c in report.components:
        table.add_row(c.name, _status_style[c.status], c.message)

    overall_label = _status_style[report.overall]
    console.print()
    console.print(Panel(
        table,
        title=f"[bold white]Governance Health Check — {overall_label}[/bold white]",
        subtitle=f"[dim]{report.healthy_count}/{len(report.components)} components healthy[/dim]",
        border_style=_border[report.overall],
    ))
    if report.degraded_count:
        degraded = [c for c in report.components if c.status == HealthStatus.DEGRADED]
        for c in degraded:
            if c.detail:
                console.print(f"  [red]{c.name}:[/red] {c.detail}")


@app.command()
def review(
    path: str = typer.Option("review_queue.jsonl", "--path", "-p", help="Path to review_queue.jsonl"),
    approve_id: str = typer.Option("", "--approve", help="Approve item by ID"),
    reject_id: str = typer.Option("", "--reject", help="Reject item by ID"),
    note: str = typer.Option("", "--note", "-n", help="Reviewer note for approve/reject"),
    clear_queue: bool = typer.Option(False, "--clear", help="Clear the review queue"),
) -> None:
    """Manage the human review queue for HUMAN_REVIEW escalations."""
    from pathlib import Path as _Path
    from app.review.queue import ReviewQueue
    from app.review.models import ReviewStatus

    queue = ReviewQueue(_Path(path))

    if clear_queue:
        queue.clear()
        console.print(f"[green]Review queue cleared: {path}[/green]")
        return

    if approve_id:
        try:
            item = queue.approve(approve_id, note)
            console.print(f"[green]Approved:[/green] {item.item_id[:8]}…  [dim]{item.reviewed_at[:19]}[/dim]")
        except KeyError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)
        return

    if reject_id:
        try:
            item = queue.reject(reject_id, note)
            console.print(f"[red]Rejected:[/red] {item.item_id[:8]}…  [dim]{item.reviewed_at[:19]}[/dim]")
        except KeyError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)
        return

    # ── List all items ────────────────────────────────────────────────────────
    items = queue.read_all()
    console.print()

    if not items:
        console.print(
            Panel(
                f"[dim]No items in review queue at [bold]{path}[/bold].[/dim]\n"
                "[dim]Items are added when AgentTrust escalates to HUMAN_REVIEW.[/dim]",
                title="[bold white]Human Review Queue[/bold white]",
                border_style="dim",
            )
        )
        return

    pending = [i for i in items if i.status == ReviewStatus.PENDING]
    _SC = {
        ReviewStatus.PENDING: "[bold yellow]PENDING[/bold yellow]",
        ReviewStatus.APPROVED: "[green]APPROVED[/green]",
        ReviewStatus.REJECTED: "[red]REJECTED[/red]",
    }

    table = Table(
        title=f"[bold white]Human Review Queue[/bold white] "
              f"[dim]({len(items)} total, {len(pending)} pending)[/dim]",
        border_style="dim",
        show_lines=True,
        header_style="bold dim",
    )
    table.add_column("ID (short)", style="white", min_width=10)
    table.add_column("Timestamp", style="dim", min_width=19)
    table.add_column("Status", justify="center", min_width=10)
    table.add_column("Query", min_width=30)
    table.add_column("Confidence", justify="right", min_width=10)
    table.add_column("Risk", justify="center", min_width=8)
    table.add_column("Note", style="dim", min_width=20)

    _RC = {"LOW": "green", "MEDIUM": "yellow", "HIGH": "red", "CRITICAL": "bold red"}

    for item in items:
        rc = _RC.get(item.validation.risk_level.value, "white")
        q_short = item.query[:40] + ("…" if len(item.query) > 40 else "")
        table.add_row(
            item.item_id[:8] + "…",
            item.timestamp[:19].replace("T", " "),
            _SC.get(item.status, item.status.value),
            q_short,
            f"{item.validation.confidence:.0f}/100",
            f"[{rc}]{item.validation.risk_level.value}[/{rc}]",
            item.reviewer_note[:30] or "[dim]—[/dim]",
        )

    console.print(table)

    if pending:
        console.print(
            f"\n[dim]To resolve: [bold]python demo.py review --approve ID[/bold] or "
            f"[bold]--reject ID[/bold]  (optionally with [bold]--note \"reason\"[/bold])[/dim]"
        )
    console.print(f"[dim]Queue file: [bold]{path}[/bold][/dim]")


@app.command()
def policy(
    path: str = typer.Option("", "--policy", "-p", help="Custom policy YAML (default = built-in)"),
    validate: bool = typer.Option(False, "--validate", help="Validate the YAML and exit 0 if valid"),
) -> None:
    """Display the active governance policy configuration."""
    from pathlib import Path as _Path
    from app.policies.loader import load_policy

    try:
        cfg = load_policy(_Path(path) if path else None)
    except FileNotFoundError as exc:
        console.print(f"[red]Policy file not found: {exc}[/red]")
        raise typer.Exit(1)
    except Exception as exc:
        console.print(f"[red]Failed to load policy: {exc}[/red]")
        raise typer.Exit(1)

    if validate:
        console.print(f"[green]Policy valid:[/green] [bold]{cfg.name}[/bold] v{cfg.version}")
        return

    src = path or "[dim](built-in default.yaml)[/dim]"
    console.print()
    console.print(
        Panel(
            f"[bold]{cfg.name}[/bold]  v{cfg.version}\n"
            + (f"[dim]{cfg.description}[/dim]\n" if cfg.description else "")
            + f"[dim]Source:[/dim] {src}",
            title="[bold white]Governance Policy[/bold white]",
            border_style="cyan",
        )
    )

    # ── Decision thresholds ───────────────────────────────────────────────────
    t = cfg.thresholds
    thresh_table = Table(show_header=True, header_style="bold dim", border_style="dim", show_lines=False)
    thresh_table.add_column("Threshold", style="white", min_width=30)
    thresh_table.add_column("Value", justify="right", min_width=10)
    thresh_table.add_rows([
        ("Block if confidence <", f"{t.block_confidence:.1f}"),
        ("Block if policy score <", f"{t.block_policy_score:.1f}"),
        ("Auto-approve if confidence ≥", f"{t.approve_confidence:.1f}"),
        ("Approve if policy score ≥ AND confidence ≥",
         f"{t.approve_combined_policy:.1f} / {t.approve_combined_confidence:.1f}"),
    ])
    console.print()
    console.print(Panel(thresh_table, title="[bold white]Decision Thresholds[/bold white]", border_style="blue"))

    # ── Violation penalties ───────────────────────────────────────────────────
    p = cfg.penalties
    pen_table = Table(show_header=True, header_style="bold dim", border_style="dim", show_lines=False)
    pen_table.add_column("Severity", style="white", min_width=12)
    pen_table.add_column("Effect", min_width=30)
    pen_table.add_rows([
        ("[bold red]CRITICAL[/bold red]", "policy_score → 0 (instant block)"),
        ("[red]HIGH[/red]", f"policy_score − {p.high:.0f}"),
        ("[yellow]MEDIUM[/yellow]", f"policy_score − {p.medium:.0f}"),
        ("[dim]LOW[/dim]", f"policy_score − {p.low:.0f}"),
    ])
    console.print()
    console.print(Panel(pen_table, title="[bold white]Violation Penalties[/bold white]", border_style="blue"))

    # ── Confidence adjustments + rules ────────────────────────────────────────
    conf = cfg.confidence
    rules_table = Table(show_header=True, header_style="bold dim", border_style="dim", show_lines=False)
    rules_table.add_column("Rule", style="white", min_width=30)
    rules_table.add_column("Value", justify="right", min_width=10)
    rules_table.add_rows([
        ("Initial confidence", f"{conf.initial:.1f}"),
        ("Short summary penalty (< " + str(cfg.output.min_summary_length) + " chars)", f"−{conf.short_summary_penalty:.1f}"),
        ("No sources penalty", f"−{conf.no_sources_penalty:.1f}"),
        ("Invalid URL scheme penalty", f"−{conf.invalid_url_penalty:.1f}"),
        ("Per-source bonus (max " + str(cfg.output.min_summary_length) + ")", f"+{conf.per_source_bonus:.1f}"),
        ("Long summary bonus (> " + str(cfg.output.long_summary_threshold) + " chars)", f"+{conf.long_summary_bonus:.1f}"),
        ("Medium summary bonus (> " + str(cfg.output.medium_summary_threshold) + " chars)", f"+{conf.medium_summary_bonus:.1f}"),
        ("Max query length", str(cfg.input.max_query_length)),
    ])
    console.print()
    console.print(Panel(rules_table, title="[bold white]Confidence Rules[/bold white]", border_style="blue"))
    console.print(f"\n[dim]Use [bold]--policy path/to/custom.yaml[/bold] to load a different policy.[/dim]")


@app.command()
def audit(
    path: str = typer.Option("audit.jsonl", "--path", "-p", help="Path to audit.jsonl"),
    clear_log: bool = typer.Option(False, "--clear", help="Clear the audit log after viewing"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max events to display (0 = all)"),
) -> None:
    """View the audit log of governed executions."""
    from pathlib import Path as _Path
    from app.audit.store import LocalAuditStore

    store = LocalAuditStore(_Path(path))
    events = store.read_all()

    console.print()
    if not events:
        console.print(
            Panel(
                f"[dim]No audit events found at [bold]{path}[/bold].[/dim]\n"
                "[dim]Run [bold]python demo.py run-governed[/bold] or [bold]compare[/bold] first.[/dim]",
                title="[bold white]Audit Log[/bold white]",
                border_style="dim",
            )
        )
        return

    to_show = events if limit == 0 else events[-limit:]
    table = Table(
        title=f"[bold white]Audit Log[/bold white] [dim]({len(events)} events, showing {len(to_show)})[/dim]",
        border_style="dim",
        show_lines=False,
        show_header=True,
        header_style="bold dim",
    )
    table.add_column("Timestamp", style="dim", min_width=19)
    table.add_column("Execution ID", style="white", min_width=18)
    table.add_column("Decision", justify="center", min_width=10)
    table.add_column("Conf", justify="right", min_width=5)
    table.add_column("Risk", justify="center", min_width=8)
    table.add_column("Latency", justify="right", min_width=10)
    table.add_column("Violations", style="dim", min_width=28)

    _DC = {"ALLOW": "green", "BLOCK": "red", "RETRY": "yellow", "HUMAN_REVIEW": "yellow"}
    _RC = {"LOW": "green", "MEDIUM": "yellow", "HIGH": "red", "CRITICAL": "bold red"}

    for ev in to_show:
        dc = _DC.get(ev.decision.value, "white")
        rc = _RC.get(ev.risk.value, "white")
        ts = ev.timestamp[:19].replace("T", " ")
        eid = ev.execution_id[:16] + ("…" if len(ev.execution_id) > 16 else "")
        viols = "; ".join(ev.violations[:2]) + ("…" if len(ev.violations) > 2 else "")
        table.add_row(
            ts,
            eid,
            f"[{dc}]{ev.decision.value}[/{dc}]",
            f"{ev.confidence:.0f}",
            f"[{rc}]{ev.risk.value}[/{rc}]",
            f"{ev.latency_ms:,.0f} ms",
            viols or "[dim]—[/dim]",
        )

    console.print(table)

    if clear_log:
        store.clear()
        console.print(f"[dim]Audit log cleared: {path}[/dim]")
    else:
        console.print(f"\n[dim]Audit file: [bold]{path}[/bold]  |  Use [bold]--clear[/bold] to reset.[/dim]")


def _empty_trace_placeholder(query: str):
    import uuid
    from app.models.base import ExecutionStatus, ExecutionTrace
    return ExecutionTrace(
        execution_id=str(uuid.uuid4()),
        query=query,
        status=ExecutionStatus.PENDING,
    )


if __name__ == "__main__":
    app()
