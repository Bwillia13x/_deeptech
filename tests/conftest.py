from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

import pytest

from signal_harvester.config import Settings, load_settings
from signal_harvester.db import init_db, run_migrations


@pytest.fixture(scope="session")
def test_settings_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create an isolated settings.yaml for tests pointing at temp DB."""

    tmp_dir = tmp_path_factory.mktemp("settings")
    settings_path = tmp_dir / "settings.yaml"
    db_path = tmp_dir / "app.db"
    settings_yaml = f"""
app:
  database_path: "{db_path}"
  fetch:
    max_results: 10
    lang: "en"
    window_hours: 24
  llm:
    provider: "dummy"
    model: "test-model"
    temperature: 0.2
  sources:
    facebook:
      access_token: "test-token"
      pages: ["testpage1"]
      groups: ["testgroup1"]
      search_queries: []
    github:
      token: ""
      orgs: []
      topics: []
      repos_per_org: 5
  weights:
    likes: 1.0
    retweets: 3.0
    replies: 2.0
    quotes: 2.5
    urgency: 4.0
    sentiment_positive: 1.0
    sentiment_negative: 1.2
    sentiment_neutral: 0.9
    category_boosts:
      bug: 1.3
      other: 1.0
    recency_half_life_hours: 24.0
    base: 1.0
    cap: 100.0
queries: []
"""
    settings_path.write_text(settings_yaml.strip(), encoding="utf-8")
    return settings_path


@pytest.fixture()
def settings(test_settings_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Load settings referencing a temporary database path."""

    db_path = tmp_path / "app.db"
    monkeypatch.setenv("HARVEST_DB_PATH", str(db_path))
    s = load_settings(str(test_settings_path))
    s.app.database_path = str(db_path)
    return s


@pytest.fixture()
def initialized_db(settings: Settings) -> Generator[str, None, None]:
    """Yield a database path after init + migrations."""

    db_path = settings.app.database_path
    init_db(db_path)
    run_migrations(db_path)
    try:
        yield db_path
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
