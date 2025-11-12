from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, cast

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from . import __version__
from .cache import cached, get_cache_stats, invalidate_cache
from .config import Settings, load_settings
from .db import get_tweet, init_db, list_top, run_migrations
from .logger import get_logger
from .pipeline import run_pipeline
from .prometheus_metrics import PrometheusMiddleware, get_prometheus_metrics
from .validation import (
    validate_api_key,
    validate_hours,
    validate_limit,
    validate_salience,
    validate_tweet_id,
)

log = get_logger(__name__)


# ============================================================================
# Pydantic Models
# ============================================================================

class SignalStatus(str, Enum):
    """Signal status enum matching frontend types."""
    active = "active"
    inactive = "inactive"
    paused = "paused"
    error = "error"


class Signal(BaseModel):
    """Signal response model matching frontend types."""
    id: str
    name: str
    source: str
    status: SignalStatus
    tags: Optional[List[str]] = None
    lastSeenAt: Optional[str] = None  # ISO string
    createdAt: str  # ISO string
    updatedAt: str  # ISO string


class CreateSignalInput(BaseModel):
    """Create signal input model."""
    name: str
    source: str
    status: SignalStatus
    tags: Optional[List[str]] = None


class UpdateSignalInput(BaseModel):
    """Update signal input model."""
    name: Optional[str] = None
    source: Optional[str] = None
    status: Optional[SignalStatus] = None
    tags: Optional[List[str]] = None


class PaginatedSignals(BaseModel):
    """Paginated signals response."""
    items: List[Signal]
    total: int
    page: int
    pageSize: int


class SignalsStats(BaseModel):
    """Signal statistics response."""
    total: int
    active: int
    paused: int
    error: int
    inactive: int


class SnapshotStatus(str, Enum):
    """Snapshot status enum."""
    ready = "ready"
    processing = "processing"
    failed = "failed"


class Snapshot(BaseModel):
    """Snapshot response model."""
    id: str
    signalId: str
    signalName: Optional[str] = None
    status: SnapshotStatus
    sizeKb: Optional[int] = None
    createdAt: str  # ISO string


class PaginatedSnapshots(BaseModel):
    """Paginated snapshots response."""
    items: List[Snapshot]
    total: int
    page: int
    pageSize: int


class BulkScope(BaseModel):
    """Bulk operation scope."""
    ids: Optional[List[str]] = None
    filters: Optional[Dict[str, Any]] = None


class BulkJobResponse(BaseModel):
    """Bulk job creation response."""
    jobId: str
    total: int


class BulkJobStatusEnum(str, Enum):
    """Bulk job status enum."""
    running = "running"
    completed = "completed"
    cancelled = "cancelled"
    failed = "failed"


class BulkJobStatus(BaseModel):
    """Bulk job status response."""
    jobId: str
    status: BulkJobStatusEnum
    total: int
    done: int
    fail: int


class BulkSetStatusInput(BaseModel):
    """Bulk set status input."""
    ids: Optional[List[str]] = None
    filters: Optional[Dict[str, Any]] = None
    status: SignalStatus


# ============================================================================
# Discovery Pydantic Models (Phase One)
# ============================================================================

class Discovery(BaseModel):
    """Discovery response model matching frontend types."""
    id: int
    artifactId: int
    artifactType: str
    source: str
    sourceId: str
    title: str
    text: Optional[str] = None
    url: Optional[str] = None
    publishedAt: str  # ISO string
    novelty: Optional[float] = None
    emergence: Optional[float] = None
    obscurity: Optional[float] = None
    discoveryScore: Optional[float] = None
    computedAt: Optional[str] = None  # ISO string
    category: Optional[str] = None
    sentiment: Optional[str] = None
    urgency: Optional[int] = None
    tags: Optional[List[str]] = None
    topics: Optional[List[str]] = None
    reasoning: Optional[str] = None
    createdAt: str  # ISO string
    updatedAt: str  # ISO string


class Topic(BaseModel):
    """Topic response model matching frontend types."""
    id: int
    name: str
    taxonomyPath: Optional[str] = None
    description: Optional[str] = None
    artifactCount: Optional[int] = None
    avgDiscoveryScore: Optional[float] = None
    createdAt: Optional[str] = None  # ISO string
    updatedAt: Optional[str] = None  # ISO string


class Entity(BaseModel):
    """Entity response model matching frontend types."""
    id: int
    entityType: str  # person, lab, organization
    name: str
    description: Optional[str] = None
    accounts: Optional[List[Dict[str, Any]]] = None
    createdAt: Optional[str] = None  # ISO string
    updatedAt: Optional[str] = None  # ISO string


class TopicTimeline(BaseModel):
    """Topic timeline data point."""
    date: str  # ISO date string
    artifactCount: int
    avgDiscoveryScore: Optional[float] = None


class PaginatedDiscoveries(BaseModel):
    """Paginated discoveries response with cursor-based pagination."""
    items: List[Discovery]
    nextCursor: Optional[str] = None
    hasMore: bool
    total: Optional[int] = None  # Optional total count


class PaginatedTopics(BaseModel):
    """Paginated topics response with cursor-based pagination."""
    items: List[Topic]
    nextCursor: Optional[str] = None
    hasMore: bool
    total: Optional[int] = None


class PaginatedArtifacts(BaseModel):
    """Paginated artifacts response with cursor-based pagination."""
    items: List[Discovery]  # Reuse Discovery model for artifacts
    nextCursor: Optional[str] = None
    hasMore: bool
    total: Optional[int] = None


# In-memory bulk jobs storage (for MVP)
bulk_jobs: Dict[str, Dict[str, Any]] = {}


def init_sentry() -> None:
    """Initialize Sentry error tracking if DSN is configured."""
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        log.info("Sentry DSN not configured, skipping error tracking")
        return
    
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        
        sentry_sdk.init(
            dsn=dsn,
            integrations=[
                FastApiIntegration(),
                LoggingIntegration(
                    level=logging.INFO,
                    event_level=logging.ERROR
                )
            ],
            traces_sample_rate=1.0,  # Capture 100% for beta
            profiles_sample_rate=1.0,
            environment=os.getenv("ENVIRONMENT", "beta"),
            release=f"signal-harvester@{__version__}",
        )
        # Set custom tags after initialization
        with sentry_sdk.configure_scope() as scope:
            scope.set_tag("component", "api")
        log.info("Sentry error tracking initialized")
    except Exception as e:
        log.warning("Failed to initialize Sentry: %s", e)
        log.info("Continuing without error tracking")


class SimpleRateLimiter:
    """Simple in-memory rate limiter for API endpoints."""
    
    def __init__(self, times: int = 10, seconds: int = 60):
        self.times = times
        self.seconds = seconds
        # key: (client_id, path) -> list of timestamps
        self.requests: defaultdict[tuple[str, str], list[float]] = defaultdict(list)
    
    def is_allowed(self, client_id: str, path: str) -> bool:
        """Check if request is allowed under rate limit."""
        key = (client_id, path)
        now = time.time()
        
        # Clean old requests
        cutoff = now - self.seconds
        self.requests[key] = [req_time for req_time in self.requests[key] if req_time > cutoff]
        
        # Check limit
        if len(self.requests[key]) >= self.times:
            return False
        
        # Record this request
        self.requests[key].append(now)
        return True
    
    def get_retry_after(self, client_id: str, path: str) -> int:
        """Get seconds until retry is allowed."""
        key = (client_id, path)
        if not self.requests[key]:
            return 0
        
        oldest_request = min(self.requests[key])
        retry_after = int(self.seconds - (time.time() - oldest_request) + 1)
        return max(0, retry_after)


