"""Performance profiling helpers for Phase Three scaling work."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from textwrap import dedent
from typing import Any, Iterable, List, Optional


@dataclass(frozen=True)
class QueryProfile:
    """Metadata for a frequently-run database query."""

    name: str
    description: str
    query: str
    expected_index: str
    critical: bool = True


def _clean_query(sql: str) -> str:
    """Ensure the SQL uses normalized whitespace and no trailing semicolon."""
    normalized = dedent(sql).strip()
    if normalized.endswith(";"):
        normalized = normalized[:-1]
    return normalized


CRITICAL_QUERIES: List[QueryProfile] = [
    QueryProfile(
        name="Top Discoveries (Limit 50)",
        description="Most frequently used discovery endpoint sorted by score.",
        query=_clean_query(
            """
            SELECT a.*, s.discovery_score, s.novelty, s.emergence, s.obscurity
            FROM artifacts a
            JOIN scores s ON s.artifact_id = a.id
            ORDER BY s.discovery_score DESC, a.published_at DESC
            LIMIT 50;
            """
        ),
        expected_index="idx_scores_discovery_artifact",
    ),
    QueryProfile(
        name="Topic Timeline (Single Topic)",
        description="Retrieve artifacts for a topic timeline (Phase Two analytics).",
        query=_clean_query(
            """
            SELECT a.id, a.title, a.published_at, a.source, at.confidence
            FROM artifacts a
            JOIN artifact_topics at ON at.artifact_id = a.id
            WHERE at.topic_id = 1
            ORDER BY a.published_at DESC
            LIMIT 100;
            """
        ),
        expected_index="idx_artifact_topics_topic_artifact",
    ),
    QueryProfile(
        name="Citation Graph - Outgoing Links",
        description="Outward relationships from an artifact (confidence filtered).",
        query=_clean_query(
            """
            SELECT ar.*, target.title, target.source
            FROM artifact_relationships ar
            JOIN artifacts target ON ar.target_artifact_id = target.id
            WHERE ar.source_artifact_id = 1 
              AND ar.confidence >= 0.80
            ORDER BY ar.confidence DESC;
            """
        ),
        expected_index="idx_relationships_source_confidence",
    ),
    QueryProfile(
        name="Citation Graph - Incoming Links",
        description="Incoming citation relationships for an artifact.",
        query=_clean_query(
            """
            SELECT ar.*, source.title, source.source
            FROM artifact_relationships ar
            JOIN artifacts source ON ar.source_artifact_id = source.id
            WHERE ar.target_artifact_id = 1
              AND ar.confidence >= 0.80
            ORDER BY ar.confidence DESC;
            """
        ),
        expected_index="idx_relationships_target_confidence",
    ),
    QueryProfile(
        name="Recent Discoveries (Last 7 Days)",
        description="Time-filtered discoveries for recency dashboards.",
        query=_clean_query(
            """
            SELECT *
            FROM artifacts
            WHERE published_at >= date('now', '-7 days')
              AND source IN ('arxiv', 'github', 'x')
            ORDER BY published_at DESC
            LIMIT 100;
            """
        ),
        expected_index="idx_artifacts_published_source",
        critical=False,
    ),
    QueryProfile(
        name="Related Topics (Forward Lookup)",
        description="Find similar topic neighbors for merge detection.",
        query=_clean_query(
            """
            SELECT ts.topic_id_2, ts.similarity, t.name
            FROM topic_similarity ts
            JOIN topics t ON t.id = ts.topic_id_2
            WHERE ts.topic_id_1 = 1
            ORDER BY ts.similarity DESC
            LIMIT 10;
            """
        ),
        expected_index="idx_topic_similarity_topic1_score",
        critical=False,
    ),
    QueryProfile(
        name="Trending Researchers (Last 30 Days)",
        description="Top influencers used by research analytics.",
        query=_clean_query(
            """
            SELECT id, name, influence_score, last_activity_date, expertise_areas
            FROM entities
            WHERE last_activity_date >= date('now', '-30 days')
            ORDER BY influence_score DESC
            LIMIT 50;
            """
        ),
        expected_index="idx_entities_activity_influence",
        critical=False,
    ),
    QueryProfile(
        name="Experiment Run History",
        description="Backtesting history for an experiment run.",
        query=_clean_query(
            """
            SELECT id, started_at, completed_at, status, precision, recall, f1_score
            FROM experiment_runs
            WHERE experiment_id = 1
            ORDER BY started_at DESC
            LIMIT 20;
            """
        ),
        expected_index="idx_experiment_runs_experiment_started",
        critical=False,
    ),
    QueryProfile(
        name="Top Discoveries with Filters (Complex)",
        description="Discovery query with recency and score filters.",
        query=_clean_query(
            """
            SELECT a.*, s.discovery_score, s.novelty, s.emergence
            FROM artifacts a
            JOIN scores s ON s.artifact_id = a.id
            WHERE a.published_at >= date('now', '-30 days')
              AND s.discovery_score >= 70.0
              AND a.source IN ('arxiv', 'github')
            ORDER BY s.discovery_score DESC, a.published_at DESC
            LIMIT 50;
            """
        ),
        expected_index="idx_scores_discovery_artifact + idx_artifacts_published_source",
    ),
    QueryProfile(
        name="All Discoveries (No Limit)",
        description="Stress test pulling every discovery ordered by score.",
        query=_clean_query(
            """
            SELECT a.id, a.title, s.discovery_score
            FROM artifacts a
            JOIN scores s ON s.artifact_id = a.id
            ORDER BY s.discovery_score DESC;
            """
        ),
        expected_index="idx_scores_discovery_artifact",
    ),
]


def benchmark_query(
    conn: sqlite3.Connection,
    query: str,
    iterations: int = 100,
) -> dict[str, Any]:
    """Benchmark a SQL query and return latency metrics."""
    timings: List[float] = []
    row_count = 0

    for _ in range(iterations):
        start = time.perf_counter()
        cursor = conn.execute(query)
        rows = cursor.fetchall()
        end = time.perf_counter()
        row_count = len(rows)
        timings.append((end - start) * 1000)

    timings.sort()
    size = len(timings)
    return {
        "min_ms": timings[0],
        "max_ms": timings[-1],
        "median_ms": timings[size // 2],
        "mean_ms": sum(timings) / size,
        "p95_ms": timings[min(size - 1, int(size * 0.95))],
        "p99_ms": timings[min(size - 1, int(size * 0.99))],
        "row_count": row_count,
    }


def explain_query(conn: sqlite3.Connection, query: str) -> List[str]:
    """Return EXPLAIN QUERY PLAN output for the provided SQL."""
    cursor = conn.execute(f"EXPLAIN QUERY PLAN {query}")
    return [row[3] for row in cursor.fetchall()]


def get_schema_version(conn: sqlite3.Connection) -> Optional[int]:
    """Fetch the current schema version recorded in the database."""
    try:
        cursor = conn.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1;"
        )
        row = cursor.fetchone()
        if row:
            return int(row[0])
    except sqlite3.Error:
        return None
    return None
