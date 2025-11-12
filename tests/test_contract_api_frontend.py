"""Contract tests to verify API response models match frontend TypeScript types.

These tests ensure that FastAPI Pydantic models align with the TypeScript types
defined in frontend/src/types/api.ts, preventing runtime errors and type mismatches.
"""
import pytest
from pydantic import ValidationError

from signal_harvester.api import (
    BulkJobResponse,
    BulkJobStatus,
    BulkJobStatusEnum,
    BulkSetStatusInput,
    CreateSignalInput,
    PaginatedSignals,
    PaginatedSnapshots,
    Signal,
    SignalsStats,
    SignalStatus,
    Snapshot,
    SnapshotStatus,
    UpdateSignalInput,
)


class TestSignalContracts:
    """Test Signal model contract with frontend types."""
    
    def test_signal_response_model(self):
        """Signal model should match frontend Signal type."""
        # Frontend expects all these fields
        signal_data = {
            "id": "sig-123",
            "name": "Test Signal",
            "source": "x.com",
            "status": "active",
            "tags": ["ai", "research"],
            "lastSeenAt": "2025-11-10T12:00:00Z",
            "createdAt": "2025-11-01T10:00:00Z",
            "updatedAt": "2025-11-10T12:00:00Z",
        }
        
        signal = Signal(**signal_data)
        
        # Verify all required fields are present
        assert signal.id == "sig-123"
        assert signal.name == "Test Signal"
        assert signal.source == "x.com"
        assert signal.status == SignalStatus.active
        assert signal.tags == ["ai", "research"]
        assert signal.lastSeenAt == "2025-11-10T12:00:00Z"
        assert signal.createdAt == "2025-11-01T10:00:00Z"
        assert signal.updatedAt == "2025-11-10T12:00:00Z"
    
    def test_signal_optional_fields(self):
        """Signal model should allow optional fields to be omitted."""
        # Frontend types show tags, lastSeenAt as optional
        minimal_signal = {
            "id": "sig-456",
            "name": "Minimal Signal",
            "source": "github.com",
            "status": "inactive",
            "createdAt": "2025-11-01T10:00:00Z",
            "updatedAt": "2025-11-01T10:00:00Z",
        }
        
        signal = Signal(**minimal_signal)
        assert signal.tags is None
        assert signal.lastSeenAt is None
    
    def test_signal_status_enum_values(self):
        """Signal status values should match frontend SignalStatus type."""
        # Frontend: type SignalStatus = "active" | "inactive" | "paused" | "error"
        expected_statuses = {"active", "inactive", "paused", "error"}
        actual_statuses = {s.value for s in SignalStatus}
        
        assert actual_statuses == expected_statuses, (
            f"Status mismatch: frontend expects {expected_statuses}, "
            f"backend has {actual_statuses}"
        )
    
    def test_create_signal_input(self):
        """CreateSignalInput should match frontend CreateSignalInput type."""
        # Frontend: name, source, status are required; tags optional
        create_data = {
            "name": "New Signal",
            "source": "arxiv.org",
            "status": "active",
            "tags": ["ml"],
        }
        
        input_model = CreateSignalInput(**create_data)
        assert input_model.name == "New Signal"
        assert input_model.tags == ["ml"]
        
        # Tags should be optional
        minimal = CreateSignalInput(name="Test", source="test", status="active")
        assert minimal.tags is None
    
    def test_update_signal_input(self):
        """UpdateSignalInput should have all fields optional."""
        # Frontend: type UpdateSignalInput = Partial<CreateSignalInput>
        # All fields should be optional
        partial_update = {"name": "Updated Name"}
        input_model = UpdateSignalInput(**partial_update)
        assert input_model.name == "Updated Name"
        assert input_model.source is None
        assert input_model.status is None


