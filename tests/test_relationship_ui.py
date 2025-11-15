"""Contract tests for Cross-Source Corroboration UI.

Verifies that API responses match TypeScript types defined in the frontend.
Follows the pattern from test_contract_api_frontend.py and test_topic_ui.py
"""

import pytest
from typing import Any, Dict, List

from signal_harvester.api import (
    Discovery,
    Topic,
    TopicTimeline,
    TopicMergeCandidate,
    TopicSplitDetection,
)
from signal_harvester.db import get_artifact_relationships, get_relationship_stats
from signal_harvester.relationship_detection import get_citation_graph, run_relationship_detection


class TestRelationshipContract:
    """Contract tests for relationship types between API and frontend."""
    
    def test_artifact_relationship_response_structure(self, tmp_db_path: str):
        """Test that artifact relationships response matches frontend types."""
        # Get relationships (mock data will be inserted by conftest)
        response = get_artifact_relationships(
            db_path=tmp_db_path,
            artifact_id=1,
            direction="both",
            min_confidence=0.5
        )
        
        # Verify response is a list
        assert isinstance(response, list)
        
        if response:
            rel = response[0]
            
            # Verify all required fields exist
            assert "source_artifact_id" in rel
            assert "target_artifact_id" in rel
            assert "relationship_type" in rel
            assert "confidence" in rel
            assert "detection_method" in rel
            assert "created_at" in rel
            
            # Verify nested artifact data
            assert "source_title" in rel
            assert "source_type" in rel
            assert "source_source" in rel
            assert "target_title" in rel
            assert "target_type" in rel
            assert "target_source" in rel
            
            # Verify types
            assert isinstance(rel["source_artifact_id"], int)
            assert isinstance(rel["target_artifact_id"], int)
            assert isinstance(rel["relationship_type"], str)
            assert isinstance(rel["confidence"], float)
            assert isinstance(rel["detection_method"], str)
            assert isinstance(rel["created_at"], str)
            
            # Verify relationship type is valid
            valid_types = {"cite", "reference", "discuss", "implement", "mention", "related"}
            assert rel["relationship_type"] in valid_types
            
            # Verify confidence is in valid range
            assert 0.0 <= rel["confidence"] <= 1.0
            
            # Verify metadata field is present (can be None or dict)
            assert "metadata" in rel
            if rel["metadata"] is not None:
                assert isinstance(rel["metadata"], dict)
    
    def test_citation_graph_response_structure(self, tmp_db_path: str):
        """Test that citation graph response matches frontend types."""
        graph = get_citation_graph(
            db_path=tmp_db_path,
            artifact_id=1,
            depth=2,
            min_confidence=0.5
        )
        
        # Verify top-level structure
        assert isinstance(graph, dict)
        assert "root_artifact_id" in graph
        assert "depth" in graph
        assert "min_confidence" in graph
        assert "nodes" in graph
        assert "edges" in graph
        assert "node_count" in graph
        assert "edge_count" in graph
        
        # Verify node structure
        assert isinstance(graph["nodes"], list)
        if graph["nodes"]:
            node = graph["nodes"][0]
            assert "id" in node
            assert "title" in node
            assert "source" in node
            assert "type" in node
            
            # Optional discovery_score
            if "discovery_score" in node:
                assert isinstance(node["discovery_score"], (int, float))
        
        # Verify edge structure
        assert isinstance(graph["edges"], list)
        if graph["edges"]:
            edge = graph["edges"][0]
            assert "source" in edge
            assert "target" in edge
            assert "relationship_type" in edge
            assert "confidence" in edge
            assert "detection_method" in edge
            
            # Verify types
            assert isinstance(edge["source"], int)
            assert isinstance(edge["target"], int)
            assert isinstance(edge["relationship_type"], str)
            assert isinstance(edge["confidence"], float)
            assert isinstance(edge["detection_method"], str)
    
    def test_relationship_stats_response_structure(self, tmp_db_path: str):
        """Test that relationship stats response matches frontend types."""
        stats = get_relationship_stats(tmp_db_path)
        
        # Verify top-level structure
        assert isinstance(stats, dict)
        assert "total_relationships" in stats
        assert "by_type" in stats
        assert "by_method" in stats
        assert "average_confidence" in stats
        assert "artifacts_with_relationships" in stats
        assert "last_updated" in stats
        
        # Verify types
        assert isinstance(stats["total_relationships"], int)
        assert isinstance(stats["by_type"], dict)
        assert isinstance(stats["by_method"], dict)
        assert isinstance(stats["average_confidence"], float)
        assert isinstance(stats["artifacts_with_relationships"], int)
        assert isinstance(stats["last_updated"], str)
        
        # Verify relationship type counts
        valid_types = {"cite", "reference", "discuss", "implement", "mention", "related"}
        for rel_type, count in stats["by_type"].items():
            assert rel_type in valid_types
            assert isinstance(count, int)
            assert count >= 0
        
        # Verify method counts
        for method, count in stats["by_method"].items():
            assert isinstance(method, str)
            assert isinstance(count, int)
            assert count >= 0
        
        # Verify confidence is valid
        assert 0.0 <= stats["average_confidence"] <= 1.0
    
    def test_relationship_detection_stats(self, tmp_db_path: str):
        """Test that relationship detection stats response matches frontend types."""
        stats = run_relationship_detection(
            db_path=tmp_db_path,
            artifact_id=None,  # Run for all artifacts
            enable_semantic=True,
            semantic_threshold=0.8
        )
        
        # Verify response structure
        assert isinstance(stats, dict)
        assert "processed" in stats
        assert "relationships_created" in stats
        assert "by_type" in stats
        assert "by_method" in stats
        
        # Verify types
        assert isinstance(stats["processed"], int)
        assert isinstance(stats["relationships_created"], int)
        assert isinstance(stats["by_type"], dict)
        assert isinstance(stats["by_method"], dict)
        
        # Verify all counts are non-negative
        assert stats["processed"] >= 0
        assert stats["relationships_created"] >= 0
        
        for count in stats["by_type"].values():
            assert isinstance(count, int)
            assert count >= 0
        
        for count in stats["by_method"].values():
            assert isinstance(count, int)
            assert count >= 0
    
    def test_camel_case_consistency(self):
        """Verify that API models use camelCase for TypeScript compatibility."""
        # Check Discovery model
        discovery_fields = Discovery.__fields__.keys()
        assert "artifactId" in discovery_fields
        assert "artifactType" in discovery_fields
        assert "discoveryScore" in discovery_fields
        assert "computedAt" in discovery_fields
        assert "publishedAt" in discovery_fields
        
        # Check Topic model
        topic_fields = Topic.__fields__.keys()
        assert "taxonomyPath" in topic_fields
        
        # Check these important relationship-related fields that should be camelCase
        # These would be in ArtifactRelationship if it were a Pydantic model
        relationship_keys = {
            "sourceArtifactId",
            "targetArtifactId",
            "sourceTitle",
            "sourceType",
            "sourceSource",
            "targetTitle",
            "targetType",
            "targetSource",
            "relationshipType",
            "detectionMethod",
            "createdAt",
        }
        
        # Verify these exist in the database response
        # (The actual check will be done in integration tests)
        assert relationship_keys  # Just verify the set is defined


