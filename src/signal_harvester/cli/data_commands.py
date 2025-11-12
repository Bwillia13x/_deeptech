"""Data management CLI commands."""

from __future__ import annotations

import typer

from ..config import load_settings
from ..db import list_top
from .core import app, console, get_config_path


@app.command()
def top(
    ctx: typer.Context,
    limit: int = typer.Option(50, "--limit", "-n", help="Number of top items to show"),
    min_salience: float = typer.Option(0.0, "--min-salience", "-s", help="Minimum salience score"),
    hours: int | None = typer.Option(None, "--hours", help="Only show items from last N hours"),
) -> None:
    """Show top-scored tweets."""
    from rich.table import Table
    
    config_path = get_config_path(ctx)
    s = load_settings(config_path)
    rows = list_top(s.app.database_path, limit=limit, min_salience=min_salience, hours=hours)
    
    if not rows:
        console.print("No tweets found matching criteria.")
        return
    
    table = Table(title=f"Top {len(rows)} Tweets")
    table.add_column("Tweet ID", style="cyan")
    table.add_column("User", style="magenta")
    table.add_column("Category", style="yellow")
    table.add_column("Salience", justify="right", style="green")
    table.add_column("Text", style="white")
    
    for r in rows:
        table.add_row(
            r.get("tweet_id", "")[:12] + "...",
            r.get("author_username", "unknown"),
            r.get("category", "other"),
            f"{r.get('salience', 0):.1f}",
            (r.get("text", "")[:50] + "...") if len(r.get("text", "")) > 50 else r.get("text", ""),
        )
    
    console.print(table)


@app.command()
def export(
    ctx: typer.Context,
    output: str = typer.Option("export.csv", "--output", "-o", help="Output file path"),
    limit: int = typer.Option(1000, "--limit", "-n", help="Maximum items to export"),
    min_salience: float = typer.Option(0.0, "--min-salience", "-s", help="Minimum salience score"),
) -> None:
    """Export tweets to CSV."""
    import csv
    
    config_path = get_config_path(ctx)
    s = load_settings(config_path)
    rows = list_top(s.app.database_path, limit=limit, min_salience=min_salience)
    
    if not rows:
        console.print("No data to export.")
        return
    
    with open(output, "w", newline="", encoding="utf-8") as f:
        if not rows:
            return
        
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    
    console.print(f"Exported {len(rows)} tweets to {output}")


@app.command()
def stats(ctx: typer.Context) -> None:
    """Show database statistics."""
    config_path = get_config_path(ctx)
    s = load_settings(config_path)
    
    import sqlite3
    from datetime import datetime, timedelta, timezone
    
    conn = sqlite3.connect(s.app.database_path)
    
    # Basic counts
    total = conn.execute("SELECT COUNT(*) FROM tweets").fetchone()[0]
    analyzed = conn.execute("SELECT COUNT(*) FROM tweets WHERE category IS NOT NULL").fetchone()[0]
    scored = conn.execute("SELECT COUNT(*) FROM tweets WHERE salience IS NOT NULL").fetchone()[0]
    notified = conn.execute("SELECT COUNT(*) FROM tweets WHERE notified_at IS NOT NULL").fetchone()[0]
    
    # Recent activity
    day_ago = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat().replace("+00:00", "Z")
    recent = conn.execute("SELECT COUNT(*) FROM tweets WHERE created_at > ?", (day_ago,)).fetchone()[0]
    
    conn.close()
    
    console.print("📊 Database Statistics")
    console.print(f"  Total tweets:    {total}")
    console.print(f"  Analyzed:        {analyzed}")
    console.print(f"  Scored:          {scored}")
    console.print(f"  Notified:        {notified}")
    console.print(f"  Last 24h:        {recent}")
