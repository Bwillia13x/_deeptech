"""Snapshot and retention CLI commands."""

from __future__ import annotations

import typer

from ..prune import main as prune_main
from ..quota import main as quota_main
from ..retain import main as retain_main
from ..snapshot_cli import main as snapshot_main
from .core import app


@app.command()
def snapshot(
    base_dir: str = typer.Option("./snapshots", "--base-dir", help="Base directory for snapshots"),
    src: str = typer.Option("data.json", "--src", help="Source data file"),
    keep: int = typer.Option(10, "--keep", help="Number of snapshots to keep"),
    gzip_copy: bool = typer.Option(True, "--gzip", help="Compress snapshot"),
    generate_diff: bool = typer.Option(True, "--diff", help="Generate diff from previous"),
    write_ndjson: bool = typer.Option(False, "--ndjson", help="Write newline-delimited JSON"),
    write_csv: bool = typer.Option(False, "--csv", help="Write CSV"),
    write_checksums: bool = typer.Option(True, "--checksums", help="Write checksums file"),
) -> None:
    """Create a snapshot of current data."""
    argv = [
        "--base-dir", base_dir,
        "--src", src,
        "--keep", str(keep),
    ]
    if gzip_copy:
        argv.append("--gzip")
    if generate_diff:
        argv.append("--diff")
    if write_ndjson:
        argv.append("--ndjson")
    if write_csv:
        argv.append("--csv")
    if write_checksums:
        argv.append("--checksums")
    
    exit_code = snapshot_main(argv)
    if exit_code != 0:
        raise typer.Exit(exit_code)


@app.command()
def prune(
    base_dir: str = typer.Option(..., "--base-dir", help="Snapshots base directory"),
    keep: int = typer.Option(..., "--keep", help="Number of snapshots to keep"),
    dry_run: bool = typer.Option(True, "--dry-run", help="Show what would be deleted"),
    force: bool = typer.Option(False, "--force", help="Apply changes"),
    rebuild_site: bool = typer.Option(False, "--rebuild-site", help="Rebuild site index after pruning"),
    rebuild_html: bool = typer.Option(False, "--rebuild-html", help="Rebuild HTML after pruning"),
) -> None:
    """Prune snapshots to keep only N most recent."""
    argv = [
        "--base-dir", base_dir,
        "--keep", str(keep),
    ]
    if not force:
        argv.append("--dry-run")
    if rebuild_site:
        argv.append("--rebuild-site")
    if rebuild_html:
        argv.append("--rebuild-html")
    
    exit_code = prune_main(argv)
    if exit_code != 0:
        raise typer.Exit(exit_code)


@app.command()
def retain(
    base_dir: str = typer.Option(..., "--base-dir", help="Snapshots base directory"),
    keep_age: str | None = typer.Option(None, "--keep-age", help="Keep snapshots newer than age (e.g., 30d, 12h)"),
    keep_hourly: int = typer.Option(0, "--keep-hourly", help="Keep N hourly snapshots"),
    keep_daily: int = typer.Option(0, "--keep-daily", help="Keep N daily snapshots"),
    keep_weekly: int = typer.Option(0, "--keep-weekly", help="Keep N weekly snapshots"),
    keep_monthly: int = typer.Option(0, "--keep-monthly", help="Keep N monthly snapshots"),
    keep_yearly: int = typer.Option(0, "--keep-yearly", help="Keep N yearly snapshots"),
    force: bool = typer.Option(False, "--force", help="Apply changes"),
    rebuild_site: bool = typer.Option(False, "--rebuild-site", help="Rebuild site index"),
    rebuild_html: bool = typer.Option(False, "--rebuild-html", help="Rebuild HTML"),
) -> None:
    """Retain snapshots based on calendar/age policies."""
    # Validate at least one policy provided
    if not (keep_age or any(x > 0 for x in (keep_hourly, keep_daily, keep_weekly, keep_monthly, keep_yearly))):
        raise typer.BadParameter("must provide keep-age and/or at least one retention policy")
    
    argv = ["--base-dir", base_dir]
    if keep_age:
        argv.extend(["--keep-age", keep_age])
    if keep_hourly > 0:
        argv.extend(["--keep-hourly", str(keep_hourly)])
    if keep_daily > 0:
        argv.extend(["--keep-daily", str(keep_daily)])
    if keep_weekly > 0:
        argv.extend(["--keep-weekly", str(keep_weekly)])
    if keep_monthly > 0:
        argv.extend(["--keep-monthly", str(keep_monthly)])
    if keep_yearly > 0:
        argv.extend(["--keep-yearly", str(keep_yearly)])
    if not force:
        pass  # dry-run is default
    if force:
        argv.append("--force")
    if rebuild_site:
        argv.append("--rebuild-site")
    if rebuild_html:
        argv.append("--rebuild-html")
    
    exit_code = retain_main(argv)
    if exit_code != 0:
        raise typer.Exit(exit_code)


@app.command()
def quota(
    base_dir: str = typer.Option(..., "--base-dir", help="Snapshots base directory"),
    max_bytes: str | None = typer.Option(None, "--max-bytes", help="Maximum total size (e.g., 10GB, 500MB)"),
    max_files: int | None = typer.Option(None, "--max-files", help="Maximum number of files"),
    keep_min: int = typer.Option(0, "--keep-min", help="Minimum snapshots to keep"),
    force: bool = typer.Option(False, "--force", help="Apply changes"),
) -> None:
    """Enforce quota on snapshots."""
    argv = ["--base-dir", base_dir]
    if max_bytes:
        argv.extend(["--max-bytes", max_bytes])
    if max_files is not None:
        argv.extend(["--max-files", str(max_files)])
    if keep_min > 0:
        argv.extend(["--keep-min", str(keep_min)])
    if not force:
        pass  # dry-run is default
    if force:
        argv.append("--force")
    
    exit_code = quota_main(argv)
    if exit_code != 0:
        raise typer.Exit(exit_code)