class TestPaginationContracts:
    """Test pagination model contracts."""
    
    def test_paginated_signals_structure(self):
        """PaginatedSignals should match frontend Paginated<T> type."""
        # Frontend: { items: T[]; total: number; page: number; pageSize: number }
        paginated_data = {
            "items": [
                {
                    "id": "1",
                    "name": "Signal 1",
                    "source": "x",
                    "status": "active",
                    "createdAt": "2025-11-01T10:00:00Z",
                    "updatedAt": "2025-11-01T10:00:00Z",
                }
            ],
            "total": 100,
            "page": 1,
            "pageSize": 20,
        }
        
        paginated = PaginatedSignals(**paginated_data)
        assert len(paginated.items) == 1
        assert paginated.total == 100
        assert paginated.page == 1
        assert paginated.pageSize == 20
    
    def test_paginated_snapshots_structure(self):
        """PaginatedSnapshots should match frontend Paginated<Snapshot> type."""
        paginated_data = {
            "items": [
                {
                    "id": "snap-1",
                    "signalId": "sig-1",
                    "status": "ready",
                    "createdAt": "2025-11-10T12:00:00Z",
                }
            ],
            "total": 50,
            "page": 2,
            "pageSize": 10,
        }
        
        paginated = PaginatedSnapshots(**paginated_data)
        assert paginated.total == 50
        assert paginated.page == 2


class TestSnapshotContracts:
    """Test Snapshot model contracts."""
    
    def test_snapshot_response_model(self):
        """Snapshot model should match frontend Snapshot type."""
        snapshot_data = {
            "id": "snap-123",
            "signalId": "sig-456",
            "signalName": "Test Signal",
            "status": "ready",
            "sizeKb": 2048,
            "createdAt": "2025-11-10T12:00:00Z",
        }
        
        snapshot = Snapshot(**snapshot_data)
        assert snapshot.id == "snap-123"
        assert snapshot.signalId == "sig-456"
        assert snapshot.signalName == "Test Signal"
        assert snapshot.status == SnapshotStatus.ready
        assert snapshot.sizeKb == 2048
    
    def test_snapshot_status_enum(self):
        """Snapshot status should match frontend SnapshotStatus type."""
        # Frontend: type SnapshotStatus = "ready" | "processing" | "failed"
        expected = {"ready", "processing", "failed"}
        actual = {s.value for s in SnapshotStatus}
        
        assert actual == expected


class TestBulkOperationContracts:
    """Test bulk operation model contracts."""
    
    def test_bulk_job_response(self):
        """BulkJobResponse should have jobId and total."""
        # Returned when starting bulk operations
        response_data = {
            "jobId": "job-abc-123",
            "total": 150,
        }
        
        response = BulkJobResponse(**response_data)
        assert response.jobId == "job-abc-123"
        assert response.total == 150
    
    def test_bulk_job_status(self):
        """BulkJobStatus should match SSE event data structure."""
        # This is sent via SSE stream and must match frontend expectations
        status_data = {
            "jobId": "job-xyz-789",
            "status": "running",
            "total": 100,
            "done": 45,
            "fail": 2,
        }
        
        status = BulkJobStatus(**status_data)
        assert status.jobId == "job-xyz-789"
        assert status.status == BulkJobStatusEnum.running
        assert status.total == 100
        assert status.done == 45
        assert status.fail == 2
    
    def test_bulk_job_status_enum(self):
        """Bulk job status enum values should be complete."""
        # Must include all states the frontend expects
        expected = {"running", "completed", "cancelled", "failed"}
        actual = {s.value for s in BulkJobStatusEnum}
        
        assert actual == expected
    
    def test_bulk_set_status_input(self):
        """BulkSetStatusInput should accept ids or filters."""
        # Test with IDs
        input_data = {
            "ids": ["sig-1", "sig-2", "sig-3"],
            "status": "paused",
        }
        input_model = BulkSetStatusInput(**input_data)
        assert input_model.ids == ["sig-1", "sig-2", "sig-3"]
        assert input_model.status == SignalStatus.paused
        
        # Test with filters
        filter_input = {
            "filters": {"source": "x.com"},
            "status": "active",
        }
        filter_model = BulkSetStatusInput(**filter_input)
        assert filter_model.filters == {"source": "x.com"}
        assert filter_model.ids is None


