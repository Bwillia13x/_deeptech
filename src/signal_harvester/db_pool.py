"""Database connection pool for SQLite with thread-safe connection management.

SQLite doesn't support traditional connection pooling like PostgreSQL, but we can
implement a pool to reuse connections and limit concurrent connections.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from queue import Empty, Queue
from typing import Any, Generator

from .logger import get_logger

log = get_logger(__name__)


class ConnectionPool:
    """Thread-safe connection pool for SQLite.
    
    Args:
        db_path: Path to SQLite database file
        pool_size: Maximum number of connections to keep in pool
        max_overflow: Maximum connections beyond pool_size
        pool_timeout: Seconds to wait for available connection
        pool_recycle: Seconds before recycling a connection (-1 to disable)
    """
    
    def __init__(
        self,
        db_path: str,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_timeout: float = 30.0,
        pool_recycle: int = 3600,
    ):
        self.db_path = db_path
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.pool_timeout = pool_timeout
        self.pool_recycle = pool_recycle
        
        self._pool: Queue[tuple[sqlite3.Connection, float]] = Queue(maxsize=pool_size)
        self._overflow_count = 0
        self._in_use_count = 0  # Track connections currently in use
        self._overflow_lock = threading.Lock()
        self._stats: dict[str, int | float] = {
            "created": 0,
            "reused": 0,
            "recycled": 0,
            "overflow_used": 0,
            "timeouts": 0,
        }
        self._stats_lock = threading.Lock()
        
        # Pre-create pool connections
        for _ in range(pool_size):
            conn = self._create_connection()
            self._pool.put((conn, time.time()))
        
        log.info(
            f"Connection pool initialized: pool_size={pool_size}, "
            f"max_overflow={max_overflow}, timeout={pool_timeout}s"
        )
    
    def _create_connection(self) -> sqlite3.Connection:
        """Create a new database connection with optimal settings."""
        conn = sqlite3.connect(
            self.db_path,
            timeout=10.0,
            isolation_level="DEFERRED",  # Enable transaction support for rollback
            check_same_thread=False,  # Allow connection sharing across threads
        )
        conn.row_factory = sqlite3.Row
        
        # Configure SQLite pragmas for performance
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=5000;")
        # Enable query optimization
        conn.execute("PRAGMA optimize;")
        
        with self._stats_lock:
            self._stats["created"] += 1
        
        log.debug(f"Created new connection (total created: {self._stats['created']})")
        return conn
    
    def _should_recycle(self, created_at: float) -> bool:
        """Check if connection should be recycled based on age."""
        if self.pool_recycle < 0:
            return False
        return (time.time() - created_at) > self.pool_recycle
    
    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for getting a pooled connection.
        
        Example:
            with pool.connection() as conn:
                cur = conn.execute("SELECT * FROM artifacts")
                results = cur.fetchall()
        
        Raises:
            TimeoutError: If no connection available within pool_timeout
        """
        conn = None
        created_at = time.time()
        from_overflow = False
        
        # Track in-use count
        with self._stats_lock:
            self._in_use_count += 1
        
        try:
            # Try to get connection from pool
            try:
                conn, created_at = self._pool.get(block=True, timeout=self.pool_timeout)
                
                # Check if connection should be recycled
                if self._should_recycle(created_at):
                    log.debug("Recycling old connection")
                    conn.close()
                    conn = self._create_connection()
                    created_at = time.time()
                    with self._stats_lock:
                        self._stats["recycled"] += 1
                else:
                    with self._stats_lock:
                        self._stats["reused"] += 1
                
            except Empty:
                # Pool is empty, check if we can create overflow connection
                with self._overflow_lock:
                    if self._overflow_count < self.max_overflow:
                        self._overflow_count += 1
                        from_overflow = True
                        with self._stats_lock:
                            self._stats["overflow_used"] += 1
                        log.debug(
                            f"Creating overflow connection "
                            f"({self._overflow_count}/{self.max_overflow})"
                        )
                    else:
                        with self._stats_lock:
                            self._stats["timeouts"] += 1
                        raise TimeoutError(
                            f"Could not acquire connection within {self.pool_timeout}s. "
                            f"Pool exhausted (size={self.pool_size}, "
                            f"overflow={self._overflow_count}/{self.max_overflow})"
                        )
                
                conn = self._create_connection()
                created_at = time.time()
            
            yield conn
            
        finally:
            # Decrement in-use count
            with self._stats_lock:
                self._in_use_count -= 1
            
            if conn is not None:
                try:
                    # Rollback any uncommitted transactions
                    conn.rollback()
                except Exception as e:
                    log.warning(f"Error rolling back connection: {e}")
                
                # Return to pool or close overflow connection
                if from_overflow:
                    conn.close()
                    with self._overflow_lock:
                        self._overflow_count -= 1
                    log.debug(f"Closed overflow connection ({self._overflow_count} remaining)")
                else:
                    try:
                        self._pool.put((conn, created_at), block=False)
                    except Exception:
                        # Pool is full (shouldn't happen), close the connection
                        conn.close()
                        log.warning("Pool full when returning connection, closed it")
    
    def get_stats(self) -> dict[str, Any]:
        """Get connection pool statistics.
        
        Returns:
            Dictionary with pool statistics:
            - created: Total connections created
            - reused: Connections reused from pool
            - recycled: Connections recycled due to age
            - overflow_used: Times overflow connections were used
            - timeouts: Times connection acquisition timed out
            - pool_size: Configured pool size
            - overflow_count: Current overflow connections
            - in_use_count: Currently in-use connections
            - pool_utilization: Percentage of pool in use
        """
        with self._stats_lock:
            stats = self._stats.copy()
            stats["in_use_count"] = self._in_use_count
            # Calculate utilization based on in-use connections
            in_use_percentage = (self._in_use_count / self.pool_size * 100.0) if self.pool_size > 0 else 0.0
        
        with self._overflow_lock:
            stats["overflow_count"] = self._overflow_count
        
        stats["pool_size"] = self.pool_size
        stats["max_overflow"] = self.max_overflow
        stats["pool_utilization"] = float(in_use_percentage)
        
        return stats
    
    def close_all(self) -> None:
        """Close all connections in the pool."""
        closed_count = 0
        
        while not self._pool.empty():
            try:
                conn, _ = self._pool.get(block=False)
                conn.close()
                closed_count += 1
            except Empty:
                break
        
        log.info(f"Closed {closed_count} pooled connections")


