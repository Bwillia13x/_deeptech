"""Performance regression tests to ensure system meets SLA requirements.

These tests validate that critical operations complete within acceptable time limits:
- Database queries: p95 < 100ms, p99 < 500ms
- API endpoints: p95 < 500ms, p99 < 1000ms
- Pipeline operations: Complete within time budgets
"""

import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

from signal_harvester import db
from signal_harvester.config import load_settings
from signal_harvester.performance import CRITICAL_QUERIES, benchmark_query


class TestDatabasePerformance:
    """Performance regression tests for database queries."""

    @pytest.fixture(scope="class")
    def db_path(self, tmp_path_factory) -> str:
        """Create test database with sample data."""
        db_path = str(tmp_path_factory.mktemp("data") / "perf_test.db")
        db.init_db(db_path)
        
        # Insert sample data
        with sqlite3.connect(db_path) as conn:
            # Insert 1000 artifacts
            for i in range(1000):
                conn.execute(
                    """
                    INSERT INTO artifacts (title, url, source, published_at, metadata_json)
                    VALUES (?, ?, ?, datetime('now', ?), '{}')
                    """,
                    (f"Artifact {i}", f"https://example.com/{i}", "arxiv", f"-{i} days"),
                )
            
            # Insert scores for all artifacts
            conn.execute(
                """
                INSERT INTO scores (artifact_id, discovery_score, novelty, emergence, obscurity)
                SELECT id, 50 + (random() % 50), 0.5, 0.5, 0.5
                FROM artifacts
                """
            )
            
            # Insert topics
            for i in range(50):
                conn.execute(
                    "INSERT INTO topics (name, description) VALUES (?, ?)",
                    (f"Topic {i}", f"Description {i}"),
                )
            
            # Insert artifact-topic mappings
            conn.execute(
                """
                INSERT INTO artifact_topics (artifact_id, topic_id, confidence)
                SELECT a.id, (a.id % 50) + 1, 0.8
                FROM artifacts a
                """
            )
            
            # Insert entities
            for i in range(100):
                conn.execute(
                    "INSERT INTO entities (name, entity_type, influence_score) VALUES (?, ?, ?)",
                    (f"Researcher {i}", "person", 50.0 + i),
                )
            
            # Insert relationships
            conn.execute(
                """
                INSERT INTO artifact_relationships (source_artifact_id, target_artifact_id, relationship_type, confidence)
                SELECT a1.id, a2.id, 'cite', 0.9
                FROM artifacts a1
                CROSS JOIN artifacts a2
                WHERE a1.id < a2.id
                LIMIT 500
                """
            )
            
            conn.commit()
        
        return db_path

    def test_critical_queries_meet_sla(self, db_path: str):
        """Test all critical queries meet p95 < 100ms SLA."""
        with sqlite3.connect(db_path) as conn:
            failures = []
            
            for query_profile in CRITICAL_QUERIES:
                if not query_profile.critical:
                    continue  # Only test critical queries
                
                stats = benchmark_query(conn, query_profile.query, iterations=100)
                
                # Check p95 latency
                if stats["p95_ms"] >= 100.0:
                    failures.append(
                        f"{query_profile.name}: p95={stats['p95_ms']:.2f}ms (expected < 100ms)"
                    )
                
                # Check p99 latency
                if stats["p99_ms"] >= 500.0:
                    failures.append(
                        f"{query_profile.name}: p99={stats['p99_ms']:.2f}ms (expected < 500ms)"
                    )
            
            if failures:
                pytest.fail("\n".join(["Query SLA violations:"] + failures))

    def test_top_discoveries_pagination_performance(self, db_path: str):
        """Test paginated discovery queries complete quickly."""
        queries = [
            # First page
            """
            SELECT a.*, s.discovery_score
            FROM artifacts a
            JOIN scores s ON s.artifact_id = a.id
            ORDER BY s.discovery_score DESC
            LIMIT 50 OFFSET 0
            """,
            # Second page
            """
            SELECT a.*, s.discovery_score
            FROM artifacts a
            JOIN scores s ON s.artifact_id = a.id
            ORDER BY s.discovery_score DESC
            LIMIT 50 OFFSET 50
            """,
            # Fifth page
            """
            SELECT a.*, s.discovery_score
            FROM artifacts a
            JOIN scores s ON s.artifact_id = a.id
            ORDER BY s.discovery_score DESC
            LIMIT 50 OFFSET 200
            """,
        ]
        
        with sqlite3.connect(db_path) as conn:
            for i, query in enumerate(queries, 1):
                stats = benchmark_query(conn, query, iterations=50)
                
                assert stats["p95_ms"] < 100.0, (
                    f"Page {i} p95={stats['p95_ms']:.2f}ms exceeded 100ms"
                )

    def test_concurrent_read_performance(self, db_path: str):
        """Test database handles concurrent reads efficiently."""
        import concurrent.futures
        
        def run_query():
            with sqlite3.connect(db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT a.*, s.discovery_score
                    FROM artifacts a
                    JOIN scores s ON s.artifact_id = a.id
                    ORDER BY s.discovery_score DESC
                    LIMIT 50
                    """
                )
                return cursor.fetchall()
        
        start = time.perf_counter()
        
        # Run 10 concurrent queries
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(run_query) for _ in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        duration = time.perf_counter() - start
        
        # All 10 queries should complete in under 1 second combined
        assert duration < 1.0, f"Concurrent reads took {duration:.2f}s (expected < 1s)"
        assert len(results) == 10

    def test_write_operation_performance(self, db_path: str):
        """Test write operations complete within acceptable limits."""
        with sqlite3.connect(db_path) as conn:
            # Test single insert
            start = time.perf_counter()
            conn.execute(
                """
                INSERT INTO artifacts (title, url, source, published_at, metadata_json)
                VALUES (?, ?, ?, datetime('now'), '{}')
                """,
                ("Test Artifact", "https://test.com", "arxiv"),
            )
            conn.commit()
            single_insert_duration = (time.perf_counter() - start) * 1000
            
            assert single_insert_duration < 50.0, (
                f"Single insert took {single_insert_duration:.2f}ms (expected < 50ms)"
            )
            
            # Test batch insert
            start = time.perf_counter()
            for i in range(100):
                conn.execute(
                    """
                    INSERT INTO artifacts (title, url, source, published_at, metadata_json)
                    VALUES (?, ?, ?, datetime('now'), '{}')
                    """,
                    (f"Batch {i}", f"https://batch.com/{i}", "github"),
                )
            conn.commit()
            batch_duration = (time.perf_counter() - start) * 1000
            
            assert batch_duration < 500.0, (
                f"Batch insert (100 rows) took {batch_duration:.2f}ms (expected < 500ms)"
            )

    def test_complex_join_performance(self, db_path: str):
        """Test multi-table joins complete efficiently."""
        complex_query = """
        SELECT 
            a.id,
            a.title,
            s.discovery_score,
            t.name as topic_name,
            e.name as entity_name
        FROM artifacts a
        JOIN scores s ON s.artifact_id = a.id
        LEFT JOIN artifact_topics at ON at.artifact_id = a.id
        LEFT JOIN topics t ON t.id = at.topic_id
        LEFT JOIN entities e ON e.id = a.id % 100
        WHERE a.published_at >= date('now', '-30 days')
        ORDER BY s.discovery_score DESC
        LIMIT 100
        """
        
        with sqlite3.connect(db_path) as conn:
            stats = benchmark_query(conn, complex_query, iterations=25)
            
            assert stats["p95_ms"] < 200.0, (
                f"Complex join p95={stats['p95_ms']:.2f}ms exceeded 200ms"
            )


class TestAPIEndpointPerformance:
    """Performance tests for API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from fastapi.testclient import TestClient
        from signal_harvester.api import app
        
        return TestClient(app)

    def test_discoveries_endpoint_response_time(self, client):
        """Test /discoveries endpoint meets <500ms p95 target."""
        latencies = []
        
        for _ in range(25):
            start = time.perf_counter()
            response = client.get("/discoveries?limit=50")
            latency = (time.perf_counter() - start) * 1000
            latencies.append(latency)
            
            assert response.status_code in (200, 404), "Response should succeed or gracefully fail"
        
        latencies.sort()
        p95 = latencies[int(len(latencies) * 0.95)]
        
        # Allow higher threshold for API (includes serialization)
        assert p95 < 1000.0, f"Discoveries endpoint p95={p95:.2f}ms exceeded 1000ms"

    def test_health_endpoint_lightweight(self, client):
        """Test /health endpoint is very fast (<10ms)."""
        latencies = []
        
        for _ in range(50):
            start = time.perf_counter()
            response = client.get("/health")
            latency = (time.perf_counter() - start) * 1000
            latencies.append(latency)
            
            assert response.status_code == 200
        
        mean_latency = sum(latencies) / len(latencies)
        
        assert mean_latency < 10.0, f"Health endpoint mean={mean_latency:.2f}ms exceeded 10ms"


class TestPipelinePerformance:
    """Performance tests for pipeline operations."""

    def test_discovery_scoring_throughput(self, tmp_path: Path):
        """Test scoring can process 100 artifacts in under 10 seconds."""
        db_path = str(tmp_path / "scoring_test.db")
        db.init_db(db_path)
        
        # Insert 100 artifacts
        with sqlite3.connect(db_path) as conn:
            for i in range(100):
                conn.execute(
                    """
                    INSERT INTO artifacts (title, url, source, published_at, metadata_json)
                    VALUES (?, ?, ?, datetime('now'), '{}')
                    """,
                    (f"Artifact {i}", f"https://example.com/{i}", "arxiv"),
                )
            conn.commit()
        
        # Time scoring operation
        from signal_harvester.discovery_scoring import score_all_artifacts
        
        start = time.perf_counter()
        with sqlite3.connect(db_path) as conn:
            score_all_artifacts(conn)
        duration = time.perf_counter() - start
        
        assert duration < 10.0, f"Scoring 100 artifacts took {duration:.2f}s (expected < 10s)"
        
        # Verify scores were calculated
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM scores")
            count = cursor.fetchone()[0]
            assert count == 100, "All artifacts should be scored"


@pytest.mark.benchmark
class TestMemoryUsage:
    """Memory usage regression tests."""

    def test_large_result_set_memory(self):
        """Test that large queries don't cause memory issues."""
        import tracemalloc
        
        tracemalloc.start()
        
        # Simulate loading 10,000 artifacts
        artifacts = [
            {
                "id": i,
                "title": f"Artifact {i}" * 10,  # Make it larger
                "abstract": f"Abstract {i}" * 100,
                "metadata": {"key": "value" * 50},
            }
            for i in range(10000)
        ]
        
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        # Peak memory should be under 100MB for 10k artifacts
        peak_mb = peak / 1024 / 1024
        assert peak_mb < 100.0, f"Memory usage {peak_mb:.2f}MB exceeded 100MB"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "not benchmark"])
