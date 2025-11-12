"""Tests for cursor-based pagination functionality."""

import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from signal_harvester.db import (
    get_trending_topics_paginated,
    init_db,
    link_artifact_topic,
    list_top_discoveries_paginated,
    run_migrations,
    update_discovery_scores,
    upsert_artifact,
    upsert_topic,
)


@pytest.fixture
def populated_db(tmp_path: Any) -> str:
    """Create a database with test data."""
    db_path = str(tmp_path / "test_pagination.db")
    init_db(db_path)
    run_migrations(db_path)
    
    # Create topics
    topic1_id = upsert_topic(db_path, "Machine Learning", "ai/ml")
    topic2_id = upsert_topic(db_path, "Quantum Computing", "physics/quantum")
    topic3_id = upsert_topic(db_path, "Robotics", "engineering/robotics")
    
    # Create 25 artifacts with varying discovery scores
    now = datetime.now(tz=timezone.utc)
    artifact_ids = []
    
    for i in range(25):
        artifact_id = upsert_artifact(
            db_path,
            artifact_type="paper",
            source="arxiv",
            source_id=f"2024.{i:05d}",
            title=f"Research Paper {i}",
            url=f"https://arxiv.org/abs/2024.{i:05d}",
            published_at=(now - timedelta(hours=i)).isoformat(),
        )
        artifact_ids.append(artifact_id)
        
        # Assign varying discovery scores (higher scores for lower i)
        score = 95.0 - (i * 2.0)  # Scores from 95 to 47
        update_discovery_scores(
            db_path,
            artifact_id,
            novelty=score,
            emergence=score,
            obscurity=score,
            discovery_score=score,
        )
        
        # Link to topics (cycle through topics)
        topic_id = [topic1_id, topic2_id, topic3_id][i % 3]
        link_artifact_topic(db_path, artifact_id, topic_id)
    
    return db_path


