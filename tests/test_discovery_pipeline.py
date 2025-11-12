from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from signal_harvester.cli.discovery_commands import store_classification_results
from signal_harvester.db import (
    connect,
    init_db,
    list_top_discoveries,
    run_migrations,
    upsert_artifact,
)
from signal_harvester.discovery_scoring import run_discovery_scoring


def _setup_db(tmp_path: Path) -> str:
    db_path = tmp_path / "pipeline.db"
    init_db(str(db_path))
    run_migrations(str(db_path))
    return str(db_path)


def _insert_sample_artifact(db_path: str, **overrides: Any) -> int:
    return upsert_artifact(
        db_path,
        artifact_type=overrides.get("artifact_type", "preprint"),
        source=overrides.get("source", "arxiv"),
        source_id=overrides.get("source_id", "arxiv:9999"),
        title=overrides.get("title", "Sample Deep Tech Artifact"),
        text=overrides.get("text", "Introduces a novel quantum-resistant protocol."),
        url=overrides.get("url", "https://example.org/artifact"),
        published_at=overrides.get("published_at", "2024-01-02T00:00:00Z"),
        author_entity_ids=overrides.get("author_entity_ids"),
        raw_json=overrides.get("raw_json", json.dumps({"source": "test"})),
    )


@pytest.mark.asyncio
async def test_discovery_pipeline_scoring_flow(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    artifact_id = _insert_sample_artifact(db_path)

    classification = {
        "category": "Breakthrough",
        "sentiment": "positive",
        "urgency": 2,
        "tags": ["quantum", "protocols"],
        "topics": ["quantum/algorithms"],
        "entities": {
            "people": ["Dr. Test"],
            "labs": ["Deep Quantum Lab"],
            "orgs": ["Future Research Institute"],
        },
        "reasoning": "Demonstrates a new security primitive for quantum-era networks.",
    }

    store_classification_results(db_path, artifact_id, classification)

    scored_count = await run_discovery_scoring(db_path, {}, limit=10)
    assert scored_count == 1

    discoveries = list_top_discoveries(db_path, min_score=0.0, limit=5)
    assert discoveries, "Expected discovery results after scoring"
    result = discoveries[0]
    assert result["artifact_id"] == artifact_id
    assert result["category"] == classification["category"]
    assert result["sentiment"] == classification["sentiment"]
    assert result["urgency"] == classification["urgency"]
    assert result["tags"] == classification["tags"]
    assert "quantum/algorithms" in result["topics"]
    assert result["discovery_score"] > 0


def test_migration_backfills_artifact_classifications(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)

    conn = connect(db_path)
    try:
        with conn:
            conn.execute("DROP TABLE IF EXISTS artifact_classifications;")
            conn.execute("DELETE FROM schema_version;")
            conn.execute("INSERT INTO schema_version (version) VALUES (5);")
    finally:
        conn.close()

    run_migrations(db_path)

    conn = connect(db_path)
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='artifact_classifications';"
        )
        assert cursor.fetchone(), "artifact_classifications table should be recreated by migration"

        version_row = conn.execute(
            "SELECT MAX(version) as version FROM schema_version;"
        ).fetchone()
        assert version_row and version_row["version"] >= 6
    finally:
        conn.close()
