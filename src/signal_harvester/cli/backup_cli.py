"""
CLI commands for database backup and recovery operations.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ..backup import BackupManager, BackupType, CompressionType, RetentionPolicy
from ..backup_scheduler import run_scheduler
from ..config import get_config
from ..logger import get_logger

log = get_logger(__name__)
console = Console()
app = typer.Typer(help="Database backup and recovery commands")


@app.command("create")
def create_backup(
    backup_type: str = typer.Option(
        "full",
        "--type",
        "-t",
        help="Backup type: full, incremental, wal",
    ),
    compression: str = typer.Option(
        None,
        "--compression",
        "-c",
        help="Compression type: none, gzip, zstd (default from config)",
    ),
    retention: str = typer.Option(
        None,
        "--retention",
        "-r",
        help="Retention policy: daily, weekly, monthly",
    ),
    upload: bool = typer.Option(
        False,
        "--upload",
        "-u",
        help="Upload to cloud storage after backup",
    ),
    verify: bool = typer.Option(
        True,
        "--verify/--no-verify",
        help="Verify backup after creation",
    ),
) -> None:
    """Create a database backup."""
    try:
        config = get_config()
        backup_config = config.app.backup
        
        if not backup_config.enabled:
            console.print("[yellow]Warning: Backup is disabled in configuration[/yellow]")
            return
        
        # Parse backup type
        try:
            btype = BackupType(backup_type.lower())
        except ValueError:
            console.print(f"[red]Error: Invalid backup type '{backup_type}'. Use: full, incremental, wal[/red]")
            raise typer.Exit(1)
        
        # Parse compression
        if compression:
            try:
                ctype = CompressionType(compression.lower())
            except ValueError:
                console.print(f"[red]Error: Invalid compression type '{compression}'. Use: none, gzip, zstd[/red]")
                raise typer.Exit(1)
        else:
            ctype = CompressionType(backup_config.compression)
        
        # Parse retention policy
        rpolicy = None
        if retention:
            try:
                rpolicy = RetentionPolicy(retention.lower())
            except ValueError:
                console.print(f"[red]Error: Invalid retention policy '{retention}'. Use: daily, weekly, monthly[/red]")
                raise typer.Exit(1)
        
        # Initialize backup manager
        manager = BackupManager(
            db_path=config.app.database_path,
            backup_dir=backup_config.backup_dir,
            compression=ctype,
            retention_days=backup_config.retention_days,
        )
        
        # Create backup
        console.print(f"[blue]Creating {btype.value} backup...[/blue]")
        backup_metadata = manager.create_backup(
            backup_type=btype,
            compression=ctype,
            retention_policy=rpolicy,
        )
        
        # Verify if requested
        if verify and backup_config.verification.verify_after_backup:
            console.print("[blue]Verifying backup...[/blue]")
            if manager.verify_backup(backup_metadata):
                console.print("[green]✓ Backup verified successfully[/green]")
            else:
                console.print("[red]✗ Backup verification failed[/red]")
                raise typer.Exit(1)
        
        # Upload to cloud if requested
        if upload and backup_config.s3.enabled:
            console.print("[blue]Uploading to S3...[/blue]")
            success = manager.upload_to_s3(
                backup_metadata,
                bucket=backup_config.s3.bucket,
                prefix=backup_config.s3.prefix,
                region=backup_config.s3.region,
            )
            if success:
                console.print(f"[green]✓ Uploaded to {backup_metadata.cloud_url}[/green]")
            else:
                console.print("[red]✗ Upload failed[/red]")
        
        # Display summary
        size_mb = backup_metadata.size_bytes / 1024 / 1024
        console.print("\n[green]Backup created successfully![/green]")
        console.print(f"  ID: {backup_metadata.backup_id}")
        console.print(f"  Type: {backup_metadata.backup_type.value}")
        console.print(f"  Size: {size_mb:.2f} MB")
        console.print(f"  Path: {backup_metadata.backup_path}")
        console.print(f"  Checksum: {backup_metadata.checksum[:16]}...")
        if backup_metadata.cloud_url:
            console.print(f"  Cloud: {backup_metadata.cloud_url}")
    
    except Exception as e:
        console.print(f"[red]Error creating backup: {e}[/red]")
        log.exception("Backup creation failed")
        raise typer.Exit(1)


@app.command("list")
def list_backups(
    backup_type: Optional[str] = typer.Option(
        None,
        "--type",
        "-t",
        help="Filter by backup type: full, incremental, wal",
    ),
    retention: Optional[str] = typer.Option(
        None,
        "--retention",
        "-r",
        help="Filter by retention policy: daily, weekly, monthly",
    ),
    verified_only: bool = typer.Option(
        False,
        "--verified",
        "-v",
        help="Show only verified backups",
    ),
    limit: int = typer.Option(
        20,
        "--limit",
        "-l",
        help="Maximum number of backups to show",
    ),
) -> None:
    """List available backups."""
    try:
        config = get_config()
        backup_config = config.app.backup
        
        # Parse filters
        btype = None
        if backup_type:
            try:
                btype = BackupType(backup_type.lower())
            except ValueError:
                console.print(f"[red]Error: Invalid backup type '{backup_type}'[/red]")
                raise typer.Exit(1)
        
        rpolicy = None
        if retention:
            try:
                rpolicy = RetentionPolicy(retention.lower())
            except ValueError:
                console.print(f"[red]Error: Invalid retention policy '{retention}'[/red]")
                raise typer.Exit(1)
        
        # Initialize backup manager
        manager = BackupManager(
            db_path=config.app.database_path,
            backup_dir=backup_config.backup_dir,
        )
        
        # List backups
        backups = manager.list_backups(
            backup_type=btype,
            retention_policy=rpolicy,
            verified_only=verified_only,
        )
        
        if not backups:
            console.print("[yellow]No backups found[/yellow]")
            return
        
        # Create table
        table = Table(title=f"Database Backups ({len(backups)} total)")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Type", style="magenta")
        table.add_column("Timestamp", style="green")
        table.add_column("Size", justify="right", style="yellow")
        table.add_column("Verified", justify="center")
        table.add_column("Cloud", style="blue")
        table.add_column("Retention")
        
        # Add rows
        for backup in backups[:limit]:
            size_mb = backup.size_bytes / 1024 / 1024
            verified_icon = "✓" if backup.verified else "✗"
            cloud_icon = "☁" if backup.cloud_url else "—"
            retention_str = backup.retention_policy.value if backup.retention_policy else "—"
            
            table.add_row(
                backup.backup_id,
                backup.backup_type.value,
                backup.timestamp.strftime("%Y-%m-%d %H:%M"),
                f"{size_mb:.1f} MB",
                verified_icon,
                cloud_icon,
                retention_str,
            )
        
        console.print(table)
        
        if len(backups) > limit:
            console.print(f"\n[dim]Showing {limit} of {len(backups)} backups. Use --limit to see more.[/dim]")
    
    except Exception as e:
        console.print(f"[red]Error listing backups: {e}[/red]")
        log.exception("Backup listing failed")
        raise typer.Exit(1)


@app.command("restore")
def restore_backup(
    backup_id: str = typer.Argument(..., help="Backup ID to restore"),
    target: Optional[str] = typer.Option(
        None,
        "--target",
        "-t",
        help="Target path for restored database (default: original database path)",
    ),
    verify: bool = typer.Option(
        True,
        "--verify/--no-verify",
        help="Verify backup before restoring",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force restore without confirmation",
    ),
) -> None:
    """Restore database from backup."""
    try:
        config = get_config()
        backup_config = config.app.backup
        
        # Initialize backup manager
        manager = BackupManager(
            db_path=config.app.database_path,
            backup_dir=backup_config.backup_dir,
        )
        
        # Get backup metadata
        backup_metadata = manager.get_backup(backup_id)
        if not backup_metadata:
            console.print(f"[red]Error: Backup '{backup_id}' not found[/red]")
            raise typer.Exit(1)
        
        # Determine target path
        target_path = Path(target) if target else Path(config.app.database_path)
        
        # Confirm restore
        if not force:
            size_mb = backup_metadata.size_bytes / 1024 / 1024
            console.print(f"\n[yellow]You are about to restore:[/yellow]")
            console.print(f"  Backup ID: {backup_metadata.backup_id}")
            console.print(f"  Type: {backup_metadata.backup_type.value}")
            console.print(f"  Timestamp: {backup_metadata.timestamp}")
            console.print(f"  Size: {size_mb:.2f} MB")
            console.print(f"  Target: {target_path}")
            
            if target_path.exists():
                console.print(f"\n[red]Warning: This will overwrite the existing database at {target_path}[/red]")
                console.print(f"[red]A backup of the current database will be created.[/red]")
            
            confirm = typer.confirm("\nDo you want to continue?")
            if not confirm:
                console.print("[yellow]Restore cancelled[/yellow]")
                return
        
        # Restore backup
        console.print("[blue]Restoring backup...[/blue]")
        success = manager.restore_backup(
            backup_metadata,
            target_path=target_path,
            verify=verify and backup_config.verification.verify_before_restore,
        )
        
        if success:
            console.print(f"[green]✓ Database restored successfully to {target_path}[/green]")
        else:
            console.print("[red]✗ Restore failed[/red]")
            raise typer.Exit(1)
    
    except Exception as e:
        console.print(f"[red]Error restoring backup: {e}[/red]")
        log.exception("Backup restore failed")
        raise typer.Exit(1)


@app.command("verify")
def verify_backup_cmd(
    backup_id: str = typer.Argument(..., help="Backup ID to verify"),
) -> None:
    """Verify backup integrity."""
    try:
        config = get_config()
        backup_config = config.app.backup
        
        # Initialize backup manager
        manager = BackupManager(
            db_path=config.app.database_path,
            backup_dir=backup_config.backup_dir,
        )
        
        # Get backup metadata
        backup_metadata = manager.get_backup(backup_id)
        if not backup_metadata:
            console.print(f"[red]Error: Backup '{backup_id}' not found[/red]")
            raise typer.Exit(1)
        
        # Verify backup
        console.print(f"[blue]Verifying backup {backup_id}...[/blue]")
        if manager.verify_backup(backup_metadata):
            console.print("[green]✓ Backup verified successfully[/green]")
        else:
            console.print("[red]✗ Backup verification failed[/red]")
            raise typer.Exit(1)
    
    except Exception as e:
        console.print(f"[red]Error verifying backup: {e}[/red]")
        log.exception("Backup verification failed")
        raise typer.Exit(1)


@app.command("delete")
def delete_backup_cmd(
    backup_id: str = typer.Argument(..., help="Backup ID to delete"),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force delete without confirmation",
    ),
) -> None:
    """Delete a backup."""
    try:
        config = get_config()
        backup_config = config.app.backup
        
        # Initialize backup manager
        manager = BackupManager(
            db_path=config.app.database_path,
            backup_dir=backup_config.backup_dir,
        )
        
        # Get backup metadata
        backup_metadata = manager.get_backup(backup_id)
        if not backup_metadata:
            console.print(f"[red]Error: Backup '{backup_id}' not found[/red]")
            raise typer.Exit(1)
        
        # Confirm delete
        if not force:
            size_mb = backup_metadata.size_bytes / 1024 / 1024
            console.print(f"\n[yellow]You are about to delete:[/yellow]")
            console.print(f"  Backup ID: {backup_metadata.backup_id}")
            console.print(f"  Type: {backup_metadata.backup_type.value}")
            console.print(f"  Timestamp: {backup_metadata.timestamp}")
            console.print(f"  Size: {size_mb:.2f} MB")
            
            confirm = typer.confirm("\nDo you want to continue?")
            if not confirm:
                console.print("[yellow]Delete cancelled[/yellow]")
                return
        
        # Delete backup
        if manager.delete_backup(backup_id):
            console.print(f"[green]✓ Backup {backup_id} deleted[/green]")
        else:
            console.print("[red]✗ Delete failed[/red]")
            raise typer.Exit(1)
    
    except Exception as e:
        console.print(f"[red]Error deleting backup: {e}[/red]")
        log.exception("Backup deletion failed")
        raise typer.Exit(1)


@app.command("prune")
def prune_backups(
    daily_keep: Optional[int] = typer.Option(
        None,
        "--daily-keep",
        help="Number of daily backups to keep (default from config)",
    ),
    weekly_keep: Optional[int] = typer.Option(
        None,
        "--weekly-keep",
        help="Number of weekly backups to keep (default from config)",
    ),
    monthly_keep: Optional[int] = typer.Option(
        None,
        "--monthly-keep",
        help="Number of monthly backups to keep (default from config)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be deleted without actually deleting",
    ),
) -> None:
    """Prune old backups according to retention policy."""
    try:
        config = get_config()
        backup_config = config.app.backup
        
        # Use config defaults if not specified
        daily = daily_keep if daily_keep is not None else backup_config.retention.daily_keep
        weekly = weekly_keep if weekly_keep is not None else backup_config.retention.weekly_keep
        monthly = monthly_keep if monthly_keep is not None else backup_config.retention.monthly_keep
        
        # Initialize backup manager
        manager = BackupManager(
            db_path=config.app.database_path,
            backup_dir=backup_config.backup_dir,
            retention_days=backup_config.retention_days,
        )
        
        # Prune backups
        console.print(f"[blue]Pruning backups (daily: {daily}, weekly: {weekly}, monthly: {monthly})...[/blue]")
        if dry_run:
            console.print("[yellow]DRY RUN - No backups will be deleted[/yellow]")
        
        deleted = manager.enforce_retention_policy(
            daily_keep=daily,
            weekly_keep=weekly,
            monthly_keep=monthly,
            dry_run=dry_run,
        )
        
        if deleted:
            console.print(f"\n[green]{'Would delete' if dry_run else 'Deleted'} {len(deleted)} backup(s):[/green]")
            for backup_id in deleted:
                console.print(f"  • {backup_id}")
        else:
            console.print("[green]No backups to prune[/green]")
    
    except Exception as e:
        console.print(f"[red]Error pruning backups: {e}[/red]")
        log.exception("Backup pruning failed")
        raise typer.Exit(1)


@app.command("upload")
def upload_backup(
    backup_id: str = typer.Argument(..., help="Backup ID to upload"),
    provider: str = typer.Option(
        "s3",
        "--provider",
        "-p",
        help="Cloud provider: s3, gcs, azure",
    ),
) -> None:
    """Upload backup to cloud storage."""
    try:
        config = get_config()
        backup_config = config.app.backup
        
        # Initialize backup manager
        manager = BackupManager(
            db_path=config.app.database_path,
            backup_dir=backup_config.backup_dir,
        )
        
        # Get backup metadata
        backup_metadata = manager.get_backup(backup_id)
        if not backup_metadata:
            console.print(f"[red]Error: Backup '{backup_id}' not found[/red]")
            raise typer.Exit(1)
        
        # Upload based on provider
        if provider == "s3":
            if not backup_config.s3.enabled:
                console.print("[red]Error: S3 upload not enabled in configuration[/red]")
                raise typer.Exit(1)
            
            console.print(f"[blue]Uploading to S3 bucket '{backup_config.s3.bucket}'...[/blue]")
            success = manager.upload_to_s3(
                backup_metadata,
                bucket=backup_config.s3.bucket,
                prefix=backup_config.s3.prefix,
                region=backup_config.s3.region,
            )
            if success:
                console.print(f"[green]✓ Uploaded to {backup_metadata.cloud_url}[/green]")
            else:
                console.print("[red]✗ Upload failed[/red]")
                raise typer.Exit(1)
        
        elif provider == "gcs":
            console.print("[yellow]GCS upload not yet implemented[/yellow]")
            raise typer.Exit(1)
        
        elif provider == "azure":
            console.print("[yellow]Azure upload not yet implemented[/yellow]")
            raise typer.Exit(1)
        
        else:
            console.print(f"[red]Error: Unknown provider '{provider}'. Use: s3, gcs, azure[/red]")
            raise typer.Exit(1)
    
    except Exception as e:
        console.print(f"[red]Error uploading backup: {e}[/red]")
        log.exception("Backup upload failed")
        raise typer.Exit(1)


@app.command("scheduler")
def run_backup_scheduler() -> None:
    """Run automated backup scheduler service.
    
    This runs a long-running service that performs scheduled backups
    based on the configuration in settings.yaml. The scheduler will:
    
    - Create daily backups at the configured time
    - Create weekly backups at the configured day/time
    - Create monthly backups at the configured day/time
    - Automatically verify backups after creation
    - Automatically upload to cloud storage (if enabled)
    - Enforce retention policies to clean up old backups
    
    The scheduler runs until interrupted with Ctrl+C or SIGTERM.
    
    Example usage:
        harvest backup scheduler
        
    To run as a systemd service, see docs/BACKUP_RECOVERY.md
    """
    try:
        config = get_config()
        backup_config = config.app.backup
        
        if not backup_config.enabled:
            console.print("[red]Error: Backup is disabled in configuration[/red]")
            console.print("[yellow]Enable backup in config/settings.yaml: app.backup.enabled = true[/yellow]")
            raise typer.Exit(1)
        
        # Display configuration
        console.print("\n[bold cyan]Backup Scheduler Configuration[/bold cyan]")
        console.print(f"  Database: {config.app.database_path}")
        console.print(f"  Backup Directory: {backup_config.backup_dir}")
        console.print(f"  Compression: {backup_config.compression}")
        console.print(f"  Retention Days: {backup_config.retention_days}")
        
        console.print("\n[bold cyan]Schedule[/bold cyan]")
        console.print(f"  Daily: {backup_config.schedule.daily_hour:02d}:{backup_config.schedule.daily_minute:02d} UTC")
        console.print(f"  Weekly: {backup_config.schedule.weekly_day} {backup_config.schedule.weekly_hour:02d}:{backup_config.schedule.weekly_minute:02d} UTC")
        console.print(f"  Monthly: Day {backup_config.schedule.monthly_day} {backup_config.schedule.monthly_hour:02d}:{backup_config.schedule.monthly_minute:02d} UTC")
        
        console.print("\n[bold cyan]Retention[/bold cyan]")
        console.print(f"  Daily: Keep {backup_config.retention.daily_keep} backups")
        console.print(f"  Weekly: Keep {backup_config.retention.weekly_keep} backups")
        console.print(f"  Monthly: Keep {backup_config.retention.monthly_keep} backups")
        
        console.print("\n[bold cyan]Cloud Storage[/bold cyan]")
        if backup_config.s3.enabled:
            console.print(f"  S3: ✓ {backup_config.s3.bucket}/{backup_config.s3.prefix}")
        else:
            console.print("  S3: ✗ Disabled")
        
        if backup_config.gcs.enabled:
            console.print(f"  GCS: ✓ {backup_config.gcs.bucket}/{backup_config.gcs.prefix}")
        else:
            console.print("  GCS: ✗ Disabled")
        
        if backup_config.azure.enabled:
            console.print(f"  Azure: ✓ {backup_config.azure.account_name}/{backup_config.azure.container}/{backup_config.azure.prefix}")
        else:
            console.print("  Azure: ✗ Disabled")
        
        console.print("\n[green]Starting backup scheduler...[/green]")
        console.print("[dim]Press Ctrl+C to stop[/dim]\n")
        
        # Run scheduler
        run_scheduler()
    
    except KeyboardInterrupt:
        console.print("\n[yellow]Scheduler stopped by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error running scheduler: {e}[/red]")
        log.exception("Backup scheduler failed")
        raise typer.Exit(1)
