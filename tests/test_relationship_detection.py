"""Tests for cross-source corroboration and relationship detection."""

from __future__ import annotations

import os
import tempfile
from typing import Any

import pytest

import signal_harvester.db
from signal_harvester.db import (
    create_artifact_relationship,
    get_artifact_relationships,
    get_relationship_stats,
    init_db,
    run_migrations,
    upsert_artifact,
)
from signal_harvester.relationship_detection import (
    compute_semantic_similarity,
    detect_citation_relationships,
    detect_semantic_relationships,
    extract_arxiv_ids,
    extract_dois,
    extract_github_repos,
    get_citation_graph,
    run_relationship_detection,
)


@pytest.fixture
def test_db():
    """Create a temporary test database."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    # Initialize with all migrations
    init_db(path)
    run_migrations(path)
    
    yield path
    
    # Cleanup
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def sample_artifacts(test_db):
    """Create sample artifacts for testing."""
    # arXiv paper
    arxiv_id = upsert_artifact(
        db_path=test_db,
        artifact_type="preprint",
        source="arxiv",
        source_id="2301.12345",
        title="Attention Is All You Need: A Survey",
        text=(
            "We present a comprehensive survey of transformer architectures "
            "and their applications in natural language processing."
        ),
        url="https://arxiv.org/abs/2301.12345",
        published_at="2023-01-15T00:00:00Z",
    )
    
    # GitHub repo implementing the paper
    github_id = upsert_artifact(
        db_path=test_db,
        artifact_type="repo",
        source="github",
        source_id="huggingface/transformers",
        title="Transformers: State-of-the-art NLP",
        text="Implementation of transformer models including BERT, GPT, T5. See arXiv:2301.12345 for details.",
        url="https://github.com/huggingface/transformers",
        published_at="2023-01-20T00:00:00Z",
    )
    
    # Tweet discussing the paper
    tweet_id = upsert_artifact(
        db_path=test_db,
        artifact_type="tweet",
        source="x",
        source_id="1234567890",
        title="Amazing new paper on transformers!",
        text=(
            "Just read arxiv.org/abs/2301.12345 - great survey on attention mechanisms. "
            "Check out the implementation at github.com/huggingface/transformers"
        ),
        url="https://twitter.com/user/status/1234567890",
        published_at="2023-01-22T00:00:00Z",
    )
    
    # Another arXiv paper (related but different)
    arxiv2_id = upsert_artifact(
        db_path=test_db,
        artifact_type="preprint",
        source="arxiv",
        source_id="2302.98765",
        title="Vision Transformers for Image Recognition",
        text=(
            "We apply transformer architectures to computer vision tasks, "
            "achieving state-of-the-art results on ImageNet."
        ),
        url="https://arxiv.org/abs/2302.98765",
        published_at="2023-02-10T00:00:00Z",
    )
    
    return {
        "arxiv": arxiv_id,
        "github": github_id,
        "tweet": tweet_id,
        "arxiv2": arxiv2_id,
    }


# Test pattern extraction


def test_extract_arxiv_ids():
    """Test arXiv ID extraction from text."""
    text = "Check out arxiv:2301.12345 and arXiv.org/abs/2302.98765 for details"
    ids = extract_arxiv_ids(text)
    assert len(ids) == 2
    assert "2301.12345" in ids
    assert "2302.98765" in ids


def test_extract_arxiv_ids_various_formats():
    """Test arXiv ID extraction with various formats."""
    assert extract_arxiv_ids("arXiv:2301.12345") == ["2301.12345"]
    assert extract_arxiv_ids("arxiv.org/abs/2301.12345") == ["2301.12345"]
    assert extract_arxiv_ids("arXiv 2301.12345") == ["2301.12345"]
    assert extract_arxiv_ids("arxiv/2301.12345") == ["2301.12345"]


def test_extract_arxiv_ids_empty():
    """Test arXiv ID extraction from empty text."""
    assert extract_arxiv_ids("") == []
    assert extract_arxiv_ids(None) == []
    assert extract_arxiv_ids("no arxiv ids here") == []


def test_extract_dois():
    """Test DOI extraction from text."""
    text = "See https://doi.org/10.1234/example.2023.01 and doi:10.5678/test"
    dois = extract_dois(text)
    assert len(dois) == 2
    assert "10.1234/example.2023.01" in dois
    assert "10.5678/test" in dois


def test_extract_dois_empty():
    """Test DOI extraction from empty text."""
    assert extract_dois("") == []
    assert extract_dois(None) == []


def test_extract_github_repos():
    """Test GitHub repository extraction from text."""
    text = "Check out github.com/openai/gpt-4 and https://github.com/pytorch/pytorch for implementations"
    repos = extract_github_repos(text)
    assert len(repos) == 2
    assert "openai/gpt-4" in repos
    assert "pytorch/pytorch" in repos


def test_extract_github_repos_empty():
    """Test GitHub repo extraction from empty text."""
    assert extract_github_repos("") == []
    assert extract_github_repos(None) == []


# Test relationship detection


def test_detect_citation_relationships_arxiv_in_tweet(test_db, sample_artifacts):
    """Test detecting when a tweet cites an arXiv paper."""
    from signal_harvester.db import get_artifact_by_id
    
    tweet = get_artifact_by_id(test_db, sample_artifacts["tweet"])
    relationships = detect_citation_relationships(test_db, tweet)
    
    # Tweet mentions both arXiv paper and GitHub repo
    assert len(relationships) >= 2
    
    # Check that we found the arXiv reference
    arxiv_rels = [r for r in relationships if r["target_artifact_id"] == sample_artifacts["arxiv"]]
    assert len(arxiv_rels) >= 1
    assert arxiv_rels[0]["confidence"] >= 0.90


def test_detect_citation_relationships_github_implements_arxiv(test_db, sample_artifacts):
    """Test detecting when a GitHub repo implements an arXiv paper."""
    from signal_harvester.db import get_artifact_by_id
    
    github = get_artifact_by_id(test_db, sample_artifacts["github"])
    relationships = detect_citation_relationships(test_db, github)
    
    # Should find relationship to arXiv paper
    implement_rels = [r for r in relationships if r["relationship_type"] == "implement"]
    assert len(implement_rels) >= 1
    
    # Check confidence
    impl_rel = implement_rels[0]
    assert impl_rel["confidence"] >= 0.90


def test_detect_citation_relationships_no_matches(test_db, sample_artifacts):
    """Test detection when there are no matching references."""
    from signal_harvester.db import get_artifact_by_id
    
    # The second arXiv paper doesn't reference anything
    arxiv2 = get_artifact_by_id(test_db, sample_artifacts["arxiv2"])
    relationships = detect_citation_relationships(test_db, arxiv2)
    
    # Should find no explicit citations
    assert len(relationships) == 0


def test_compute_semantic_similarity(test_db, sample_artifacts):
    """Test semantic similarity computation."""
    from signal_harvester.db import get_artifact_by_id
    
    arxiv1 = get_artifact_by_id(test_db, sample_artifacts["arxiv"])
    arxiv2 = get_artifact_by_id(test_db, sample_artifacts["arxiv2"])
    
    # Both are about transformers, should have some similarity
    similarity = compute_semantic_similarity(arxiv1, arxiv2)
    assert 0.0 <= similarity <= 1.0
    # Related papers should have some similarity (exact value depends on model)
    assert similarity > 0.3  # Conservative threshold


def test_compute_semantic_similarity_empty_text():
    """Test semantic similarity with empty text."""
    artifact1 = {"title": "", "text": ""}
    artifact2 = {"title": "Test", "text": "Content"}
    
    similarity = compute_semantic_similarity(artifact1, artifact2)
    assert similarity == 0.0


def test_detect_semantic_relationships(test_db, sample_artifacts):
    """Test semantic relationship detection."""
    from signal_harvester.db import get_artifact_by_id
    
    # Use the arXiv paper as source
    arxiv1 = get_artifact_by_id(test_db, sample_artifacts["arxiv"])
    
    # Should find related artifacts from different sources
    relationships = detect_semantic_relationships(
        db_path=test_db,
        source_artifact=arxiv1,
        min_similarity=0.3,  # Conservative threshold
        max_results=10,
    )
    
    # Should find at least the GitHub repo (same topic, different source)
    assert len(relationships) >= 1
    
    # Check that all relationships meet threshold
    for rel in relationships:
        assert rel["confidence"] >= 0.3
        assert rel["detection_method"] == "semantic_similarity"


def test_detect_semantic_relationships_different_sources_only(test_db, sample_artifacts):
    """Test that semantic detection only finds cross-source relationships."""
    from signal_harvester.db import get_artifact_by_id
    
    arxiv1 = get_artifact_by_id(test_db, sample_artifacts["arxiv"])
    
    relationships = detect_semantic_relationships(
        db_path=test_db,
        source_artifact=arxiv1,
        min_similarity=0.0,  # Accept all similarities
    )
    
    # Should not find the other arXiv paper (same source)
    arxiv_targets = [
        r for r in relationships
        if r["target_artifact_id"] == sample_artifacts["arxiv2"]
    ]
    assert len(arxiv_targets) == 0


# Test database operations


def test_create_artifact_relationship(test_db, sample_artifacts):
    """Test creating a relationship between artifacts."""
    rel_id = create_artifact_relationship(
        db_path=test_db,
        source_artifact_id=sample_artifacts["tweet"],
        target_artifact_id=sample_artifacts["arxiv"],
        relationship_type="reference",
        confidence=0.95,
        detection_method="arxiv_id_match",
        metadata={"arxiv_id": "2301.12345"},
    )
    
    assert rel_id is not None
    assert rel_id > 0


def test_create_artifact_relationship_duplicate(test_db, sample_artifacts):
    """Test that duplicate relationships update confidence."""
    # Create initial relationship
    create_artifact_relationship(
        db_path=test_db,
        source_artifact_id=sample_artifacts["tweet"],
        target_artifact_id=sample_artifacts["arxiv"],
        relationship_type="reference",
        confidence=0.80,
    )
    
    # Try to create duplicate with higher confidence
    rel_id = create_artifact_relationship(
        db_path=test_db,
        source_artifact_id=sample_artifacts["tweet"],
        target_artifact_id=sample_artifacts["arxiv"],
        relationship_type="reference",
        confidence=0.95,
    )
    
    # Should return None for duplicate
    assert rel_id is None
    
    # Check that confidence was updated
    rels = get_artifact_relationships(
        db_path=test_db,
        artifact_id=sample_artifacts["tweet"],
        direction="outgoing",
    )
    
    assert len(rels) == 1
    assert rels[0]["confidence"] == 0.95


def test_get_artifact_relationships_outgoing(test_db, sample_artifacts):
    """Test getting outgoing relationships."""
    # Create relationships
    create_artifact_relationship(
        db_path=test_db,
        source_artifact_id=sample_artifacts["tweet"],
        target_artifact_id=sample_artifacts["arxiv"],
        relationship_type="reference",
        confidence=0.95,
    )
    
    create_artifact_relationship(
        db_path=test_db,
        source_artifact_id=sample_artifacts["tweet"],
        target_artifact_id=sample_artifacts["github"],
        relationship_type="reference",
        confidence=0.90,
    )
    
    # Get outgoing relationships
    rels = get_artifact_relationships(
        db_path=test_db,
        artifact_id=sample_artifacts["tweet"],
        direction="outgoing",
    )
    
    assert len(rels) == 2
    # Should be sorted by confidence (descending)
    assert rels[0]["confidence"] >= rels[1]["confidence"]


def test_get_artifact_relationships_incoming(test_db, sample_artifacts):
    """Test getting incoming relationships."""
    # Create relationship
    create_artifact_relationship(
        db_path=test_db,
        source_artifact_id=sample_artifacts["tweet"],
        target_artifact_id=sample_artifacts["arxiv"],
        relationship_type="reference",
        confidence=0.95,
    )
    
    # Get incoming relationships for arXiv paper
    rels = get_artifact_relationships(
        db_path=test_db,
        artifact_id=sample_artifacts["arxiv"],
        direction="incoming",
    )
    
    assert len(rels) == 1
    assert rels[0]["source_artifact_id"] == sample_artifacts["tweet"]


def test_get_artifact_relationships_both(test_db, sample_artifacts):
    """Test getting bidirectional relationships."""
    # Create bidirectional relationships
    create_artifact_relationship(
        db_path=test_db,
        source_artifact_id=sample_artifacts["tweet"],
        target_artifact_id=sample_artifacts["arxiv"],
        relationship_type="reference",
        confidence=0.95,
    )
    
    create_artifact_relationship(
        db_path=test_db,
        source_artifact_id=sample_artifacts["arxiv"],
        target_artifact_id=sample_artifacts["arxiv2"],
        relationship_type="cite",
        confidence=0.90,
    )
    
    # Get all relationships for arXiv paper
    rels = get_artifact_relationships(
        db_path=test_db,
        artifact_id=sample_artifacts["arxiv"],
        direction="both",
    )
    
    assert len(rels) == 2


def test_get_artifact_relationships_min_confidence(test_db, sample_artifacts):
    """Test filtering relationships by confidence."""
    # Create relationships with different confidences
    create_artifact_relationship(
        db_path=test_db,
        source_artifact_id=sample_artifacts["tweet"],
        target_artifact_id=sample_artifacts["arxiv"],
        relationship_type="reference",
        confidence=0.95,
    )
    
    create_artifact_relationship(
        db_path=test_db,
        source_artifact_id=sample_artifacts["tweet"],
        target_artifact_id=sample_artifacts["github"],
        relationship_type="reference",
        confidence=0.60,
    )
    
    # Get only high-confidence relationships
    rels = get_artifact_relationships(
        db_path=test_db,
        artifact_id=sample_artifacts["tweet"],
        direction="outgoing",
        min_confidence=0.80,
    )
    
    assert len(rels) == 1
    assert rels[0]["confidence"] >= 0.80


def test_get_relationship_stats(test_db, sample_artifacts):
    """Test relationship statistics."""
    # Create various relationships
    create_artifact_relationship(
        db_path=test_db,
        source_artifact_id=sample_artifacts["tweet"],
        target_artifact_id=sample_artifacts["arxiv"],
        relationship_type="reference",
        confidence=0.95,
    )
    
    create_artifact_relationship(
        db_path=test_db,
        source_artifact_id=sample_artifacts["github"],
        target_artifact_id=sample_artifacts["arxiv"],
        relationship_type="implement",
        confidence=0.90,
    )
    
    create_artifact_relationship(
        db_path=test_db,
        source_artifact_id=sample_artifacts["arxiv"],
        target_artifact_id=sample_artifacts["arxiv2"],
        relationship_type="related",
        confidence=0.70,
    )
    
    stats = get_relationship_stats(test_db)
    
    assert stats["total_relationships"] == 3
    assert stats["high_confidence_count"] == 2  # ≥0.8
    assert stats["artifacts_with_relationships"] >= 3
    assert len(stats["by_type"]) >= 2  # At least 2 different types


def test_run_relationship_detection(test_db, sample_artifacts):
    """Test running full relationship detection pipeline."""
    stats = run_relationship_detection(
        db_path=test_db,
        artifact_id=None,  # Process all
        enable_semantic=True,
        semantic_threshold=0.70,
    )
    
    assert stats["processed"] == 4  # All 4 artifacts
    assert stats["relationships_created"] >= 2  # At least tweet->arxiv and github->arxiv
    assert "by_type" in stats
    assert "by_method" in stats


def test_run_relationship_detection_specific_artifact(test_db, sample_artifacts):
    """Test relationship detection for specific artifact."""
    stats = run_relationship_detection(
        db_path=test_db,
        artifact_id=sample_artifacts["tweet"],
        enable_semantic=False,  # Only citation detection
        semantic_threshold=0.80,
    )
    
    assert stats["processed"] == 1
    assert stats["relationships_created"] >= 1  # Should find arXiv reference


def test_run_relationship_detection_no_semantic(test_db, sample_artifacts):
    """Test detection with semantic similarity disabled."""
    stats = run_relationship_detection(
        db_path=test_db,
        artifact_id=None,
        enable_semantic=False,
        semantic_threshold=0.80,
    )
    
    # Should only find citation-based relationships
    assert stats["processed"] == 4
    assert "arxiv_id_match" in stats.get("by_method", {}) or "github_url_match" in stats.get("by_method", {})
    assert "semantic_similarity" not in stats.get("by_method", {})


def test_get_citation_graph(test_db, sample_artifacts):
    """Test citation graph generation."""
    # Create some relationships
    create_artifact_relationship(
        db_path=test_db,
        source_artifact_id=sample_artifacts["tweet"],
        target_artifact_id=sample_artifacts["arxiv"],
        relationship_type="reference",
        confidence=0.95,
    )
    
    create_artifact_relationship(
        db_path=test_db,
        source_artifact_id=sample_artifacts["github"],
        target_artifact_id=sample_artifacts["arxiv"],
        relationship_type="implement",
        confidence=0.90,
    )
    
    # Get citation graph
    graph = get_citation_graph(
        db_path=test_db,
        artifact_id=sample_artifacts["arxiv"],
        depth=2,
        min_confidence=0.5,
    )
    
    assert graph["root_artifact_id"] == sample_artifacts["arxiv"]
    assert graph["depth"] == 2
    assert len(graph["nodes"]) >= 2  # At least arXiv + tweet or github
    assert len(graph["edges"]) >= 1


def test_get_citation_graph_depth_limiting(test_db, sample_artifacts):
    """Test that citation graph respects depth limit."""
    # Create chain: tweet -> arxiv -> arxiv2 -> github
    create_artifact_relationship(
        db_path=test_db,
        source_artifact_id=sample_artifacts["tweet"],
        target_artifact_id=sample_artifacts["arxiv"],
        relationship_type="reference",
        confidence=0.95,
    )
    
    create_artifact_relationship(
        db_path=test_db,
        source_artifact_id=sample_artifacts["arxiv"],
        target_artifact_id=sample_artifacts["arxiv2"],
        relationship_type="cite",
        confidence=0.90,
    )
    
    create_artifact_relationship(
        db_path=test_db,
        source_artifact_id=sample_artifacts["arxiv2"],
        target_artifact_id=sample_artifacts["github"],
        relationship_type="related",
        confidence=0.80,
    )
    
    # Get graph with depth=1
    graph_d1 = get_citation_graph(
        db_path=test_db,
        artifact_id=sample_artifacts["tweet"],
        depth=1,
        min_confidence=0.5,
    )
    
    # Should only include direct neighbors
    assert graph_d1["depth"] == 1
    assert len(graph_d1["nodes"]) <= 3  # tweet + connections at depth 1
    
    # Get graph with depth=2
    graph_d2 = get_citation_graph(
        db_path=test_db,
        artifact_id=sample_artifacts["tweet"],
        depth=2,
        min_confidence=0.5,
    )
    
    # Should include more nodes
    assert graph_d2["depth"] == 2
    assert len(graph_d2["nodes"]) >= len(graph_d1["nodes"])


# Helper function for tests
def get_artifact_by_id(db_path: str, artifact_id: int) -> dict[str, Any]:
    """Get artifact by ID (helper for tests)."""
    from signal_harvester.db import list_artifacts_for_scoring
    
    artifacts = list_artifacts_for_scoring(db_path)
    for artifact in artifacts:
        if artifact["id"] == artifact_id:
            return artifact
    
    raise ValueError(f"Artifact {artifact_id} not found")


# Add helper to db module for testing
signal_harvester.db.get_artifact_by_id = get_artifact_by_id
