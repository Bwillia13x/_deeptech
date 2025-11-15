"""Core CLI application and shared utilities."""

from __future__ import annotations

import os
from typing import Optional

import typer
from click import get_current_context
from rich.console import Console
from rich.table import Table

from ..logger import get_logger
from ..postgres_validation import (
    DEFAULT_DATABASE_URL,
    obfuscate_password,
    run_postgres_validation,
)
from .backup_cli import app as backup_app
from .db_commands import db_app
from .phase_two_commands import phase_two_app

quality_app = typer.Typer(help="Quality assurance commands")
app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(quality_app, name="quality")
app.add_typer(phase_two_app, name="phase-two")
app.add_typer(db_app, name="db")
app.add_typer(backup_app, name="backup")
console = Console()
log = get_logger(__name__)

# Import sub-command modules after app is created to avoid circular imports
def _register_commands() -> None:
    from .quality_commands import (
        add_review_item,
        compute_quality_score,
        get_audit_log,
        get_quality_metrics,
        get_review_queue,
        initialize_quality_system,
        process_review,
        run_full_quality_check,
        run_validation,
    )

    quality_app.command("run-validation")(run_validation)
    quality_app.command("compute-score")(compute_quality_score)
    quality_app.command("full-check")(run_full_quality_check)
    quality_app.command("review-queue")(get_review_queue)
    quality_app.command("process-review")(process_review)
    quality_app.command("add-review")(add_review_item)
    quality_app.command("audit-log")(get_audit_log)
    quality_app.command("metrics")(get_quality_metrics)
    quality_app.command("initialize")(initialize_quality_system)


# Register commands when module is loaded
_register_commands()


@app.callback()
def main(
    ctx: typer.Context,
    config: str = typer.Option(None, "--config", "-c", help="Path to settings.yaml"),
    log_level: str = typer.Option(None, "--log-level", help="Log level (DEBUG, INFO, WARNING, ERROR)"),
) -> None:
    """Signal Harvester - Collect and analyze social signals from X (Twitter)."""
    from ..logger import configure_logging
    
    configure_logging(level=log_level)
    ctx.obj = {"config": config}


def get_config_path(ctx: typer.Context | None = None) -> str | None:
    """Get config path from context."""
    context = ctx or get_current_context(silent=True)
    return context.obj.get("config") if context and context.obj else None


@app.command("beta-invite")
def beta_invite(
    ctx: typer.Context,
    email: str = typer.Argument(..., help="Email address to invite"),
    name: Optional[str] = typer.Option(None, "--name", help="User name"),
) -> None:
    """Create a beta invite for a user."""
    from ..beta import create_beta_user
    from ..config import load_settings
    
    try:
        config_path = get_config_path(ctx)
        s = load_settings(config_path)
        user = create_beta_user(s.app.database_path, email, metadata={"name": name} if name else {})
        console.print(f"✅ Created beta invite for {email}")
        console.print(f"Invite code: {user.invite_code}")
        console.print(f"Status: {user.status}")
    except Exception as e:
        console.print(f"❌ Failed to create invite: {e}")
        raise typer.Exit(1)


@app.command("beta-list")
def beta_list(
    ctx: typer.Context,
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status (pending, active, expired)"),
) -> None:
    """List beta users."""
    from ..beta import get_beta_stats, list_beta_users
    from ..config import load_settings
    
    config_path = get_config_path(ctx)
    s = load_settings(config_path)
    
    # Show stats first
    stats = get_beta_stats(s.app.database_path)
    console.print(f"📊 Beta Users: {stats['total']} total")
    console.print(f"   Pending: {stats['pending']} | Active: {stats['active']} | Expired: {stats['expired']}")
    console.print()
    
    # List users
    users = list_beta_users(s.app.database_path, status)
    
    if not users:
        console.print("No beta users found")
        return
        
    table = Table(title="Beta Users")
    table.add_column("Email", style="cyan", no_wrap=True)
    table.add_column("Status", style="green")
    table.add_column("Created", style="yellow")
    table.add_column("Activated", style="magenta")
    table.add_column("Invite Code", style="dim")
    
    for user in users:
        table.add_row(
            user.email,
            user.status,
            user.created_at.strftime("%Y-%m-%d %H:%M"),
            user.activated_at.strftime("%Y-%m-%d %H:%M") if user.activated_at else "-",
            user.invite_code[:16] + "...",  # Truncate for display
        )
    
    console.print(table)