class TestDiscoveriesPagination:
    """Tests for discoveries cursor-based pagination."""

    def test_basic_pagination(self, populated_db: str) -> None:
        """Test basic pagination without cursor."""
        results, next_cursor, has_more = list_top_discoveries_paginated(
            populated_db,
            min_score=50.0,
            limit=10,
        )
        
        assert len(results) == 10
        assert has_more is True
        assert next_cursor is not None
        
        # Scores should be descending
        scores = [r["discovery_score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_pagination_with_cursor(self, populated_db: str) -> None:
        """Test pagination using cursor from previous page."""
        # Get first page
        page1, cursor1, has_more1 = list_top_discoveries_paginated(
            populated_db,
            min_score=50.0,
            limit=10,
        )
        
        assert len(page1) == 10
        assert has_more1 is True
        assert cursor1 is not None
        
        # Get second page using cursor
        page2, cursor2, has_more2 = list_top_discoveries_paginated(
            populated_db,
            min_score=50.0,
            limit=10,
            cursor=cursor1,
        )
        
        assert len(page2) == 10
        assert has_more2 is True  # 23 results total with score >= 50 (95, 93, ..., 51)
        
        # Get third page
        page3, cursor3, has_more3 = list_top_discoveries_paginated(
            populated_db,
            min_score=50.0,
            limit=10,
            cursor=cursor2,
        )
        
        assert len(page3) == 3  # Remaining results (scores 55, 53, 51)
        assert has_more3 is False  # No more results
        
        # Ensure no overlap between pages
        page1_ids = {r["id"] for r in page1}
        page2_ids = {r["id"] for r in page2}
        page3_ids = {r["id"] for r in page3}
        assert page1_ids.isdisjoint(page2_ids)
        assert page1_ids.isdisjoint(page3_ids)
        assert page2_ids.isdisjoint(page3_ids)
        
        # Ensure continuation of scores
        last_score_page1 = page1[-1]["discovery_score"]
        first_score_page2 = page2[0]["discovery_score"]
        last_score_page2 = page2[-1]["discovery_score"]
        first_score_page3 = page3[0]["discovery_score"]
        assert first_score_page2 <= last_score_page1
        assert first_score_page3 <= last_score_page2

    def test_last_page_no_cursor(self, populated_db: str) -> None:
        """Test that last page has no next cursor."""
        # Request all results that should fit in one page
        results, next_cursor, has_more = list_top_discoveries_paginated(
            populated_db,
            min_score=50.0,
            limit=50,  # Request more than available
        )
        
        assert len(results) == 23  # Only 23 artifacts have score >= 50
        assert has_more is False
        assert next_cursor is None

    def test_pagination_with_hours_filter(self, populated_db: str) -> None:
        """Test pagination with hours filter."""
        results, next_cursor, has_more = list_top_discoveries_paginated(
            populated_db,
            min_score=50.0,
            limit=5,
            hours=10,  # Only last 10 hours
        )
        
        # Should only get artifacts from last 10 hours
        assert len(results) <= 10
        assert all(r["discovery_score"] >= 50.0 for r in results)

    def test_invalid_cursor_ignored(self, populated_db: str) -> None:
        """Test that invalid cursor is ignored gracefully."""
        # Invalid base64
        results1, _, _ = list_top_discoveries_paginated(
            populated_db,
            min_score=50.0,
            limit=10,
            cursor="invalid-cursor",
        )
        
        # Should return first page when cursor invalid
        assert len(results1) == 10
        
        # Invalid JSON
        bad_cursor = base64.b64encode(b"not-json").decode('utf-8')
        results2, _, _ = list_top_discoveries_paginated(
            populated_db,
            min_score=50.0,
            limit=10,
            cursor=bad_cursor,
        )
        
        assert len(results2) == 10

    def test_cursor_format(self, populated_db: str) -> None:
        """Test cursor contains expected fields."""
        _, cursor, _ = list_top_discoveries_paginated(
            populated_db,
            min_score=50.0,
            limit=10,
        )
        
        assert cursor is not None
        
        # Decode cursor
        cursor_data = json.loads(base64.b64decode(cursor).decode('utf-8'))
        
        assert "score" in cursor_data
        assert "id" in cursor_data
        assert isinstance(cursor_data["score"], (int, float))
        assert isinstance(cursor_data["id"], int)

    def test_consistent_ordering(self, populated_db: str) -> None:
        """Test that pagination maintains consistent ordering."""
        # Get all results in pages
        all_results = []
        cursor = None
        
        while True:
            results, cursor, has_more = list_top_discoveries_paginated(
                populated_db,
                min_score=50.0,
                limit=5,
                cursor=cursor,
            )
            all_results.extend(results)
            
            if not has_more:
                break
        
        # Verify ordering is consistent (descending by score)
        scores = [r["discovery_score"] for r in all_results]
        assert scores == sorted(scores, reverse=True)
        
        # Verify no duplicates
        ids = [r["id"] for r in all_results]
        assert len(ids) == len(set(ids))


class TestTopicsPagination:
    """Tests for topics cursor-based pagination."""

    def test_basic_pagination(self, populated_db: str) -> None:
        """Test basic topics pagination."""
        results, next_cursor, has_more = get_trending_topics_paginated(
            populated_db,
            window_days=30,
            limit=2,
        )
        
        # We created 3 topics
        assert len(results) == 2
        assert has_more is True
        assert next_cursor is not None

    def test_pagination_with_cursor(self, populated_db: str) -> None:
        """Test topics pagination with cursor."""
        # Get first page
        page1, cursor1, has_more1 = get_trending_topics_paginated(
            populated_db,
            window_days=30,
            limit=2,
        )
        
        assert len(page1) == 2
        assert has_more1 is True
        
        # Get second page
        page2, cursor2, has_more2 = get_trending_topics_paginated(
            populated_db,
            window_days=30,
            limit=2,
            cursor=cursor1,
        )
        
        assert len(page2) == 1  # Only 3 topics total
        assert has_more2 is False
        
        # No overlap
        page1_ids = {r["id"] for r in page1}
        page2_ids = {r["id"] for r in page2}
        assert page1_ids.isdisjoint(page2_ids)

    def test_topics_ordering(self, populated_db: str) -> None:
        """Test topics are ordered by artifact count."""
        results, _, _ = get_trending_topics_paginated(
            populated_db,
            window_days=30,
            limit=10,
        )
        
        # All topics should have similar artifact counts (8 or 9 each)
        counts = [r["artifact_count"] for r in results]
        assert counts == sorted(counts, reverse=True)

    def test_cursor_format_topics(self, populated_db: str) -> None:
        """Test topics cursor format."""
        _, cursor, _ = get_trending_topics_paginated(
            populated_db,
            window_days=30,
            limit=2,
        )
        
        assert cursor is not None
        
        cursor_data = json.loads(base64.b64decode(cursor).decode('utf-8'))
        
        assert "count" in cursor_data
        assert "id" in cursor_data
        assert isinstance(cursor_data["count"], int)
        assert isinstance(cursor_data["id"], int)


class TestPaginationEdgeCases:
    """Tests for pagination edge cases."""

    def test_empty_results(self, populated_db: str) -> None:
        """Test pagination with no matching results."""
        results, cursor, has_more = list_top_discoveries_paginated(
            populated_db,
            min_score=99.0,  # No artifacts have this score
            limit=10,
        )
        
        assert len(results) == 0
        assert cursor is None
        assert has_more is False

    def test_single_result(self, populated_db: str) -> None:
        """Test pagination with single result."""
        results, cursor, has_more = list_top_discoveries_paginated(
            populated_db,
            min_score=94.0,  # Only highest-scored artifact
            limit=10,
        )
        
        assert len(results) == 1
        assert cursor is None
        assert has_more is False

    def test_exact_limit_match(self, populated_db: str) -> None:
        """Test when results exactly match limit."""
        # We have exactly 23 artifacts with score >= 50
        results, cursor, has_more = list_top_discoveries_paginated(
            populated_db,
            min_score=50.0,
            limit=23,
        )
        
        assert len(results) == 23
        assert cursor is None
        assert has_more is False

    def test_large_limit(self, populated_db: str) -> None:
        """Test with very large limit."""
        results, cursor, has_more = list_top_discoveries_paginated(
            populated_db,
            min_score=0.0,
            limit=1000,
        )
        
        assert len(results) == 25  # All artifacts
        assert cursor is None
        assert has_more is False

    def test_pagination_deterministic(self, populated_db: str) -> None:
        """Test that repeated pagination gives same results."""
        # First iteration
        results1 = []
        cursor = None
        while True:
            page, cursor, has_more = list_top_discoveries_paginated(
                populated_db,
                min_score=50.0,
                limit=5,
                cursor=cursor,
            )
            results1.extend(page)
            if not has_more:
                break
        
        # Second iteration
        results2 = []
        cursor = None
        while True:
            page, cursor, has_more = list_top_discoveries_paginated(
                populated_db,
                min_score=50.0,
                limit=5,
                cursor=cursor,
            )
            results2.extend(page)
            if not has_more:
                break
        
        # Should get same results in same order
        ids1 = [r["id"] for r in results1]
        ids2 = [r["id"] for r in results2]
        assert ids1 == ids2
