"""Tests for entity UI backend endpoints."""

import pytest
from fastapi.testclient import TestClient

from signal_harvester.api import create_app
from signal_harvester.config import load_settings


@pytest.fixture(autouse=True)
def api_key_env(monkeypatch):
    """Configure API key expected by the API server."""
    key = "test-api-key-123456"
    monkeypatch.setenv("HARVEST_API_KEY", key)
    return key


@pytest.fixture
def test_client(tmp_path, api_key_env):
    """Create test API client."""
    settings_path = tmp_path / "settings.yaml"
    db_path = tmp_path / "test.db"
    
    # Create minimal settings
    settings_path.write_text(f"""
app:
  database_path: {db_path}
  log_level: INFO

sources:
  - name: arxiv
    enabled: true
  - name: github
    enabled: true
""")
    
    app = create_app(settings_path=str(settings_path))
    return TestClient(app)


@pytest.fixture
def sample_entities_db(tmp_path):
    """Create database with sample entities."""
    from signal_harvester.db import connect, upsert_entity, upsert_account
    
    db_path = tmp_path / "entities.db"
    
    # Create entities
    entity1_id = upsert_entity(
        str(db_path),
        entity_type="person",
        name="Dr. Jane Smith", 
        description="AI researcher at Stanford",
        homepage_url="https://stanford.edu/~jsmith"
    )
    
    entity2_id = upsert_entity(
        str(db_path),
        entity_type="lab",
        name="MIT CSAIL",
        description="MIT Computer Science and AI Lab",
        homepage_url="https://csail.mit.edu"
    )
    
    # Add accounts
    upsert_account(str(db_path), entity1_id, "x", "@janesmith", 
                   raw_json='{"description": "AI researcher @ Stanford"}')
    
    return str(db_path)


@pytest.fixture
def api_headers(api_key_env):
    return {"X-API-Key": api_key_env}


def test_list_entities_empty(test_client):
    """Test listing entities with empty database."""
    response = test_client.get("/entities")
    assert response.status_code == 200
    
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] == 0
    assert len(data["items"]) == 0


def test_list_entities_with_data(test_client, sample_entities_db):
    """Test listing entities with data."""
    # Update client to use entities database
    from signal_harvester.api import create_app
    
    settings_path = sample_entities_db.replace("entities.db", "settings.yaml")
    app = create_app(settings_path=settings_path)
    client = TestClient(app)
    
    response = client.get("/entities")
    assert response.status_code == 200
    
    data = response.json()
    assert data["total"] >= 2
    assert len(data["items"]) >= 2
    
    # Check entity structure
    entity = data["items"][0]
    assert "id" in entity
    assert "entityType" in entity
    assert "name" in entity
    assert "createdAt" in entity


def test_list_entities_with_type_filter(test_client, sample_entities_db):
    """Test filtering entities by type."""
    from signal_harvester.api import create_app
    
    settings_path = sample_entities_db.replace("entities.db", "settings.yaml")
    app = create_app(settings_path=settings_path)
    client = TestClient(app)
    
    # Filter by person
    response = client.get("/entities?entity_type=person")
    assert response.status_code == 200
    
    data = response.json()
    assert all(e["entityType"] == "person" for e in data["items"])


def test_list_entities_search(test_client, sample_entities_db):
    """Test searching entities."""
    from signal_harvester.api import create_app
    
    settings_path = sample_entities_db.replace("entities.db", "settings.yaml")
    app = create_app(settings_path=settings_path)
    client = TestClient(app)
    
    response = client.get("/entities?search=Stanford")
    assert response.status_code == 200
    
    data = response.json()
    assert len(data["items"]) > 0
    # Stanford should be in name or description
    assert any("Stanford" in (e.get("name", "") + e.get("description", "")) 
               for e in data["items"])


def test_search_entities_endpoint(test_client, sample_entities_db):
    """Test entity search endpoint."""
    from signal_harvester.api import create_app
    
    settings_path = sample_entities_db.replace("entities.db", "settings.yaml")
    app = create_app(settings_path=settings_path)
    client = TestClient(app)
    
    response = client.get("/entities/search?q=Smith")
    assert response.status_code == 200
    
    results = response.json()
    assert isinstance(results, list)
    if len(results) > 0:
        result = results[0]
        assert "entity" in result
        assert "relevanceScore" in result
        assert result["relevanceScore"] > 0
        assert "Smith" in result["entity"]["name"]


