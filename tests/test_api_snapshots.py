"""Tests for snapshots API endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from signal_harvester.api import create_app
from signal_harvester.db import create_signal, create_snapshot, init_db


@pytest.fixture
def temp_db(tmp_path) -> str:
    """Create a temporary database for testing."""
    db = tmp_path / "test.db"
    init_db(str(db))
    return str(db)


@pytest.fixture
def client(temp_db: str, tmp_path) -> TestClient:
    """Create test client with temporary database."""
    # Create config in tmp_path
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    cfg_file = cfg_dir / "settings.yaml"
    
    # Write minimal config
    cfg_file.write_text(f"""
app:
  database_path: "{temp_db}"
  fetch:
    max_results: 100
  llm:
    provider: dummy

queries: []
""")
    
    # Create app with test config
    app = create_app(settings_path=str(cfg_file))
    return TestClient(app)


@pytest.fixture
def sample_signals(temp_db: str) -> list[dict]:
    """Create sample signals for testing."""
    signals = []
    for i in range(5):
        signal = create_signal(
            temp_db,
            name=f"Signal {i}",
            source=f"source_{i}",
            status="active" if i % 2 == 0 else "paused",
            tags=["test", f"tag_{i}"],
        )
        signals.append(signal)
    return signals


@pytest.fixture
def sample_snapshots(temp_db: str, sample_signals: list[dict]) -> list[dict]:
    """Create sample snapshots for testing."""
    snapshots = []
    for i, signal in enumerate(sample_signals[:3]):
        snapshot = create_snapshot(
            temp_db,
            signal_id=signal["id"],
            file_path=f"/snapshots/snapshot_{i}.json" if i % 2 == 0 else None,
            size_kb=1024 * (i + 1) if i % 2 == 0 else None,
        )
        snapshots.append(snapshot)
    return snapshots


class TestSnapshotsAPI:
    """Test snapshots API endpoints."""

    def test_list_snapshots_empty(self, client: TestClient) -> None:
        """Test listing snapshots when none exist."""
        response = client.get("/snapshots")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["pageSize"] == 20

    def test_list_snapshots(self, client: TestClient, sample_snapshots: list[dict]) -> None:
        """Test listing snapshots."""
        response = client.get("/snapshots")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 3
        assert data["total"] == 3
        assert data["page"] == 1

    def test_list_snapshots_pagination(self, client: TestClient, sample_snapshots: list[dict]) -> None:
        """Test snapshot pagination."""
        # Page 1 with size 2
        response = client.get("/snapshots?page=1&pageSize=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 3
        assert data["page"] == 1
        assert data["pageSize"] == 2

        # Page 2
        response = client.get("/snapshots?page=2&pageSize=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["page"] == 2

    def test_list_snapshots_filter_by_status(
        self, client: TestClient, sample_snapshots: list[dict]
    ) -> None:
        """Test filtering snapshots by status."""
        response = client.get("/snapshots?status=ready")
        assert response.status_code == 200
        data = response.json()
        # Every other snapshot has a file_path (status=ready)
        assert len(data["items"]) == 2
        for item in data["items"]:
            assert item["status"] == "ready"

        response = client.get("/snapshots?status=processing")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        for item in data["items"]:
            assert item["status"] == "processing"

    def test_list_snapshots_filter_by_signal_id(
        self, client: TestClient, sample_snapshots: list[dict], sample_signals: list[dict]
    ) -> None:
        """Test filtering snapshots by signal ID."""
        signal_id = sample_signals[0]["id"]
        response = client.get(f"/snapshots?signalId={signal_id}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["signalId"] == signal_id

    def test_list_snapshots_search(
        self, client: TestClient, sample_snapshots: list[dict]
    ) -> None:
        """Test searching snapshots by signal name."""
        response = client.get("/snapshots?search=Signal 1")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert "Signal 1" in data["items"][0]["signalName"]

    def test_get_snapshot(self, client: TestClient, sample_snapshots: list[dict]) -> None:
        """Test getting a specific snapshot."""
        snapshot_id = sample_snapshots[0]["id"]
        response = client.get(f"/snapshots/{snapshot_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == snapshot_id
        assert data["signalId"] == sample_snapshots[0]["signalId"]
        assert "signalName" in data
        assert "status" in data
        assert "createdAt" in data

    def test_get_snapshot_not_found(self, client: TestClient) -> None:
        """Test getting non-existent snapshot."""
        response = client.get("/snapshots/nonexistent-id")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_create_snapshot(
        self, client: TestClient, sample_signals: list[dict]
    ) -> None:
        """Test creating a new snapshot."""
        signal_id = sample_signals[0]["id"]
        response = client.post("/snapshots", json={"signalId": signal_id})
        assert response.status_code == 201
        data = response.json()
        assert data["signalId"] == signal_id
        assert data["status"] == "processing"
        assert "id" in data
        assert "createdAt" in data

        # Verify it appears in the list
        response = client.get("/snapshots")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    def test_create_snapshot_invalid_signal(self, client: TestClient) -> None:
        """Test creating snapshot for non-existent signal."""
        response = client.post("/snapshots", json={"signalId": "nonexistent-id"})
        assert response.status_code == 404
        assert "Signal not found" in response.json()["detail"]

    def test_snapshot_ordering(
        self, client: TestClient, sample_snapshots: list[dict]
    ) -> None:
        """Test that snapshots are ordered by creation date (newest first)."""
        response = client.get("/snapshots")
        assert response.status_code == 200
        data = response.json()
        
        # Verify descending order by createdAt
        created_times = [item["createdAt"] for item in data["items"]]
        assert created_times == sorted(created_times, reverse=True)

    def test_snapshot_signal_name_populated(
        self, client: TestClient, sample_snapshots: list[dict], sample_signals: list[dict]
    ) -> None:
        """Test that snapshot signalName is correctly populated from signal."""
        response = client.get("/snapshots")
        assert response.status_code == 200
        data = response.json()
        
        for item in data["items"]:
            # Find corresponding signal
            signal = next(s for s in sample_signals if s["id"] == item["signalId"])
            assert item["signalName"] == signal["name"]

    def test_snapshot_size_and_path(
        self, client: TestClient, sample_snapshots: list[dict]
    ) -> None:
        """Test that size and file path are correctly stored."""
        # Get a snapshot that has file_path set (even indices)
        snapshot = next(s for s in sample_snapshots if s["sizeKb"] is not None)
        
        response = client.get(f"/snapshots/{snapshot['id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["sizeKb"] is not None
        assert data["sizeKb"] > 0
        assert data["status"] == "ready"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
