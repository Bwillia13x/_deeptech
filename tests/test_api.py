from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from signal_harvester.api import create_app
from signal_harvester.config import Settings
from signal_harvester.db import update_analysis, update_salience, upsert_tweet


def test_api_top_and_tweet(initialized_db: str, settings: Settings):
    """Test API endpoints using shared fixtures."""
    db_path = initialized_db

    # Seed DB
    tweet_data = {
        "tweet_id": "1234567890123456789",
        "text": "App is broken, please help",
        "author_id": "u1",
        "author_username": "user1",
        "created_at": "2024-01-01T00:00:00Z",
        "lang": "en",
        "like_count": 5,
        "retweet_count": 1,
        "reply_count": 0,
        "quote_count": 0,
        "raw_json": "{}",
    }
    
    upsert_tweet(db_path, tweet_data, query_name="test")
    
    # Add analysis and salience
    update_analysis(
        db_path,
        tweet_id="1234567890123456789",
        category="bug",
        sentiment="negative",
        urgency=2,
        tags_json='["bug"]',
        reasoning="Test analysis"
    )
    update_salience(db_path, "1234567890123456789", 85.0)

    # Create temp settings file for API
    with tempfile.TemporaryDirectory() as tmp_dir:
        cfg_dir = Path(tmp_dir) / "config"
        cfg_dir.mkdir()
        cfg_file = cfg_dir / "settings.yaml"
        cfg_file.write_text(
            f"""
app:
  database_path: "{db_path}"
  fetch:
    max_results: 10
    lang: "en"
  llm:
    provider: "dummy"
    model: "test-model"
    temperature: 0.2
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
            """,
            encoding="utf-8",
        )
        
        app = create_app(settings_path=str(cfg_file))
        client = TestClient(app)

        r = client.get("/top?limit=1")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["tweet_id"] == "1234567890123456789"

        r2 = client.get("/tweet/1234567890123456789")
        assert r2.status_code == 200
        row = r2.json()
        assert row["category"] == "bug"
        assert row["salience"] >= 80


def test_health_endpoint():
    """Basic health endpoint test."""
    app = create_app()
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    # The health endpoint returns "healthy" not "ok"
    assert r.json()["status"] == "healthy"
