"""Pipeline-related CLI commands."""

from __future__ import annotations

import typer

from ..config import load_settings
from ..db import init_db
from ..pipeline import analyze_unanalyzed, fetch_once, notify_high_salience, run_pipeline, score_unscored
from .core import app, console, get_config_path


@app.command()
def init_db_cmd(ctx: typer.Context) -> None:
    """Initialize the database."""
    config_path = get_config_path(ctx)
    s = load_settings(config_path)
    init_db(s.app.database_path)
    console.print(f"Initialized DB at {s.app.database_path}")


@app.command()
def fetch(ctx: typer.Context) -> None:
    """Fetch tweets from X/Twitter."""
    config_path = get_config_path(ctx)
    s = load_settings(config_path)
    stats = fetch_once(s)
    console.print(f"Fetch: {stats}")


@app.command()
def analyze(
    ctx: typer.Context,
    limit: int = typer.Option(200, "--limit", "-n", help="Max unanalyzed items to process"),
) -> None:
    """Analyze unanalyzed tweets."""
    config_path = get_config_path(ctx)
    s = load_settings(config_path)
    count = analyze_unanalyzed(s, limit=limit)
    console.print(f"Analyzed {count} items")


@app.command()
def score(
    ctx: typer.Context,
    limit: int = typer.Option(500, "--limit", "-n", help="Max unscored items to process"),
) -> None:
    """Score unscored tweets."""
    config_path = get_config_path(ctx)
    s = load_settings(config_path)
    count = score_unscored(s, limit=limit)
    console.print(f"Scored {count} items")


@app.command()
def notify(
    ctx: typer.Context,
    threshold: float = typer.Option(80.0, "--threshold", "-t", help="Min salience to notify"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max notifications to send"),
    hours: int | None = typer.Option(None, "--hours", help="Only notify items within last N hours"),
) -> None:
    """Send notifications for high-salience tweets."""
    config_path = get_config_path(ctx)
    s = load_settings(config_path)
    sent = notify_high_salience(s, threshold=threshold, limit=limit, hours=hours)
    console.print(f"Sent {sent} notifications")


@app.command()
def pipeline(
    ctx: typer.Context,
    notify_threshold: float | None = typer.Option(None, "--notify-threshold", "-t", help="Min salience to notify"),
    notify_limit: int = typer.Option(10, "--notify-limit", "-n", help="Max notifications to send"),
    notify_hours: int | None = typer.Option(None, "--notify-hours", help="Only notify items within last N hours"),
) -> None:
    """Run the complete pipeline (fetch → analyze → score → notify)."""
    config_path = get_config_path(ctx)
    s = load_settings(config_path)
    stats = run_pipeline(
        s,
        notify_threshold=notify_threshold,
        notify_limit=notify_limit,
        notify_hours=notify_hours,
    )
    console.print(f"Pipeline: {stats}")


@app.command()
def migrate(
    ctx: typer.Context,
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what migrations would be applied"),
) -> None:
    """Run database migrations."""
    from ..db import run_migrations
    
    config_path = get_config_path(ctx)
    s = load_settings(config_path)
    
    if dry_run:
        console.print("[yellow]Dry run mode - showing pending migrations:[/yellow]")
    else:
        console.print(f"Running migrations on {s.app.database_path}...")
        try:
            run_migrations(s.app.database_path)
            console.print("[green]Migrations completed successfully![/green]")
        except Exception as e:
            console.print(f"[red]Migration failed: {e}[/red]")
            raise typer.Exit(1)
