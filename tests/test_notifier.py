from __future__ import annotations

import os
import tempfile

from signal_harvester.db import init_db, upsert_tweet, update_analysis, update_salience, list_for_notification
from signal_harvester.notifier import SlackNotifier, notify_high_salience


def seed(db_path: str, tid: str = "t1") -> None:
    init_db(db_path)
    upsert_tweet(
        db_path,
        {
            "tweet_id": tid,
            "text": "App crashed with error 500",
            "author_id": "u1",
            "author_username": "user1",
            "created_at": "2024-01-01T00:00:00Z",
            "lang": "en",
            "like_count": 0,
            "retweet_count": 0,
            "reply_count": 0,
            "quote_count": 0,
            "raw_json": "{}",
        }
    )
    update_analysis(
        db_path,
        tweet_id=tid,
        category="bug",
        sentiment="negative",
        urgency=3,
        tags_json='["bug"]',
        reasoning="crash"
    )
    update_salience(db_path, tid, 90.0)


def test_notifier_disabled():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        seed(db_path)
        
        # Remove webhook URL from environment
        if "SLACK_WEBHOOK_URL" in os.environ:
            original_webhook = os.environ["SLACK_WEBHOOK_URL"]
            del os.environ["SLACK_WEBHOOK_URL"]
        else:
            original_webhook = None
            
        # Test with direct database path
        from signal_harvester.db import list_for_notification
        rows = list_for_notification(db_path, threshold=80, limit=5)
        assert len(rows) == 1
        
        notifier = SlackNotifier()
        sent = notifier.notify_rows(rows)
        assert sent == 0  # Should be 0 because webhook is disabled
        
        # Restore webhook URL if it existed
        if original_webhook:
            os.environ["SLACK_WEBHOOK_URL"] = original_webhook
            
    finally:
        os.unlink(db_path)


def test_notifier_format_message():
    row = {
        "tweet_id": "t1",
        "text": "App is broken",
        "author_username": "user1",
        "created_at": "2024-01-01T00:00:00Z",
        "category": "bug",
        "sentiment": "negative",
        "salience": 85.0,
        "like_count": 5,
        "retweet_count": 2,
        "reply_count": 1,
        "quote_count": 0,
    }
    
    msg = SlackNotifier.format_message(row)
    assert "85.0" in msg
    assert "bug/negative" in msg
    assert "@user1" in msg
    assert "App is broken" in msg
    assert "❤ 5 🔁 2 💬 1" in msg
    assert "https://x.com/user1/status/t1" in msg


def test_list_for_notification():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        seed(db_path)
        
        rows = list_for_notification(db_path, threshold=80, limit=5)
        assert len(rows) == 1
        assert rows[0]["tweet_id"] == "t1"
        assert rows[0]["salience"] == 90.0
        
        # Test with higher threshold
        rows_high = list_for_notification(db_path, threshold=95, limit=5)
        assert len(rows_high) == 0
        
    finally:
        os.unlink(db_path)
