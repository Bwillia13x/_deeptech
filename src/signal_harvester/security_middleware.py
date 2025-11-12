"""Security middleware for API protection.

This module provides security middleware for the FastAPI application including:
- Security headers (HSTS, CSP, X-Frame-Options, etc.)
- Enhanced rate limiting
- API key rotation support
- Request throttling
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta
from typing import Any, Callable

from fastapi import Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .logger import get_logger

log = get_logger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses.

    Adds headers for:
    - HSTS (HTTP Strict Transport Security)
    - CSP (Content Security Policy)
    - X-Frame-Options (Clickjacking protection)
    - X-Content-Type-Options (MIME sniffing protection)
    - X-XSS-Protection (XSS protection)
    - Referrer-Policy (Referrer control)
    """

    def __init__(
        self,
        app: ASGIApp,
        hsts_max_age: int = 31536000,  # 1 year
        hsts_include_subdomains: bool = True,
        enable_csp: bool = True,
    ):
        super().__init__(app)
        self.hsts_max_age = hsts_max_age
        self.hsts_include_subdomains = hsts_include_subdomains
        self.enable_csp = enable_csp

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add security headers to response."""
        response = await call_next(request)

        # HSTS header (only for HTTPS)
        if request.url.scheme == "https":
            hsts_value = f"max-age={self.hsts_max_age}"
            if self.hsts_include_subdomains:
                hsts_value += "; includeSubDomains"
            response.headers["Strict-Transport-Security"] = hsts_value

        # Content Security Policy
        if self.enable_csp:
            # Restrictive CSP - adjust based on your needs
            csp_directives = [
                "default-src 'self'",
                "script-src 'self' 'unsafe-inline'",  # Unsafe-inline needed for some frameworks
                "style-src 'self' 'unsafe-inline'",
                "img-src 'self' data: https:",
                "font-src 'self' data:",
                "connect-src 'self'",
                "frame-ancestors 'none'",
                "base-uri 'self'",
                "form-action 'self'",
            ]
            response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        # Clickjacking protection
        response.headers["X-Frame-Options"] = "DENY"

        # MIME sniffing protection
        response.headers["X-Content-Type-Options"] = "nosniff"

        # XSS protection (deprecated but still useful for older browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions policy (restrict browser features)
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        return response


class RateLimitExceeded(HTTPException):
    """Exception raised when rate limit is exceeded."""

    def __init__(self, detail: str = "Rate limit exceeded", retry_after: int = 60):
        super().__init__(status_code=429, detail=detail)
        self.retry_after = retry_after


class InMemoryRateLimiter:
    """Simple in-memory rate limiter.

    Uses token bucket algorithm for smooth rate limiting.
    For production, consider using Redis-backed rate limiting.
    """

    def __init__(self):
        self.buckets: dict[str, dict[str, Any]] = {}
        self.cleanup_interval = 3600  # Clean up old buckets every hour
        self.last_cleanup = time.time()

    def _cleanup_old_buckets(self) -> None:
        """Remove expired buckets to prevent memory leaks."""
        now = time.time()
        if now - self.last_cleanup > self.cleanup_interval:
            expired_keys = [
                key for key, bucket in self.buckets.items() if now - bucket["last_check"] > self.cleanup_interval
            ]
            for key in expired_keys:
                del self.buckets[key]
            self.last_cleanup = now
            if expired_keys:
                log.debug(f"Cleaned up {len(expired_keys)} expired rate limit buckets")

    def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[bool, int]:
        """Check if request is within rate limit.

        Args:
            key: Unique identifier for the client (IP, API key, etc.)
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds

        Returns:
            Tuple of (allowed, retry_after_seconds)
        """
        self._cleanup_old_buckets()

        now = time.time()

        if key not in self.buckets:
            self.buckets[key] = {
                "tokens": max_requests - 1,
                "last_check": now,
                "max_tokens": max_requests,
                "refill_rate": max_requests / window_seconds,
            }
            return True, 0

        bucket = self.buckets[key]
        time_passed = now - bucket["last_check"]

        # Refill tokens based on time passed
        bucket["tokens"] = min(bucket["max_tokens"], bucket["tokens"] + time_passed * bucket["refill_rate"])

        bucket["last_check"] = now

        if bucket["tokens"] >= 1:
            bucket["tokens"] -= 1
            return True, 0
        else:
            # Calculate retry after (when bucket will have 1 token)
            retry_after = int((1 - bucket["tokens"]) / bucket["refill_rate"])
            return False, retry_after


# Global rate limiter instance
_rate_limiter = InMemoryRateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware for rate limiting requests.

    Applies different rate limits based on:
    - API key (if present) - higher limits
    - IP address (fallback) - lower limits
    - Specific endpoints (can have custom limits)
    """

    def __init__(
        self,
        app: ASGIApp,
        default_max_requests: int = 100,
        default_window_seconds: int = 60,
        api_key_max_requests: int = 1000,
        api_key_window_seconds: int = 60,
    ):
        super().__init__(app)
        self.default_max_requests = default_max_requests
        self.default_window_seconds = default_window_seconds
        self.api_key_max_requests = api_key_max_requests
        self.api_key_window_seconds = api_key_window_seconds

    def _get_client_identifier(self, request: Request) -> str:
        """Get unique identifier for the client."""
        # Check for API key
        api_key = request.headers.get("x-api-key") or request.headers.get("authorization", "").replace("Bearer ", "")

        if api_key:
            # Hash API key for privacy
            return f"apikey:{hashlib.sha256(api_key.encode()).hexdigest()[:16]}"

        # Fall back to IP address
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"

        return f"ip:{client_ip}"

    def _get_rate_limit_params(self, request: Request, client_id: str) -> tuple[int, int]:
        """Get rate limit parameters for the request.

        Returns:
            Tuple of (max_requests, window_seconds)
        """
        # API key gets higher limits
        if client_id.startswith("apikey:"):
            return self.api_key_max_requests, self.api_key_window_seconds

        # Default limits for IP-based requests
        return self.default_max_requests, self.default_window_seconds

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Apply rate limiting to request."""
        # Skip rate limiting for health check
        if request.url.path in ["/health", "/metrics"]:
            return await call_next(request)

        client_id = self._get_client_identifier(request)
        max_requests, window_seconds = self._get_rate_limit_params(request, client_id)

        # Check rate limit
        allowed, retry_after = _rate_limiter.check_rate_limit(client_id, max_requests, window_seconds)

        if not allowed:
            log.warning(f"Rate limit exceeded for {client_id}: {request.method} {request.url.path}")
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded", "retry_after": retry_after},
                headers={"Retry-After": str(retry_after), "X-RateLimit-Reset": str(int(time.time() + retry_after))},
            )

        # Add rate limit headers to response
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(max_requests)
        response.headers["X-RateLimit-Window"] = str(window_seconds)

        return response


class APIKeyRotation:
    """API key rotation and validation system.

    Supports:
    - Multiple active API keys
    - Scheduled key rotation
    - Deprecation warnings
    - Key revocation
    """

    def __init__(self):
        self.keys: dict[str, dict[str, Any]] = {}

    def generate_key(self, name: str, expires_days: int = 90) -> str:
        """Generate a new API key.

        Args:
            name: Human-readable name for the key
            expires_days: Days until key expires

        Returns:
            Generated API key (should be shown to user once)
        """
        # Generate cryptographically secure random key
        api_key = f"sh_{secrets.token_urlsafe(32)}"

        # Store key metadata
        expires_at = datetime.now() + timedelta(days=expires_days)
        self.keys[api_key] = {
            "name": name,
            "created_at": datetime.now().isoformat(),
            "expires_at": expires_at.isoformat(),
            "last_used": None,
            "deprecated": False,
            "revoked": False,
        }

        log.info(f"Generated new API key '{name}' (expires in {expires_days} days)")
        return api_key

    def validate_key(self, api_key: str) -> tuple[bool, str]:
        """Validate an API key.

        Args:
            api_key: API key to validate

        Returns:
            Tuple of (valid, message)
        """
        if api_key not in self.keys:
            return False, "Invalid API key"

        key_info = self.keys[api_key]

        # Check if revoked
        if key_info["revoked"]:
            return False, "API key has been revoked"

        # Check if expired
        expires_at = datetime.fromisoformat(key_info["expires_at"])
        if datetime.now() > expires_at:
            return False, "API key has expired"

        # Update last used
        key_info["last_used"] = datetime.now().isoformat()

        # Warning if deprecated
        if key_info["deprecated"]:
            return True, "API key is deprecated. Please rotate to a new key."

        return True, "Valid"

    def deprecate_key(self, api_key: str) -> bool:
        """Mark a key as deprecated (still works but warns users).

        Args:
            api_key: API key to deprecate

        Returns:
            True if key was deprecated
        """
        if api_key in self.keys:
            self.keys[api_key]["deprecated"] = True
            log.info(f"Deprecated API key: {self.keys[api_key]['name']}")
            return True
        return False

    def revoke_key(self, api_key: str) -> bool:
        """Revoke a key immediately (stops working).

        Args:
            api_key: API key to revoke

        Returns:
            True if key was revoked
        """
        if api_key in self.keys:
            self.keys[api_key]["revoked"] = True
            log.info(f"Revoked API key: {self.keys[api_key]['name']}")
            return True
        return False

    def list_keys(self, include_revoked: bool = False) -> list[dict[str, Any]]:
        """List all API keys with metadata.

        Args:
            include_revoked: Include revoked keys in list

        Returns:
            List of key metadata dictionaries
        """
        keys_list = []
        for api_key, info in self.keys.items():
            if not include_revoked and info["revoked"]:
                continue

            keys_list.append(
                {
                    "key_preview": api_key[:10] + "..." + api_key[-4:],
                    "name": info["name"],
                    "created_at": info["created_at"],
                    "expires_at": info["expires_at"],
                    "last_used": info["last_used"],
                    "deprecated": info["deprecated"],
                    "revoked": info["revoked"],
                }
            )

        return keys_list


# Global API key manager
_api_key_manager = APIKeyRotation()


def get_api_key_manager() -> APIKeyRotation:
    """Get global API key manager instance."""
    return _api_key_manager


async def verify_api_key(x_api_key: str = Header(None)) -> str:
    """Dependency to verify API key in requests.

    Args:
        x_api_key: API key from X-Api-Key header

    Returns:
        Valid API key

    Raises:
        HTTPException: If API key is invalid, expired, or revoked
    """
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")

    valid, message = _api_key_manager.validate_key(x_api_key)

    if not valid:
        raise HTTPException(status_code=401, detail=message)

    # Log warning if deprecated
    if "deprecated" in message.lower():
        log.warning(f"Using deprecated API key: {message}")

    return x_api_key
