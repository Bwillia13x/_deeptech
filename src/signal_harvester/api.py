from __future__ import annotations

import logging
import os
import sqlite3
import time
from collections import defaultdict
from typing import Any, Awaitable, Callable, Dict, List, Optional, cast

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from . import __version__
from .config import Settings, load_settings
from .db import get_tweet, init_db, list_top
from .logger import get_logger
from .pipeline import run_pipeline
from .validation import (
    validate_api_key,
    validate_hours,
    validate_limit,
    validate_salience,
    validate_tweet_id,
)

log = get_logger(__name__)


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
            # Add custom tags
            initial_scope={
                "tags": {"component": "api"}
            }
        )
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
    state["settings"] = settings

    cors_origins = [o.strip() for o in (os.getenv("CORS_ORIGINS") or "*").split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)

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
        try:
            settings = load_settings()
            health_status["checks"]["settings"] = "ok"
        except Exception as e:
            health_status["checks"]["settings"] = f"error: {str(e)}"
            health_status["status"] = "unhealthy"
        
        # Check database connectivity
        try:
            db_path = settings.app.database_path if 'settings' in locals() else "var/app.db"
            conn = sqlite3.connect(db_path, timeout=1.0)
            conn.execute("SELECT 1")
            conn.close()
            health_status["checks"]["database"] = "ok"
        except Exception as e:
            health_status["checks"]["database"] = f"error: {str(e)}"
            health_status["status"] = "unhealthy"
        
        from datetime import datetime
        health_status["timestamp"] = datetime.utcnow().isoformat() + "Z"
        
        return health_status

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
        from datetime import datetime, timedelta
        
        db_path = settings.app.database_path
        metrics_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
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
            day_ago = (datetime.utcnow() - timedelta(hours=24)).isoformat() + "Z"
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

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
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
