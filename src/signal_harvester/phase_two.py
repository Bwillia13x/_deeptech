from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class PhaseTwoSurface(Enum):
    """Enumerate the priority surfaces for Phase Two exploration."""

    entity_resolution = "entity_resolution"
    topic_evolution = "topic_evolution"
    embeddings = "embeddings"
    new_sources = "new_sources"
    backtesting = "backtesting"


@dataclass(frozen=True)
class PhaseTwoTask:
    surface: PhaseTwoSurface
    priority: int
    status: str
    summary: str


PHASE_TWO_TASKS: list[PhaseTwoTask] = [
    PhaseTwoTask(
        surface=PhaseTwoSurface.entity_resolution,
        priority=1,
        status="scoping",
        summary="Finalize dedupe/merge heuristics and reuse identity_resolution configs.",
    ),
    PhaseTwoTask(
        surface=PhaseTwoSurface.topic_evolution,
        priority=2,
        status="drafting",
        summary="Design topic modeling pipeline, dynamic topics, and split/merge detection strategies.",
    ),
    PhaseTwoTask(
        surface=PhaseTwoSurface.embeddings,
        priority=3,
        status="backlog",
        summary="Add sentence-transformers caching with Redis and refresh workflows for signal embeddings.",
    ),
    PhaseTwoTask(
        surface=PhaseTwoSurface.new_sources,
        priority=4,
        status="backlog",
        summary="Plan ingestion adapters for Facebook and LinkedIn within the existing source abstraction.",
    ),
    PhaseTwoTask(
        surface=PhaseTwoSurface.backtesting,
        priority=5,
        status="backlog",
        summary=(
            "Capture historical replay/linkage experiments including "
            "experiments/relationships tables for validation."
        ),
    ),
]


def iter_phase_two_surfaces() -> Iterable[PhaseTwoTask]:
    """Yield Phase Two tasks in priority order for dashboards or orchestration."""

    for task in sorted(PHASE_TWO_TASKS, key=lambda t: t.priority):
        yield task
