from __future__ import annotations

from datetime import datetime, timezone, timedelta

from signal_harvester.llm_client import Analysis
from signal_harvester.scoring import compute_salience


def test_compute_salience():
    # Test tweet data (recent date)
    recent_time = (datetime.now(tz=timezone.utc) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    tweet_row = {
        "tweet_id": "1234567890",
        "text": "Test tweet",
        "author_id": "user123",
        "author_username": "testuser",
        "created_at": recent_time,
        "lang": "en",
        "like_count": 10,
        "retweet_count": 5,
        "reply_count": 3,
        "quote_count": 2,
    }

    # Test analysis
    analysis = Analysis(
        category="bug",
        sentiment="negative",
        urgency=3,
        tags=["bug", "issue"],
        reasoning="Test reasoning",
    )

    # Test weights
    weights = {
        "likes": 1.0,
        "retweets": 3.0,
        "replies": 2.0,
        "quotes": 2.5,
        "urgency": 4.0,
        "base": 1.0,
        "cap": 100.0,
        "recency_half_life_hours": 24.0,
        "category_boosts": {
            "bug": 1.3,
            "outage": 1.5,
            "other": 1.0,
        },
        "sentiment_positive": 1.0,
        "sentiment_negative": 1.2,
        "sentiment_neutral": 0.9,
    }

    score = compute_salience(tweet_row, analysis, weights)
    
    # Score should be positive and reasonable
    assert score > 0
    assert score <= 100
    
    # More urgent/negative should score higher
    urgent_analysis = Analysis(
        category="outage",
        sentiment="negative", 
        urgency=5,
        tags=["outage"],
        reasoning="Critical issue",
    )
    
    urgent_score = compute_salience(tweet_row, urgent_analysis, weights)
    assert urgent_score > score
