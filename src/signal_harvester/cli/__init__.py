"""CLI commands for Signal Harvester."""

# These imports register CLI commands with the app via decorators
from . import (  # noqa: F401
    backup_cli,
    db_commands,
    data_commands,
    discovery_commands,
    pipeline_commands,
    researcher_commands,  # Phase 2.3
    security_commands,  # Phase 3 Week 4
    snapshot_commands,
)
from .core import app


def main() -> None:
    """Console entry point for the Signal Harvester CLI."""
    app()


__all__ = ["app", "main"]