class TestStatsContracts:
    """Test statistics model contracts."""
    
    def test_signals_stats(self):
        """SignalsStats should match frontend SignalsStats type."""
        stats_data = {
            "total": 250,
            "active": 180,
            "paused": 40,
            "error": 10,
            "inactive": 20,
        }
        
        stats = SignalsStats(**stats_data)
        assert stats.total == 250
        assert stats.active == 180
        assert stats.paused == 40
        assert stats.error == 10
        assert stats.inactive == 20
        
        # Verify sum logic holds
        assert stats.active + stats.paused + stats.error + stats.inactive == stats.total


class TestFieldNamingConventions:
    """Test that field naming conventions match frontend expectations."""
    
    def test_camel_case_consistency(self):
        """All API models should use camelCase for field names (matching frontend)."""
        # Verify Signal uses camelCase
        signal = Signal(
            id="1",
            name="Test",
            source="test",
            status="active",
            lastSeenAt="2025-11-10T12:00:00Z",  # camelCase
            createdAt="2025-11-10T12:00:00Z",   # camelCase
            updatedAt="2025-11-10T12:00:00Z",   # camelCase
        )
        
        # Verify serialization preserves camelCase
        serialized = signal.model_dump()
        assert "lastSeenAt" in serialized
        assert "createdAt" in serialized
        assert "updatedAt" in serialized
        assert "last_seen_at" not in serialized  # Should not have snake_case
    
    def test_bulk_job_camel_case(self):
        """Bulk job models should use camelCase."""
        status = BulkJobStatus(
            jobId="job-1",  # camelCase
            status="running",
            total=10,
            done=5,
            fail=1,
        )
        
        serialized = status.model_dump()
        assert "jobId" in serialized
        assert "job_id" not in serialized