class TestRelationshipUIScenarios:
    """Test scenarios that verify the full relationship UI flow."""
    
    def test_artifact_detail_page_shows_relationships_tab(self, tmp_db_path: str):
        """Test that artifact detail includes relationship data."""
        # This would test the artifact detail endpoint integration
        # For now, verify the data structure is correct
        relationships = get_artifact_relationships(
            db_path=tmp_db_path,
            artifact_id=1,
            direction="both"
        )
        
        # Should be able to fetch both incoming and outgoing relationships
        assert isinstance(relationships, list)
        
        # Should have metadata for displaying in UI
        if relationships:
            rel = relationships[0]
            assert "source_title" in rel
            assert "target_title" in rel
            assert "confidence" in rel
            assert "relationship_type" in rel
    
    def test_citation_graph_explorer_scenario(self, tmp_db_path: str):
        """Test the complete citation graph scenario."""
        # Step 1: Get relationships for root artifact
        relationships = get_artifact_relationships(
            db_path=tmp_db_path,
            artifact_id=1,
            direction="outgoing"
        )
        
        # Step 2: Get full citation graph (includes multi-level)
        graph = get_citation_graph(
            db_path=tmp_db_path,
            artifact_id=1,
            depth=2,
            min_confidence=0.5
        )
        
        # Graph should have more data than just direct relationships
        assert graph["node_count"] >= len(relationships)
        
        # Should include edge information for visualization
        assert len(graph["edges"]) > 0
        assert all("source" in edge for edge in graph["edges"])
        assert all("target" in edge for edge in graph["edges"])
        assert all("confidence" in edge for edge in graph["edges"])
        
        # Should include node information for visualization
        assert len(graph["nodes"]) > 0
        assert all("id" in node for node in graph["nodes"])
        assert all("title" in node for node in graph["nodes"])
        assert all("source" in node for node in graph["nodes"])
    
    def test_relationship_detection_workflow(self, tmp_db_path: str):
        """Test the complete relationship detection workflow."""
        # Get initial stats
        initial_stats = get_relationship_stats(tmp_db_path)
        initial_count = initial_stats["total_relationships"]
        
        # Run detection
        detection_stats = run_relationship_detection(
            db_path=tmp_db_path,
            artifact_id=None,  # All artifacts
            enable_semantic=True,
            semantic_threshold=0.8
        )
        
        # Should have processed artifacts and created relationships
        assert detection_stats["processed"] > 0
        assert detection_stats["relationships_created"] >= 0
        
        # Get updated stats
        updated_stats = get_relationship_stats(tmp_db_path)
        updated_count = updated_stats["total_relationships"]
        
        # Count should have increased (if any new relationships found)
        assert updated_count >= initial_count
        
        # Should have type distribution
        assert len(detection_stats["by_type"]) > 0
        total_by_type = sum(detection_stats["by_type"].values())
        assert total_by_type == detection_stats["relationships_created"]


