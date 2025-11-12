from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from signal_harvester.cli.discovery_commands import store_classification_results
from signal_harvester.db import connect, init_db, list_top_discoveries, run_migrations, upsert_artifact


def _setup_db(tmp_path: Path) -> str:
    db_path = tmp_path / "test.db"
    init_db(str(db_path))
    run_migrations(str(db_path))
    return str(db_path)


def _insert_artifact(db_path: str, **overrides: Any) -> int:
    return upsert_artifact(
        db_path,
        artifact_type=overrides.get("artifact_type", "preprint"),
        source=overrides.get("source", "arxiv"),
        source_id=overrides.get("source_id", "arxiv:1234"),
        title=overrides.get("title", "Quantum Breakthrough"),
        text=overrides.get("text", "Demonstrates a new quantum error correction method."),
        url=overrides.get("url", "https://arxiv.org/abs/1234"),
        published_at=overrides.get("published_at", "2024-01-01T00:00:00Z"),
        author_entity_ids=overrides.get("author_entity_ids"),
        raw_json=overrides.get("raw_json", "{}"),
    )


def _set_score(db_path: str, artifact_id: int, *, score: float = 90.0) -> None:
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO scores (artifact_id, novelty, emergence, obscurity, discovery_score, computed_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(artifact_id) DO UPDATE SET
                    novelty=excluded.novelty,
                    emergence=excluded.emergence,
                    obscurity=excluded.obscurity,
                    discovery_score=excluded.discovery_score,
                    computed_at=excluded.computed_at
                """,
                (artifact_id, 88.0, 75.0, 64.0, score),
            )
    finally:
        conn.close()


@pytest.mark.parametrize("classification", [
    {
        "category": "Breakthrough",
        "sentiment": "positive",
        "urgency": 2,
        "tags": ["quantum", "error-correction"],
        "topics": ["quantum/error-correction"],
        "entities": {
            "people": ["Alice Example"],
            "labs": ["Quantum Lab"],
            "orgs": ["DeepTech Institute"],
        },
        "reasoning": "Novel approach to stabilizing qubits.",
    }
])
def test_store_classification_persists_artifact_classification(tmp_path: Path, classification: dict[str, Any]) -> None:
    db_path = _setup_db(tmp_path)
    artifact_id = _insert_artifact(db_path)

    store_classification_results(db_path, artifact_id, classification)

    conn = connect(db_path)
    try:
        row = conn.execute(
            (
                "SELECT category, sentiment, urgency, tags_json, reasoning, raw_json "
                "FROM artifact_classifications WHERE artifact_id = ?"
            ),
            (artifact_id,),
        ).fetchone()
        assert row is not None
        assert row["category"] == classification["category"]
        assert row["sentiment"] == classification["sentiment"]
        assert row["urgency"] == classification["urgency"]
        assert json.loads(row["tags_json"]) == classification["tags"]
        stored_raw = json.loads(row["raw_json"])
        assert stored_raw["category"] == classification["category"]
    finally:
        conn.close()


def test_list_top_discoveries_includes_classification(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    artifact_id = _insert_artifact(db_path, source_id="arxiv:5678")
    _set_score(db_path, artifact_id, score=92.5)

    classification = {
        "category": "Preprint",
        "sentiment": "neutral",
        "urgency": 1,
        "tags": ["ai/ml/theory"],
        "topics": ["ai/ml/theory"],
        "entities": {"people": [], "labs": [], "orgs": []},
        "reasoning": "Baseline reasoning",
    }
    store_classification_results(db_path, artifact_id, classification)

    rows = list_top_discoveries(db_path, min_score=80.0, limit=5)
    assert rows, "Expected discoveries to be returned"
    result = rows[0]
    assert result["category"] == "Preprint"
    assert result["sentiment"] == "neutral"
    assert result["urgency"] == 1
    assert result["tags"] == ["ai/ml/theory"]
    assert "ai/ml/theory" in result["topics"]
