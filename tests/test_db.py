from __future__ import annotations

import tempfile

from signal_harvester.db import init_db, list_top, update_analysis, update_salience, upsert_tweet


def test_db_operations():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        # Initialize database
        init_db(db_path)

        # Insert a test tweet
        tweet_data = {
            "tweet_id": "1234567890",
            "text": "Test tweet about a bug in the system",
            "author_id": "user123",
            "author_username": "testuser",
            "created_at": "2024-01-01T12:00:00Z",
            "lang": "en",
            "like_count": 5,
            "retweet_count": 2,
            "reply_count": 1,
            "quote_count": 0,
            "raw_json": "{}",
        }

        inserted = upsert_tweet(db_path, tweet_data, query_name="test_query")
        assert inserted is True

        # Add analysis and salience
        update_analysis(
            db_path,
            tweet_id="1234567890",
            category="bug",
            sentiment="negative",
            urgency=2,
            tags_json='["bug"]',
            reasoning="Test analysis"
        )
        update_salience(db_path, "1234567890", 85.0)

        # Query top items
        top_items = list_top(db_path, limit=10)
        assert len(top_items) == 1
        assert top_items[0]["tweet_id"] == "1234567890"

    finally:
        import os
        os.unlink(db_path)