async def _process_bulk_job(job_id: str) -> None:
    """Process a bulk job in the background."""
    from . import db as db_module
    
    job = bulk_jobs.get(job_id)
    if not job:
        return
    
    try:
        operation = job["operation"]
        target_ids = job["target_ids"]
        db_path = job["db_path"]
        
        for signal_id in target_ids:
            # Check if cancelled
            if job["status"] == "cancelled":
                break
            
            try:
                if operation == "set_status":
                    target_status = job["target_status"]
                    db_module.update_signal(db_path, signal_id, {"status": target_status})
                elif operation == "delete":
                    db_module.delete_signal(db_path, signal_id)
                
                job["done"] += 1
            except Exception as e:
                log.error(f"Error processing signal {signal_id}: {e}")
                job["fail"] += 1
            
            # Small delay to avoid blocking
            await asyncio.sleep(0.01)
        
        # Mark as completed if not cancelled
        if job["status"] == "running":
            job["status"] = "completed"
    except Exception as e:
        log.error(f"Bulk job {job_id} failed: {e}")
        job["status"] = "failed"


# Pydantic models for request bodies
class ExperimentRequest(BaseModel):
    """Request model for creating experiments."""
    name: str
    description: Optional[str] = None
    scoring_weights: Dict[str, float]
    min_score_threshold: float = 70.0
    lookback_days: int = 7
    baseline_id: Optional[int] = None