class TestValidationErrorHandling:
    """Test that validation errors match frontend expectations."""
    
    def test_invalid_status_raises_validation_error(self):
        """Providing invalid status should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            Signal(
                id="1",
                name="Test",
                source="test",
                status="invalid_status",  # Not in enum
                createdAt="2025-11-10T12:00:00Z",
                updatedAt="2025-11-10T12:00:00Z",
            )
        
        # Error should mention valid options
        errors = exc_info.value.errors()
        assert len(errors) > 0
        assert "status" in str(errors[0])
    
    def test_missing_required_field(self):
        """Missing required fields should raise ValidationError."""
        with pytest.raises(ValidationError):
            Signal(
                id="1",
                name="Test",
                # Missing required 'source'
                status="active",
                createdAt="2025-11-10T12:00:00Z",
                updatedAt="2025-11-10T12:00:00Z",
            )


class TestJSONSerialization:
    """Test that models serialize to JSON matching frontend expectations."""
    
    def test_signal_json_serialization(self):
        """Signal should serialize to JSON matching frontend type."""
        signal = Signal(
            id="sig-1",
            name="Test Signal",
            source="x.com",
            status="active",
            tags=["ai", "ml"],
            lastSeenAt="2025-11-10T12:00:00Z",
            createdAt="2025-11-01T10:00:00Z",
            updatedAt="2025-11-10T12:00:00Z",
        )
        
        json_str = signal.model_dump_json()
        import json
        parsed = json.loads(json_str)
        
        # Verify structure matches frontend expectations
        assert parsed["id"] == "sig-1"
        assert parsed["status"] == "active"
        assert isinstance(parsed["tags"], list)
        assert "lastSeenAt" in parsed
    
    def test_bulk_job_status_json(self):
        """BulkJobStatus should serialize for SSE events."""
        status = BulkJobStatus(
            jobId="job-123",
            status="completed",
            total=50,
            done=50,
            fail=0,
        )
        
        # SSE stream sends: data: {json}
        json_str = status.model_dump_json()
        import json
        parsed = json.loads(json_str)
        
        # Frontend will parse this from SSE event
        assert parsed["jobId"] == "job-123"
        assert parsed["status"] == "completed"
        assert parsed["done"] == 50


class TestDiscoveryContracts:
    """Test Discovery model contracts for Phase One."""

    def test_discovery_response_model(self):
        """Discovery model should match frontend Discovery type."""
        from signal_harvester.api import Discovery

        discovery_data = {
            "id": 1,
            "artifactId": 101,
            "artifactType": "preprint",
            "source": "arxiv",
            "sourceId": "2301.12345",
            "title": "Novel Quantum Algorithm",
            "text": "We propose a new quantum algorithm...",
            "url": "https://arxiv.org/abs/2301.12345",
            "publishedAt": "2025-01-15T10:00:00Z",
            "novelty": 85.5,
            "emergence": 72.0,
            "obscurity": 90.0,
            "discoveryScore": 82.5,
            "computedAt": "2025-01-16T08:00:00Z",
            "category": "research",
            "sentiment": "positive",
            "urgency": 7,
            "tags": ["quantum", "optimization"],
            "topics": ["quantum/algorithms", "optimization/combinatorial"],
            "reasoning": "Novel approach with strong theoretical foundations",
            "createdAt": "2025-01-15T10:00:00Z",
            "updatedAt": "2025-01-16T08:00:00Z",
        }

        discovery = Discovery(**discovery_data)

        assert discovery.id == 1
        assert discovery.artifactId == 101
        assert discovery.artifactType == "preprint"
        assert discovery.source == "arxiv"
        assert discovery.title == "Novel Quantum Algorithm"
        assert discovery.discoveryScore == 82.5
        assert discovery.tags == ["quantum", "optimization"]
        assert discovery.topics == ["quantum/algorithms", "optimization/combinatorial"]

    def test_discovery_optional_fields(self):
        """Discovery should allow optional fields to be omitted."""
        from signal_harvester.api import Discovery

        minimal_discovery = {
            "id": 1,
            "artifactId": 101,
            "artifactType": "preprint",
            "source": "arxiv",
            "sourceId": "2301.12345",
            "title": "Novel Algorithm",
            "publishedAt": "2025-01-15T10:00:00Z",
            "createdAt": "2025-01-15T10:00:00Z",
            "updatedAt": "2025-01-15T10:00:00Z",
        }

        discovery = Discovery(**minimal_discovery)
        assert discovery.text is None
        assert discovery.novelty is None
        assert discovery.tags is None
        assert discovery.reasoning is None


class TestTopicContracts:
    """Test Topic model contracts for Phase One."""

    def test_topic_response_model(self):
        """Topic model should match frontend Topic type."""
        from signal_harvester.api import Topic

        topic_data = {
            "id": 1,
            "name": "Quantum Networking",
            "taxonomyPath": "physics/quantum/networking",
            "description": "Low-latency entanglement routers",
            "artifactCount": 42,
            "avgDiscoveryScore": 85.3,
            "createdAt": "2025-01-10T08:00:00Z",
            "updatedAt": "2025-01-15T12:00:00Z",
        }

        topic = Topic(**topic_data)

        assert topic.id == 1
        assert topic.name == "Quantum Networking"
        assert topic.taxonomyPath == "physics/quantum/networking"
        assert topic.artifactCount == 42
        assert topic.avgDiscoveryScore == 85.3

    def test_topic_optional_fields(self):
        """Topic should allow optional fields to be omitted."""
        from signal_harvester.api import Topic

        minimal_topic = {
            "id": 1,
            "name": "Machine Learning",
        }

        topic = Topic(**minimal_topic)
        assert topic.taxonomyPath is None
        assert topic.description is None
        assert topic.artifactCount is None


class TestEntityContracts:
    """Test Entity model contracts for Phase One."""

    def test_entity_response_model(self):
        """Entity model should match frontend Entity type."""
        from signal_harvester.api import Entity

        entity_data = {
            "id": 1,
            "entityType": "person",
            "name": "Dr. Sarah Johnson",
            "description": "Quantum computing researcher at MIT",
            "accounts": [
                {"platform": "twitter", "handle": "sarah_quantum"},
                {"platform": "github", "handle": "sarahjohnson"},
            ],
            "createdAt": "2025-01-10T08:00:00Z",
            "updatedAt": "2025-01-15T12:00:00Z",
        }

        entity = Entity(**entity_data)

        assert entity.id == 1
        assert entity.entityType == "person"
        assert entity.name == "Dr. Sarah Johnson"
        assert entity.accounts is not None
        assert len(entity.accounts) == 2

    def test_entity_types(self):
        """Entity should support person, lab, organization types."""
        from signal_harvester.api import Entity

        for entity_type in ["person", "lab", "organization"]:
            entity = Entity(
                id=1,
                entityType=entity_type,
                name=f"Test {entity_type}",
            )
            assert entity.entityType == entity_type


class TestTopicTimelineContracts:
    """Test TopicTimeline model contracts."""

    def test_topic_timeline_response(self):
        """TopicTimeline should match frontend type."""
        from signal_harvester.api import TopicTimeline

        timeline_data = {
            "date": "2025-01-15",
            "artifactCount": 12,
            "avgDiscoveryScore": 82.5,
        }

        timeline = TopicTimeline(**timeline_data)

        assert timeline.date == "2025-01-15"
        assert timeline.artifactCount == 12
        assert timeline.avgDiscoveryScore == 82.5

    def test_topic_timeline_optional_score(self):
        """TopicTimeline avgDiscoveryScore should be optional."""
        from signal_harvester.api import TopicTimeline

        timeline = TopicTimeline(
            date="2025-01-15",
            artifactCount=5,
        )

        assert timeline.avgDiscoveryScore is None


class TestDiscoveryFieldNaming:
    """Test that discovery models use camelCase consistently."""

    def test_discovery_camel_case(self):
        """Discovery model should use camelCase for all fields."""
        from signal_harvester.api import Discovery

        discovery = Discovery(
            id=1,
            artifactId=101,  # camelCase
            artifactType="preprint",  # camelCase
            source="arxiv",
            sourceId="123",  # camelCase
            title="Test",
            publishedAt="2025-01-15T10:00:00Z",  # camelCase
            discoveryScore=85.0,  # camelCase
            createdAt="2025-01-15T10:00:00Z",  # camelCase
            updatedAt="2025-01-15T10:00:00Z",  # camelCase
        )

        serialized = discovery.model_dump()
        assert "artifactId" in serialized
        assert "artifactType" in serialized
        assert "sourceId" in serialized
        assert "publishedAt" in serialized
        assert "discoveryScore" in serialized
        assert "createdAt" in serialized
        assert "updatedAt" in serialized
        # Verify no snake_case
        assert "artifact_id" not in serialized
        assert "discovery_score" not in serialized

    def test_topic_camel_case(self):
        """Topic model should use camelCase for all fields."""
        from signal_harvester.api import Topic

        topic = Topic(
            id=1,
            name="Test Topic",
            taxonomyPath="test/path",  # camelCase
            artifactCount=10,  # camelCase
            avgDiscoveryScore=85.0,  # camelCase
        )

        serialized = topic.model_dump()
        assert "taxonomyPath" in serialized
        assert "artifactCount" in serialized
        assert "avgDiscoveryScore" in serialized
        assert "taxonomy_path" not in serialized

    def test_entity_camel_case(self):
        """Entity model should use camelCase for all fields."""
        from signal_harvester.api import Entity

        entity = Entity(
            id=1,
            entityType="person",  # camelCase
            name="Test Person",
        )

        serialized = entity.model_dump()
        assert "entityType" in serialized
        assert "entity_type" not in serialized


class TestDiscoveryJSONSerialization:
    """Test discovery models serialize to JSON correctly."""

    def test_discovery_json_output(self):
        """Discovery should serialize to JSON matching frontend expectations."""
        import json

        from signal_harvester.api import Discovery

        discovery = Discovery(
            id=1,
            artifactId=101,
            artifactType="preprint",
            source="arxiv",
            sourceId="2301.12345",
            title="Test",
            publishedAt="2025-01-15T10:00:00Z",
            discoveryScore=85.0,
            tags=["quantum", "ml"],
            createdAt="2025-01-15T10:00:00Z",
            updatedAt="2025-01-15T10:00:00Z",
        )

        json_str = discovery.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["id"] == 1
        assert parsed["artifactId"] == 101
        assert parsed["discoveryScore"] == 85.0
        assert isinstance(parsed["tags"], list)
        assert "quantum" in parsed["tags"]

    def test_topic_json_output(self):
        """Topic should serialize to JSON matching frontend expectations."""
        import json

        from signal_harvester.api import Topic

        topic = Topic(
            id=1,
            name="Quantum Computing",
            artifactCount=25,
            avgDiscoveryScore=82.5,
        )

        json_str = topic.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["name"] == "Quantum Computing"
        assert parsed["artifactCount"] == 25
        assert parsed["avgDiscoveryScore"] == 82.5


# Documentation for contract test maintenance
"""
CONTRACT TEST MAINTENANCE GUIDE
================================

