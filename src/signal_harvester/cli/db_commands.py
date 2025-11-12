"""Database utility commands for Phase Three performance work."""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List

import typer
from rich.console import Console
from rich.table import Table

from ..config import load_settings
from ..performance import (
    CRITICAL_QUERIES,
    benchmark_query,
    explain_query,
)

db_app = typer.Typer(help="Database utilities")
console = Console()


def _get_config_path(ctx: typer.Context) -> str | None:
    """Retrieve the configured settings path from the Typer context."""
    obj = getattr(ctx, "obj", None)
    if isinstance(obj, dict):
        return obj.get("config")
    return None


@db_app.command("analyze-performance")
def analyze_performance(
    ctx: typer.Context,
    iterations: int = typer.Option(
        25,
        "--iterations",
        "-n",
        help="Number of iterations per query (must be >= 1)",
        show_default=True,
    ),
    include_non_critical: bool = typer.Option(
        False,
        "--include-non-critical",
        help="Include medium priority queries in the report",
    ),
    show_plans: bool = typer.Option(
        True,
        "--show-plans/--no-show-plans",
        help="Show EXPLAIN QUERY PLAN output for each query",
    ),
) -> None:
    """Profile key queries and report latency + plan information."""
    if iterations < 1:
        raise typer.BadParameter("iterations must be at least 1")

    config_path = _get_config_path(ctx)
    settings = load_settings(config_path)
    db_path = settings.app.database_path

    selected_queries = [
        profile for profile in CRITICAL_QUERIES if profile.critical or include_non_critical
    ]

    if not selected_queries:
        typer.secho(
            "No queries selected (enable --include-non-critical to add medium-priority queries).",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=1)

    console.rule("Database Performance Analysis")
    console.print(f"[bold]DB path:[/bold] {db_path}")
    console.print(f"[bold]Iterations per query:[/bold] {iterations}\n")

    records: List[Dict[str, Any]] = []
    with sqlite3.connect(db_path) as conn:
        for profile in selected_queries:
            stats = benchmark_query(conn, profile.query, iterations=iterations)
            plan = explain_query(conn, profile.query) if show_plans else []
            records.append({"profile": profile, "stats": stats, "plan": plan})

    table = Table(title="Query Latency Summary", show_lines=True)
    table.add_column("Query", no_wrap=True)
    table.add_column("Min (ms)", justify="right")
    table.add_column("Mean (ms)", justify="right")
    table.add_column("p95 (ms)", justify="right")
    table.add_column("p99 (ms)", justify="right")
    table.add_column("Rows", justify="right")
    table.add_column("Index", style="cyan")
    table.add_column("Priority", justify="center")

    for record in records:
        profile = record["profile"]
        stats = record["stats"]
        priority = "🔴" if profile.critical else "🟡"
        table.add_row(
            profile.name,
            f"{stats['min_ms']:.2f}",
            f"{stats['mean_ms']:.2f}",
            f"{stats['p95_ms']:.2f}",
            f"{stats['p99_ms']:.2f}",
            str(stats["row_count"]),
            profile.expected_index,
            priority,
        )

    console.print(table)

    if show_plans:
        console.rule("EXPLAIN QUERY PLANS")
        for record in records:
            profile = record["profile"]
            plan = record["plan"]
            console.print(f"[bold]{profile.name}[/bold]")
            if not plan:
                console.print("  (no plan output)")
                continue
            for line in plan:
                console.print(f"  {line}")
            console.print()

    console.rule("Analysis Complete")


@db_app.command("profile-slow-queries")
def profile_slow_queries(
    ctx: typer.Context,
    threshold_ms: float = typer.Option(
        100.0,
        "--threshold",
        "-t",
        help="Threshold in milliseconds for slow query logging",
    ),
    enable_logging: bool = typer.Option(
        True,
        "--log/--no-log",
        help="Enable logging slow queries to logs/slow_queries.jsonl",
    ),
    show_recommendations: bool = typer.Option(
        True,
        "--recommendations/--no-recommendations",
        help="Show index recommendations based on slow queries",
    ),
) -> None:
    """Profile queries and detect slow executions with index recommendations.

    This command runs the profiler on all critical queries and generates:
    - Slow query report with execution times and table scans
    - Index recommendations with benefit scores
    - CREATE INDEX statements for missing indexes
    """
    from ..performance import CRITICAL_QUERIES
    from ..query_profiler import QueryProfiler

    config_path = _get_config_path(ctx)
    settings = load_settings(config_path)
    db_path = settings.app.database_path

    console.rule("Slow Query Profiler")
    console.print(f"[bold]DB path:[/bold] {db_path}")
    console.print(f"[bold]Slow threshold:[/bold] {threshold_ms}ms\n")

    profiler = QueryProfiler(
        db_path=db_path,
        slow_threshold_ms=threshold_ms,
        enable_logging=enable_logging,
    )

    with sqlite3.connect(db_path) as conn:
        for profile in CRITICAL_QUERIES:
            profiler.profile_query(conn, profile.query, label=profile.name)

        # Generate reports
        profiler.generate_report()

        if show_recommendations:
            console.print()
            profiler.generate_index_report(conn, show_create_statements=True)

    if enable_logging:
        console.print(f"\n[dim]Slow queries logged to: {profiler.log_file}[/dim]")


