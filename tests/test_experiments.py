"""
Tests for experiment tracking and backtesting functionality.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from signal_harvester.db import init_db, run_migrations
from signal_harvester.experiment import (
    ExperimentConfig,
    add_discovery_label,
    calculate_metrics,
    compare_experiments,
    create_experiment,
    create_experiment_run,
    get_experiment,
    get_experiment_runs,
    get_labeled_artifacts,
    list_experiments,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        init_db(db_path)
        run_migrations(db_path)
        yield db_path


class TestMetricsCalculation:
    """Test precision, recall, F1, and accuracy calculations."""
    
    def test_perfect_precision_recall(self):
        """Test metrics with perfect predictions (all correct)."""
        metrics = calculate_metrics(
            true_positives=10,
            false_positives=0,
            true_negatives=10,
            false_negatives=0,
        )
        
        assert metrics.precision == 1.0
        assert metrics.recall == 1.0
        assert metrics.f1_score == 1.0
        assert metrics.accuracy == 1.0
        assert metrics.artifact_count == 20
    
    def test_zero_precision_recall(self):
        """Test metrics with complete failures (all wrong)."""
        metrics = calculate_metrics(
            true_positives=0,
            false_positives=10,
            true_negatives=0,
            false_negatives=10,
        )
        
        assert metrics.precision == 0.0
        assert metrics.recall == 0.0
        assert metrics.f1_score == 0.0
        assert metrics.accuracy == 0.0
        assert metrics.artifact_count == 20
    
    def test_mixed_performance(self):
        """Test metrics with mixed performance."""
        # TP=8, FP=2, TN=6, FN=4
        # Precision = 8/(8+2) = 0.8
        # Recall = 8/(8+4) = 0.667
        # F1 = 2*(0.8*0.667)/(0.8+0.667) = 0.727
        # Accuracy = (8+6)/20 = 0.7
        metrics = calculate_metrics(
            true_positives=8,
            false_positives=2,
            true_negatives=6,
            false_negatives=4,
        )
        
        assert metrics.precision == pytest.approx(0.8, abs=0.01)
        assert metrics.recall == pytest.approx(0.667, abs=0.01)
        assert metrics.f1_score == pytest.approx(0.727, abs=0.01)
        assert metrics.accuracy == 0.7
    
    def test_empty_dataset(self):
        """Test metrics with empty dataset."""
        metrics = calculate_metrics(
            true_positives=0,
            false_positives=0,
            true_negatives=0,
            false_negatives=0,
        )
        
        assert metrics.precision == 0.0
        assert metrics.recall == 0.0
        assert metrics.f1_score == 0.0
        assert metrics.accuracy == 0.0
        assert metrics.artifact_count == 0
    
    def test_only_true_positives(self):
        """Test metrics with only true positives (no negatives)."""
        metrics = calculate_metrics(
            true_positives=15,
            false_positives=0,
            true_negatives=0,
            false_negatives=0,
        )
        
        assert metrics.precision == 1.0
        assert metrics.recall == 1.0
        assert metrics.f1_score == 1.0
        assert metrics.accuracy == 1.0
    
    def test_high_precision_low_recall(self):
        """Test scenario with high precision but low recall."""
        # TP=5, FP=0, TN=10, FN=15
        # Precision = 5/(5+0) = 1.0
        # Recall = 5/(5+15) = 0.25
        metrics = calculate_metrics(
            true_positives=5,
            false_positives=0,
            true_negatives=10,
            false_negatives=15,
        )
        
        assert metrics.precision == 1.0
        assert metrics.recall == 0.25
        assert metrics.f1_score == pytest.approx(0.4, abs=0.01)


class TestExperimentCreation:
    """Test experiment creation and management."""
    
    def test_create_experiment(self, temp_db):
        """Test creating a new experiment."""
        config = ExperimentConfig(
            scoring_weights={"novelty": 0.4, "impact": 0.3, "quality": 0.3},
            min_score_threshold=75.0,
            lookback_days=7,
            description="Test experiment",
        )
        
        exp_id = create_experiment(temp_db, "test_exp_1", config)
        assert exp_id > 0
        
        # Verify experiment exists
        exp = get_experiment(temp_db, exp_id)
        assert exp is not None
        assert exp["name"] == "test_exp_1"
        assert exp["description"] == "Test experiment"
        assert exp["config"]["scoring_weights"] == config.scoring_weights
        assert exp["status"] == "draft"
    
    def test_create_duplicate_experiment_fails(self, temp_db):
        """Test that creating duplicate experiment name fails."""
        config = ExperimentConfig(
            scoring_weights={"novelty": 0.5, "impact": 0.5},
            min_score_threshold=70.0,
            lookback_days=3,
        )
        
        create_experiment(temp_db, "duplicate_exp", config)
        
        with pytest.raises(ValueError, match="already exists"):
            create_experiment(temp_db, "duplicate_exp", config)
    
    def test_list_experiments(self, temp_db):
        """Test listing experiments."""
        config1 = ExperimentConfig(
            scoring_weights={"novelty": 0.5, "impact": 0.5},
        )
        config2 = ExperimentConfig(
            scoring_weights={"novelty": 0.3, "impact": 0.7},
        )
        
        create_experiment(temp_db, "exp_1", config1)
        create_experiment(temp_db, "exp_2", config2)
        
        experiments = list_experiments(temp_db)
        assert len(experiments) == 2
        assert any(e["name"] == "exp_1" for e in experiments)
        assert any(e["name"] == "exp_2" for e in experiments)
    
    def test_experiment_with_baseline(self, temp_db):
        """Test creating experiment with baseline reference."""
        config = ExperimentConfig(
            scoring_weights={"novelty": 0.5, "impact": 0.5},
        )
        
        baseline_id = create_experiment(temp_db, "baseline", config)
        
        new_config = ExperimentConfig(
            scoring_weights={"novelty": 0.6, "impact": 0.4},
        )
        exp_id = create_experiment(temp_db, "experiment", new_config, baseline_id)
        
        exp = get_experiment(temp_db, exp_id)
        assert exp["baselineId"] == baseline_id


class TestExperimentRuns:
    """Test experiment run tracking."""
    
    def test_create_experiment_run(self, temp_db):
        """Test creating an experiment run with metrics."""
        config = ExperimentConfig(
            scoring_weights={"novelty": 0.5, "impact": 0.5},
        )
        exp_id = create_experiment(temp_db, "run_test", config)
        
        metrics = calculate_metrics(
            true_positives=8,
            false_positives=2,
            true_negatives=5,
            false_negatives=3,
        )
        
        run_id = create_experiment_run(temp_db, exp_id, metrics)
        assert run_id > 0
        
        # Verify run exists
        runs = get_experiment_runs(temp_db, exp_id)
        assert len(runs) == 1
        run = runs[0]
        assert run["artifactCount"] == 18
        assert run["truePositives"] == 8
        assert run["falsePositives"] == 2
        assert run["precision"] == metrics.precision
        assert run["recall"] == metrics.recall
        assert run["f1Score"] == metrics.f1_score
        assert run["status"] == "completed"
    
    def test_multiple_runs(self, temp_db):
        """Test multiple runs for same experiment."""
        config = ExperimentConfig(
            scoring_weights={"novelty": 0.5, "impact": 0.5},
        )
        exp_id = create_experiment(temp_db, "multi_run", config)
        
        # Run 1
        metrics1 = calculate_metrics(8, 2, 5, 3)
        create_experiment_run(temp_db, exp_id, metrics1)
        
        # Run 2
        metrics2 = calculate_metrics(9, 1, 6, 2)
        create_experiment_run(temp_db, exp_id, metrics2)
        
        runs = get_experiment_runs(temp_db, exp_id)
        assert len(runs) == 2


class TestExperimentComparison:
    """Test A/B comparison of experiments."""
    
    def test_compare_experiments(self, temp_db):
        """Test comparing two experiments."""
        # Create baseline
        config_a = ExperimentConfig(
            scoring_weights={"novelty": 0.5, "impact": 0.5},
        )
        exp_a = create_experiment(temp_db, "baseline", config_a)
        metrics_a = calculate_metrics(7, 3, 5, 5)  # F1 = 0.636
        create_experiment_run(temp_db, exp_a, metrics_a)
        
        # Create improved version
        config_b = ExperimentConfig(
            scoring_weights={"novelty": 0.6, "impact": 0.4},
        )
        exp_b = create_experiment(temp_db, "improved", config_b)
        metrics_b = calculate_metrics(9, 1, 6, 4)  # F1 = 0.750
        create_experiment_run(temp_db, exp_b, metrics_b)
        
        # Compare
        comparison = compare_experiments(temp_db, exp_a, exp_b)
        
        assert "experimentA" in comparison
        assert "experimentB" in comparison
        assert "deltas" in comparison
        assert "winner" in comparison
        
        # Experiment B should be better
        assert comparison["deltas"]["f1Score"] > 0
        assert comparison["winner"] == "experimentB"
    
    def test_compare_no_completed_runs(self, temp_db):
        """Test comparison when experiments have no completed runs."""
        config = ExperimentConfig(
            scoring_weights={"novelty": 0.5, "impact": 0.5},
        )
        exp_a = create_experiment(temp_db, "exp_a", config)
        exp_b = create_experiment(temp_db, "exp_b", config)
        
        comparison = compare_experiments(temp_db, exp_a, exp_b)
        assert "error" in comparison


class TestDiscoveryLabels:
    """Test ground truth labeling functionality."""
    
    def test_add_label(self, temp_db):
        """Test adding a label to an artifact."""
        # First need an artifact - add a dummy one
        from signal_harvester.db import upsert_artifact
        artifact_id = upsert_artifact(
            temp_db,
            artifact_type="paper",
            source="test",
            source_id="test_123",
            title="Test Artifact",
            url="https://example.com/test",
            published_at="2025-11-11T00:00:00Z",
        )
        
        label_id = add_discovery_label(
            temp_db,
            artifact_id,
            "true_positive",
            confidence=0.9,
            annotator="test_user",
            notes="Clear breakthrough",
        )
        
        assert label_id > 0
        
        # Verify label
        labels = get_labeled_artifacts(temp_db)
        assert len(labels) == 1
        label = labels[0]
        assert label["artifactId"] == artifact_id
        assert label["label"] == "true_positive"
        assert label["confidence"] == 0.9
        assert label["annotator"] == "test_user"
        assert label["notes"] == "Clear breakthrough"
    
    def test_update_existing_label(self, temp_db):
        """Test updating an existing label."""
        from signal_harvester.db import upsert_artifact
        artifact_id = upsert_artifact(
            temp_db,
            artifact_type="paper",
            source="test",
            source_id="test_456",
            title="Test Artifact 2",
            url="https://example.com/test2",
            published_at="2025-11-11T00:00:00Z",
        )
        
        # Add initial label
        label_id_1 = add_discovery_label(
            temp_db,
            artifact_id,
            "true_positive",
            confidence=0.8,
        )
        
        # Update label
        label_id_2 = add_discovery_label(
            temp_db,
            artifact_id,
            "false_positive",
            confidence=0.95,
            notes="Upon review, not actually significant",
        )
        
        # Should be same ID (update, not insert)
        assert label_id_1 == label_id_2
        
        # Verify updated label
        labels = get_labeled_artifacts(temp_db)
        assert len(labels) == 1
        label = labels[0]
        assert label["label"] == "false_positive"
        assert label["confidence"] == 0.95
    
    def test_filter_labels_by_type(self, temp_db):
        """Test filtering labeled artifacts by label type."""
        from signal_harvester.db import upsert_artifact
        
        # Add multiple artifacts with different labels
        for i, label_type in enumerate(["true_positive", "false_positive", "relevant", "irrelevant"]):
            artifact_id = upsert_artifact(
                temp_db,
                artifact_type="paper",
                source="test",
                source_id=f"test_{i}",
                title=f"Artifact {i}",
                url=f"https://example.com/{i}",
                published_at="2025-11-11T00:00:00Z",
            )
            add_discovery_label(temp_db, artifact_id, label_type)
        
        # Get all labels
        all_labels = get_labeled_artifacts(temp_db)
        assert len(all_labels) == 4
        
        # Filter by specific label
        tp_labels = get_labeled_artifacts(temp_db, label="true_positive")
        assert len(tp_labels) == 1
        assert tp_labels[0]["label"] == "true_positive"


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_nonexistent_experiment(self, temp_db):
        """Test getting nonexistent experiment."""
        exp = get_experiment(temp_db, 99999)
        assert exp is None
    
    def test_empty_experiment_list(self, temp_db):
        """Test listing when no experiments exist."""
        experiments = list_experiments(temp_db)
        assert experiments == []
    
    def test_experiment_runs_empty(self, temp_db):
        """Test getting runs for experiment with none."""
        config = ExperimentConfig(
            scoring_weights={"novelty": 0.5, "impact": 0.5},
        )
        exp_id = create_experiment(temp_db, "no_runs", config)
        
        runs = get_experiment_runs(temp_db, exp_id)
        assert runs == []
    
    def test_metrics_with_zero_denominator(self):
        """Test metrics calculation with edge case denominators."""
        # Only true negatives (no predictions made)
        metrics = calculate_metrics(0, 0, 10, 0)
        assert metrics.precision == 0.0
        assert metrics.recall == 0.0
        assert metrics.f1_score == 0.0
        assert metrics.accuracy == 1.0  # All correct (no false predictions)
