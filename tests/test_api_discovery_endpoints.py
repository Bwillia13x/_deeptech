"""Smoke tests for discovery-related API endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from signal_harvester.api import create_app
from signal_harvester.db import init_db


@pytest.fixture
def discovery_client(tmp_path: Path) -> TestClient:
    """Provide a TestClient backed by a temporary discovery database."""

    db_path = tmp_path / "discoveries.db"
    init_db(str(db_path))

    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    cfg_file = cfg_dir / "settings.yaml"
    cfg_file.write_text(
        """
app:
  database_path: "{db}"
  fetch:
    max_results: 100
  llm:
    provider: dummy

queries: []
""".replace("{db}", str(db_path))
    )

    app = create_app(settings_path=str(cfg_file))
    return TestClient(app)


def test_discoveries_endpoint_returns_array(discovery_client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr("signal_harvester.db.list_top_discoveries", lambda *args, **kwargs: [])
    response = discovery_client.get("/discoveries")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_trending_topics_endpoint_returns_array(discovery_client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr("signal_harvester.db.get_trending_topics", lambda *args, **kwargs: [])
    response = discovery_client.get("/topics/trending")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_topic_timeline_endpoint_returns_array(discovery_client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr("signal_harvester.db.get_topic_timeline", lambda *args, **kwargs: [])
    response = discovery_client.get("/topics/example/timeline")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
