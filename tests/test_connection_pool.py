"""Tests for database connection pooling."""

import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from typing import Generator

import pytest

from signal_harvester.db_pool import (
    ConnectionPool,
    get_pool,
    init_pool,
    pooled_connection,
)


@pytest.fixture
def temp_db() -> Generator[Path, None, None]:
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    
    # Initialize database with a test table
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO test (value) VALUES ('test1')")
    conn.commit()
    conn.close()
    
    yield db_path
    
    # Cleanup
    db_path.unlink(missing_ok=True)


@pytest.fixture
def pool(temp_db: Path) -> Generator[ConnectionPool, None, None]:
    """Create a connection pool for testing."""
    pool = ConnectionPool(
        db_path=str(temp_db),
        pool_size=2,
        max_overflow=2,
        pool_timeout=2.0,
        pool_recycle=5,
    )
    yield pool
    pool.close_all()


def test_pool_initialization(temp_db: Path) -> None:
    """Test connection pool initialization."""
    pool = ConnectionPool(
        db_path=str(temp_db),
        pool_size=3,
        max_overflow=5,
        pool_timeout=10.0,
        pool_recycle=60,
    )
    
    assert pool.pool_size == 3
    assert pool.max_overflow == 5
    assert pool.pool_timeout == 10.0
    assert pool.pool_recycle == 60
    assert pool._overflow_count == 0
    
    # Pool should pre-create connections
    stats = pool.get_stats()
    assert stats["created"] == 3  # pool_size connections pre-created
    
    pool.close_all()


def test_connection_acquisition(pool: ConnectionPool, temp_db: Path) -> None:
    """Test acquiring a connection from the pool."""
    with pool.connection() as conn:
        cursor = conn.execute("SELECT value FROM test WHERE id = 1")
        result = cursor.fetchone()
        assert result is not None
        assert result[0] == "test1"


def test_connection_reuse(pool: ConnectionPool) -> None:
    """Test that connections are reused from the pool."""
    # Pool starts with pool_size pre-created connections
    stats_init = pool.get_stats()
    initial_created = stats_init["created"]  # Should be pool_size=2
    
    # First acquisition reuses a pre-created connection
    with pool.connection() as conn1:
        conn1.execute("SELECT 1")
    
    stats1 = pool.get_stats()
    assert stats1["created"] == initial_created  # No new connections
    assert stats1["reused"] == 1  # Reused pre-created connection
    
    # Second acquisition also reuses
    with pool.connection() as conn2:
        conn2.execute("SELECT 1")
    
    stats2 = pool.get_stats()
    assert stats2["created"] == initial_created  # Still no new connections
    assert stats2["reused"] == 2  # Reused again


def test_overflow_behavior(pool: ConnectionPool) -> None:
    """Test pool overflow when pool_size is exceeded."""
    connections = []
    
    # Acquire pool_size + 1 connections (should use overflow)
    with pool.connection() as conn1:
        connections.append(conn1)
        with pool.connection() as conn2:
            connections.append(conn2)
            # Third connection should use overflow
            with pool.connection() as conn3:
                connections.append(conn3)
                stats = pool.get_stats()
                assert stats["overflow_used"] >= 1


def test_pool_timeout(pool: ConnectionPool) -> None:
    """Test timeout when pool is exhausted."""
    # Acquire all connections (pool_size + max_overflow)
    contexts = []
    
    try:
        # Acquire pool_size + max_overflow connections
        for _ in range(4):  # pool_size=2 + max_overflow=2
            ctx = pool.connection()
            ctx.__enter__()
            contexts.append(ctx)
        
        # Try to acquire one more connection - should timeout
        with pytest.raises(TimeoutError, match="Could not acquire connection"):
            with pool.connection():
                pass
    finally:
        # Cleanup
        for ctx in contexts:
            try:
                ctx.__exit__(None, None, None)
            except Exception:
                pass


def test_connection_recycling(temp_db: Path) -> None:
    """Test connection recycling based on age."""
    pool = ConnectionPool(
        db_path=str(temp_db),
        pool_size=2,
        max_overflow=0,
        pool_timeout=1.0,
        pool_recycle=1,  # Recycle after 1 second
    )
    
    try:
        # Pool starts with 2 pre-created connections
        stats_init = pool.get_stats()
        initial_created = stats_init["created"]  # Should be 2
        
        # Use a connection
        with pool.connection() as conn:
            conn.execute("SELECT 1")
        
        stats1 = pool.get_stats()
        assert stats1["created"] == initial_created
        assert stats1["recycled"] == 0
        
        # Wait for recycle period
        time.sleep(1.5)
        
        # Next connection should be recycled
        with pool.connection() as conn:
            conn.execute("SELECT 1")
        
        stats2 = pool.get_stats()
        assert stats2["recycled"] == 1
    finally:
        pool.close_all()


def test_statistics_tracking(pool: ConnectionPool) -> None:
    """Test pool statistics tracking."""
    stats = pool.get_stats()
    
    # Initial stats - pool has pre-created connections
    assert stats["created"] == 2  # pool_size=2
    assert stats["reused"] == 0
    assert stats["recycled"] == 0
    assert stats["overflow_used"] == 0
    assert stats["timeouts"] == 0
    assert stats["pool_utilization"] == 0.0  # No connections in use
    
    # Acquire a connection
    with pool.connection():
        stats_in_use = pool.get_stats()
        assert stats_in_use["pool_utilization"] == 50.0  # 1 of 2 connections
    
    # After release
    stats = pool.get_stats()
    assert stats["created"] == 2  # No new connections
    assert stats["reused"] == 1  # One reuse


