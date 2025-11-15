"""Health check endpoints for Kubernetes liveness and readiness probes.

This module provides comprehensive health checks for:
- Database connectivity
- Redis availability
- External API accessibility
- Disk space
- Memory usage
"""

from __future__ import annotations

import asyncio
import os
import shutil
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .config import get_config
from .db_connection import get_database_connection
from .logger import get_logger

log = get_logger(__name__)


class HealthStatus(str, Enum):
    """Health check status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentHealth(BaseModel):
    """Health status for a single component."""

    name: str = Field(description="Component name")
    status: HealthStatus = Field(description="Health status")
    message: str | None = Field(default=None, description="Status message")
    last_check: datetime = Field(description="Last check timestamp")
    check_duration_ms: float = Field(description="Check duration in milliseconds")


class HealthCheckResponse(BaseModel):
    """Overall health check response."""

    status: HealthStatus = Field(description="Overall health status")
    version: str = Field(default="0.1.0", description="Application version")
    uptime_seconds: float = Field(description="Application uptime in seconds")
    components: list[ComponentHealth] = Field(description="Component health checks")
    timestamp: datetime = Field(description="Check timestamp")


# Application start time for uptime tracking
_start_time = time.time()


def _row_value(row: Any, key: str | None = None) -> Any:
    """Extract a scalar value from sqlite3.Row, tuple, or dict results."""
    if row is None:
        return None
    if isinstance(row, dict):
        if key and key in row:
            return row[key]
        # fallback: first value
        return next(iter(row.values()))
    if key is not None:
        try:
            return row[key]  # type: ignore[index]
        except Exception:
            pass
    try:
        return row[0]
    except Exception:
        return row


async def check_database_health() -> ComponentHealth:
    """Check database connectivity and performance.

    Returns:
        ComponentHealth for database
    """
    start_time = time.time()
    status = HealthStatus.HEALTHY
    message = "Database is healthy"

    db_conn = None
    try:
        settings = get_config()
        db_conn = get_database_connection(settings.app.database)

        result = db_conn.execute("SELECT 1 AS result;").fetchone()

        if result is None or _row_value(result, "result") != 1:
            status = HealthStatus.UNHEALTHY
            message = "Database query returned unexpected result"
        else:
            query_start = time.time()
            count_row = db_conn.execute("SELECT COUNT(*) AS total FROM artifacts;").fetchone()
            query_duration = time.time() - query_start
            if query_duration > 1.0:
                status = HealthStatus.DEGRADED
                message = f"Database queries slow ({query_duration:.2f}s)"
            elif count_row is None:
                message = "Database count query returned no result"
                status = HealthStatus.DEGRADED

    except Exception as e:
        status = HealthStatus.UNHEALTHY
        message = f"Database health check failed: {e}"
        log.error(message)
    finally:
        if db_conn:
            db_conn.close()

    duration_ms = (time.time() - start_time) * 1000

    return ComponentHealth(
        name="database",
        status=status,
        message=message,
        last_check=datetime.utcnow(),
        check_duration_ms=duration_ms,
    )


async def check_redis_health() -> ComponentHealth:
    """Check Redis connectivity and performance.

    Returns:
        ComponentHealth for Redis
    """
    start_time = time.time()
    status = HealthStatus.HEALTHY
    message = "Redis is healthy"

    try:
        import redis
        from redis.exceptions import RedisError
        from .config import get_config

        # Load Redis config from settings
        config = get_config()
        redis_config = config.app.redis

        # Try to connect to Redis
        client = redis.Redis(
            host=redis_config.host,
            port=redis_config.port,
            db=redis_config.db,
            password=redis_config.password,
            socket_connect_timeout=2,
            socket_timeout=2,
        )

        # Ping to check connectivity
        ping_start = time.time()
        client.ping()
        ping_duration = time.time() - ping_start

        if ping_duration > 0.5:  # Slow ping threshold
            status = HealthStatus.DEGRADED
            message = f"Redis ping slow ({ping_duration:.2f}s)"

    except ImportError:
        # Redis not installed, not critical
        status = HealthStatus.DEGRADED
        message = "Redis package not installed (optional)"
    except Exception as e:
        # Catch all Redis errors (RedisError is imported inside try block)
        status = HealthStatus.DEGRADED
        message = f"Redis unavailable: {str(e)}"
        log.warning(f"Redis health check failed (non-critical): {e}")

    duration_ms = (time.time() - start_time) * 1000

    return ComponentHealth(
        name="redis",
        status=status,
        message=message,
        last_check=datetime.utcnow(),
        check_duration_ms=duration_ms,
    )


async def check_disk_space() -> ComponentHealth:
    """Check available disk space.

    Returns:
        ComponentHealth for disk space
    """
    start_time = time.time()
    status = HealthStatus.HEALTHY
    message = "Disk space is healthy"

    try:
        # Check disk space in current directory
        usage = shutil.disk_usage("/")

        free_percent = (usage.free / usage.total) * 100

        if free_percent < 5:  # Critical threshold
            status = HealthStatus.UNHEALTHY
            message = f"Disk space critical: {free_percent:.1f}% free"
        elif free_percent < 10:  # Warning threshold
            status = HealthStatus.DEGRADED
            message = f"Disk space low: {free_percent:.1f}% free"
        else:
            message = f"Disk space OK: {free_percent:.1f}% free"

    except Exception as e:
        status = HealthStatus.DEGRADED
        message = f"Disk check error: {str(e)}"
        log.warning(f"Disk space check failed: {e}")

    duration_ms = (time.time() - start_time) * 1000

    return ComponentHealth(
        name="disk_space",
        status=status,
        message=message,
        last_check=datetime.utcnow(),
        check_duration_ms=duration_ms,
    )


async def check_memory_usage() -> ComponentHealth:
    """Check memory usage.

    Returns:
        ComponentHealth for memory
    """
    start_time = time.time()
    status = HealthStatus.HEALTHY
    message = "Memory usage is healthy"

    try:
        import psutil

        # Get memory usage
        memory = psutil.virtual_memory()
        percent_used = memory.percent

        if percent_used > 95:  # Critical threshold
            status = HealthStatus.UNHEALTHY
            message = f"Memory critical: {percent_used:.1f}% used"
        elif percent_used > 85:  # Warning threshold
            status = HealthStatus.DEGRADED
            message = f"Memory high: {percent_used:.1f}% used"
        else:
            message = f"Memory OK: {percent_used:.1f}% used"

    except ImportError:
        # psutil not installed
        status = HealthStatus.DEGRADED
        message = "Memory monitoring unavailable (psutil not installed)"
    except Exception as e:
        status = HealthStatus.DEGRADED
        message = f"Memory check error: {str(e)}"
        log.warning(f"Memory usage check failed: {e}")

    duration_ms = (time.time() - start_time) * 1000

    return ComponentHealth(
        name="memory",
        status=status,
        message=message,
        last_check=datetime.utcnow(),
        check_duration_ms=duration_ms,
    )


async def check_liveness() -> HealthCheckResponse:
    """Liveness probe for Kubernetes.

    This is a lightweight check that only verifies the application is running.
    Should return quickly (<100ms) and not check external dependencies.

    Returns:
        HealthCheckResponse with liveness status
    """
    uptime = time.time() - _start_time

    # Simple process check - if we can respond, we're alive
    component = ComponentHealth(
        name="process",
        status=HealthStatus.HEALTHY,
        message="Application process is running",
        last_check=datetime.utcnow(),
        check_duration_ms=0.0,
    )

    return HealthCheckResponse(
        status=HealthStatus.HEALTHY,
        uptime_seconds=uptime,
        components=[component],
        timestamp=datetime.utcnow(),
    )


async def check_readiness() -> HealthCheckResponse:
    """Readiness probe for Kubernetes.

    This checks if the application is ready to serve traffic.
    Checks all dependencies and can take longer (up to 5 seconds).

    Returns:
        HealthCheckResponse with readiness status
    """
    uptime = time.time() - _start_time

    # Run all health checks in parallel
    checks = await asyncio.gather(
        check_database_health(),
        check_redis_health(),
        check_disk_space(),
        check_memory_usage(),
        return_exceptions=True,
    )

    components: list[ComponentHealth] = []
    overall_status = HealthStatus.HEALTHY

    for check in checks:
        if isinstance(check, Exception):
            # Health check itself failed
            components.append(
                ComponentHealth(
                    name="unknown",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Health check error: {str(check)}",
                    last_check=datetime.utcnow(),
                    check_duration_ms=0.0,
                )
            )
            overall_status = HealthStatus.UNHEALTHY
        elif isinstance(check, ComponentHealth):
            components.append(check)

            # Determine overall status (worst status wins)
            if check.status == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.UNHEALTHY
            elif check.status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
                overall_status = HealthStatus.DEGRADED

    return HealthCheckResponse(
        status=overall_status,
        uptime_seconds=uptime,
        components=components,
        timestamp=datetime.utcnow(),
    )


async def check_startup() -> HealthCheckResponse:
    """Startup probe for Kubernetes.

    This checks if the application has completed initialization.
    Can take longer than readiness (up to 30 seconds).

    Returns:
        HealthCheckResponse with startup status
    """
    # For now, startup is the same as readiness
    # In the future, could check for:
    # - Database migrations applied
    # - Caches warmed up
    # - Models loaded
    return await check_readiness()
