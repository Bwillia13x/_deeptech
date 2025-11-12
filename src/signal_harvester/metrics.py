"""Prometheus metrics exporter for application monitoring.

This module provides comprehensive metrics export for production monitoring:
- Request counts and latencies by endpoint and status code
- Cache hit/miss rates for Redis and in-memory caches
- Database query performance metrics
- Rate limiter statistics
- Error rates and types
- Background task metrics
"""

from __future__ import annotations

import time
from functools import wraps
from typing import Any, Callable

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)

from .logger import get_logger

log = get_logger(__name__)

# Application info
app_info = Info("signal_harvester", "Signal Harvester application information")
app_info.info({"version": "0.1.0", "python_version": "3.12"})

# HTTP request metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

http_requests_in_progress = Gauge(
    "http_requests_in_progress",
    "HTTP requests currently in progress",
    ["method", "endpoint"],
)

# Database metrics
db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database query latency in seconds",
    ["operation", "table"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

db_queries_total = Counter(
    "db_queries_total",
    "Total database queries",
    ["operation", "table", "status"],
)

db_connections_active = Gauge(
    "db_connections_active",
    "Number of active database connections",
)

db_connection_pool_size = Gauge(
    "db_connection_pool_size",
    "Database connection pool size",
)

# Cache metrics
cache_hits_total = Counter(
    "cache_hits_total",
    "Total cache hits",
    ["cache_type", "cache_name"],
)

cache_misses_total = Counter(
    "cache_misses_total",
    "Total cache misses",
    ["cache_type", "cache_name"],
)

cache_size_bytes = Gauge(
    "cache_size_bytes",
    "Cache size in bytes",
    ["cache_type", "cache_name"],
)

cache_items_total = Gauge(
    "cache_items_total",
    "Total items in cache",
    ["cache_type", "cache_name"],
)

# Embedding cache metrics
embedding_cache_hits = Counter(
    "embedding_cache_hits_total",
    "Embedding cache hits",
    ["cache_type"],  # redis or memory
)

embedding_cache_misses = Counter(
    "embedding_cache_misses_total",
    "Embedding cache misses",
    ["cache_type"],
)

embeddings_computed_total = Counter(
    "embeddings_computed_total",
    "Total embeddings computed",
)

embedding_computation_duration_seconds = Histogram(
    "embedding_computation_duration_seconds",
    "Embedding computation latency",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

# Rate limiter metrics
rate_limit_requests_total = Counter(
    "rate_limit_requests_total",
    "Total rate limit checks",
    ["tier", "result"],  # result: allowed or denied
)

rate_limit_denials_total = Counter(
    "rate_limit_denials_total",
    "Total rate limit denials",
    ["tier"],
)

rate_limiter_buckets_active = Gauge(
    "rate_limiter_buckets_active",
    "Active rate limiter buckets",
    ["backend"],  # redis or memory
)

# Discovery pipeline metrics
discoveries_fetched_total = Counter(
    "discoveries_fetched_total",
    "Total discoveries fetched",
    ["source"],  # arxiv, github, x, etc.
)

discoveries_scored_total = Counter(
    "discoveries_scored_total",
    "Total discoveries scored",
)

discovery_fetch_duration_seconds = Histogram(
    "discovery_fetch_duration_seconds",
    "Discovery fetch operation latency",
    ["source"],
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

discovery_score_histogram = Histogram(
    "discovery_score",
    "Distribution of discovery scores",
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

# Topic evolution metrics
topics_active_total = Gauge(
    "topics_active_total",
    "Total active topics being tracked",
)

topic_evolution_runs_total = Counter(
    "topic_evolution_runs_total",
    "Total topic evolution pipeline runs",
    ["status"],  # success or error
)

topic_merges_detected_total = Counter(
    "topic_merges_detected_total",
    "Total topic merges detected",
)

topic_splits_detected_total = Counter(
    "topic_splits_detected_total",
    "Total topic splits detected",
)

# Entity resolution metrics
entities_resolved_total = Counter(
    "entities_resolved_total",
    "Total entities resolved",
)

entity_matches_total = Counter(
    "entity_matches_total",
    "Total entity matches found",
    ["confidence_level"],  # high, medium, low
)

entity_resolution_duration_seconds = Histogram(
    "entity_resolution_duration_seconds",
    "Entity resolution operation latency",
    buckets=(0.1, 0.5, 1.0, 5.0, 10.0, 30.0),
)

# Relationship detection metrics
relationships_detected_total = Counter(
    "relationships_detected_total",
    "Total relationships detected",
    ["type"],  # cite, reference, implement, etc.
)

relationship_confidence_histogram = Histogram(
    "relationship_confidence",
    "Distribution of relationship confidence scores",
    buckets=(0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 1.0),
)

# Background task metrics
background_tasks_active = Gauge(
    "background_tasks_active",
    "Background tasks currently running",
    ["task_name"],
)

background_tasks_completed_total = Counter(
    "background_tasks_completed_total",
    "Total background tasks completed",
    ["task_name", "status"],
)

background_task_duration_seconds = Histogram(
    "background_task_duration_seconds",
    "Background task execution time",
    ["task_name"],
    buckets=(1.0, 10.0, 60.0, 300.0, 600.0, 1800.0, 3600.0),
)

# Error metrics
errors_total = Counter(
    "errors_total",
    "Total errors",
    ["error_type", "severity"],  # severity: critical, high, medium, low
)

exceptions_unhandled_total = Counter(
    "exceptions_unhandled_total",
    "Total unhandled exceptions",
    ["exception_type"],
)

# API key metrics
api_keys_active_total = Gauge(
    "api_keys_active_total",
    "Total active API keys",
)

api_key_requests_total = Counter(
    "api_key_requests_total",
    "Requests by API key",
    ["key_hash"],  # First 8 chars of SHA256 hash
)

# LLM metrics
llm_requests_total = Counter(
    "llm_requests_total",
    "Total LLM API requests",
    ["provider", "model", "status"],
)

llm_request_duration_seconds = Histogram(
    "llm_request_duration_seconds",
    "LLM API request latency",
    ["provider", "model"],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0),
)

llm_tokens_used_total = Counter(
    "llm_tokens_used_total",
    "Total LLM tokens used",
    ["provider", "model", "type"],  # type: prompt or completion
)


# Decorator for tracking HTTP requests
def track_http_request(endpoint: str | None = None):
    """Decorator to track HTTP request metrics.

    Args:
        endpoint: Optional endpoint name (defaults to function name)
    """

    def decorator(func: Callable) -> Callable:
        endpoint_name = endpoint or func.__name__

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            method = kwargs.get("request", args[0] if args else None)
            method_name = getattr(method, "method", "GET") if method else "GET"

            # Track in-progress requests
            http_requests_in_progress.labels(method=method_name, endpoint=endpoint_name).inc()

            start_time = time.time()
            status_code = 200

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status_code = getattr(e, "status_code", 500)
                raise
            finally:
                duration = time.time() - start_time

                # Record metrics
                http_requests_total.labels(method=method_name, endpoint=endpoint_name, status_code=status_code).inc()
                http_request_duration_seconds.labels(method=method_name, endpoint=endpoint_name).observe(duration)
                http_requests_in_progress.labels(method=method_name, endpoint=endpoint_name).dec()

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            method = kwargs.get("request", args[0] if args else None)
            method_name = getattr(method, "method", "GET") if method else "GET"

            http_requests_in_progress.labels(method=method_name, endpoint=endpoint_name).inc()

            start_time = time.time()
            status_code = 200

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status_code = getattr(e, "status_code", 500)
                raise
            finally:
                duration = time.time() - start_time

                http_requests_total.labels(method=method_name, endpoint=endpoint_name, status_code=status_code).inc()
                http_request_duration_seconds.labels(method=method_name, endpoint=endpoint_name).observe(duration)
                http_requests_in_progress.labels(method=method_name, endpoint=endpoint_name).dec()

        # Return appropriate wrapper based on function type
        import inspect

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# Decorator for tracking database queries
def track_db_query(operation: str, table: str):
    """Decorator to track database query metrics.

    Args:
        operation: Query operation (select, insert, update, delete)
        table: Table name
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception:
                status = "error"
                raise
            finally:
                duration = time.time() - start_time
                db_query_duration_seconds.labels(operation=operation, table=table).observe(duration)
                db_queries_total.labels(operation=operation, table=table, status=status).inc()

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"

            try:
                result = func(*args, **kwargs)
                return result
            except Exception:
                status = "error"
                raise
            finally:
                duration = time.time() - start_time
                db_query_duration_seconds.labels(operation=operation, table=table).observe(duration)
                db_queries_total.labels(operation=operation, table=table, status=status).inc()

        import inspect

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def get_metrics() -> bytes:
    """Get current metrics in Prometheus exposition format.

    Returns:
        Metrics data in Prometheus text format
    """
    return generate_latest()


def record_cache_hit(cache_type: str, cache_name: str) -> None:
    """Record a cache hit."""
    cache_hits_total.labels(cache_type=cache_type, cache_name=cache_name).inc()


def record_cache_miss(cache_type: str, cache_name: str) -> None:
    """Record a cache miss."""
    cache_misses_total.labels(cache_type=cache_type, cache_name=cache_name).inc()


def record_rate_limit_check(tier: str, allowed: bool) -> None:
    """Record a rate limit check result."""
    result = "allowed" if allowed else "denied"
    rate_limit_requests_total.labels(tier=tier, result=result).inc()
    if not allowed:
        rate_limit_denials_total.labels(tier=tier).inc()


def record_discovery_fetch(source: str, count: int, duration: float) -> None:
    """Record discovery fetch metrics."""
    discoveries_fetched_total.labels(source=source).inc(count)
    discovery_fetch_duration_seconds.labels(source=source).observe(duration)


def record_discovery_score(score: float) -> None:
    """Record a discovery score."""
    discoveries_scored_total.inc()
    discovery_score_histogram.observe(score)


def record_error(error_type: str, severity: str) -> None:
    """Record an error occurrence."""
    errors_total.labels(error_type=error_type, severity=severity).inc()


def record_llm_request(provider: str, model: str, duration: float, status: str, tokens: dict[str, int]) -> None:
    """Record LLM API request metrics."""
    llm_requests_total.labels(provider=provider, model=model, status=status).inc()
    llm_request_duration_seconds.labels(provider=provider, model=model).observe(duration)
    if tokens:
        llm_tokens_used_total.labels(provider=provider, model=model, type="prompt").inc(tokens.get("prompt", 0))
        llm_tokens_used_total.labels(provider=provider, model=model, type="completion").inc(
            tokens.get("completion", 0)
        )
