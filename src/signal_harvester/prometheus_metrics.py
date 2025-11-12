"""Prometheus metrics instrumentation for Signal Harvester.

This module provides Prometheus metrics collection for monitoring application
performance, resource usage, and business metrics.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Callable

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

if TYPE_CHECKING:
    from collections.abc import Awaitable


# ============================================================================
# HTTP Metrics
# ============================================================================

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint", "status"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0),
)

http_requests_in_progress = Gauge(
    "http_requests_in_progress",
    "Number of HTTP requests currently being processed",
    ["method", "endpoint"],
)


# ============================================================================
# Application Metrics
# ============================================================================

# Database metrics
db_connections_active = Gauge(
    "db_connections_active",
    "Number of active database connections",
)

db_size_bytes = Gauge(
    "db_size_bytes",
    "Database size in bytes",
)

db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database query duration in seconds",
    ["query_type"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

# Signal/Tweet metrics
signals_total = Gauge(
    "signals_total",
    "Total number of signals in database",
)

signals_scored = Gauge(
    "signals_scored",
    "Number of scored signals",
)

signals_analyzed = Gauge(
    "signals_analyzed",
    "Number of analyzed signals",
)

signals_notified = Gauge(
    "signals_notified",
    "Number of notified signals",
)

signals_fetched_total = Counter(
    "signals_fetched_total",
    "Total number of signals fetched",
    ["source"],
)

signals_fetch_errors_total = Counter(
    "signals_fetch_errors_total",
    "Total number of signal fetch errors",
    ["source", "error_type"],
)

# Discovery metrics
discoveries_total = Gauge(
    "discoveries_total",
    "Total number of discoveries in database",
)

discoveries_by_source = Gauge(
    "discoveries_by_source",
    "Number of discoveries by source",
    ["source"],
)

discoveries_fetched_total = Counter(
    "discoveries_fetched_total",
    "Total number of discoveries fetched",
    ["source"],
)

discoveries_fetch_duration_seconds = Histogram(
    "discoveries_fetch_duration_seconds",
    "Discovery fetch duration in seconds",
    ["source"],
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
)

# Topic metrics
topics_total = Gauge(
    "topics_total",
    "Total number of topics tracked",
)

topics_active = Gauge(
    "topics_active",
    "Number of active topics (with recent activity)",
)

topic_artifacts_total = Gauge(
    "topic_artifacts_total",
    "Total number of artifacts assigned to topics",
)

# Entity metrics
entities_total = Gauge(
    "entities_total",
    "Total number of unique entities",
)

entity_resolutions_total = Counter(
    "entity_resolutions_total",
    "Total number of entity resolutions performed",
)

entity_merges_total = Counter(
    "entity_merges_total",
    "Total number of entity merges",
)

# Relationship metrics
relationships_total = Gauge(
    "relationships_total",
    "Total number of artifact relationships",
)

relationships_by_type = Gauge(
    "relationships_by_type",
    "Number of relationships by type",
    ["relationship_type"],
)

relationship_detections_total = Counter(
    "relationship_detections_total",
    "Total number of relationship detections",
    ["detection_type"],  # pattern, semantic
)

# Cache metrics
cache_hits_total = Counter(
    "cache_hits_total",
    "Total number of cache hits",
    ["cache_type"],
)

cache_misses_total = Counter(
    "cache_misses_total",
    "Total number of cache misses",
    ["cache_type"],
)

cache_size = Gauge(
    "cache_size",
    "Current cache size (number of items)",
    ["cache_type"],
)

# Embedding metrics
embeddings_generated_total = Counter(
    "embeddings_generated_total",
    "Total number of embeddings generated",
)

embedding_generation_duration_seconds = Histogram(
    "embedding_generation_duration_seconds",
    "Embedding generation duration in seconds",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

# Pipeline metrics
pipeline_runs_total = Counter(
    "pipeline_runs_total",
    "Total number of pipeline runs",
    ["pipeline_type"],  # discovery, legacy, topic_evolution, etc.
)

pipeline_run_duration_seconds = Histogram(
    "pipeline_run_duration_seconds",
    "Pipeline run duration in seconds",
    ["pipeline_type"],
    buckets=(10.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1800.0, 3600.0),
)

pipeline_errors_total = Counter(
    "pipeline_errors_total",
    "Total number of pipeline errors",
    ["pipeline_type", "error_type"],
)

# LLM metrics
llm_requests_total = Counter(
    "llm_requests_total",
    "Total number of LLM requests",
    ["provider", "model"],
)

llm_request_duration_seconds = Histogram(
    "llm_request_duration_seconds",
    "LLM request duration in seconds",
    ["provider", "model"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total number of LLM tokens used",
    ["provider", "model", "token_type"],  # prompt, completion
)

llm_errors_total = Counter(
    "llm_errors_total",
    "Total number of LLM request errors",
    ["provider", "model", "error_type"],
)


# ============================================================================
# Backup Metrics
# ============================================================================

backup_runs_total = Counter(
    "backup_runs_total",
    "Total number of backup operations",
    ["backup_type", "status"],  # status: success, failed
)

backup_duration_seconds = Histogram(
    "backup_duration_seconds",
    "Backup operation duration in seconds",
    ["backup_type"],  # full, incremental, wal
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1800.0),
)

backup_size_bytes = Histogram(
    "backup_size_bytes",
    "Backup file size in bytes",
    ["backup_type", "compression"],  # compression: none, gzip, zstd
    buckets=(
        1024 * 1024,  # 1 MB
        10 * 1024 * 1024,  # 10 MB
        100 * 1024 * 1024,  # 100 MB
        500 * 1024 * 1024,  # 500 MB
        1024 * 1024 * 1024,  # 1 GB
        5 * 1024 * 1024 * 1024,  # 5 GB
        10 * 1024 * 1024 * 1024,  # 10 GB
    ),
)

backup_errors_total = Counter(
    "backup_errors_total",
    "Total number of backup errors",
    ["backup_type", "error_type"],  # error_type: creation, verification, upload, restore
)

backup_uploads_total = Counter(
    "backup_uploads_total",
    "Total number of cloud storage uploads",
    ["provider", "status"],  # provider: s3, gcs, azure; status: success, failed
)

backup_upload_duration_seconds = Histogram(
    "backup_upload_duration_seconds",
    "Cloud upload duration in seconds",
    ["provider"],
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1800.0),
)

backup_verifications_total = Counter(
    "backup_verifications_total",
    "Total number of backup verifications",
    ["status"],  # success, failed
)

backup_restores_total = Counter(
    "backup_restores_total",
    "Total number of restore operations",
    ["status"],  # success, failed
)

backup_retention_pruned_total = Counter(
    "backup_retention_pruned_total",
    "Total number of backups pruned by retention policy",
    ["retention_policy"],  # daily, weekly, monthly
)

backup_oldest_age_seconds = Gauge(
    "backup_oldest_age_seconds",
    "Age of the oldest backup in seconds",
)

backup_newest_age_seconds = Gauge(
    "backup_newest_age_seconds",
    "Age of the newest backup in seconds",
)

backup_total_count = Gauge(
    "backup_total_count",
    "Total number of backups available",
    ["backup_type"],
)

backup_total_size_bytes = Gauge(
    "backup_total_size_bytes",
    "Total size of all backups in bytes",
)


# ============================================================================
# Middleware
# ============================================================================

class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware to collect HTTP request metrics for Prometheus."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Process request and collect metrics."""
        # Skip metrics endpoint to avoid recursion
        if request.url.path == "/prometheus":
            return await call_next(request)

        method = request.method
        endpoint = request.url.path

        # Normalize endpoint for metrics (remove IDs)
        endpoint_normalized = self._normalize_endpoint(endpoint)

        # Track in-progress requests
        http_requests_in_progress.labels(method=method, endpoint=endpoint_normalized).inc()

        start_time = time.time()
        status = 500  # Default to error if exception occurs

        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            # Record metrics
            duration = time.time() - start_time
            http_requests_in_progress.labels(method=method, endpoint=endpoint_normalized).dec()
            http_requests_total.labels(method=method, endpoint=endpoint_normalized, status=status).inc()
            http_request_duration_seconds.labels(
                method=method, endpoint=endpoint_normalized, status=status
            ).observe(duration)

    @staticmethod
    def _normalize_endpoint(endpoint: str) -> str:
        """Normalize endpoint by removing IDs and query parameters."""
        # Remove query parameters
        endpoint = endpoint.split("?")[0]

        # Replace numeric IDs with placeholder
        parts = endpoint.split("/")
        normalized_parts = []
        for part in parts:
            if part.isdigit():
                normalized_parts.append("{id}")
            elif len(part) == 36 and part.count("-") == 4:  # UUID
                normalized_parts.append("{uuid}")
            else:
                normalized_parts.append(part)

        return "/".join(normalized_parts)


