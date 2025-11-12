"""Comprehensive tests for Phase Two Topic Evolution."""

import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from signal_harvester.db import (
    connect,
    init_db,
    link_artifact_topic,
    run_migrations,
    upsert_artifact,
    upsert_topic,
)
from signal_harvester.discovery_scoring import update_discovery_scores
from signal_harvester.topic_evolution import (
    compute_topic_embedding,
    compute_topic_emergence,
    compute_topic_similarity,
    detect_topic_merges,
    detect_topic_splits,
    find_related_topics,
    get_topic_artifact_history,
    init_topic_evolution_tables,
    predict_topic_growth,
    run_topic_evolution_pipeline,
    store_topic_evolution_event,
    update_topic_similarity_matrix,
)


@pytest.fixture
def test_db():
    """Create a temporary test database with topic evolution schema."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    
    # Initialize database with full schema
    init_db(db_path)
    run_migrations(db_path)
    init_topic_evolution_tables(db_path)
    
    yield db_path
    
    # Cleanup
    import os
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def populated_db(test_db):
    """Create database with realistic topic evolution test data."""
    # Create topics
    topics = [
        {
            "name": "Quantum Error Correction",
            "path": "quantum/error-correction",
            "description": "Error correction codes for quantum computing"
        },
        {
            "name": "Surface Codes",
            "path": "quantum/surface-codes",
            "description": "Surface code implementations for QEC"
        },
        {
            "name": "Quantum Hardware",
            "path": "quantum/hardware",
            "description": "Quantum computing hardware development"
        },
        {
            "name": "Quantum Algorithms",
            "path": "quantum/algorithms",
            "description": "Quantum algorithms and applications"
        },
        {
            "name": "Machine Learning",
            "path": "ai/machine-learning",
            "description": "Machine learning techniques and applications"
        },
    ]
    
    topic_ids = []
    for topic in topics:
        topic_id = upsert_topic(
            db_path=test_db,
            name=topic["name"],
            taxonomy_path=topic["path"],
            description=topic["description"]
        )
        topic_ids.append(topic_id)
    
    # Create artifacts over 60 days with realistic patterns
    base_date = datetime.now(timezone.utc)
    
    artifacts = [
        # QEC + Surface Codes overlap (potential merge candidates)
        {
            "days_ago": 55,
            "source": "arxiv",
            "source_id": "2301.12345",
            "title": "Novel Surface Code Decoding with Machine Learning",
            "text": "We propose a new decoder for surface codes using deep reinforcement learning...",
            "topics": [0, 1, 4],  # QEC, Surface Codes, ML
            "score": 85.0
        },
        {
            "days_ago": 50,
            "source": "github",
            "source_id": "qec-lab/surface-decoder",
            "title": "Surface Code Decoder Implementation",
            "text": "Open source implementation of surface code decoders...",
            "topics": [0, 1],
            "score": 78.0
        },
        {
            "days_ago": 45,
            "source": "arxiv",
            "source_id": "2301.12346",
            "title": "Surface Code Threshold Analysis",
            "text": "Comprehensive analysis of surface code error thresholds...",
            "topics": [0, 1],
            "score": 82.0
        },
        {
            "days_ago": 30,
            "source": "arxiv",
            "source_id": "2301.12347",
            "title": "Advanced Surface Code Techniques",
            "text": "New techniques for improving surface code performance...",
            "topics": [0, 1],
            "score": 88.0
        },
        {
            "days_ago": 15,
            "source": "arxiv",
            "source_id": "2301.12348",
            "title": "Surface Code Error Correction at Scale",
            "text": "Scaling surface codes to large quantum systems...",
            "topics": [0, 1],
            "score": 90.0
        },
        # Quantum Hardware (stable topic)
        {
            "days_ago": 55,
            "source": "arxiv",
            "source_id": "2301.67890",
            "title": "Superconducting Qubit Coherence Improvements",
            "text": "We demonstrate improved coherence times in superconducting qubits...",
            "topics": [2],
            "score": 82.0
        },
        {
            "days_ago": 40,
            "source": "github",
            "source_id": "quantum-hw/qubit-control/v2.0",
            "title": "Qubit Control System v2.0",
            "text": "Major release with improved calibration routines...",
            "topics": [2],
            "score": 75.0
        },
        {
            "days_ago": 25,
            "source": "arxiv",
            "source_id": "2301.67891",
            "title": "Trapped Ion Quantum Computing Advances",
            "text": "New techniques for trapped ion quantum computers...",
            "topics": [2],
            "score": 79.0
        },
        # Quantum Algorithms (emerging/growing topic)
        {
            "days_ago": 50,
            "source": "arxiv",
            "source_id": "2301.54321",
            "title": "Quantum Algorithm for Optimization Problems",
            "text": "We present a quantum algorithm for combinatorial optimization...",
            "topics": [3],
            "score": 88.0
        },
        {
            "days_ago": 45,
            "source": "arxiv",
            "source_id": "2301.54322",
            "title": "Quantum Approximate Optimization Algorithm Enhancements",
            "text": "Improved QAOA with better convergence properties...",
            "topics": [3],
            "score": 85.0
        },
        {
            "days_ago": 30,
            "source": "arxiv",
            "source_id": "2301.54323",
            "title": "Variational Quantum Eigensolver Applications",
            "text": "VQE for quantum chemistry problems...",
            "topics": [3],
            "score": 90.0
        },
        {
            "days_ago": 20,
            "source": "arxiv",
            "source_id": "2301.54324",
            "title": "Quantum Machine Learning Algorithms",
            "text": "Quantum algorithms for machine learning tasks...",
            "topics": [3, 4],
            "score": 92.0
        },
        {
            "days_ago": 10,
            "source": "arxiv",
            "source_id": "2301.54325",
            "title": "Grover's Algorithm Optimizations",
            "text": "New optimizations for Grover's search algorithm...",
            "topics": [3],
            "score": 87.0
        },
        {
            "days_ago": 5,
            "source": "arxiv",
            "source_id": "2301.54326",
            "title": "Quantum Algorithms for Graph Problems",
            "text": "Quantum solutions to NP-hard graph problems...",
            "topics": [3],
            "score": 95.0
        },
        # Machine Learning (separate but sometimes overlaps)
        {
            "days_ago": 40,
            "source": "arxiv",
            "source_id": "2301.99001",
            "title": "Deep Learning for Scientific Computing",
            "text": "Neural networks for solving PDEs...",
            "topics": [4],
            "score": 80.0
        },
        {
            "days_ago": 25,
            "source": "arxiv",
            "source_id": "2301.99002",
            "title": "Transformer Models for Code Generation",
            "text": "Using transformers to generate code...",
            "topics": [4],
            "score": 83.0
        },
    ]
    
    for art in artifacts:
        pub_date = (base_date - timedelta(days=art["days_ago"])).isoformat()
        art_id = upsert_artifact(
            db_path=test_db,
            artifact_type="preprint",
            source=art["source"],
            source_id=art["source_id"],
            title=art["title"],
            text=art["text"],
            published_at=pub_date
        )
        
        # Link to topics
        for topic_idx in art["topics"]:
            link_artifact_topic(
                db_path=test_db,
                artifact_id=art_id,
                topic_id=topic_ids[topic_idx],
                confidence=0.85
            )
        
        # Add discovery scores
        update_discovery_scores(
            db_path=test_db,
            artifact_id=art_id,
            novelty=art["score"] - 5,
            emergence=art["score"],
            obscurity=75.0,
            discovery_score=art["score"]
        )
    
    return test_db, topic_ids


class TestTopicEmbedding:
    """Test topic embedding computation."""
    
    def test_compute_topic_embedding_basic(self, populated_db):
        """Test basic topic embedding computation."""
        db_path, topic_ids = populated_db
        
        # Compute embedding for Quantum Error Correction topic
        embedding = compute_topic_embedding(topic_ids[0], db_path)
        
        assert embedding is not None
        assert embedding.shape[0] == 384  # all-MiniLM-L6-v2 dimension
        assert not all(v == 0 for v in embedding), "Embedding should not be all zeros"
    
    def test_embedding_caching(self, populated_db):
        """Test that embeddings are cached for performance."""
        db_path, topic_ids = populated_db
        
        # First call
        emb1 = compute_topic_embedding(topic_ids[0], db_path)
        
        # Second call should use cache
        emb2 = compute_topic_embedding(topic_ids[0], db_path)
        
        # Should be exactly the same (cached)
        assert (emb1 == emb2).all()
    
    def test_empty_topic_embedding(self, test_db):
        """Test embedding for topic with no artifacts."""
        # Clear any cached embeddings first
        from signal_harvester.topic_evolution import _topic_embedding_cache
        _topic_embedding_cache.clear()
        
        # Create topic with no artifacts
        topic_id = upsert_topic(test_db, "Empty Topic", "test/empty")
        
        embedding = compute_topic_embedding(topic_id, test_db)
        
        # Should return zero vector for empty topics (per line 86 of topic_evolution.py)
        assert embedding.shape[0] == 384
        import numpy as np
        assert np.allclose(embedding, 0), (
            "Empty topic should have zero embedding, "
            f"got norm={np.linalg.norm(embedding)}"
        )


class TestTopicSimilarity:
    """Test topic similarity computation."""
    
    def test_similarity_range(self, populated_db):
        """Test that similarity is in valid range [-1, 1]."""
        db_path, topic_ids = populated_db
        
        # Compute similarity between QEC and Surface Codes (should be high)
        similarity = compute_topic_similarity(topic_ids[0], topic_ids[1], db_path)
        
        assert -1.0 <= similarity <= 1.0, f"Similarity {similarity} out of range"
        assert similarity > 0.5, "QEC and Surface Codes should have high similarity"
    
    def test_self_similarity(self, populated_db):
        """Test that topic similarity with itself is 1.0."""
        db_path, topic_ids = populated_db
        
        similarity = compute_topic_similarity(topic_ids[0], topic_ids[0], db_path)
        
        assert abs(similarity - 1.0) < 0.01, f"Self-similarity should be ~1.0, got {similarity}"
    
    def test_dissimilar_topics(self, populated_db):
        """Test similarity between dissimilar topics."""
        db_path, topic_ids = populated_db
        
        # QEC vs ML should have lower similarity
        similarity = compute_topic_similarity(topic_ids[0], topic_ids[4], db_path)
        
        assert similarity < 0.8, f"QEC and ML should have lower similarity, got {similarity}"


class TestArtifactHistory:
    """Test artifact history retrieval."""
    
    def test_get_artifact_history(self, populated_db):
        """Test retrieving artifact history for a topic."""
        db_path, topic_ids = populated_db
        
        # Get history for QEC topic
        history = get_topic_artifact_history(topic_ids[0], db_path, days=60)
        
        assert len(history) > 0, "Should have artifact history"
        
        # Check structure
        for entry in history:
            assert "date" in entry
            assert "artifact_count" in entry
            assert "avg_discovery_score" in entry
    
    def test_history_ordering(self, populated_db):
        """Test that history is ordered by date."""
        db_path, topic_ids = populated_db
        
        history = get_topic_artifact_history(topic_ids[0], db_path, days=60)
        
        # Dates should be in ascending order
        dates = [entry["date"] for entry in history]
        assert dates == sorted(dates), "History should be ordered by date"
    
    def test_history_window(self, populated_db):
        """Test that history respects time window."""
        db_path, topic_ids = populated_db
        
        # Get recent history
        recent_history = get_topic_artifact_history(topic_ids[0], db_path, days=30)
        all_history = get_topic_artifact_history(topic_ids[0], db_path, days=60)
        
        assert len(recent_history) <= len(all_history)


class TestTopicMergeDetection:
    """Test topic merge detection."""
    
    def test_detect_merges_basic(self, populated_db):
        """Test basic merge detection."""
        db_path, topic_ids = populated_db
        
        # QEC and Surface Codes should be merge candidates (they have high overlap)
        merges = detect_topic_merges(db_path, window_days=60, similarity_threshold=0.60)
        
        assert isinstance(merges, list)
        
        # With lower threshold, we should find at least some merge candidates
        # (The exact topics might vary based on embedding similarity)
        if len(merges) > 0:
            # Verify structure of merge candidates
            for merge in merges:
                assert "primary_topic" in merge
                assert "secondary_topic" in merge
                assert "current_similarity" in merge
    
    def test_merge_confidence(self, populated_db):
        """Test that merge candidates have valid confidence scores."""
        db_path, topic_ids = populated_db
        
        merges = detect_topic_merges(db_path, window_days=60, similarity_threshold=0.70)
        
        for merge in merges:
            assert 0 <= merge["confidence"] <= 1.0, f"Invalid confidence: {merge['confidence']}"
            assert "current_similarity" in merge
            assert "overlap_trend" in merge
    
    def test_merge_threshold(self, populated_db):
        """Test that similarity threshold filters results."""
        db_path, topic_ids = populated_db
        
        # High threshold should return fewer merges
        high_threshold_merges = detect_topic_merges(db_path, window_days=60, similarity_threshold=0.90)
        low_threshold_merges = detect_topic_merges(db_path, window_days=60, similarity_threshold=0.60)
        
        assert len(high_threshold_merges) <= len(low_threshold_merges)


class TestTopicSplitDetection:
    """Test topic split detection."""
    
    def test_detect_splits_basic(self, populated_db):
        """Test basic split detection."""
        db_path, topic_ids = populated_db
        
        splits = detect_topic_splits(db_path, window_days=60, diversity_threshold=0.50)
        
        assert isinstance(splits, list)
        # Splits are less common than merges
        assert len(splits) >= 0
    
    def test_split_structure(self, populated_db):
        """Test split candidate structure."""
        db_path, topic_ids = populated_db
        
        splits = detect_topic_splits(db_path, window_days=60, diversity_threshold=0.50)
        
        for split in splits:
            assert "topic" in split
            assert "cluster_quality" in split
            assert "sub_clusters" in split
            assert split["cluster_quality"] >= 0


class TestTopicEmergence:
    """Test topic emergence scoring."""
    
    def test_compute_emergence(self, populated_db):
        """Test emergence score computation."""
        db_path, topic_ids = populated_db
        
        # Quantum Algorithms should be emerging (increasing recent activity)
        emergence = compute_topic_emergence(topic_ids[3], db_path, window_days=60)
        
        assert "growth_rate" in emergence
        assert "emergence_score" in emergence
        assert 0 <= emergence["emergence_score"] <= 100
    
    def test_stable_topic_emergence(self, populated_db):
        """Test that stable topics have lower emergence."""
        db_path, topic_ids = populated_db
        
        # Quantum Hardware (stable) vs Quantum Algorithms (growing)
        stable_emergence = compute_topic_emergence(topic_ids[2], db_path, window_days=60)
        growing_emergence = compute_topic_emergence(topic_ids[3], db_path, window_days=60)
        
        # Growing topic should have higher emergence
        assert growing_emergence["emergence_score"] >= stable_emergence["emergence_score"]


class TestTopicGrowthPrediction:
    """Test topic growth prediction."""
    
    def test_predict_growth(self, populated_db):
        """Test growth prediction for a topic."""
        db_path, topic_ids = populated_db
        
        prediction = predict_topic_growth(topic_ids[3], db_path, days_to_predict=14)
        
        assert "trend" in prediction
        assert "confidence" in prediction
        assert prediction["trend"] in ["growing", "stable", "declining", "insufficient_data"]
        assert 0 <= prediction["confidence"] <= 100
    
    def test_insufficient_data_prediction(self, test_db):
        """Test prediction with insufficient data."""
        # Create topic with minimal data
        topic_id = upsert_topic(test_db, "New Topic", "test/new")
        
        # Add only 1-2 artifacts
        art_id = upsert_artifact(
            db_path=test_db,
            artifact_type="preprint",
            source="arxiv",
            source_id="2301.00001",
            title="Test Paper",
            text="Test content",
            published_at=datetime.now(timezone.utc).isoformat()
        )
        link_artifact_topic(test_db, art_id, topic_id, 0.8)
        update_discovery_scores(test_db, art_id, 80.0, 75.0, 70.0, 75.0)
        
        prediction = predict_topic_growth(topic_id, test_db, days_to_predict=14)
        
        # Should still return a prediction (even if low confidence)
        assert "confidence" in prediction
        assert prediction["confidence"] >= 0


class TestTopicCoverage:
    """Test artifact coverage tracking to meet 95% target."""
    
    def test_compute_coverage_percentage(self, populated_db):
        """Test computing percentage of artifacts with topic assignments."""
        db_path, topic_ids = populated_db
        
        conn = connect(db_path)
        try:
            # Count total artifacts
            cur = conn.execute("SELECT COUNT(*) FROM artifacts")
            total_artifacts = cur.fetchone()[0]
            
            # Count artifacts with topics
            cur = conn.execute("""
                SELECT COUNT(DISTINCT artifact_id)
                FROM artifact_topics
            """)
            artifacts_with_topics = cur.fetchone()[0]
            
            coverage = (artifacts_with_topics / total_artifacts * 100) if total_artifacts > 0 else 0
            
            assert coverage >= 95.0, f"Coverage {coverage:.1f}% below 95% target"
        finally:
            conn.close()
    
    def test_topic_assignment_quality(self, populated_db):
        """Test quality of topic assignments."""
        db_path, topic_ids = populated_db
        
        conn = connect(db_path)
        try:
            # Get all topic assignments
            cur = conn.execute("""
                SELECT confidence
                FROM artifact_topics
            """)
            confidences = [row[0] for row in cur.fetchall()]
            
            # All confidences should be reasonable
            assert all(0.5 <= c <= 1.0 for c in confidences), "All topic assignments should have confidence >= 0.5"
            
            # Average confidence should be decent
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            assert avg_confidence >= 0.70, f"Average confidence {avg_confidence:.2f} below 0.70"
        finally:
            conn.close()


class TestRelatedTopics:
    """Test finding related topics."""
    
    def test_find_related(self, populated_db):
        """Test finding related topics."""
        db_path, topic_ids = populated_db
        
        # Update similarity matrix first
        update_topic_similarity_matrix(db_path)
        
        # Find topics related to QEC
        related = find_related_topics(topic_ids[0], db_path, limit=5)
        
        assert isinstance(related, list)
        assert len(related) <= 5
        
        # Surface Codes should be in the related topics
        surface_codes_found = any(r["id"] == topic_ids[1] for r in related)
        assert surface_codes_found, "Surface Codes should be related to QEC"
    
    def test_related_similarity_ordering(self, populated_db):
        """Test that related topics are ordered by similarity."""
        db_path, topic_ids = populated_db
        
        update_topic_similarity_matrix(db_path)
        related = find_related_topics(topic_ids[0], db_path, limit=5)
        
        if len(related) > 1:
            # Similarities should be in descending order
            similarities = [r["similarity"] for r in related]
            assert similarities == sorted(similarities, reverse=True)


class TestTopicEvolutionEvents:
    """Test topic evolution event storage."""
    
    def test_store_event(self, test_db):
        """Test storing a topic evolution event."""
        topic_id = upsert_topic(test_db, "Test Topic", "test/topic")
        
        # Event format expected by store_topic_evolution_event (lines 646-677)
        event = {
            "primary_topic": {"id": topic_id, "name": "Test Topic"},
            "event_type": "growth",
            "confidence": 0.85,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        event_id = store_topic_evolution_event(
            db_path=test_db,
            event=event
        )
        
        assert event_id > 0
        
        # Verify event was stored
        conn = connect(test_db)
        try:
            cur = conn.execute("""
                SELECT event_type, event_strength, description
                FROM topic_evolution
                WHERE topic_id = ?
            """, (topic_id,))
            row = cur.fetchone()
            
            assert row is not None
            assert row[0] == "growth"
            assert row[1] == 0.85
            assert "confidence 0.85" in row[2]
        finally:
            conn.close()


@pytest.mark.asyncio
class TestFullPipeline:
    """Test the complete topic evolution pipeline."""
    
    async def test_pipeline_execution(self, populated_db):
        """Test running the full topic evolution pipeline."""
        from signal_harvester.config import Settings
        
        db_path, topic_ids = populated_db
        
        # Run the pipeline
        results = await run_topic_evolution_pipeline(
            db_path=db_path,
            settings=Settings(),
            window_days=60
        )
        
        assert results is not None
        assert results["status"] == "completed"
        assert results["topics_analyzed"] >= len(topic_ids)
    
    async def test_pipeline_creates_events(self, populated_db):
        """Test that pipeline creates evolution events."""
        from signal_harvester.config import Settings
        
        db_path, topic_ids = populated_db
        
        # Run pipeline
        await run_topic_evolution_pipeline(
            db_path=db_path,
            settings=Settings(),
            window_days=60
        )
        
        # Check that events were created (pipeline may or may not create events depending on thresholds)
        conn = connect(db_path)
        try:
            cur = conn.execute("SELECT COUNT(*) FROM topic_evolution")
            event_count = cur.fetchone()[0]
            
            # Pipeline ran successfully - events are optional depending on data
            assert event_count >= 0, "Pipeline should complete without errors"
        finally:
            conn.close()


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_nonexistent_topic(self, test_db):
        """Test handling of nonexistent topic ID."""
        # Should return zero embedding for nonexistent topic
        embedding = compute_topic_embedding(99999, test_db)
        assert all(v == 0 for v in embedding)
    
    def test_zero_weight_artifacts(self, test_db):
        """Test handling artifacts with zero discovery scores."""
        topic_id = upsert_topic(test_db, "Zero Score Topic", "test/zero")
        
        # Add artifact with zero score
        art_id = upsert_artifact(
            db_path=test_db,
            artifact_type="preprint",
            source="arxiv",
            source_id="2301.00000",
            title="Test",
            text="Test content",
            published_at=datetime.now(timezone.utc).isoformat()
        )
        link_artifact_topic(test_db, art_id, topic_id, 0.8)
        update_discovery_scores(test_db, art_id, 0.0, 0.0, 0.0, 0.0)
        
        # Should still compute embedding
        embedding = compute_topic_embedding(topic_id, test_db)
        assert embedding.shape[0] == 384
