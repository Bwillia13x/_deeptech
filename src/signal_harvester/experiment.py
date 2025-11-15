"""
Experiment tracking and backtesting for Signal Harvester.

This module provides experiment management for A/B testing discovery scoring algorithms,
calculating precision/recall metrics, and validating improvements.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from collections.abc import Mapping

from .db import connect, utc_now_iso, _insert_and_return_id

log = logging.getLogger(__name__)


@dataclass
class ExperimentConfig:
    """Configuration for an experiment run."""
    
    scoring_weights: dict[str, float]
    source_filters: list[str] | None = None
    min_score_threshold: float = 70.0
    lookback_days: int = 7
    description: str | None = None


@dataclass
class ExperimentMetrics:
    """Metrics calculated from an experiment run."""
    
    artifact_count: int
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    precision: float
    recall: float
    f1_score: float
    accuracy: float


def create_experiment(
    db_path: str,
    name: str,
    config: ExperimentConfig,
    baseline_id: int | None = None,
) -> int:
    """
    Create a new experiment with the given configuration.
    
    Args:
        db_path: Path to SQLite database
        name: Unique experiment name
        config: Experiment configuration
        baseline_id: Optional ID of baseline experiment for comparison
        
    Returns:
        Experiment ID
        
    Raises:
        ValueError: If experiment name already exists
    """
    conn = connect(db_path)
    try:
        now = utc_now_iso()
        config_json = json.dumps({
            "scoring_weights": config.scoring_weights,
            "source_filters": config.source_filters,
            "min_score_threshold": config.min_score_threshold,
            "lookback_days": config.lookback_days,
        })
        
        with conn:
            # Check if name exists
            cur = conn.execute("SELECT id FROM experiments WHERE name = ?", (name,))
            if cur.fetchone():
                raise ValueError(f"Experiment '{name}' already exists")
            
            # Insert new experiment
            experiment_id = _insert_and_return_id(
                conn,
                db_path,
                """
                INSERT INTO experiments (name, description, config_json, baseline_id, created_at, updated_at, status)
                VALUES (?, ?, ?, ?, ?, ?, 'draft')
                """,
                (name, config.description, config_json, baseline_id, now, now),
            )
            
        log.info("Created experiment %d: %s", experiment_id, name)
        return experiment_id
    finally:
        conn.close()


def calculate_metrics(
    true_positives: int,
    false_positives: int,
    true_negatives: int,
    false_negatives: int,
) -> ExperimentMetrics:
    """
    Calculate precision, recall, F1 score, and accuracy from confusion matrix.
    
    Args:
        true_positives: Count of correctly identified positives
        false_positives: Count of incorrectly identified positives
        true_negatives: Count of correctly identified negatives
        false_negatives: Count of incorrectly identified negatives
        
    Returns:
        ExperimentMetrics with calculated values
    """
    total = true_positives + false_positives + true_negatives + false_negatives
    
    # Precision = TP / (TP + FP)
    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
    
    # Recall = TP / (TP + FN)
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0
    
    # F1 Score = 2 * (Precision * Recall) / (Precision + Recall)
    f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    
    # Accuracy = (TP + TN) / Total
    accuracy = (true_positives + true_negatives) / total if total > 0 else 0.0
    
    return ExperimentMetrics(
        artifact_count=total,
        true_positives=true_positives,
        false_positives=false_positives,
        true_negatives=true_negatives,
        false_negatives=false_negatives,
        precision=precision,
        recall=recall,
        f1_score=f1_score,
        accuracy=accuracy,
    )


def create_experiment_run(
    db_path: str,
    experiment_id: int,
    metrics: ExperimentMetrics,
    metadata: dict[str, Any] | None = None,
) -> int:
    """
    Record an experiment run with its results.
    
    Args:
        db_path: Path to SQLite database
        experiment_id: ID of experiment being run
        metrics: Calculated metrics from the run
        metadata: Optional metadata (e.g., artifact IDs, timestamps)
        
    Returns:
        Experiment run ID
    """
    conn = connect(db_path)
    try:
        now = utc_now_iso()
        metadata_json = json.dumps(metadata) if metadata else None
        
        with conn:
            run_id = _insert_and_return_id(
                conn,
                db_path,
                """
                INSERT INTO experiment_runs (
                    experiment_id,
                    artifact_count,
                    true_positives,
                    false_positives,
                    true_negatives,
                    false_negatives,
                    precision,
                    recall,
                    f1_score,
                    accuracy,
                    started_at,
                    completed_at,
                    status,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?)
                """,
                (
                    experiment_id,
                    metrics.artifact_count,
                    metrics.true_positives,
                    metrics.false_positives,
                    metrics.true_negatives,
                    metrics.false_negatives,
                    metrics.precision,
                    metrics.recall,
                    metrics.f1_score,
                    metrics.accuracy,
                    now,
                    now,
                    metadata_json,
                ),
            )
            
            # Update experiment status
            conn.execute(
                "UPDATE experiments SET status = 'completed', updated_at = ? WHERE id = ?",
                (now, experiment_id)
            )
            
        log.info("Created experiment run %d for experiment %d (P=%.3f, R=%.3f, F1=%.3f)",
                 run_id, experiment_id, metrics.precision, metrics.recall, metrics.f1_score)
        return run_id
    finally:
        conn.close()


def _row_to_mapping(row: Any) -> dict[str, Any]:
    """Return a plain dict for SQLite Row, psycopg RealDictRow, or tuple."""
    if isinstance(row, Mapping):
        return dict(row)
    if hasattr(row, "keys"):
        # sqlite3.Row exposes keys() even though it's not a Mapping subclass
        return {key: row[key] for key in row.keys()}
    return dict(row)


def _serialize_experiment(row: Any) -> dict[str, Any]:
    data = _row_to_mapping(row)
    return {
        "id": data["id"],
        "name": data["name"],
        "description": data.get("description"),
        "config": json.loads(data["config_json"]),
        "baselineId": data.get("baseline_id"),
        "createdAt": data.get("created_at"),
        "updatedAt": data.get("updated_at"),
        "status": data.get("status"),
    }


def get_experiment(db_path: str, experiment_id: int) -> dict[str, Any] | None:
    """
    Retrieve experiment details by ID.
    
    Args:
        db_path: Path to SQLite database
        experiment_id: Experiment ID
        
    Returns:
        Experiment dict or None if not found
    """
    conn = connect(db_path)
    try:
        cur = conn.execute(
            "SELECT id, name, description, config_json, baseline_id, created_at, updated_at, status "
            "FROM experiments WHERE id = ?",
            (experiment_id,)
        )
        row = cur.fetchone()
        if not row:
            return None

        return _serialize_experiment(row)
    finally:
        conn.close()


def list_experiments(db_path: str, status: str | None = None) -> list[dict[str, Any]]:
    """
    List all experiments, optionally filtered by status.
    
    Args:
        db_path: Path to SQLite database
        status: Optional status filter ('draft', 'running', 'completed')
        
    Returns:
        List of experiment dicts
    """
    conn = connect(db_path)
    try:
        if status:
            cur = conn.execute(
                "SELECT id, name, description, config_json, baseline_id, created_at, updated_at, status "
                "FROM experiments WHERE status = ? ORDER BY created_at DESC",
                (status,)
            )
        else:
            cur = conn.execute(
                "SELECT id, name, description, config_json, baseline_id, created_at, updated_at, status "
                "FROM experiments ORDER BY created_at DESC"
            )
        
        return [_serialize_experiment(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_experiment_runs(db_path: str, experiment_id: int) -> list[dict[str, Any]]:
    """
    Get all runs for an experiment.
    
    Args:
        db_path: Path to SQLite database
        experiment_id: Experiment ID
        
    Returns:
        List of experiment run dicts
    """
    conn = connect(db_path)
    try:
        cur = conn.execute(
            """
            SELECT id, artifact_count, true_positives, false_positives, true_negatives, false_negatives,
                   precision, recall, f1_score, accuracy, started_at, completed_at, status, metadata_json
            FROM experiment_runs
            WHERE experiment_id = ?
            ORDER BY started_at DESC
            """,
            (experiment_id,)
        )
        
        runs = []
        for row in cur.fetchall():
            data = _row_to_mapping(row)
            runs.append({
                "id": data["id"],
                "artifactCount": data["artifact_count"],
                "truePositives": data["true_positives"],
                "falsePositives": data["false_positives"],
                "trueNegatives": data["true_negatives"],
                "falseNegatives": data["false_negatives"],
                "precision": data["precision"],
                "recall": data["recall"],
                "f1Score": data["f1_score"],
                "accuracy": data["accuracy"],
                "startedAt": data["started_at"],
                "completedAt": data["completed_at"],
                "status": data["status"],
                "metadata": json.loads(data["metadata_json"]) if data.get("metadata_json") else None,
            })
        
        return runs
    finally:
        conn.close()


def compare_experiments(
    db_path: str,
    experiment_id_a: int,
    experiment_id_b: int,
) -> dict[str, Any]:
    """
    Compare results of two experiments.
    
    Args:
        db_path: Path to SQLite database
        experiment_id_a: First experiment ID
        experiment_id_b: Second experiment ID
        
    Returns:
        Comparison dict with metrics from both experiments
    """
    conn = connect(db_path)
    try:
        # Get latest run for each experiment
        cur_a = conn.execute(
            """
            SELECT precision, recall, f1_score, accuracy, artifact_count
            FROM experiment_runs
            WHERE experiment_id = ? AND status = 'completed'
            ORDER BY completed_at DESC
            LIMIT 1
            """,
            (experiment_id_a,)
        )
        row_a = cur_a.fetchone()
        
        cur_b = conn.execute(
            """
            SELECT precision, recall, f1_score, accuracy, artifact_count
            FROM experiment_runs
            WHERE experiment_id = ? AND status = 'completed'
            ORDER BY completed_at DESC
            LIMIT 1
            """,
            (experiment_id_b,)
        )
        row_b = cur_b.fetchone()
        
        if not row_a or not row_b:
            return {
                "error": "One or both experiments have no completed runs"
            }
        
        data_a = _row_to_mapping(row_a)
        data_b = _row_to_mapping(row_b)
        
        # Calculate deltas
        precision_delta = (data_b["precision"] or 0.0) - (data_a["precision"] or 0.0)
        recall_delta = (data_b["recall"] or 0.0) - (data_a["recall"] or 0.0)
        f1_delta = (data_b["f1_score"] or 0.0) - (data_a["f1_score"] or 0.0)
        accuracy_delta = (data_b["accuracy"] or 0.0) - (data_a["accuracy"] or 0.0)
        
        return {
            "experimentA": {
                "id": experiment_id_a,
                "precision": data_a["precision"],
                "recall": data_a["recall"],
                "f1Score": data_a["f1_score"],
                "accuracy": data_a["accuracy"],
                "artifactCount": data_a["artifact_count"],
            },
            "experimentB": {
                "id": experiment_id_b,
                "precision": data_b["precision"],
                "recall": data_b["recall"],
                "f1Score": data_b["f1_score"],
                "accuracy": data_b["accuracy"],
                "artifactCount": data_b["artifact_count"],
            },
            "deltas": {
                "precision": precision_delta,
                "recall": recall_delta,
                "f1Score": f1_delta,
                "accuracy": accuracy_delta,
            },
            "winner": "experimentB" if f1_delta > 0 else ("experimentA" if f1_delta < 0 else "tie"),
        }
    finally:
        conn.close()


def add_discovery_label(
    db_path: str,
    artifact_id: int,
    label: str,
    confidence: float = 1.0,
    annotator: str | None = None,
    notes: str | None = None,
) -> int:
    """
    Add or update ground truth label for an artifact.
    
    Args:
        db_path: Path to SQLite database
        artifact_id: Artifact ID to label
        label: Label value (e.g., 'true_positive', 'false_positive', 'relevant', 'irrelevant')
        confidence: Confidence in label (0.0-1.0)
        annotator: Who applied the label
        notes: Optional notes
        
    Returns:
        Label ID
    """
    conn = connect(db_path)
    try:
        now = utc_now_iso()
        
        with conn:
            # Check if label exists
            cur = conn.execute(
                "SELECT id FROM discovery_labels WHERE artifact_id = ?",
                (artifact_id,)
            )
            row = cur.fetchone()
            
            if row:
                row_dict = _row_to_mapping(row)
                label_id = int(row_dict["id"])
                conn.execute(
                    """
                    UPDATE discovery_labels
                    SET label = ?, confidence = ?, annotator = ?, notes = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (label, confidence, annotator, notes, now, label_id)
                )
                log.info("Updated label %d for artifact %d: %s", label_id, artifact_id, label)
            else:
                label_id = _insert_and_return_id(
                    conn,
                    db_path,
                    """
                    INSERT INTO discovery_labels
                    (artifact_id, label, confidence, annotator, notes, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (artifact_id, label, confidence, annotator, notes, now, now),
                )
                log.info("Created label %d for artifact %d: %s", label_id, artifact_id, label)
        
        return label_id
    finally:
        conn.close()


def get_labeled_artifacts(db_path: str, label: str | None = None) -> list[dict[str, Any]]:
    """
    Get all labeled artifacts, optionally filtered by label.
    
    Args:
        db_path: Path to SQLite database
        label: Optional label filter
        
    Returns:
        List of labeled artifact dicts
    """
    conn = connect(db_path)
    try:
        if label:
            cur = conn.execute(
                """
                SELECT dl.id, dl.artifact_id, dl.label, dl.confidence, dl.annotator, dl.notes,
                       dl.created_at, dl.updated_at, a.title, a.source
                FROM discovery_labels dl
                JOIN artifacts a ON a.id = dl.artifact_id
                WHERE dl.label = ?
                ORDER BY dl.updated_at DESC
                """,
                (label,)
            )
        else:
            cur = conn.execute(
                """
                SELECT dl.id, dl.artifact_id, dl.label, dl.confidence, dl.annotator, dl.notes,
                       dl.created_at, dl.updated_at, a.title, a.source
                FROM discovery_labels dl
                JOIN artifacts a ON a.id = dl.artifact_id
                ORDER BY dl.updated_at DESC
                """
            )
        
        labels = []
        for row in cur.fetchall():
            data = _row_to_mapping(row)
            labels.append({
                "id": data["id"],
                "artifactId": data["artifact_id"],
                "label": data["label"],
                "confidence": data["confidence"],
                "annotator": data["annotator"],
                "notes": data["notes"],
                "createdAt": data["created_at"],
                "updatedAt": data["updated_at"],
                "artifactTitle": data["title"],
                "artifactSource": data["source"],
            })
        
        return labels
    finally:
        conn.close()