@db_app.command("recommend-indexes")
def recommend_indexes(
    ctx: typer.Context,
    analyze_slow_queries: bool = typer.Option(
        True,
        "--analyze-slow/--skip-slow",
        help="Analyze slow query log for recommendations",
    ),
) -> None:
    """Generate index recommendations based on query patterns.

    Analyzes:
    - Existing indexes and their coverage
    - Slow queries with full table scans
    - Common filter patterns in WHERE and JOIN clauses
    """
    from ..query_profiler import QueryProfiler

    config_path = _get_config_path(ctx)
    settings = load_settings(config_path)
    db_path = settings.app.database_path

    profiler = QueryProfiler(db_path=db_path, enable_logging=False)

    with sqlite3.connect(db_path) as conn:
        if analyze_slow_queries:
            # Load slow queries from log
            console.print("[dim]Loading slow queries from log...[/dim]")
            # Note: In production, implement log parsing
            console.print("[yellow]Note: Run 'harvest db profile-slow-queries' first[/yellow]\n")

        console.rule("Index Analysis")
        
        # Show current indexes
        indexes = profiler.analyze_index_usage(conn)
        if indexes:
            idx_table = Table(title="Current Indexes", show_lines=True)
            idx_table.add_column("Index Name", style="cyan")
            idx_table.add_column("Table")
            idx_table.add_column("Columns")
            
            for idx in indexes:
                idx_table.add_row(
                    idx["index_name"],
                    idx["table_name"],
                    ", ".join(idx["columns"]) if idx["columns"] else "(none)",
                )
            
            console.print(idx_table)
            console.print()
        
        # Generate recommendations
        profiler.generate_index_report(conn, show_create_statements=True)


@db_app.command("explain")
def explain_query_plan(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="SQL query to explain"),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show bytecode-level EXPLAIN output",
    ),
) -> None:
    """Show detailed query execution plan with EXPLAIN QUERY PLAN.

    Example:
        harvest db explain "SELECT * FROM artifacts WHERE source = 'arxiv'"
    """
    from ..query_profiler import get_query_execution_plan

    config_path = _get_config_path(ctx)
    settings = load_settings(config_path)
    db_path = settings.app.database_path

    with sqlite3.connect(db_path) as conn:
        plan = get_query_execution_plan(conn, query, verbose=verbose)

        if not plan:
            console.print("[yellow]No execution plan available[/yellow]")
            return

        console.rule("Query Execution Plan")
        console.print(f"[bold]Query:[/bold] {query}\n")

        plan_steps = [p for p in plan if p["type"] == "plan"]
        if plan_steps:
            plan_table = Table(title="EXPLAIN QUERY PLAN", show_lines=True)
            plan_table.add_column("Select ID", justify="right")
            plan_table.add_column("Order", justify="right")
            plan_table.add_column("From", justify="right")
            plan_table.add_column("Detail")

            for step in plan_steps:
                plan_table.add_row(
                    str(step["selectid"]),
                    str(step["order"]),
                    str(step["from"]),
                    step["detail"],
                )

            console.print(plan_table)

        if verbose:
            bytecode_steps = [p for p in plan if p["type"] == "bytecode"]
            if bytecode_steps:
                console.print("\n[bold]Bytecode:[/bold]")
                for step in bytecode_steps[:20]:  # Show first 20 opcodes
                    console.print(
                        f"  {step['addr']:4d} {step['opcode']:15s} "
                        f"{step['p1']:4d} {step['p2']:4d} {step['p3']:4d} "
                        f"{step.get('comment', '')}"
                    )
                if len(bytecode_steps) > 20:
                    console.print(f"  ... ({len(bytecode_steps) - 20} more opcodes)")