# ============================================================================
# Metrics Endpoint
# ============================================================================

def get_prometheus_metrics() -> Response:
    """Generate Prometheus metrics in text format."""
    metrics_output = generate_latest(REGISTRY)
    return Response(content=metrics_output, media_type=CONTENT_TYPE_LATEST)


# ============================================================================
# Helper Functions
# ============================================================================

def track_db_query(query_type: str, duration: float) -> None:
    """Track database query metrics.
    
    Args:
        query_type: Type of query (select, insert, update, delete)
        duration: Query duration in seconds
    """
    db_query_duration_seconds.labels(query_type=query_type).observe(duration)


def track_discovery_fetch(source: str, count: int, duration: float, error: bool = False) -> None:
    """Track discovery fetch metrics.
    
    Args:
        source: Discovery source (arxiv, github, x, etc.)
        count: Number of discoveries fetched
        duration: Fetch duration in seconds
        error: Whether an error occurred
    """
    if not error:
        discoveries_fetched_total.labels(source=source).inc(count)
        discoveries_fetch_duration_seconds.labels(source=source).observe(duration)


def track_llm_request(
    provider: str,
    model: str,
    duration: float,
    prompt_tokens: int,
    completion_tokens: int,
    error: bool = False,
    error_type: str | None = None,
) -> None:
    """Track LLM request metrics.
    
    Args:
        provider: LLM provider (openai, anthropic, xai)
        model: Model name
        duration: Request duration in seconds
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens
        error: Whether an error occurred
        error_type: Type of error if error=True
    """
    if error and error_type:
        llm_errors_total.labels(provider=provider, error_type=error_type).inc()
    else:
        llm_requests_total.labels(provider=provider, model=model).inc()
        llm_request_duration_seconds.labels(provider=provider, model=model).observe(duration)
        llm_tokens_total.labels(provider=provider, model=model, token_type="prompt").inc(prompt_tokens)
        llm_tokens_total.labels(provider=provider, model=model, token_type="completion").inc(completion_tokens)


