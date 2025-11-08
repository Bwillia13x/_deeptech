"""Core CLI application and shared utilities."""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ..logger import get_logger

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()
log = get_logger(__name__)


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


def get_config_path(ctx: typer.Context) -> str | None:
    """Get config path from context."""
    return ctx.obj.get("config") if ctx.obj else None


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
    from ..beta import list_beta_users, get_beta_stats
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
