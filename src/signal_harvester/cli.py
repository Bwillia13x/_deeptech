from __future__ import annotations

import os

import typer
import uvicorn

from .api import create_app
from .cli.core import app
from .logger import get_logger

log = get_logger(__name__)


# Additional commands that haven't been refactored yet
@app.command()
def verify():
    """Verify data integrity."""
    from .verify import main as verify_main
    raise typer.Exit(verify_main())


@app.command()
def site():
    """Build static site."""
    from .config import load_settings
    from .site import build_all
    
    load_settings(None)
    build_all(
        base_dir=".",
        base_url=os.getenv("SITE_BASE_URL", "http://localhost:8000"),
        write_robots=True,
        write_sitemap=True,
        write_latest=True,
        write_feeds=True,
    )


@app.command()
def html():
    """Build HTML pages."""
    from .html import main as html_main
    raise typer.Exit(html_main())


@app.command()
def serve():
    """Serve static files."""
    from .serve import main as serve_main
    raise typer.Exit(serve_main())


@app.command()
def daemon(
    interval: int = typer.Option(300, "--interval", "-i", help="Run pipeline every N seconds"),
):
    """Run pipeline in daemon mode."""
    import time

    from .config import load_settings
    from .pipeline import run_pipeline
    
    s = load_settings(None)
    typer.echo(f"Starting daemon (interval: {interval}s)...")
    
    try:
        while True:
            stats = run_pipeline(s)
            typer.echo(f"Pipeline run: {stats}")
            time.sleep(interval)
    except KeyboardInterrupt:
        typer.echo("Daemon stopped")


@app.command()
def api(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind to"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to settings.yaml"),
):
    """Run the API server."""
    uvicorn.run(create_app(settings_path=config), host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