When to Update These Tests:
---------------------------
1. Before modifying any Pydantic model in api.py
2. After changing TypeScript types in frontend/src/types/api.ts
3. When adding new API endpoints with response models
4. Before releasing API version changes

How to Add New Contract Tests:
------------------------------
1. Identify the backend Pydantic model (e.g., NewModel in api.py)
2. Identify the frontend TypeScript type (e.g., NewType in types/api.ts)
3. Create a test class: class TestNewModelContracts
4. Test required fields, optional fields, enums, and serialization
5. Verify field naming (camelCase for API, as frontend expects)

Common Contract Issues:
----------------------
- Field name mismatch (snake_case vs camelCase)
- Missing optional fields (frontend expects field but it's not in model)
- Enum value differences (frontend string unions vs backend Enum)
- Timestamp format inconsistencies (ISO 8601 strings expected)
- Nested object structure differences

Running These Tests:
-------------------
    pytest tests/test_contract_api_frontend.py -v

Include in CI/CD:
----------------
Add to .github/workflows or CI config to run before deployment:
    - pytest tests/test_contract_api_frontend.py --strict-markers
"""


# Documentation for contract test maintenance
"""
CONTRACT TEST MAINTENANCE GUIDE
================================

When to Update These Tests:
---------------------------
1. Before modifying any Pydantic model in api.py
2. After changing TypeScript types in frontend/src/types/api.ts
3. When adding new API endpoints with response models
4. Before releasing API version changes


How to Add New Contract Tests:
------------------------------
1. Identify the backend Pydantic model (e.g., NewModel in api.py)
2. Identify the frontend TypeScript type (e.g., NewType in types/api.ts)
3. Create a test class: class TestNewModelContracts
4. Test required fields, optional fields, enums, and serialization
5. Verify field naming (camelCase for API, as frontend expects)

Common Contract Issues:
----------------------
- Field name mismatch (snake_case vs camelCase)
- Missing optional fields (frontend expects field but it does not exist in model)
- Enum value differences (frontend string unions vs backend Enum)
- Timestamp format inconsistencies (ISO 8601 strings expected)
- Nested object structure differences

Running These Tests:
-------------------
    pytest tests/test_contract_api_frontend.py -v

Include in CI/CD:
----------------
Add to .github/workflows or CI config to run before deployment:
    pytest tests/test_contract_api_frontend.py --strict-markers
"""


class TestPaginatedDiscoveriesContracts:
    """Test cursor-based discovery pagination contracts match frontend expectations."""
    
    def test_paginated_discoveries_response(self):
        """PaginatedDiscoveries should have items, nextCursor, hasMore, total fields."""
        from signal_harvester.api import PaginatedDiscoveries
        
        # Frontend expects: { items: Discovery[], nextCursor: string | null, hasMore: boolean, total?: number }
        paginated_data = {
            "items": [
                {
                    "id": 1,
                    "artifactId": 1,
                    "artifactType": "paper",
                    "source": "arxiv",
                    "sourceId": "2024.00001",
                    "title": "Test Paper",
                    "url": "https://arxiv.org/abs/2024.00001",
                    "publishedAt": "2025-11-10T12:00:00Z",
                    "novelty": 85.0,
                    "emergence": 80.0,
                    "obscurity": 75.0,
                    "discoveryScore": 80.0,
                    "createdAt": "2025-11-10T10:00:00Z",
                    "updatedAt": "2025-11-10T12:00:00Z",
                }
            ],
            "nextCursor": "eyJzY29yZSI6ODAsImlkIjoxfQ==",
            "hasMore": True,
            "total": None,
        }
        
        paginated = PaginatedDiscoveries(**paginated_data)
        
        # Verify required fields
        assert len(paginated.items) == 1
        assert paginated.nextCursor == "eyJzY29yZSI6ODAsImlkIjoxfQ=="
        assert paginated.hasMore is True
        assert paginated.total is None
        
        # Verify cursor can be null
        last_page = PaginatedDiscoveries(items=[], nextCursor=None, hasMore=False)
        assert last_page.nextCursor is None
        assert last_page.hasMore is False
    
    def test_paginated_topics_response(self):
        """PaginatedTopics should have items, nextCursor, hasMore, total fields."""
        from signal_harvester.api import PaginatedTopics
        
        paginated_data = {
            "items": [
                {
                    "id": 1,
                    "name": "Machine Learning",
                    "taxonomyPath": "ai/ml",
                    "description": "ML research",
                    "artifactCount": 15,
                    "createdAt": "2025-11-01T10:00:00Z",
                    "updatedAt": "2025-11-10T12:00:00Z",
                }
            ],
            "nextCursor": "eyJjb3VudCI6MTUsImlkIjoxfQ==",
            "hasMore": True,
        }
        
        paginated = PaginatedTopics(**paginated_data)
        
        assert len(paginated.items) == 1
        assert paginated.nextCursor == "eyJjb3VudCI6MTUsImlkIjoxfQ=="
        assert paginated.hasMore is True
    
    def test_cursor_format(self):
        """Cursors should be base64-encoded strings."""
        import base64
        import json
        
        # Validate cursor is valid base64
        cursor = "eyJzY29yZSI6ODAsImlkIjoxfQ=="
        
        try:
            decoded = base64.b64decode(cursor).decode('utf-8')
            cursor_data = json.loads(decoded)
            
            # Cursor should contain score and id for discoveries
            assert "score" in cursor_data or "count" in cursor_data or "id" in cursor_data
        except (ValueError, json.JSONDecodeError) as e:
            pytest.fail(f"Invalid cursor format: {e}")
    
    def test_pagination_empty_results(self):
        """Pagination should handle empty results gracefully."""
        from signal_harvester.api import PaginatedDiscoveries
        
        empty_page = PaginatedDiscoveries(items=[], nextCursor=None, hasMore=False)
        
        assert empty_page.items == []
        assert empty_page.nextCursor is None
        assert empty_page.hasMore is False
    
    def test_pagination_field_names_camelcase(self):
        """Pagination response fields should use camelCase for frontend."""
        from signal_harvester.api import PaginatedDiscoveries
        
        data = {"items": [], "nextCursor": None, "hasMore": False}
        paginated = PaginatedDiscoveries(**data)
        
        # Serialize to dict and check field names
        serialized = paginated.model_dump(by_alias=True)
        
        # Frontend expects camelCase
        assert "nextCursor" in serialized
        assert "hasMore" in serialized
        assert "next_cursor" not in serialized  # Should not have snake_case
        assert "has_more" not in serialized
