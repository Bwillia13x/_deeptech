"""Tests for Topic Evolution UI API endpoints.

Follows the same pattern as test_contract_api_frontend.py
"""

import pytest
from pydantic import ValidationError

from signal_harvester.api import (
    Topic,
    TopicTimeline,
    TopicEvolutionEvent,
    TopicMergeCandidate,
    TopicSplitDetection,
    TopicEmergenceMetrics,
    TopicGrowthPrediction,
    RelatedTopic,
    TopicStats,
)


class TestTopicContracts:
    """Test Topic model contract with frontend types."""
    
    def test_topic_response_model(self):
        """Topic model should match frontend Topic type."""
        topic_data = {
            "id": 1,
            "name": "quantum computing",
            "taxonomyPath": "physics/computing",
            "description": "Research on quantum computation",
            "artifactCount": 156,
            "avgDiscoveryScore": 72.3,
            "createdAt": "2024-01-15T00:00:00Z",
            "updatedAt": "2024-01-20T00:00:00Z",
        }
        
        topic = Topic(**topic_data)
        
        assert topic.id == 1
        assert topic.name == "quantum computing"
        assert topic.taxonomyPath == "physics/computing"
        assert topic.artifactCount == 156
        assert topic.avgDiscoveryScore == 72.3
    
    def test_topic_optional_fields(self):
        """Topic model should allow optional fields to be omitted."""
        minimal_topic = {
            "id": 1,
            "name": "quantum computing",
        }
        
        topic = Topic(**minimal_topic)
        assert topic.taxonomyPath is None
        assert topic.description is None
        assert topic.artifactCount is None
        assert topic.avgDiscoveryScore is None
        assert topic.createdAt is None
        assert topic.updatedAt is None


class TestTopicTimelineContracts:
    """Test TopicTimeline model contract."""
    
    def test_topic_timeline_response_model(self):
        """TopicTimeline model should match frontend TopicTimelinePoint type."""
        timeline_data = {
            "date": "2024-01-15",
            "artifactCount": 25,
            "avgDiscoveryScore": 73.5,
        }
        
        timeline = TopicTimeline(**timeline_data)
        
        assert timeline.date == "2024-01-15"
        assert timeline.artifactCount == 25
        assert timeline.avgDiscoveryScore == 73.5
    
    def test_topic_timeline_optional_score(self):
        """TopicTimeline avgDiscoveryScore should be optional."""
        timeline_without_score = {
            "date": "2024-01-15",
            "artifactCount": 25,
        }
        
        timeline = TopicTimeline(**timeline_without_score)
        assert timeline.avgDiscoveryScore is None


class TestTopicStatsContracts:
    """Test TopicStats model contract with frontend TopicStats type."""
    
    def test_topic_stats_complete_model(self):
        """TopicStats with all fields should validate correctly."""
        # Test with emergence metrics
        emergence_metrics = TopicEmergenceMetrics(
            growthRate=0.15,
            acceleration=0.02,
            velocity=2.3,
            emergenceScore=78.5,
        )
        
        # Test with growth prediction
        growth_prediction = TopicGrowthPrediction(
            dailyGrowthRate=0.12,
            predictedCounts=[25, 28, 32, 36, 40],
            confidence=0.85,
            trend="emerging",
            predictionWindowDays=14,
        )
        
        # Test with related topics
        related_topics = [
            RelatedTopic(
                id=2,
                name="quantum algorithms",
                taxonomyPath="physics/computing/algorithms",
                similarity=0.92,
            ),
            RelatedTopic(
                id=3,
                name="quantum error correction",
                similarity=0.88,
            ),
        ]
        
        # Test with evolution events
        evolution_events = [
            TopicEvolutionEvent(
                id=1,
                topicId=1,
                eventType="growth",
                eventStrength=0.78,
                eventDate="2024-01-15T00:00:00Z",
                description="Significant growth detected",
            ),
        ]
        
        # Test with timeline
        timeline = [
            TopicTimeline(
                date="2024-01-15",
                artifactCount=25,
                avgDiscoveryScore=73.5,
            ),
        ]
        
        # Create complete TopicStats
        stats = TopicStats(
            topicId=1,
            name="quantum computing",
            taxonomyPath="physics/computing",
            totalArtifacts=245,
            avgDiscoveryScore=72.3,
            emergenceMetrics=emergence_metrics,
            growthPrediction=growth_prediction,
            relatedTopics=related_topics,
            recentEvents=evolution_events,
            timeline=timeline,
        )
        
        assert stats.topicId == 1
        assert stats.name == "quantum computing"
        assert stats.totalArtifacts == 245
        assert stats.emergenceMetrics.emergenceScore == 78.5
        assert len(stats.relatedTopics) == 2
        assert stats.relatedTopics[0].similarity == 0.92
        assert len(stats.recentEvents) == 1
        assert len(stats.timeline) == 1
    
    def test_topic_stats_minimal_model(self):
        """TopicStats should work with only required fields."""
        stats = TopicStats(
            topicId=1,
            name="quantum computing",
            totalArtifacts=245,
            avgDiscoveryScore=72.3,
        )
        
        assert stats.topicId == 1
        assert stats.totalArtifacts == 245
        assert stats.emergenceMetrics is None
        assert stats.growthPrediction is None
        assert stats.relatedTopics is None
        assert stats.recentEvents is None
        assert stats.timeline is None