def test_get_entity_details(test_client, sample_entities_db):
    """Test getting single entity details."""
    from signal_harvester.api import create_app
    from signal_harvester.config import load_settings
    from signal_harvester.db import list_entities
    
    settings_path = sample_entities_db.replace("entities.db", "settings.yaml")
    
    # Get first entity ID
    entities, _ = list_entities(sample_entities_db)
    if not entities:
        pytest.skip("No entities in test database")
    
    entity_id = entities[0]["id"]
    
    app = create_app(settings_path=settings_path)
    client = TestClient(app)
    
    response = client.get(f"/entities/{entity_id}")
    assert response.status_code == 200
    
    entity = response.json()
    assert entity["id"] == entity_id
    assert "entityType" in entity
    assert "name" in entity


def test_get_entity_not_found(test_client):
    """Test getting non-existent entity."""
    response = test_client.get("/entities/999999")
    assert response.status_code == 404


def test_get_entity_stats(test_client, sample_entities_db):
    """Test getting entity statistics."""
    from signal_harvester.api import create_app
    from signal_harvester.db import list_entities
    
    settings_path = sample_entities_db.replace("entities.db", "settings.yaml")
    
    # Get first entity ID
    entities, _ = list_entities(sample_entities_db)
    if not entities:
        pytest.skip("No entities in test database")
    
    entity_id = entities[0]["id"]
    
    app = create_app(settings_path=settings_path)
    client = TestClient(app)
    
    response = client.get(f"/entities/{entity_id}/stats")
    assert response.status_code in [200, 404]  # 404 if no stats
    
    if response.status_code == 200:
        stats = response.json()
        assert "entityId" in stats
        assert "artifactCount" in stats
        assert "avgDiscoveryScore" in stats
        assert "totalImpact" in stats


def test_get_entity_artifacts(test_client, sample_entities_db):
    """Test getting entity artifacts."""
    from signal_harvester.api import create_app
    from signal_harvester.db import list_entities
    
    settings_path = sample_entities_db.replace("entities.db", "settings.yaml")
    
    # Get first entity ID
    entities, _ = list_entities(sample_entities_db)
    if not entities:
        pytest.skip("No entities in test database")
    
    entity_id = entities[0]["id"]
    
    app = create_app(settings_path=settings_path)
    client = TestClient(app)
    
    response = client.get(f"/entities/{entity_id}/artifacts")
    assert response.status_code == 200
    
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "hasMore" in data


def test_pagination_parameters(test_client, sample_entities_db):
    """Test pagination parameters."""
    from signal_harvester.api import create_app
    
    settings_path = sample_entities_db.replace("entities.db", "settings.yaml")
    app = create_app(settings_path=settings_path)
    client = TestClient(app)
    
    # Test page 1
    response = client.get("/entities?page=1&page_size=1")
    assert response.status_code == 200
    data1 = response.json()
    
    # Test page 2
    response = client.get("/entities?page=2&page_size=1")
    assert response.status_code == 200
    data2 = response.json()
    
    # Should have different items
    if data1["total"] > 1:
        assert data1["items"][0]["id"] != data2["items"][0]["id"]


def test_search_entities_min_length(test_client):
    """Test search query validation."""
    response = test_client.get("/entities/search?q=ab")
    # Should either return results or handle short queries gracefully
    assert response.status_code in [200, 400]


def test_entity_stats_days_parameter(test_client, sample_entities_db):
    """Test days parameter for entity stats."""
    from signal_harvester.api import create_app
    from signal_harvester.db import list_entities
    
    settings_path = sample_entities_db.replace("entities.db", "settings.yaml")
    
    entities, _ = list_entities(sample_entities_db)
    if not entities:
        pytest.skip("No entities in test database")
    
    entity_id = entities[0]["id"]
    
    app = create_app(settings_path=settings_path)
    client = TestClient(app)
    
    # Test different days parameters
    for days in [7, 30, 90]:
        response = client.get(f"/entities/{entity_id}/stats?days={days}")
        assert response.status_code in [200, 404]