@app.command("beta-activate")
def beta_activate(
    ctx: typer.Context,
    invite_code: str = typer.Argument(..., help="Invite code to activate"),
) -> None:
    """Activate a beta user by invite code."""
    from ..beta import activate_beta_user
    from ..config import load_settings
    
    config_path = get_config_path(ctx)
    s = load_settings(config_path)
    
    if activate_beta_user(s.app.database_path, invite_code):
        console.print(f"✅ Activated invite: {invite_code}")
    else:
        console.print(f"❌ Failed to activate invite: {invite_code}")
        console.print("Check that the invite code is valid and not already activated")
        raise typer.Exit(1)


@app.command("beta-stats")
def beta_stats(ctx: typer.Context) -> None:
    """Show beta program statistics."""
    from ..beta import get_beta_stats
    from ..config import load_settings
    
    config_path = get_config_path(ctx)
    s = load_settings(config_path)
    stats = get_beta_stats(s.app.database_path)
    
    table = Table(title="Beta Program Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", style="green")
    
    table.add_row("Total Users", str(stats['total']))
    table.add_row("Pending Invites", str(stats['pending']))
    table.add_row("Active Users", str(stats['active']))
    table.add_row("Expired Invites", str(stats['expired']))
    
    if stats['total'] > 0:
        activation_rate = (stats['active'] / stats['total']) * 100
        table.add_row("Activation Rate", f"{activation_rate:.1f}%")
    
    console.print(table)


@app.command("verify-postgres")
def verify_postgres(
    ctx: typer.Context,
    database_url: Optional[str] = typer.Option(
        None,
        "--database-url",
        "-d",
        help="PostgreSQL DSN to validate (defaults to DATABASE_URL env or local fallback)",
    ),
    show_tables: bool = typer.Option(
        True,
        "--show-tables/--hide-tables",
        help="Display the discovered table list",
    ),
    show_row_counts: bool = typer.Option(
        True,
        "--show-row-counts/--hide-row-counts",
        help="Display row counts for key tables",
    ),
) -> None:
    """Validate the PostgreSQL deployment used for remote rehearsals."""

    _ = ctx  # currently unused but kept for future config wiring
    url = database_url or os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL

    console.rule("PostgreSQL Schema Validation")
    console.print(f"Using DSN: {obfuscate_password(url)}")
    result = run_postgres_validation(url)

    if result.error or not result.connected:
        console.print(f"[red]✗ Validation failed:[/red] {result.error or 'Unable to connect'}")
        raise typer.Exit(1)

    if result.version_string:
        console.print(f"✓ Connected to PostgreSQL: {result.version_string[:60]}...")

    if show_tables:
        table = Table(title="Tables", show_lines=False)
        table.add_column("Name", style="cyan")
        for table_name in result.tables:
            table.add_row(table_name)
        console.print(table)

    if result.missing_tables:
        console.print(f"[red]✗ Missing tables:[/red] {', '.join(result.missing_tables)}")
        raise typer.Exit(1)

    if result.type_mismatches:
        console.print("[red]✗ Column type mismatches detected:[/red]")
        for mismatch in result.type_mismatches:
            console.print(f"  - {mismatch}")
        raise typer.Exit(1)

    console.print(f"\n✓ Found {result.artifacts_index_count} indexes on artifacts table")

    if show_row_counts and result.row_counts:
        counts_table = Table(title="Row Counts", show_lines=False)
        counts_table.add_column("Table")
        counts_table.add_column("Rows", justify="right")
        for name, count in sorted(result.row_counts.items()):
            counts_table.add_row(name, str(count))
        console.print(counts_table)

    if result.schema_version is None:
        console.print("[red]✗ schema_version table is empty or missing[/red]")
        raise typer.Exit(1)

    console.print(f"\n✓ Schema version: {result.schema_version}")
    console.rule("PostgreSQL Migration Validation: SUCCESS")
