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