def test_entity_artifacts_filters(test_client, sample_entities_db):
    """Test entity artifacts filtering."""
    from signal_harvester.api import create_app
    from signal_harvester.db import list_entities
    
    settings_path = sample_entities_db.replace("entities.db", "settings.yaml")
    
    entities, _ = list_entities(sample_entities_db)
    if not entities:
        pytest.skip("No entities in test database")
    
    entity_id = entities[0]["id"]
    
    app = create_app(settings_path=settings_path)
    client = TestClient(app)
    
    # Test source filter
    response = client.get(f"/entities/{entity_id}/artifacts?source=arxiv")
    assert response.status_code == 200
    
    # Test min_score filter
    response = client.get(f"/entities/{entity_id}/artifacts?min_score=50")
    assert response.status_code == 200
    
    # Test limit and offset
    response = client.get(f"/entities/{entity_id}/artifacts?limit=5&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) <= 5


def test_merge_entity_requires_api_key(test_client):
    """Merge endpoint should reject requests without API key."""
    response = test_client.post(
        "/entities/1/merge",
        json={"candidateEntityId": 2}
    )
    assert response.status_code == 401


def test_merge_entity_success(monkeypatch, test_client, api_headers):
    """Merge endpoint returns success response when authorized."""
    from signal_harvester import db as db_module
    from signal_harvester import identity_resolution as ir_module
    import signal_harvester.api as api_module

    def fake_get_entity_with_accounts(db_path, entity_id):
        return {
            "id": entity_id,
            "entity_type": "person",
            "name": f"Entity {entity_id}"
        }

    record_calls = {}

    def fake_record_entity_merge_history(*args, **kwargs):
        record_calls["called"] = True

    monkeypatch.setattr(db_module, "get_entity_with_accounts", fake_get_entity_with_accounts)
    monkeypatch.setattr(db_module, "record_entity_merge_history", fake_record_entity_merge_history)
    monkeypatch.setattr(ir_module, "merge_entities", lambda *args, **kwargs: True)
    monkeypatch.setattr(api_module, "invalidate_cache", lambda pattern: 0)

    response = test_client.post(
        "/entities/1/merge",
        headers=api_headers,
        json={
            "candidateEntityId": 2,
            "similarityScore": 0.95,
            "reviewer": "tester",
            "notes": "Looks like duplicate"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["primaryEntityId"] == 1
    assert data["mergedEntityId"] == 2
    assert record_calls.get("called") is True


def test_record_entity_decision_requires_api_key(test_client):
    """Decision endpoint should require API key."""
    response = test_client.post(
        "/entities/1/decisions",
        json={
            "candidateEntityId": 2,
            "decision": "ignore"
        }
    )
    assert response.status_code == 401


def test_record_entity_decision_success(monkeypatch, test_client, api_headers):
    """Decision endpoint returns persisted history row when authorized."""
    from signal_harvester import db as db_module

    def fake_get_entity_with_accounts(db_path, entity_id):
        return {
            "id": entity_id,
            "entity_type": "person",
            "name": f"Entity {entity_id}"
        }

    history_row = {
        "id": 42,
        "primary_entity_id": 1,
        "candidate_entity_id": 2,
        "decision": "ignore",
        "similarity_score": 0.8,
        "reviewer": "reviewer",
        "notes": "Not duplicate",
        "created_at": "2025-01-01T00:00:00Z",
        "primary_name": "Entity 1",
        "candidate_name": "Entity 2",
    }

    monkeypatch.setattr(db_module, "get_entity_with_accounts", fake_get_entity_with_accounts)
    monkeypatch.setattr(db_module, "record_entity_merge_history", lambda *args, **kwargs: None)
    monkeypatch.setattr(db_module, "list_entity_merge_history", lambda *args, **kwargs: [history_row])

    response = test_client.post(
        "/entities/1/decisions",
        headers=api_headers,
        json={
            "candidateEntityId": 2,
            "decision": "ignore",
            "similarityScore": 0.75,
            "reviewer": "reviewer",
            "notes": "Not duplicate"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "ignore"
    assert data["primaryEntityId"] == 1
    assert data["candidateEntityId"] == 2
    assert data["primaryName"] == "Entity 1"
    assert data["candidateName"] == "Entity 2"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