# Global pool instance (initialized by API)
_global_pool: ConnectionPool | None = None


def init_pool(
    db_path: str,
    pool_size: int = 5,
    max_overflow: int = 10,
    pool_timeout: float = 30.0,
    pool_recycle: int = 3600,
) -> ConnectionPool:
    """Initialize global connection pool.
    
    Args:
        db_path: Path to SQLite database
        pool_size: Number of connections to keep in pool (default: 5)
        max_overflow: Additional connections allowed beyond pool_size (default: 10)
        pool_timeout: Seconds to wait for connection (default: 30)
        pool_recycle: Seconds before recycling connection (default: 3600, -1 to disable)
    
    Returns:
        Initialized ConnectionPool instance
    """
    global _global_pool
    _global_pool = ConnectionPool(
        db_path=db_path,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
    )
    return _global_pool


def get_pool() -> ConnectionPool:
    """Get global connection pool instance.
    
    Raises:
        RuntimeError: If pool not initialized
    """
    if _global_pool is None:
        raise RuntimeError(
            "Connection pool not initialized. Call init_pool() first."
        )
    return _global_pool


@contextmanager
def pooled_connection() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for getting a connection from the global pool.
    
    Example:
        from signal_harvester.db_pool import pooled_connection
        
        with pooled_connection() as conn:
            cur = conn.execute("SELECT * FROM artifacts")
            results = cur.fetchall()
    """
    pool = get_pool()
    with pool.connection() as conn:
        yield conn