def track_pipeline_run(pipeline_type: str, duration: float, error: bool = False, error_type: str | None = None) -> None:
    """Track pipeline execution metrics.
    
    Args:
        pipeline_type: Type of pipeline (discovery, legacy, topic_evolution, etc.)
        duration: Pipeline duration in seconds
        error: Whether an error occurred
        error_type: Type of error if error=True
    """
    pipeline_runs_total.labels(pipeline_type=pipeline_type).inc()
    if error and error_type:
        pipeline_errors_total.labels(pipeline_type=pipeline_type, error_type=error_type).inc()
    else:
        pipeline_run_duration_seconds.labels(pipeline_type=pipeline_type).observe(duration)


def track_embedding_generation(count: int, duration: float) -> None:
    """Track embedding generation metrics.
    
    Args:
        count: Number of embeddings generated
        duration: Total generation duration in seconds
    """
    embeddings_generated_total.inc(count)
    if count > 0:
        embedding_generation_duration_seconds.observe(duration / count)


def update_cache_stats(cache_type: str, hits: int, misses: int, size: int) -> None:
    """Update cache statistics.
    
    Args:
        cache_type: Type of cache (embedding, discovery, etc.)
        hits: Number of cache hits
        misses: Number of cache misses
        size: Current cache size
    """
    cache_hits_total.labels(cache_type=cache_type).inc(hits)
    cache_misses_total.labels(cache_type=cache_type).inc(misses)
    cache_size.labels(cache_type=cache_type).set(size)
