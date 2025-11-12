from __future__ import annotations

from typing import Sequence

import typer
from rich.table import Table

from ..phase_two import PHASE_TWO_TASKS

phase_two_app = typer.Typer(help="Commands for Phase Two roadmap tracking")


def build_phase_two_rows() -> Sequence[tuple[str, str, str, str]]:
    """Return rows describing each Phase Two task for display or testing."""

    sorted_tasks = sorted(PHASE_TWO_TASKS, key=lambda task: task.priority)
    return [
        (
            str(task.priority),
            task.surface.value,
            task.status,
            task.summary,
        )
        for task in sorted_tasks
    ]


@phase_two_app.command("status")
def phase_two_status() -> None:
    """Show current Phase Two surfaces, priority, and status."""

    table = Table(title="Phase Two Roadmap", show_lines=True)
    table.add_column("Priority", justify="right")
    table.add_column("Surface", justify="left")
    table.add_column("Status", justify="center")
    table.add_column("Summary", justify="left")

    for row in build_phase_two_rows():
        table.add_row(*row)

    typer.echo(table)