def create_app(settings_path: Optional[str] = None) -> FastAPI:
    # Initialize Sentry first to catch any errors during setup
    init_sentry()
    app = FastAPI(
        title="Signal Harvester API",
        version="0.1.0",
        description="""
        Harvest, triage, and score social signals from X (Twitter) with LLM-assisted classification.
        
        ## Features
        
        - **Fetch**: Collect tweets from X/Twitter API
        - **Analyze**: LLM-powered content analysis (OpenAI, Anthropic, or heuristic fallback)
        - **Score**: Advanced salience scoring algorithm
        - **Notify**: Slack notifications for high-priority items
        
        ## Authentication
        
        Most endpoints require an API key passed in the `X-API-Key` header.
        Set `HARVEST_API_KEY` environment variable to enable API key authentication.
        
        ## Rate Limiting
        
        API endpoints are rate-limited to 10 requests per minute per client.
        Rate limiting can be disabled by setting `RATE_LIMITING_ENABLED=false`.
        
        ## Quick Start
        
        1. Configure your API keys in `.env`
        2. Set up queries in `config/settings.yaml`
        3. Run the pipeline: `POST /refresh`
        4. View results: `GET /top`
        """,
        openapi_tags=[
            {
                "name": "tweets",
                "description": "Operations with harvested tweets and signals",
            },
            {
                "name": "pipeline",
                "description": "Pipeline control and operations",
            },
            {
                "name": "monitoring",
                "description": "Health checks and monitoring",
            },
        ],
    )

    class SecurityHeadersMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
            response = await call_next(request)
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("Referrer-Policy", "no-referrer")
            # HSTS is meaningful over HTTPS; harmless if not
            response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload")
            return response

    state: Dict[str, Any] = {}
    state["settings_path"] = settings_path
    state["api_key"] = os.getenv("HARVEST_API_KEY")
    state["rate_limiter_enabled"] = os.getenv("RATE_LIMITING_ENABLED", "true").lower() == "true"
    state["rate_limiter"] = SimpleRateLimiter(times=10, seconds=60) if state["rate_limiter_enabled"] else None

    # Load settings and ensure DB
    settings = load_settings(settings_path)
    init_db(settings.app.database_path)
    run_migrations(settings.app.database_path)
    state["settings"] = settings
    
    # Initialize connection pool if enabled
    if settings.app.connection_pool.enabled:
        from .db_pool import init_pool
        pool = init_pool(
            db_path=settings.app.database_path,
            pool_size=settings.app.connection_pool.pool_size,
            max_overflow=settings.app.connection_pool.max_overflow,
            pool_timeout=settings.app.connection_pool.pool_timeout,
            pool_recycle=settings.app.connection_pool.pool_recycle,
        )
        state["connection_pool"] = pool
        log.info(
            f"Connection pool initialized: size={settings.app.connection_pool.pool_size}, "
            f"max_overflow={settings.app.connection_pool.max_overflow}"
        )
    else:
        state["connection_pool"] = None
        log.info("Connection pool disabled, using direct connections")

    cors_origins = [o.strip() for o in (os.getenv("CORS_ORIGINS") or "*").split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    
    # Add Prometheus metrics middleware
    app.add_middleware(PrometheusMiddleware)
    
    # Add GZip compression for responses > 1KB
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    def get_settings_dep() -> Settings:
        return cast(Settings, state["settings"])

    def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
        expected = state["api_key"]
        if expected:
            # Validate API key format
            validated_key = validate_api_key(x_api_key)
            if (validated_key or "") != expected:
                raise HTTPException(status_code=401, detail="Invalid API key")
    
    def check_rate_limit(request: Request) -> None:
        """Check rate limit for the request."""
        if not state["rate_limiter"]:
            return
        
        # Get client identifier (IP + user agent)
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        client_id = f"{client_ip}:{user_agent[:20]}"  # Truncate for safety
        path = request.url.path
        
        if not state["rate_limiter"].is_allowed(client_id, path):
            retry_after = state["rate_limiter"].get_retry_after(client_id, path)
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Retry after {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)}
            )

    @app.get(
        "/top",
        tags=["tweets"],
        summary="Get top-scored tweets",
        description="Retrieve the highest-scoring tweets based on salience score.",
        response_model=List[Dict[str, Any]],
    )
    def top(
        limit: int = Query(50, ge=1, le=200, description="Maximum number of tweets to return"),
        min_salience: float = Query(0.0, ge=0.0, le=100.0, description="Minimum salience score filter"),
        hours: Optional[int] = Query(None, ge=1, le=168, description="Filter to tweets from last N hours"),
        settings: Settings = Depends(get_settings_dep),
    ) -> List[Dict[str, Any]]:
        # Validate and sanitize inputs
        validated_limit = validate_limit(limit, min_val=1, max_val=200)
        validated_min_salience = validate_salience(min_salience, min_val=0.0, max_val=100.0)
        validated_hours = validate_hours(hours, min_val=1, max_val=168) if hours is not None else None
        
        rows = list_top(
            settings.app.database_path,
            limit=validated_limit,
            min_salience=validated_min_salience,
            hours=validated_hours
        )
        for r in rows:
            tid = r.get("tweet_id")
            user = r.get("author_username")
            r["url"] = f"https://x.com/{user}/status/{tid}" if user else f"https://x.com/i/web/status/{tid}"
        return rows

    @app.get(
        "/tweet/{tweet_id}",
        tags=["tweets"],
        summary="Get a specific tweet",
        description="Retrieve detailed information about a single tweet by ID.",
        response_model=Dict[str, Any],
    )
    def get(
        tweet_id: str,
        settings: Settings = Depends(get_settings_dep),
    ) -> Dict[str, Any]:
        # Validate tweet ID
        validated_tweet_id = validate_tweet_id(tweet_id)
        
        row = get_tweet(settings.app.database_path, validated_tweet_id)
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        tid = row.get("tweet_id")
        user = row.get("author_username")
        row["url"] = f"https://x.com/{user}/status/{tid}" if user else f"https://x.com/i/web/status/{tid}"
        return row

    @app.post(
        "/refresh",
        tags=["pipeline"],
        summary="Run the harvest pipeline",
        description="""
        Execute the complete pipeline: fetch tweets, analyze content, compute salience scores,
        and send notifications for high-priority items.
        
        Requires API key authentication.
        """,
        response_model=Dict[str, int],
        dependencies=[Depends(require_api_key), Depends(check_rate_limit)],
    )
    def refresh(
        notify_threshold: Optional[float] = Query(
            None, ge=0.0, le=100.0, description="Minimum salience score for notifications"
        ),
        notify_limit: int = Query(10, ge=0, le=50, description="Maximum number of notifications to send"),
        notify_hours: Optional[int] = Query(
            None, ge=1, le=168, description="Only consider tweets from last N hours"
        ),
        settings: Settings = Depends(get_settings_dep),
    ) -> Dict[str, int]:
        # Validate parameters
        validated_threshold = (
            validate_salience(notify_threshold, min_val=0.0, max_val=100.0)
            if notify_threshold is not None
            else None
        )
        validated_limit = validate_limit(notify_limit, min_val=0, max_val=50)
        validated_hours = (
            validate_hours(notify_hours, min_val=1, max_val=168)
            if notify_hours is not None
            else None
        )
        
        stats = run_pipeline(
            settings,
            notify_threshold=validated_threshold,
            notify_limit=validated_limit,
            notify_hours=validated_hours
        )
        return stats

    @app.get(
        "/health",
        tags=["monitoring"],
        summary="Health check",
        description="Check the health status of the API and its dependencies.",
        response_model=Dict[str, Any],
    )
    def health_check() -> Dict[str, Any]:
        """Health check endpoint for monitoring and readiness probes."""
        health_status: Dict[str, Any] = {
            "status": "healthy",
            "version": __version__,
            "timestamp": "",
            "checks": {
                "database": "unknown",
                "settings": "unknown"
            }
        }
        
        # Check settings
        db_path = "var/app.db"  # Default
        try:
            settings = load_settings()
            db_path = settings.app.database_path
            health_status["checks"]["settings"] = "ok"
        except Exception as e:
            health_status["checks"]["settings"] = f"error: {str(e)}"
            health_status["status"] = "unhealthy"
        
        # Check database connectivity
        try:
            conn = sqlite3.connect(db_path, timeout=1.0)
            conn.execute("SELECT 1")
            conn.close()
            health_status["checks"]["database"] = "ok"
        except Exception as e:
            health_status["checks"]["database"] = f"error: {str(e)}"
            health_status["status"] = "unhealthy"
        
        health_status["timestamp"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        return health_status

    @app.get(
        "/prometheus",
        tags=["monitoring"],
        summary="Prometheus metrics",
        description="Prometheus-compatible metrics endpoint for monitoring and alerting.",
        include_in_schema=False,  # Hide from OpenAPI docs
    )
    def prometheus_endpoint() -> Response:
        """Prometheus metrics endpoint in text/plain format."""
        return get_prometheus_metrics()

    @app.get(
        "/pool/stats",
        tags=["monitoring"],
        summary="Get connection pool statistics",
        description="Retrieve connection pool statistics for monitoring and optimization.",
        response_model=Dict[str, Any],
    )
    def pool_stats() -> Dict[str, Any]:
        """Connection pool statistics endpoint for monitoring."""
        pool = state.get("connection_pool")
        
        if pool is None:
            return {
                "enabled": False,
                "message": "Connection pooling is disabled"
            }
        
        stats = pool.get_stats()
        stats["enabled"] = True
        
        # Add configuration details
        settings = state.get("settings")
        if settings and hasattr(settings, "app") and hasattr(settings.app, "connection_pool"):
            pool_config = settings.app.connection_pool
            stats["config"] = {
                "pool_size": pool_config.pool_size,
                "max_overflow": pool_config.max_overflow,
                "pool_timeout": pool_config.pool_timeout,
                "pool_recycle": pool_config.pool_recycle
            }
        
        return stats

    @app.get(
        "/metrics",
        tags=["monitoring"],
        summary="Get system metrics",
        description="Retrieve system performance and usage metrics.",
        response_model=Dict[str, Any],
    )
    def metrics(settings: Settings = Depends(get_settings_dep)) -> Dict[str, Any]:
        """Get system metrics and statistics."""
        import sqlite3

        db_path = settings.app.database_path
        metrics_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "database": {},
            "tweets": {},
            "performance": {},
        }
        
        try:
            conn = sqlite3.connect(db_path)
            
            # Database size
            cursor = conn.execute("PRAGMA page_count;")
            page_count = cursor.fetchone()[0]
            cursor = conn.execute("PRAGMA page_size;")
            page_size = cursor.fetchone()[0]
            db_size_bytes = page_count * page_size
            
            metrics_data["database"] = {
                "size_bytes": db_size_bytes,
                "size_human": f"{db_size_bytes / 1024 / 1024:.2f} MB",
                "page_count": page_count,
            }
            
            # Tweet statistics
            cursor = conn.execute("SELECT COUNT(*) FROM tweets;")
            total_tweets = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM tweets WHERE salience IS NOT NULL;")
            scored_tweets = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM tweets WHERE category IS NOT NULL;")
            analyzed_tweets = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM tweets WHERE notified_at IS NOT NULL;")
            notified_tweets = cursor.fetchone()[0]
            
            # Recent activity (last 24 hours)
            day_ago = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat().replace("+00:00", "Z")
            cursor = conn.execute(
                "SELECT COUNT(*) FROM tweets WHERE created_at > ?;",
                (day_ago,)
            )
            recent_tweets = cursor.fetchone()[0]
            
            tweet_metrics: Dict[str, Any] = {
                "total": total_tweets,
                "scored": scored_tweets,
                "analyzed": analyzed_tweets,
                "notified": notified_tweets,
                "recent_24h": recent_tweets,
            }

            # Category distribution
            cursor = conn.execute(
                "SELECT category, COUNT(*) FROM tweets WHERE category IS NOT NULL GROUP BY category;"
            )
            category_dist = {row[0]: row[1] for row in cursor.fetchall()}
            tweet_metrics["by_category"] = category_dist

            metrics_data["tweets"] = tweet_metrics

            # Average metrics
            cursor = conn.execute(
                "SELECT AVG(salience), MAX(salience), AVG(urgency) FROM tweets WHERE salience IS NOT NULL;"
            )
            avg_row = cursor.fetchone()
            performance_metrics: Dict[str, Any] = {}
            if avg_row and avg_row[0] is not None:
                performance_metrics["avg_salience"] = round(avg_row[0], 2)
                performance_metrics["max_salience"] = round(avg_row[1], 2)
                performance_metrics["avg_urgency"] = round(avg_row[2], 2)

            metrics_data["performance"] = performance_metrics
            
            conn.close()
            
        except Exception as e:
            log.error(f"Error collecting metrics: {e}")
            metrics_data["error"] = str(e)
        
        return metrics_data

    @app.get(
        "/metrics/prometheus",
        tags=["monitoring"],
        summary="Prometheus metrics",
        description="Expose Prometheus metrics in text format.",
    )
    def prometheus_metrics() -> Response:
        from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest
        data = generate_latest(REGISTRY)
        return Response(content=data, media_type=CONTENT_TYPE_LATEST)

    # ========================================================================
    # Signals & Snapshots Endpoints
    # ========================================================================

    @app.get(
        "/signals",
        tags=["signals"],
        summary="List signals",
        description="Get paginated list of signals with optional filters.",
        response_model=PaginatedSignals,
    )
    def list_signals_endpoint(
        page: int = Query(1, ge=1, description="Page number"),
        pageSize: int = Query(20, ge=1, le=100, description="Page size"),
        search: Optional[str] = Query(None, description="Search query"),
        status: Optional[SignalStatus] = Query(None, description="Filter by status"),
        source: Optional[str] = Query(None, description="Filter by source"),
        sort: str = Query("createdAt", description="Sort field"),
        order: str = Query("desc", description="Sort order (asc/desc)"),
        settings: Settings = Depends(get_settings_dep),
    ) -> PaginatedSignals:
        """List signals with pagination and filters."""
        from . import db as db_module
        
        signals, total = db_module.list_signals(
            settings.app.database_path,
            page=page,
            page_size=pageSize,
            search=search,
            status=status.value if status else None,
            source=source,
            sort=sort,
            order=order,
        )
        
        return PaginatedSignals(
            items=[Signal(**s) for s in signals],
            total=total,
            page=page,
            pageSize=pageSize,
        )

    @app.get(
        "/signals/stats",
        tags=["signals"],
        summary="Get signals statistics",
        description="Get aggregated statistics for all signals.",
        response_model=SignalsStats,
    )
    def get_signals_stats_endpoint(
        settings: Settings = Depends(get_settings_dep),
    ) -> SignalsStats:
        """Get signal statistics."""
        from . import db as db_module
        
        stats = db_module.get_signals_stats(settings.app.database_path)
        return SignalsStats(**stats)

    @app.get(
        "/signals/{signal_id}",
        tags=["signals"],
        summary="Get a specific signal",
        description="Retrieve detailed information about a single signal by ID.",
        response_model=Signal,
    )
    def get_signal_endpoint(
        signal_id: str,
        settings: Settings = Depends(get_settings_dep),
    ) -> Signal:
        """Get a specific signal by ID."""
        from . import db as db_module
        
        signal = db_module.get_signal(settings.app.database_path, signal_id)
        if not signal:
            raise HTTPException(status_code=404, detail="Signal not found")
        return Signal(**signal)

    @app.post(
        "/signals",
        tags=["signals"],
        summary="Create a new signal",
        description="Create a new signal with the provided details.",
        response_model=Signal,
        status_code=201,
    )
    def create_signal_endpoint(
        input_data: CreateSignalInput,
        settings: Settings = Depends(get_settings_dep),
    ) -> Signal:
        """Create a new signal."""
        from . import db as db_module
        
        signal = db_module.create_signal(
            settings.app.database_path,
            name=input_data.name,
            source=input_data.source,
            status=input_data.status.value,
            tags=input_data.tags,
        )
        return Signal(**signal)

    @app.patch(
        "/signals/{signal_id}",
        tags=["signals"],
        summary="Update a signal",
        description="Update an existing signal with partial data.",
        response_model=Signal,
    )
    def update_signal_endpoint(
        signal_id: str,
        input_data: UpdateSignalInput,
        settings: Settings = Depends(get_settings_dep),
    ) -> Signal:
        """Update a signal."""
        from . import db as db_module
        
        updates = input_data.model_dump(exclude_unset=True)
        
        # Convert enum to value if present
        if "status" in updates and updates["status"] is not None:
            updates["status"] = updates["status"].value
        
        signal = db_module.update_signal(settings.app.database_path, signal_id, updates)
        if not signal:
            raise HTTPException(status_code=404, detail="Signal not found")
        return Signal(**signal)

    @app.delete(
        "/signals/{signal_id}",
        tags=["signals"],
        summary="Delete a signal",
        description="Delete a signal by ID.",
        status_code=204,
        response_model=None,
    )
    def delete_signal_endpoint(
        signal_id: str,
        settings: Settings = Depends(get_settings_dep),
    ) -> None:
        """Delete a signal."""
        from . import db as db_module
        
        deleted = db_module.delete_signal(settings.app.database_path, signal_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Signal not found")

    @app.get(
        "/snapshots",
        tags=["snapshots"],
        summary="List snapshots",
        description="Get paginated list of snapshots with optional filters.",
        response_model=PaginatedSnapshots,
    )
    def list_snapshots_endpoint(
        page: int = Query(1, ge=1, description="Page number"),
        pageSize: int = Query(20, ge=1, le=100, description="Page size"),
        search: Optional[str] = Query(None, description="Search query"),
        status: Optional[SnapshotStatus] = Query(None, description="Filter by status"),
        signalId: Optional[str] = Query(None, description="Filter by signal ID"),
        settings: Settings = Depends(get_settings_dep),
    ) -> PaginatedSnapshots:
        """List snapshots with pagination and filters."""
        from . import db as db_module
        
        snapshots, total = db_module.list_snapshots(
            settings.app.database_path,
            page=page,
            page_size=pageSize,
            search=search,
            status=status.value if status else None,
            signal_id=signalId,
        )
        
        return PaginatedSnapshots(
            items=[Snapshot(**s) for s in snapshots],
            total=total,
            page=page,
            pageSize=pageSize,
        )

    @app.get(
        "/snapshots/{snapshot_id}",
        tags=["snapshots"],
        summary="Get a specific snapshot",
        description="Retrieve detailed information about a single snapshot by ID.",
        response_model=Snapshot,
    )
    def get_snapshot_endpoint(
        snapshot_id: str,
        settings: Settings = Depends(get_settings_dep),
    ) -> Snapshot:
        """Get a specific snapshot by ID."""
        from . import db as db_module
        
        snapshot = db_module.get_snapshot(settings.app.database_path, snapshot_id)
        if not snapshot:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        return Snapshot(**snapshot)

    @app.post(
        "/snapshots",
        tags=["snapshots"],
        summary="Create a new snapshot",
        description="Create a snapshot for a specific signal.",
        response_model=Snapshot,
        status_code=201,
    )
    def create_snapshot_endpoint(
        signalId: str = Body(..., embed=True),
        settings: Settings = Depends(get_settings_dep),
    ) -> Snapshot:
        """Create a new snapshot for a signal."""
        from . import db as db_module
        
        # Verify signal exists
        signal = db_module.get_signal(settings.app.database_path, signalId)
        if not signal:
            raise HTTPException(status_code=404, detail="Signal not found")
        
        # Create snapshot (initially in processing state)
        snapshot = db_module.create_snapshot(
            settings.app.database_path,
            signal_id=signalId,
        )
        return Snapshot(**snapshot)

    # ========================================================================
    # Bulk Operations Endpoints
    # ========================================================================

    @app.post(
        "/signals/bulk/status",
        tags=["signals", "bulk"],
        summary="Bulk update signal status",
        description="Update status for multiple signals matching the provided scope.",
        response_model=BulkJobResponse,
    )
    async def bulk_set_signal_status(
        input_data: BulkSetStatusInput,
        settings: Settings = Depends(get_settings_dep),
    ) -> BulkJobResponse:
        """Start a bulk signal status update job."""
        from . import db as db_module
        
        job_id = str(uuid.uuid4())
        
        # Determine which signals to update
        target_ids = []
        if input_data.ids:
            target_ids = input_data.ids
        elif input_data.filters:
            # Query signals matching filters
            signals, _ = db_module.list_signals(
                settings.app.database_path,
                page=1,
                page_size=10000,  # Large page to get all matching
                search=input_data.filters.get("search"),
                status=input_data.filters.get("status"),
                source=input_data.filters.get("source"),
            )
            target_ids = [s["id"] for s in signals]
        
        # Create job
        bulk_jobs[job_id] = {
            "jobId": job_id,
            "status": "running",
            "total": len(target_ids),
            "done": 0,
            "fail": 0,
            "operation": "set_status",
            "target_ids": target_ids,
            "target_status": input_data.status.value,
            "db_path": settings.app.database_path,
        }
        
        # Start background task
        asyncio.create_task(_process_bulk_job(job_id))
        
        return BulkJobResponse(jobId=job_id, total=len(target_ids))

    @app.post(
        "/signals/bulk/delete",
        tags=["signals", "bulk"],
        summary="Bulk delete signals",
        description="Delete multiple signals matching the provided scope.",
        response_model=BulkJobResponse,
    )
    async def bulk_delete_signals(
        scope: BulkScope,
        settings: Settings = Depends(get_settings_dep),
    ) -> BulkJobResponse:
        """Start a bulk signal delete job."""
        from . import db as db_module
        
        job_id = str(uuid.uuid4())
        
        # Determine which signals to delete
        target_ids = []
        if scope.ids:
            target_ids = scope.ids
        elif scope.filters:
            # Query signals matching filters
            signals, _ = db_module.list_signals(
                settings.app.database_path,
                page=1,
                page_size=10000,  # Large page to get all matching
                search=scope.filters.get("search"),
                status=scope.filters.get("status"),
                source=scope.filters.get("source"),
            )
            target_ids = [s["id"] for s in signals]
        
        # Create job
        bulk_jobs[job_id] = {
            "jobId": job_id,
            "status": "running",
            "total": len(target_ids),
            "done": 0,
            "fail": 0,
            "operation": "delete",
            "target_ids": target_ids,
            "db_path": settings.app.database_path,
        }
        
        # Start background task
        asyncio.create_task(_process_bulk_job(job_id))
        
        return BulkJobResponse(jobId=job_id, total=len(target_ids))

    @app.get(
        "/bulk-jobs/{job_id}",
        tags=["bulk"],
        summary="Get bulk job status",
        description="Get the current status of a bulk operation job.",
        response_model=BulkJobStatus,
    )
    def get_bulk_job(job_id: str) -> BulkJobStatus:
        """Get bulk job status."""
        if job_id not in bulk_jobs:
            raise HTTPException(status_code=404, detail="Job not found")
        
        job = bulk_jobs[job_id]
        return BulkJobStatus(
            jobId=job["jobId"],
            status=job["status"],
            total=job["total"],
            done=job["done"],
            fail=job["fail"],
        )

    @app.post(
        "/bulk-jobs/{job_id}/cancel",
        tags=["bulk"],
        summary="Cancel bulk job",
        description="Cancel a running bulk operation job.",
        status_code=204,
        response_model=None,
    )
    def cancel_bulk_job(job_id: str) -> None:
        """Cancel a bulk job."""
        if job_id not in bulk_jobs:
            raise HTTPException(status_code=404, detail="Job not found")
        
        job = bulk_jobs[job_id]
        if job["status"] == "running":
            job["status"] = "cancelled"

    @app.get(
        "/bulk-jobs/{job_id}/stream",
        tags=["bulk"],
        summary="Stream bulk job updates",
        description="Server-Sent Events stream for bulk job progress updates.",
    )
    async def stream_bulk_job(job_id: str) -> StreamingResponse:
        """Stream bulk job updates via SSE."""
        if job_id not in bulk_jobs:
            raise HTTPException(status_code=404, detail="Job not found")
        
        async def event_generator():  # type: ignore[no-untyped-def]
            """Generate SSE events for job updates."""
            try:
                job = bulk_jobs[job_id]
                last_done = -1
                
                while True:
                    # Check if job state changed
                    current_done = job["done"]
                    current_status = job["status"]
                    
                    if current_done != last_done or current_status != "running":
                        # Send update
                        status_data = BulkJobStatus(
                            jobId=job["jobId"],
                            status=job["status"],
                            total=job["total"],
                            done=job["done"],
                            fail=job["fail"],
                        )
                        yield f"data: {status_data.model_dump_json()}\n\n"
                        last_done = current_done
                    
                    # Exit if job finished
                    if current_status in ["completed", "cancelled", "failed"]:
                        break
                    
                    # Wait before next check
                    await asyncio.sleep(0.5)
            except Exception as e:
                log.error(f"Error in SSE stream: {e}")
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    # Phase One: Deep Tech Discovery endpoints
    
    # Cached helper function for discoveries
    @cached(prefix='discovery', ttl_key='discovery_ttl')
    def _get_discoveries_cached(
        db_path: str,
        min_score: float,
        limit: int,
        hours: Optional[int]
    ) -> List[Discovery]:
        """Cached discovery results."""
        from .db import list_top_discoveries
        
        raw_discoveries = list_top_discoveries(
            db_path,
            min_score=min_score,
            limit=limit,
            hours=hours
        )
        
        # Convert raw dict results to Discovery models
        discoveries = []
        for d in raw_discoveries:
            discovery = Discovery(
                id=d["id"],
                artifactId=d["artifact_id"],
                artifactType=d["artifact_type"],
                source=d["source"],
                sourceId=d["source_id"],
                title=d["title"],
                text=d.get("text"),
                url=d.get("url"),
                publishedAt=d["published_at"],
                novelty=d.get("novelty"),
                emergence=d.get("emergence"),
                obscurity=d.get("obscurity"),
                discoveryScore=d.get("discovery_score"),
                computedAt=d.get("computed_at"),
                category=d.get("category"),
                sentiment=d.get("sentiment"),
                urgency=d.get("urgency"),
                tags=d.get("tags"),
                topics=d.get("topics"),
                reasoning=d.get("reasoning"),
                createdAt=d["created_at"],
                updatedAt=d["updated_at"],
            )
            discoveries.append(discovery)
        
        return discoveries
    
    @app.get(
        "/discoveries",
        tags=["discovery"],
        summary="List discoveries",
        description="Get top discoveries by discovery score with optional filters.",
        response_model=List[Discovery],
    )
    def get_discoveries(
        min_score: float = Query(80.0, ge=0.0, le=100.0, description="Minimum discovery score"),
        limit: int = Query(50, ge=1, le=200, description="Maximum number of results"),
        hours: Optional[int] = Query(None, ge=1, le=168, description="Filter by hours since publication"),
        settings: Settings = Depends(get_settings_dep),
    ) -> List[Discovery]:
        """Get top discoveries by discovery score."""
        return _get_discoveries_cached(
            settings.app.database_path,
            min_score,
            limit,
            hours
        )

    @app.get(
        "/discoveries/paginated",
        tags=["discovery"],
        summary="List discoveries with cursor pagination",
        description="Get top discoveries with cursor-based pagination for efficient large dataset traversal.",
        response_model=PaginatedDiscoveries,
    )
    def get_discoveries_paginated(
        min_score: float = Query(80.0, ge=0.0, le=100.0, description="Minimum discovery score"),
        limit: int = Query(50, ge=1, le=200, description="Maximum number of results"),
        hours: Optional[int] = Query(None, ge=1, le=168, description="Filter by hours since publication"),
        cursor: Optional[str] = Query(None, description="Cursor for pagination (from previous response)"),
        settings: Settings = Depends(get_settings_dep),
    ) -> PaginatedDiscoveries:
        """Get top discoveries with cursor-based pagination."""
        from .db import list_top_discoveries_paginated
        
        raw_discoveries, next_cursor, has_more = list_top_discoveries_paginated(
            settings.app.database_path,
            min_score=min_score,
            limit=limit,
            hours=hours,
            cursor=cursor,
        )
        
        # Convert raw dict results to Discovery models
        discoveries = []
        for d in raw_discoveries:
            discovery = Discovery(
                id=d["id"],
                artifactId=d["artifact_id"],
                artifactType=d["artifact_type"],
                source=d["source"],
                sourceId=d["source_id"],
                title=d["title"],
                text=d.get("text"),
                url=d.get("url"),
                publishedAt=d["published_at"],
                novelty=d.get("novelty"),
                emergence=d.get("emergence"),
                obscurity=d.get("obscurity"),
                discoveryScore=d.get("discovery_score"),
                computedAt=d.get("computed_at"),
                category=d.get("category"),
                sentiment=d.get("sentiment"),
                urgency=d.get("urgency"),
                tags=d.get("tags"),
                topics=d.get("topics"),
                reasoning=d.get("reasoning"),
                createdAt=d["created_at"],
                updatedAt=d["updated_at"],
            )
            discoveries.append(discovery)
        
        return PaginatedDiscoveries(
            items=discoveries,
            nextCursor=next_cursor,
            hasMore=has_more,
        )

    # Cached helper function for trending topics
    @cached(prefix='topic', ttl_key='topic_ttl')
    def _get_trending_topics_cached(
        db_path: str,
        window_days: int,
        limit: int
    ) -> List[Topic]:
        """Cached trending topics results."""
        from .db import get_trending_topics
        
        raw_topics = get_trending_topics(
            db_path,
            window_days=window_days,
            limit=limit
        )
        
        # Convert raw dict results to Topic models
        topics = []
        for t in raw_topics:
            topic = Topic(
                id=t["id"],
                name=t["name"],
                taxonomyPath=t.get("taxonomy_path"),
                description=t.get("description"),
                artifactCount=t.get("artifact_count"),
                avgDiscoveryScore=t.get("avg_discovery_score"),
                createdAt=t.get("created_at"),
                updatedAt=t.get("updated_at"),
            )
            topics.append(topic)
        
        return topics

    @app.get(
        "/topics/trending",
        tags=["discovery"],
        summary="Get trending topics",
        description="Get trending research topics by artifact count and discovery score.",
        response_model=List[Topic],
    )
    def get_trending_topics(
        window_days: int = Query(14, ge=1, le=365, alias="window", description="Time window in days"),
        limit: int = Query(20, ge=1, le=200, description="Maximum number of topics"),
        settings: Settings = Depends(get_settings_dep),
    ) -> List[Topic]:
        """Get trending research topics."""
        return _get_trending_topics_cached(
            settings.app.database_path,
            window_days,
            limit
        )

    @app.get(
        "/topics/trending/paginated",
        tags=["discovery"],
        summary="Get trending topics with cursor pagination",
        description="Get trending research topics with cursor-based pagination.",
        response_model=PaginatedTopics,
    )
    def get_trending_topics_paginated(
        window_days: int = Query(14, ge=1, le=365, alias="window", description="Time window in days"),
        limit: int = Query(20, ge=1, le=200, description="Maximum number of topics"),
        cursor: Optional[str] = Query(None, description="Cursor for pagination (from previous response)"),
        settings: Settings = Depends(get_settings_dep),
    ) -> PaginatedTopics:
        """Get trending research topics with cursor-based pagination."""
        from .db import get_trending_topics_paginated
        
        raw_topics, next_cursor, has_more = get_trending_topics_paginated(
            settings.app.database_path,
            window_days=window_days,
            limit=limit,
            cursor=cursor,
        )
        
        # Convert raw dict results to Topic models
        topics = []
        for t in raw_topics:
            topic = Topic(
                id=t["id"],
                name=t["name"],
                taxonomyPath=t.get("taxonomy_path"),
                description=t.get("description"),
                artifactCount=t.get("artifact_count"),
                avgDiscoveryScore=t.get("avg_discovery_score"),
                createdAt=t.get("created_at"),
                updatedAt=t.get("updated_at"),
            )
            topics.append(topic)
        
        return PaginatedTopics(
            items=topics,
            nextCursor=next_cursor,
            hasMore=has_more,
        )

    # Cached helper function for entity details
    @cached(prefix='entity', ttl_key='entity_ttl')
    def _get_entity_cached(db_path: str, entity_id: int) -> Optional[Entity]:
        """Cached entity details results."""
        from .db import get_entity_with_accounts
        
        raw_entity = get_entity_with_accounts(db_path, entity_id)
        if not raw_entity:
            return None
        
        entity = Entity(
            id=raw_entity["id"],
            entityType=raw_entity["entity_type"],
            name=raw_entity["name"],
            description=raw_entity.get("description"),
            createdAt=raw_entity.get("created_at"),
            updatedAt=raw_entity.get("updated_at"),
            accounts=[
                {
                    "platform": acc["platform"],
                    "accountId": acc["account_id"],
                    "username": acc.get("username"),
                    "followerCount": acc.get("follower_count"),
                    "url": acc.get("url"),
                }
                for acc in raw_entity.get("accounts", [])
            ],
        )
        
        return entity

    @app.get(
        "/entities/{entity_id}",
        tags=["discovery"],
        summary="Get entity details",
        description="Get details for a person, lab, or organization with their accounts and artifacts.",
        response_model=Entity,
    )
    def get_entity(
        entity_id: int,
        settings: Settings = Depends(get_settings_dep),
    ) -> Entity:
        """Get entity details with accounts and artifacts."""
        entity = _get_entity_cached(settings.app.database_path, entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        
        return entity

    @app.get(
        "/topics/{topic_name}/timeline",
        tags=["discovery"],
        summary="Get topic timeline",
        description="Get timeline data for a specific topic showing artifact count and average scores over time.",
        response_model=List[TopicTimeline],
    )
    def get_topic_timeline(
        topic_name: str,
        days: int = Query(14, description="Number of days to look back"),
        settings: Settings = Depends(get_settings_dep),
    ) -> List[TopicTimeline]:
        """Get timeline data for a specific topic."""
        from .db import get_topic_timeline
        
        raw_timeline = get_topic_timeline(
            settings.app.database_path,
            topic_name=topic_name,
            days=days
        )
        
        # Convert raw dict results to TopicTimeline models
        timeline = []
        for t in raw_timeline:
            timeline_point = TopicTimeline(
                date=t["date"],
                artifactCount=t["artifact_count"],
                avgDiscoveryScore=t.get("avg_discovery_score"),
            )
            timeline.append(timeline_point)
        
        return timeline

    @app.get(
        "/artifacts/{artifact_id}/relationships",
        tags=["discovery"],
        summary="Get artifact relationships",
        description="Get citation graph and cross-source relationships for an artifact.",
        response_model=Dict[str, Any],
    )
    def get_artifact_relationships_endpoint(
        artifact_id: int,
        direction: str = Query("both", description="Relationship direction: outgoing, incoming, or both"),
        min_confidence: float = Query(0.5, description="Minimum confidence threshold"),
        settings: Settings = Depends(get_settings_dep),
    ) -> Dict[str, Any]:
        """Get relationships for an artifact."""
        from .db import get_artifact_relationships as get_relationships
        
        relationships = get_relationships(
            settings.app.database_path,
            artifact_id=artifact_id,
            direction=direction,
            min_confidence=min_confidence,
        )
        
        return {
            "artifact_id": artifact_id,
            "direction": direction,
            "min_confidence": min_confidence,
            "count": len(relationships),
            "relationships": relationships,
        }
    
    @app.get(
        "/artifacts/{artifact_id}/citation-graph",
        tags=["discovery"],
        summary="Get citation graph",
        description="Get multi-level citation graph for an artifact with configurable depth.",
        response_model=Dict[str, Any],
    )
    def get_citation_graph_endpoint(
        artifact_id: int,
        depth: int = Query(2, description="Graph traversal depth (1-3)"),
        min_confidence: float = Query(0.5, description="Minimum confidence threshold"),
        settings: Settings = Depends(get_settings_dep),
    ) -> Dict[str, Any]:
        """Get citation graph for an artifact."""
        from .relationship_detection import get_citation_graph
        
        # Clamp depth to reasonable range
        depth = max(1, min(3, depth))
        
        graph = get_citation_graph(
            db_path=settings.app.database_path,
            artifact_id=artifact_id,
            depth=depth,
            min_confidence=min_confidence,
        )
        
        return graph
    
    @app.get(
        "/relationships/stats",
        tags=["discovery"],
        summary="Get relationship statistics",
        description="Get overall statistics about artifact relationships.",
        response_model=Dict[str, Any],
    )
    def get_relationship_stats_endpoint(
        settings: Settings = Depends(get_settings_dep),
    ) -> Dict[str, Any]:
        """Get relationship statistics."""
        from .db import get_relationship_stats
        
        return get_relationship_stats(settings.app.database_path)
    
    @app.post(
        "/relationships/detect",
        tags=["discovery"],
        summary="Run relationship detection",
        description="Detect cross-source relationships for all or specific artifacts.",
        response_model=Dict[str, Any],
    )
    async def run_relationship_detection_endpoint(
        artifact_id: Optional[int] = None,
        enable_semantic: bool = Query(True, description="Enable semantic similarity detection"),
        semantic_threshold: float = Query(0.80, description="Minimum similarity threshold"),
        settings: Settings = Depends(get_settings_dep),
        api_key: str = Depends(validate_api_key),
    ) -> Dict[str, Any]:
        """Run relationship detection."""
        from .relationship_detection import run_relationship_detection
        
        stats = run_relationship_detection(
            db_path=settings.app.database_path,
            artifact_id=artifact_id,
            enable_semantic=enable_semantic,
            semantic_threshold=semantic_threshold,
        )
        
        return stats

    @app.post(
        "/refresh",
        tags=["discovery"],
        summary="Refresh discovery pipeline",
        description="Run fetch, analyze, and score for discoveries.",
        response_model=Dict[str, Any],
    )
    async def refresh_discoveries(
        refresh_type: str = Query("discovery", description="Type of refresh: discovery or all"),
        settings: Settings = Depends(get_settings_dep),
        api_key: str = Depends(validate_api_key),
    ) -> Dict[str, Any]:
        """Run discovery pipeline refresh."""
        from .discovery_scoring import run_discovery_scoring
        from .pipeline import analyze_unanalyzed, fetch_once
        
        stats = {}
        
        if refresh_type in ["all", "discovery"]:
            # Fetch from all enabled sources
            f_stats = fetch_once(settings)
            stats["fetch"] = f_stats
            
            # Analyze unanalyzed artifacts
            # Note: This would need to be updated to handle artifacts, not just tweets
            a_count = analyze_unanalyzed(settings, limit=300)
            stats["analyze"] = {"count": a_count}
            
            # Score discoveries
            s_count = await run_discovery_scoring(
                settings.app.database_path,
                settings.model_dump(),
                limit=1000
            )
            stats["score"] = {"count": s_count}
        
        return {
            "status": "success",
            "stats": stats
        }

    @app.get(
        "/analytics/sources",
        tags=["analytics"],
        summary="Source distribution analytics",
        description="Get artifact distribution across sources with metrics.",
        response_model=Dict[str, Any],
    )
    def get_source_analytics(
        hours: Optional[int] = Query(None, description="Time window in hours"),
        settings: Settings = Depends(get_settings_dep),
    ) -> Dict[str, Any]:
        """Get source distribution analytics."""
        from . import analytics
        
        return analytics.get_source_distribution(
            settings.app.database_path,
            hours=hours
        )

    @app.get(
        "/analytics/trends",
        tags=["analytics"],
        summary="Temporal trends",
        description="Get temporal trends for artifacts and scores.",
        response_model=Dict[str, Any],
    )
    def get_trend_analytics(
        days: int = Query(30, description="Number of days to analyze"),
        settings: Settings = Depends(get_settings_dep),
    ) -> Dict[str, Any]:
        """Get temporal trend analytics."""
        from . import analytics
        
        return analytics.get_temporal_trends(
            settings.app.database_path,
            days=days
        )

    @app.get(
        "/analytics/correlations",
        tags=["analytics"],
        summary="Cross-source correlations",
        description="Analyze correlations between different sources for topics.",
        response_model=Dict[str, Any],
    )
    def get_correlation_analytics(
        hours: int = Query(168, description="Time window in hours"),
        settings: Settings = Depends(get_settings_dep),
    ) -> Dict[str, Any]:
        """Get cross-source correlation analytics."""
        from . import analytics
        
        return analytics.get_cross_source_correlations(
            settings.app.database_path,
            hours=hours
        )

    @app.get(
        "/analytics/score-distributions",
        tags=["analytics"],
        summary="Score distributions",
        description="Get distributions of discovery scores and components.",
        response_model=Dict[str, Any],
    )
    def get_score_distributions(
        settings: Settings = Depends(get_settings_dep),
    ) -> Dict[str, Any]:
        """Get score distribution analytics."""
        from . import analytics
        
        return analytics.get_score_distributions(settings.app.database_path)

    @app.get(
        "/analytics/health",
        tags=["analytics"],
        summary="System health",
        description="Get comprehensive system health metrics.",
        response_model=Dict[str, Any],
    )
    def get_system_health_analytics(
        settings: Settings = Depends(get_settings_dep),
    ) -> Dict[str, Any]:
        """Get system health analytics."""
        from . import analytics
        
        return analytics.get_system_health(
            settings.app.database_path,
            settings
        )

    @app.get(
        "/analytics/dashboard",
        tags=["analytics"],
        summary="Dashboard data",
        description="Get all dashboard analytics data in a single call.",
        response_model=Dict[str, Any],
    )
    def get_dashboard_analytics(
        days: int = Query(30, description="Number of days for trend analysis"),
        settings: Settings = Depends(get_settings_dep),
    ) -> Dict[str, Any]:
        """Get comprehensive dashboard analytics."""
        from . import analytics
        
        return {
            "source_distribution": analytics.get_source_distribution(
                settings.app.database_path,
                hours=days*24
            ),
            "temporal_trends": analytics.get_temporal_trends(
                settings.app.database_path,
                days=days
            ),
            "cross_source_correlations": analytics.get_cross_source_correlations(
                settings.app.database_path,
                hours=days*24
            ),
            "score_distributions": analytics.get_score_distributions(
                settings.app.database_path
            ),
            "system_health": analytics.get_system_health(
                settings.app.database_path,
                settings
            )
        }
    
    # Experiment & Backtesting Endpoints
    
    @app.post(
        "/experiments",
        tags=["experiments"],
        summary="Create experiment",
        description="Create a new experiment configuration for A/B testing scoring algorithms.",
        response_model=Dict[str, Any],
    )
    def create_experiment_endpoint(
        request: ExperimentRequest,
        settings: Settings = Depends(get_settings_dep),
        api_key: str = Depends(validate_api_key),
    ) -> Dict[str, Any]:
        """Create a new experiment."""
        from .experiment import ExperimentConfig, create_experiment
        
        config = ExperimentConfig(
            scoring_weights=request.scoring_weights,
            min_score_threshold=request.min_score_threshold,
            lookback_days=request.lookback_days,
            description=request.description,
        )
        
        try:
            experiment_id = create_experiment(
                settings.app.database_path,
                request.name,
                config,
                request.baseline_id,
            )
            return {
                "status": "success",
                "experimentId": experiment_id,
                "name": request.name,
            }
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    @app.get(
        "/experiments",
        tags=["experiments"],
        summary="List experiments",
        description="List all experiments, optionally filtered by status.",
        response_model=Dict[str, Any],
    )
    def list_experiments_endpoint(
        status: Optional[str] = Query(None, description="Filter by status (draft, running, completed)"),
        settings: Settings = Depends(get_settings_dep),
    ) -> Dict[str, Any]:
        """List all experiments."""
        from .experiment import list_experiments
        
        experiments = list_experiments(settings.app.database_path, status)
        return {
            "experiments": experiments,
            "count": len(experiments),
        }
    
    @app.get(
        "/experiments/{experiment_id}",
        tags=["experiments"],
        summary="Get experiment details",
        description="Get detailed information about a specific experiment.",
        response_model=Dict[str, Any],
    )
    def get_experiment_endpoint(
        experiment_id: int,
        settings: Settings = Depends(get_settings_dep),
    ) -> Dict[str, Any]:
        """Get experiment details."""
        from .experiment import get_experiment
        
        experiment = get_experiment(settings.app.database_path, experiment_id)
        if not experiment:
            raise HTTPException(status_code=404, detail="Experiment not found")
        return experiment
    
    @app.get(
        "/experiments/{experiment_id}/runs",
        tags=["experiments"],
        summary="Get experiment runs",
        description="Get all runs for a specific experiment.",
        response_model=Dict[str, Any],
    )
    def get_experiment_runs_endpoint(
        experiment_id: int,
        settings: Settings = Depends(get_settings_dep),
    ) -> Dict[str, Any]:
        """Get experiment runs."""
        from .experiment import get_experiment_runs
        
        runs = get_experiment_runs(settings.app.database_path, experiment_id)
        return {
            "experimentId": experiment_id,
            "runs": runs,
            "count": len(runs),
        }
    
    @app.get(
        "/experiments/compare",
        tags=["experiments"],
        summary="Compare experiments",
        description="Compare results of two experiments.",
        response_model=Dict[str, Any],
    )
    def compare_experiments_endpoint(
        experiment_a: int = Query(..., description="First experiment ID"),
        experiment_b: int = Query(..., description="Second experiment ID"),
        settings: Settings = Depends(get_settings_dep),
    ) -> Dict[str, Any]:
        """Compare two experiments."""
        from .experiment import compare_experiments
        
        comparison = compare_experiments(
            settings.app.database_path,
            experiment_a,
            experiment_b,
        )
        
        if "error" in comparison:
            raise HTTPException(status_code=400, detail=comparison.get("error", "Comparison failed"))
        
        return comparison
    
    @app.get(
        "/labels",
        tags=["experiments"],
        summary="Get labeled artifacts",
        description="Get all labeled artifacts for ground truth validation.",
        response_model=Dict[str, Any],
    )
    def get_labels_endpoint(
        label: Optional[str] = Query(None, description="Filter by label type"),
        settings: Settings = Depends(get_settings_dep),
    ) -> Dict[str, Any]:
        """Get labeled artifacts."""
        from .experiment import get_labeled_artifacts
        
        labels = get_labeled_artifacts(settings.app.database_path, label)
        return {
            "labels": labels,
            "count": len(labels),
        }
    
    @app.post(
        "/labels",
        tags=["experiments"],
        summary="Add label",
        description="Add or update ground truth label for an artifact.",
        response_model=Dict[str, Any],
    )
    def add_label_endpoint(
        artifact_id: int = Query(..., description="Artifact ID"),
        label: str = Query(..., description="Label value"),
        confidence: float = Query(1.0, description="Confidence in label (0.0-1.0)"),
        annotator: Optional[str] = Query(None, description="Annotator name"),
        notes: Optional[str] = Query(None, description="Notes about the label"),
        settings: Settings = Depends(get_settings_dep),
        api_key: str = Depends(validate_api_key),
    ) -> Dict[str, Any]:
        """Add or update artifact label."""
        from .experiment import add_discovery_label
        
        if not 0.0 <= confidence <= 1.0:
            raise HTTPException(status_code=400, detail="Confidence must be between 0.0 and 1.0")
        
        label_id = add_discovery_label(
            settings.app.database_path,
            artifact_id,
            label,
            confidence,
            annotator,
            notes,
        )
        
        return {
            "status": "success",
            "labelId": label_id,
            "artifactId": artifact_id,
            "label": label,
        }

    # ============================================================================
    # Cache Management Endpoints
    # ============================================================================

    @app.get(
        "/cache/stats",
        tags=["admin"],
        summary="Get cache statistics",
        description="Get cache hit rates and performance metrics.",
        response_model=Dict[str, Any],
    )
    def get_cache_stats_endpoint() -> Dict[str, Any]:
        """Get cache statistics."""
        return get_cache_stats()

    @app.post(
        "/cache/invalidate",
        tags=["admin"],
        summary="Invalidate cache",
        description="Invalidate cache entries by pattern. Use '*' to clear all cache.",
        response_model=Dict[str, Any],
    )
    def invalidate_cache_endpoint(
        pattern: str = Query("*", description="Cache key pattern to invalidate"),
        api_key: str = Depends(validate_api_key),
    ) -> Dict[str, Any]:
        """Invalidate cache entries."""
        count = invalidate_cache(pattern)
        return {
            "status": "success",
            "pattern": pattern,
            "invalidated_count": count,
        }

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):  # type: ignore[no-untyped-def]
        """Catch-all exception handler that reports to Sentry."""
        # Log the error (Sentry will automatically capture it)
        log.error("Unhandled exception: %s", exc, exc_info=True)
        
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "message": "An unexpected error occurred. Our team has been notified.",
                "path": str(request.url.path),
                "method": request.method,
            }
        )

    @app.on_event("shutdown")
    def shutdown_event() -> None:
        """Cleanup resources on application shutdown."""
        log.info("Application shutdown initiated")
        
        # Close connection pool if enabled
        pool = state.get("connection_pool")
        if pool:
            log.info("Closing connection pool...")
            pool.close_all()
            log.info("Connection pool closed")

    return app


def main() -> None:
    """Entry point for harvest-api console script."""
    import argparse

    import uvicorn
    
    parser = argparse.ArgumentParser(description="Signal Harvester API Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    parser.add_argument("--config", help="Path to settings.yaml")
    
    args = parser.parse_args()
    
    app = create_app(settings_path=args.config)
    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)