def test_concurrent_access(pool: ConnectionPool, temp_db: Path) -> None:
    """Test concurrent connection access from multiple threads."""
    results = []
    errors = []
    
    def worker(worker_id: int) -> None:
        """Worker function for thread testing."""
        try:
            with pool.connection() as conn:
                cursor = conn.execute("SELECT value FROM test WHERE id = 1")
                result = cursor.fetchone()
                results.append((worker_id, result[0] if result else None))
        except Exception as e:
            errors.append((worker_id, str(e)))
    
    # Create multiple threads
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    
    # Start all threads
    for thread in threads:
        thread.start()
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    # Verify results
    assert len(errors) == 0, f"Errors occurred: {errors}"
    assert len(results) == 5
    for worker_id, value in results:
        assert value == "test1"


def test_rollback_on_error(pool: ConnectionPool) -> None:
    """Test automatic rollback when exception occurs."""
    # Start a transaction and raise an error
    try:
        with pool.connection() as conn:
            conn.execute("INSERT INTO test (value) VALUES ('error_test')")
            raise ValueError("Test error")
    except ValueError:
        pass
    
    # Verify transaction was rolled back
    with pool.connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM test WHERE value = 'error_test'")
        count = cursor.fetchone()[0]
        assert count == 0


def test_global_pool_initialization(temp_db: Path) -> None:
    """Test global pool initialization."""
    pool = init_pool(
        db_path=str(temp_db),
        pool_size=3,
        max_overflow=5,
        pool_timeout=10.0,
        pool_recycle=60,
    )
    
    assert pool is not None
    
    # Get the global pool
    retrieved_pool = get_pool()
    assert retrieved_pool is pool
    
    # Test pooled_connection context manager
    with pooled_connection() as conn:
        cursor = conn.execute("SELECT value FROM test WHERE id = 1")
        result = cursor.fetchone()
        assert result is not None
        assert result[0] == "test1"
    
    pool.close_all()


def test_global_pool_error_without_init() -> None:
    """Test that get_pool raises error when pool not initialized."""
    # Reset global pool state
    import signal_harvester.db_pool as db_pool_module
    db_pool_module._global_pool = None
    
    with pytest.raises(RuntimeError, match="Connection pool not initialized"):
        get_pool()


def test_connection_properties(pool: ConnectionPool) -> None:
    """Test that connections have correct SQLite properties."""
    with pool.connection() as conn:
        # Check WAL mode
        cursor = conn.execute("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0]
        assert journal_mode.upper() == "WAL"
        
        # Check foreign keys enabled
        cursor = conn.execute("PRAGMA foreign_keys")
        foreign_keys = cursor.fetchone()[0]
        assert foreign_keys == 1
        
        # Check synchronous mode
        cursor = conn.execute("PRAGMA synchronous")
        synchronous = cursor.fetchone()[0]
        assert synchronous == 1  # NORMAL


def test_pool_close_all(pool: ConnectionPool) -> None:
    """Test closing all connections in the pool."""
    # Create some connections
    with pool.connection():
        pass
    with pool.connection():
        pass
    
    stats_before = pool.get_stats()
    assert stats_before["created"] > 0
    
    # Close all connections
    pool.close_all()
    
    # Pool should be empty
    assert pool._pool.qsize() == 0


def test_pool_utilization_calculation(pool: ConnectionPool) -> None:
    """Test pool utilization percentage calculation."""
    stats = pool.get_stats()
    assert stats["pool_utilization"] == 0.0
    
    # Acquire one connection
    with pool.connection():
        stats = pool.get_stats()
        # pool_size = 2, so 1 connection = 50% utilization
        assert stats["pool_utilization"] == 50.0

        # Acquire second connection while the first is still in use
        with pool.connection():
            stats = pool.get_stats()
            # 2 connections = 100% utilization
            assert stats["pool_utilization"] == 100.0


def test_overflow_count_tracking(pool: ConnectionPool) -> None:
    """Test overflow connection count tracking."""
    contexts = []
    
    try:
        # Acquire pool_size connections
        for _ in range(2):  # pool_size = 2
            ctx = pool.connection()
            ctx.__enter__()
            contexts.append(ctx)
        
        stats = pool.get_stats()
        assert stats["overflow_used"] == 0
        
        # Acquire overflow connection
        ctx = pool.connection()
        ctx.__enter__()
        contexts.append(ctx)
        
        stats = pool.get_stats()
        assert stats["overflow_used"] >= 1
    finally:
        # Cleanup
        for ctx in contexts:
            try:
                ctx.__exit__(None, None, None)
            except Exception:
                pass


def test_connection_isolation(pool: ConnectionPool) -> None:
    """Test that connections are properly isolated."""
    # Create temporary table in first connection
    with pool.connection() as conn1:
        conn1.execute("CREATE TEMP TABLE temp_test (id INTEGER)")
        conn1.execute("INSERT INTO temp_test VALUES (1)")
    
    # Temp table should not exist in second connection
    with pool.connection() as conn2:
        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            conn2.execute("SELECT * FROM temp_test")