class TestTopicEvolutionEventContracts:
    """Test TopicEvolutionEvent model contract."""
    
    def test_evolution_event_model(self):
        """TopicEvolutionEvent should match frontend type."""
        event_data = {
            "id": 1,
            "topicId": 1,
            "eventType": "merge",
            "relatedTopicIds": [2, 3],
            "eventStrength": 0.85,
            "eventDate": "2024-01-10T00:00:00Z",
            "description": "Topics merged",
            "createdAt": "2024-01-10T00:00:00Z",
        }
        
        event = TopicEvolutionEvent(**event_data)
        
        assert event.id == 1
        assert event.topicId == 1
        assert event.eventType == "merge"
        assert event.relatedTopicIds == [2, 3]
        assert event.eventStrength == 0.85
    
    def test_evolution_event_optional_fields(self):
        """Evolution event optional fields should work."""
        minimal_event = {
            "id": 1,
            "topicId": 1,
            "eventType": "growth",
            "eventDate": "2024-01-10T00:00:00Z",
        }
        
        event = TopicEvolutionEvent(**minimal_event)
        assert event.relatedTopicIds is None
        assert event.eventStrength is None
        assert event.description is None
        assert event.createdAt is None


class TestTopicMergeCandidateContracts:
    """Test TopicMergeCandidate model contract."""
    
    def test_merge_candidate_model(self):
        """TopicMergeCandidate should match frontend type."""
        merge_data = {
            "primaryTopic": {
                "id": 1,
                "name": "quantum computing",
                "taxonomyPath": "physics/computing",
            },
            "secondaryTopic": {
                "id": 2,
                "name": "quantum information",
                "taxonomyPath": "physics/info",
            },
            "currentSimilarity": 0.92,
            "overlapTrend": 0.15,
            "confidence": 0.88,
            "eventType": "merge",
            "timestamp": "2024-01-10T00:00:00Z",
        }
        
        merge = TopicMergeCandidate(**merge_data)
        
        assert merge.primaryTopic.id == 1
        assert merge.secondaryTopic.id == 2
        assert merge.currentSimilarity == 0.92
        assert merge.confidence == 0.88
        assert merge.eventType == "merge"


class TestTopicSplitDetectionContracts:
    """Test TopicSplitDetection model contract."""
    
    def test_split_detection_model(self):
        """TopicSplitDetection should match frontend type."""
        split_data = {
            "primaryTopic": {
                "id": 5,
                "name": "artificial intelligence",
                "taxonomyPath": "ai",
            },
            "coherenceDrop": 0.35,
            "subClusters": [
                {"artifacts": [{"id": 1, "title": "Neural networks"}], "size": 1},
                {"artifacts": [{"id": 2, "title": "Symbolic reasoning"}], "size": 1},
            ],
            "confidence": 0.82,
            "eventType": "split",
            "timestamp": "2024-01-05T00:00:00Z",
        }
        
        split = TopicSplitDetection(**split_data)
        
        assert split.primaryTopic.id == 5
        assert split.coherenceDrop == 0.35
        assert len(split.subClusters) == 2
        assert split.confidence == 0.82
        assert split.eventType == "split"
    
    def test_split_detection_optional_clusters(self):
        """Split detection subClusters should be optional."""
        minimal_split = {
            "primaryTopic": {"id": 5, "name": "artificial intelligence"},
            "coherenceDrop": 0.35,
            "confidence": 0.82,
            "eventType": "split",
            "timestamp": "2024-01-05T00:00:00Z",
        }
        
        split = TopicSplitDetection(**minimal_split)
        assert split.subClusters is None


def test_camel_case_field_names():
    """Verify all new models use camelCase for field names to match frontend."""
    from pydantic import BaseModel
    
    models = [
        TopicEvolutionEvent,
        TopicMergeCandidate,
        TopicSplitDetection,
        TopicEmergenceMetrics,
        TopicGrowthPrediction,
        RelatedTopic,
        TopicStats,
    ]
    
    for model in models:
        # Get the model fields
        fields = model.model_fields
        
        # Check that field names use camelCase (no underscores)
        for field_name in fields.keys():
            assert "_" not in field_name, (
                f"Model {model.__name__} field '{field_name}' uses snake_case. "
                f"Should use camelCase to match frontend types."
            )


def test_topics_response_models():
    """Test that topic-related models can be instantiated with typical data."""
    # Test creating a topic with typical API response data
    topic = Topic(
        id=1,
        name="machine learning",
        taxonomyPath="ai/ml",
        artifactCount=234,
        avgDiscoveryScore=68.5,
    )
    
    assert topic.id == 1
    assert topic.name == "machine learning"
    assert topic.artifactCount == 234
    
    # Test that it serializes to dict correctly
    topic_dict = topic.model_dump()
    assert topic_dict["id"] == 1
    assert topic_dict["name"] == "machine learning"
    assert "taxonomyPath" in topic_dict


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
