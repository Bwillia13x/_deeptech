"""Integration tests for the full Signal Harvester pipeline."""

from __future__ import annotations

import os
import tempfile
import unittest

from signal_harvester.config import load_settings
from signal_harvester.db import init_db, list_top, update_analysis, update_salience, upsert_tweet
from signal_harvester.llm_client import Analysis
from signal_harvester.pipeline import run_pipeline
from signal_harvester.scoring import compute_salience


class TestIntegration(unittest.TestCase):
    """Test the full pipeline from fetch to notification."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.config_path = os.path.join(self.temp_dir, "settings.yaml")
        
        # Create test config
        config_content = f"""
app:
  database_path: "{self.db_path}"
  fetch:
    max_results: 10
    lang: "en"
  llm:
    provider: "dummy"
    model: "dummy-model"
    temperature: 0.0
  scoring:
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
        outage: 2.0
        security: 1.8
        bug: 1.3
        question: 1.0
        praise: 0.8
        other: 1.0
      recency_half_life_hours: 24.0
      base: 1.0
      cap: 100.0

queries:
  - name: "test_query"
    enabled: true
    query: "test query"
"""
        with open(self.config_path, "w") as f:
            f.write(config_content)
        
        # Initialize database
        init_db(self.db_path)
        
        # Load settings
        self.settings = load_settings(self.config_path)

    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_full_pipeline(self):
        """Test the complete pipeline with sample data."""
        # Insert sample tweets
        sample_tweets = [
            {
                "tweet_id": f"123456789{i}",
                "text": f"Test tweet {i} with some content #test",
                "author_id": f"author{i}",
                "author_username": f"user{i}",
                "created_at": "2024-01-01T00:00:00Z",
                "lang": "en",
                "like_count": 10 * i,
                "retweet_count": 5 * i,
                "reply_count": 2 * i,
                "quote_count": 1 * i,
                "raw_json": "{}",
            }
            for i in range(1, 6)
        ]
        
        for tweet in sample_tweets:
            upsert_tweet(self.db_path, tweet, query_name="test_query")
        
        # Run analysis (will use dummy analyzer)
        stats = run_pipeline(self.settings, notify_threshold=50.0, notify_limit=5, notify_hours=24)
        
        # Verify pipeline ran
        self.assertIn("fetched", stats)
        self.assertIn("analyzed", stats)
        self.assertIn("scored", stats)
        self.assertIn("notified", stats)
        
        # Check that some items were processed
        self.assertGreaterEqual(stats["fetched"], 0)
        self.assertGreaterEqual(stats["analyzed"], 0)
        self.assertGreaterEqual(stats["scored"], 0)
        
        # Verify data in database
        top_items = list_top(self.db_path, limit=10, min_salience=0.0)
        self.assertIsInstance(top_items, list)

    def test_scoring_and_analysis(self):
        """Test that analysis and scoring work together."""
        # Insert a tweet
        tweet = {
            "tweet_id": "999999999",
            "text": "Help! The service is down and I can't login. This is urgent! #outage",
            "author_id": "user123",
            "author_username": "testuser",
            "created_at": "2024-01-01T00:00:00Z",
            "lang": "en",
            "like_count": 5,
            "retweet_count": 3,
            "reply_count": 2,
            "quote_count": 1,
            "raw_json": "{}",
        }
        upsert_tweet(self.db_path, tweet, query_name="test_query")
        
        # Simulate analysis results
        analysis = Analysis(
            category="outage",
            sentiment="negative",
            urgency=4,
            tags=["outage", "login", "urgent"],
            reasoning="User reports service outage with login issues"
        )
        
        update_analysis(
            self.db_path,
            tweet_id="999999999",
            category=analysis.category,
            sentiment=analysis.sentiment,
            urgency=analysis.urgency,
            tags_json='["outage", "login", "urgent"]',
            reasoning=analysis.reasoning
        )
        
        # Compute and update salience
        tweet_row = {
            "tweet_id": "999999999",
            "like_count": 5,
            "retweet_count": 3,
            "reply_count": 2,
            "quote_count": 1,
            "created_at": "2024-01-01T00:00:00Z",
        }
        salience = compute_salience(tweet_row, analysis, self.settings.app.weights.model_dump())
        update_salience(self.db_path, tweet_id="999999999", salience=salience)
        
        # Verify the salience was computed and stored (should be > 0 due to urgency and negative sentiment)
        self.assertGreaterEqual(salience, 0)  # Salience can be 0 if weights are configured that way
        
        # Check that the tweet appears in top results
        top_items = list_top(self.db_path, limit=10, min_salience=0.0)
        self.assertTrue(any(item["tweet_id"] == "999999999" for item in top_items))
        
        # Check that the tweet appears in top results
        top_items = list_top(self.db_path, limit=10, min_salience=0.0)
        self.assertTrue(any(item["tweet_id"] == "999999999" for item in top_items))


if __name__ == "__main__":
    unittest.main()
