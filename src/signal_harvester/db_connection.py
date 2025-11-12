"""
Database connection utilities supporting both SQLite and PostgreSQL.

This module provides a unified interface for database connections, allowing
the application to work with both SQLite (development) and PostgreSQL (production)
without code changes.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict, Optional, Union
from urllib.parse import urlparse

from .config import DatabaseConfig
from .logger import get_logger

log = get_logger(__name__)

# Optional PostgreSQL support
try:
    import psycopg2
    import psycopg2.extensions
    import psycopg2.extras
    from psycopg2.pool import SimpleConnectionPool
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    log.debug("PostgreSQL support not available (psycopg2 not installed)")


class DatabaseConnection:
    """
    Unified database connection that works with both SQLite and PostgreSQL.
    
    Provides a consistent interface regardless of the underlying database,
    handling connection management, cursor creation, and query execution.
    """
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._sqlite_conn: Optional[sqlite3.Connection] = None
        self._pg_conn: Optional[Any] = None  # psycopg2.extensions.connection
        self._pool: Optional[Any] = None  # SimpleConnectionPool
    
    @property
    def is_postgres(self) -> bool:
        return self.config.is_postgres
    
    @property
    def is_sqlite(self) -> bool:
        return self.config.is_sqlite
    
    def connect(self) -> DatabaseConnection:
        """Establish database connection."""
        if self.is_postgres:
            return self._connect_postgres()
        else:
            return self._connect_sqlite()
    
    def _connect_sqlite(self) -> DatabaseConnection:
        """Connect to SQLite database."""
        # Extract path from sqlite:/// URL
        url_path = self.config.url.replace("sqlite:///", "")
        
        # Ensure directory exists
        db_dir = os.path.dirname(os.path.abspath(url_path))
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        self._sqlite_conn = sqlite3.connect(
            url_path,
            timeout=self.config.query_timeout,
            isolation_level=None
        )
        self._sqlite_conn.row_factory = sqlite3.Row
        
        # SQLite optimizations
        with self._sqlite_conn:
            self._sqlite_conn.execute("PRAGMA journal_mode=WAL;")
            self._sqlite_conn.execute("PRAGMA synchronous=NORMAL;")
            self._sqlite_conn.execute("PRAGMA foreign_keys=ON;")
            self._sqlite_conn.execute("PRAGMA busy_timeout=5000;")
        
        log.info(f"Connected to SQLite: {url_path}")
        return self
    
    def _connect_postgres(self) -> DatabaseConnection:
        """Connect to PostgreSQL database with connection pooling."""
        if not POSTGRES_AVAILABLE:
            raise RuntimeError(
                "PostgreSQL support not available. "
                "Install with: pip install psycopg2-binary"
            )
        
        # Parse connection URL
        parsed = urlparse(self.config.url)
        host_info = f"{parsed.hostname}:{parsed.port or 5432}"
        
        if self.config.pool.enabled:
            # Use connection pool
            self._pool = SimpleConnectionPool(
                minconn=1,
                maxconn=self.config.pool.pool_size + self.config.pool.max_overflow,
                dsn=self.config.url,
                connect_timeout=int(self.config.query_timeout)
            )
            self._pg_conn = self._pool.getconn()
            log.info(f"Connected to PostgreSQL with pooling: {host_info}")
        else:
            # Direct connection
            self._pg_conn = psycopg2.connect(
                self.config.url,
                connect_timeout=int(self.config.query_timeout)
            )
            log.info(f"Connected to PostgreSQL: {host_info}")
        
        # Use RealDictCursor for row factory-like behavior
        self._pg_conn.set_session(autocommit=False)
        
        return self
    
    def close(self):
        """Close database connection."""
        if self._sqlite_conn:
            self._sqlite_conn.close()
            self._sqlite_conn = None
        
        if self._pg_conn:
            if self._pool:
                self._pool.putconn(self._pg_conn)
            else:
                self._pg_conn.close()
            self._pg_conn = None
        
        if self._pool:
            self._pool.closeall()
            self._pool = None
    
    def cursor(self):
        """Get a cursor for executing queries."""
        if self.is_sqlite:
            if not self._sqlite_conn:
                raise RuntimeError("SQLite connection not established")
            return self._sqlite_conn.cursor()
        else:
            if not self._pg_conn:
                raise RuntimeError("PostgreSQL connection not established")
            # Use RealDictCursor for dict-like row access
            return self._pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    def execute(self, query: str, params: Optional[tuple] = None):
        """Execute a query and return cursor."""
        cursor = self.cursor()
        
        if self.is_postgres:
            # Convert SQLite ? placeholders to PostgreSQL %s
            query = query.replace("?", "%s")
        
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        return cursor
    
    def commit(self):
        """Commit current transaction."""
        if self._sqlite_conn:
            self._sqlite_conn.commit()
        elif self._pg_conn:
            self._pg_conn.commit()
    
    def rollback(self):
        """Rollback current transaction."""
        if self._sqlite_conn:
            self._sqlite_conn.rollback()
        elif self._pg_conn:
            self._pg_conn.rollback()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if exc_type:
            self.rollback()
        else:
            self.commit()
        return False


def get_database_connection(config: DatabaseConfig) -> DatabaseConnection:
    """
    Factory function to create database connection from config.
    
    Args:
        config: Database configuration
    
    Returns:
        DatabaseConnection instance
    
    Example:
        >>> from signal_harvester.config import load_settings
        >>> settings = load_settings()
        >>> conn = get_database_connection(settings.app.database)
        >>> conn.connect()
        >>> with conn:
        >>>     cursor = conn.execute("SELECT * FROM artifacts LIMIT 10")
        >>>     rows = cursor.fetchall()
    """
    return DatabaseConnection(config).connect()


def ensure_postgres_dependencies():
    """
    Check if PostgreSQL dependencies are available.
    
    Raises:
        RuntimeError: If psycopg2 is not installed
    """
    if not POSTGRES_AVAILABLE:
        raise RuntimeError(
            "PostgreSQL support requires psycopg2. "
            "Install with: pip install psycopg2-binary"
        )


def convert_query_placeholders(query: str, from_db: str, to_db: str) -> str:
    """
    Convert query placeholders between database types.
    
    Args:
        query: SQL query string
        from_db: Source database type ('sqlite' or 'postgresql')
        to_db: Target database type ('sqlite' or 'postgresql')
    
    Returns:
        Converted query string
    
    Example:
        >>> query = "SELECT * FROM artifacts WHERE id = ?"
        >>> convert_query_placeholders(query, 'sqlite', 'postgresql')
        'SELECT * FROM artifacts WHERE id = %s'
    """
    if from_db == 'sqlite' and to_db == 'postgresql':
        # SQLite uses ?, PostgreSQL uses %s
        return query.replace("?", "%s")
    elif from_db == 'postgresql' and to_db == 'sqlite':
        # PostgreSQL uses %s, SQLite uses ?
        return query.replace("%s", "?")
    return query


def get_database_type_from_url(url: str) -> str:
    """
    Detect database type from connection URL.
    
    Args:
        url: Database connection URL
    
    Returns:
        Database type: 'sqlite' or 'postgresql'
    
    Example:
        >>> get_database_type_from_url("postgresql://user:pass@localhost/db")
        'postgresql'
        >>> get_database_type_from_url("sqlite:///var/app.db")
        'sqlite'
    """
    if url.startswith("postgresql://"):
        return "postgresql"
    elif url.startswith("sqlite://"):
        return "sqlite"
    else:
        # Assume SQLite for bare paths
        return "sqlite"