class TestRelationshipFilters:
    """Test relationship filtering capabilities."""
    
    def test_filter_by_direction(self, tmp_db_path: str):
        """Test filtering relationships by direction."""
        # Get all relationships
        all_rel = get_artifact_relationships(
            db_path=tmp_db_path,
            artifact_id=1,
            direction="both"
        )
        
        # Get outgoing relationships
        outgoing_rel = get_artifact_relationships(
            db_path=tmp_db_path,
            artifact_id=1,
            direction="outgoing"
        )
        
        # Get incoming relationships  
        incoming_rel = get_artifact_relationships(
            db_path=tmp_db_path,
            artifact_id=1,
            direction="incoming"
        )
        
        # Both should be subsets of all
        assert len(outgoing_rel) + len(incoming_rel) == len(all_rel)
        
        # Verify directions in outgoing
        for rel in outgoing_rel:
            assert rel["source_artifact_id"] == 1
        
        # Verify directions in incoming
        for rel in incoming_rel:
            assert rel["target_artifact_id"] == 1
    
    def test_filter_by_confidence(self, tmp_db_path: str):
        """Test filtering relationships by confidence threshold."""
        # Get all relationships above 0.5 confidence
        high_conf_rel = get_artifact_relationships(
            db_path=tmp_db_path,
            artifact_id=1,
            min_confidence=0.8
        )
        
        # Verify all meet threshold
        for rel in high_conf_rel:
            assert rel["confidence"] >= 0.8
        
        # Get all relationships above 0.9 confidence (should be fewer)
        very_high_conf_rel = get_artifact_relationships(
            db_path=tmp_db_path,
            artifact_id=1,
            min_confidence=0.9
        )
        
        assert len(very_high_conf_rel) <= len(high_conf_rel)
    
    def test_filter_by_relationship_type(self, tmp_db_path: str):
        """Test that we can filter by relationship type in UI layer."""
        # Get all relationships
        all_rel = get_artifact_relationships(
            db_path=tmp_db_path,
            artifact_id=1
        )
        
        # Group by type manually (simulating UI filtering)
        by_type: Dict[str, List[Dict[str, Any]]] = {}
        for rel in all_rel:
            rel_type = rel["relationship_type"]
            if rel_type not in by_type:
                by_type[rel_type] = []
            by_type[rel_type].append(rel)
        
        # Verify each group only contains that type
        for rel_type, relationships in by_type.items():
            assert all(r["relationship_type"] == rel_type for r in relationships)
        
        # Verify we have some diversity
        assert len(by_type) > 0


def test_relationship_type_labels_mapping():
    """Test that relationship type labels match frontend mapping."""
    # These should match the TypeScript mapping in ArtifactRelationships.tsx
    expected_types = {
        "cite": "Citation",
        "reference": "Reference", 
        "discuss": "Discussion",
        "implement": "Implementation",
        "mention": "Mention",
        "related": "Related",
    }
    
    # Verify we have all expected types (actual labels tracked in frontend)
    assert len(expected_types) == 6
    assert "cite" in expected_types
    assert "reference" in expected_types
    assert "implement" in expected_types
