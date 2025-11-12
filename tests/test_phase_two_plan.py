from __future__ import annotations

from signal_harvester.cli.phase_two_commands import build_phase_two_rows
from signal_harvester.phase_two import PHASE_TWO_TASKS, PhaseTwoSurface


def test_phase_two_priority_order() -> None:
    expected = (
        PhaseTwoSurface.entity_resolution,
        PhaseTwoSurface.topic_evolution,
        PhaseTwoSurface.embeddings,
        PhaseTwoSurface.new_sources,
        PhaseTwoSurface.backtesting,
    )
    actual = tuple(task.surface for task in PHASE_TWO_TASKS)
    assert actual == expected, "Phase Two surfaces must preserve the documented priority"


def test_phase_two_summaries_present() -> None:
    assert all(task.summary for task in PHASE_TWO_TASKS), "Every Phase Two task needs a brief summary"


def test_phase_two_status_strings() -> None:
    assert all(isinstance(task.status, str) and task.status for task in PHASE_TWO_TASKS)


def test_phase_two_rows_reflect_tasks() -> None:
    rows = build_phase_two_rows()
    assert len(rows) == len(PHASE_TWO_TASKS)
    priorities = [int(row[0]) for row in rows]
    assert priorities == sorted(priorities)
