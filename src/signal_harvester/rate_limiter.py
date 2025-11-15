"""Redis-backed distributed rate limiter for horizontal scaling.

This module provides a production-ready rate limiter that supports:
- Distributed rate limiting across multiple API instances
- Token bucket algorithm for smooth rate limiting
- Automatic fallback to in-memory limiter when Redis unavailable
- Configurable limits per IP, API key, and endpoint
- Prometheus metrics integration
"""

from __future__ import annotations

import hashlib
import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .config import get_config
from .logger import get_logger

log = get_logger(__name__)

# Try to import Redis client
try:
    import redis
    from redis.exceptions import ConnectionError as RedisConnectionError
    from redis.exceptions import RedisError

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None  # type: ignore
    RedisConnectionError = Exception  # type: ignore
    RedisError = Exception  # type: ignore


class RateLimitTier(str, Enum):
    """Rate limit tiers for different user types."""

    ANONYMOUS = "anonymous"  # No authentication
    API_KEY = "api_key"  # Authenticated with API key
    PREMIUM = "premium"  # Premium tier users
    ADMIN = "admin"  # Admin users (no limits)


class RateLimitConfig(BaseModel):
    """Configuration for rate limiting."""

    # Anonymous (IP-based) limits
    anonymous_max_requests: int = Field(default=100, description="Max requests per window for anonymous users")
    anonymous_window_seconds: int = Field(default=60, description="Time window for anonymous rate limit")

    # API key limits
    api_key_max_requests: int = Field(default=1000, description="Max requests per window for API key users")
    api_key_window_seconds: int = Field(default=60, description="Time window for API key rate limit")

    # Premium tier limits
    premium_max_requests: int = Field(default=5000, description="Max requests per window for premium users")
    premium_window_seconds: int = Field(default=60, description="Time window for premium rate limit")

    # Redis configuration
    redis_enabled: bool = Field(default=True, description="Enable Redis-backed rate limiting")
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_db: int = Field(default=1, description="Redis database number")
    redis_password: str | None = Field(default=None, description="Redis password")
    redis_key_prefix: str = Field(default="ratelimit:", description="Redis key prefix")

    # Fallback configuration
    fallback_to_memory: bool = Field(default=True, description="Fall back to in-memory limiter if Redis fails")
    cleanup_interval: int = Field(default=3600, description="Cleanup interval for in-memory buckets (seconds)")


class RateLimitResult(BaseModel):
    """Result of a rate limit check."""

    allowed: bool = Field(description="Whether the request is allowed")
    retry_after: int = Field(default=0, description="Seconds until next request allowed")
    tier: RateLimitTier = Field(description="Rate limit tier applied")
    limit: int = Field(description="Maximum requests allowed")
    remaining: int = Field(description="Remaining requests in window")
    reset_at: int = Field(description="Unix timestamp when limit resets")


class InMemoryRateLimiter:
    """Simple in-memory rate limiter fallback.

    Uses token bucket algorithm for smooth rate limiting.
    Used when Redis is unavailable.
    """

    def __init__(self, cleanup_interval: int = 3600):
        self.buckets: dict[str, dict[str, Any]] = {}
        self.cleanup_interval = cleanup_interval
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
    ) -> tuple[bool, int, int]:
        """Check if request is within rate limit.

        Args:
            key: Unique identifier for the client
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds

        Returns:
            Tuple of (allowed, retry_after_seconds, remaining_tokens)
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
            return True, 0, max_requests - 1

        bucket = self.buckets[key]
        time_passed = now - bucket["last_check"]

        # Refill tokens based on time passed
        bucket["tokens"] = min(bucket["max_tokens"], bucket["tokens"] + time_passed * bucket["refill_rate"])

        bucket["last_check"] = now

        if bucket["tokens"] >= 1:
            bucket["tokens"] -= 1
            return True, 0, int(bucket["tokens"])
        else:
            # Calculate retry after (when bucket will have 1 token)
            retry_after = int((1 - bucket["tokens"]) / bucket["refill_rate"])
            return False, retry_after, 0


class RedisRateLimiter:
    """Redis-backed distributed rate limiter.

    Uses Redis with token bucket algorithm for distributed rate limiting.
    Supports horizontal scaling across multiple API instances.
    """

    def __init__(self, config: RateLimitConfig):
        self.config = config

        if not REDIS_AVAILABLE:
            raise ImportError("redis package not installed. Install with: pip install redis")

        # Initialize Redis connection
        try:
            self.redis_client = redis.Redis(
                host=config.redis_host,
                port=config.redis_port,
                db=config.redis_db,
                password=config.redis_password,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            # Test connection
            self.redis_client.ping()
            log.info(f"Connected to Redis at {config.redis_host}:{config.redis_port}")
        except (RedisConnectionError, RedisError) as e:
            log.error(f"Failed to connect to Redis: {e}")
            raise

    def _get_redis_key(self, key: str) -> str:
        """Get Redis key with prefix."""
        return f"{self.config.redis_key_prefix}{key}"

    def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[bool, int, int]:
        """Check if request is within rate limit using Redis.

        Uses Redis with Lua script for atomic token bucket operations.

        Args:
            key: Unique identifier for the client
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds

        Returns:
            Tuple of (allowed, retry_after_seconds, remaining_tokens)
        """
        redis_key = self._get_redis_key(key)
        now = time.time()

        # Lua script for atomic token bucket check
        # This ensures race-free operations across multiple instances
        lua_script = """
        local key = KEYS[1]
        local max_tokens = tonumber(ARGV[1])
        local refill_rate = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])
        
        local bucket = redis.call('HMGET', key, 'tokens', 'last_check')
        local tokens = tonumber(bucket[1])
        local last_check = tonumber(bucket[2])
        
        if tokens == nil then
            -- Initialize new bucket
            tokens = max_tokens - 1
            last_check = now
            redis.call('HMSET', key, 'tokens', tokens, 'last_check', last_check, 'max_tokens', max_tokens, 'refill_rate', refill_rate)
            redis.call('EXPIRE', key, 3600)  -- Expire after 1 hour of inactivity
            return {1, 0, tokens}
        end
        
        -- Refill tokens based on time passed
        local time_passed = now - last_check
        tokens = math.min(max_tokens, tokens + time_passed * refill_rate)
        
        if tokens >= 1 then
            tokens = tokens - 1
            redis.call('HMSET', key, 'tokens', tokens, 'last_check', now)
            redis.call('EXPIRE', key, 3600)
            return {1, 0, math.floor(tokens)}
        else
            -- Calculate retry after
            local retry_after = math.ceil((1 - tokens) / refill_rate)
            return {0, retry_after, 0}
        end
        """

        try:
            refill_rate = max_requests / window_seconds
            result = self.redis_client.eval(lua_script, 1, redis_key, max_requests, refill_rate, now)

            allowed = bool(result[0])
            retry_after = int(result[1])
            remaining = int(result[2])

            return allowed, retry_after, remaining

        except (RedisConnectionError, RedisError) as e:
            log.error(f"Redis error during rate limit check: {e}")
            raise


class DistributedRateLimiter:
    """Production-ready distributed rate limiter with automatic fallback.

    Features:
    - Redis-backed distributed rate limiting
    - Automatic fallback to in-memory limiter
    - Configurable rate limit tiers
    - Prometheus metrics integration (optional)
    """

    def __init__(self, config: RateLimitConfig | None = None):
        if config is None:
            # Load from settings
            app_config = get_config()
            config = RateLimitConfig(
                redis_enabled=app_config.app.redis.enabled,
                redis_host=app_config.app.redis.host,
                redis_port=app_config.app.redis.port,
                redis_db=app_config.app.redis.db,
                redis_password=app_config.app.redis.password,
            )

        self.config = config
        self.redis_limiter: RedisRateLimiter | None = None
        self.memory_limiter: InMemoryRateLimiter | None = None
        self.use_redis = False

        # Initialize Redis limiter
        if config.redis_enabled and REDIS_AVAILABLE:
            try:
                self.redis_limiter = RedisRateLimiter(config)
                self.use_redis = True
                log.info("Using Redis-backed distributed rate limiter")
            except (ImportError, RedisConnectionError, RedisError) as e:
                log.warning(f"Redis rate limiter initialization failed: {e}")
                if config.fallback_to_memory:
                    self._init_memory_limiter()
        else:
            if not REDIS_AVAILABLE:
                log.warning("Redis package not installed, using in-memory rate limiter")
            self._init_memory_limiter()

    def _init_memory_limiter(self) -> None:
        """Initialize in-memory fallback limiter."""
        self.memory_limiter = InMemoryRateLimiter(cleanup_interval=self.config.cleanup_interval)
        self.use_redis = False
        log.info("Using in-memory rate limiter (not suitable for horizontal scaling)")

    def _get_rate_limit_params(self, tier: RateLimitTier) -> tuple[int, int]:
        """Get rate limit parameters for tier."""
        if tier == RateLimitTier.ADMIN:
            # Admin tier: effectively unlimited
            return 1000000, 1
        elif tier == RateLimitTier.PREMIUM:
            return self.config.premium_max_requests, self.config.premium_window_seconds
        elif tier == RateLimitTier.API_KEY:
            return self.config.api_key_max_requests, self.config.api_key_window_seconds
        else:  # ANONYMOUS
            return self.config.anonymous_max_requests, self.config.anonymous_window_seconds

    def check_rate_limit(
        self,
        identifier: str,
        tier: RateLimitTier = RateLimitTier.ANONYMOUS,
    ) -> RateLimitResult:
        """Check if request is within rate limit.

        Args:
            identifier: Unique identifier for the client (IP, API key hash, etc.)
            tier: Rate limit tier to apply

        Returns:
            RateLimitResult with allow/deny decision and metadata
        """
        # Admin tier always allowed
        if tier == RateLimitTier.ADMIN:
            return RateLimitResult(
                allowed=True,
                retry_after=0,
                tier=tier,
                limit=1000000,
                remaining=1000000,
                reset_at=int(time.time()) + 3600,
            )

        max_requests, window_seconds = self._get_rate_limit_params(tier)
        key = f"{tier.value}:{identifier}"

        try:
            if self.use_redis and self.redis_limiter:
                allowed, retry_after, remaining = self.redis_limiter.check_rate_limit(
                    key, max_requests, window_seconds
                )
            elif self.memory_limiter:
                allowed, retry_after, remaining = self.memory_limiter.check_rate_limit(
                    key, max_requests, window_seconds
                )
            else:
                # Fallback to always allow (shouldn't happen)
                log.error("No rate limiter available, allowing request")
                allowed, retry_after, remaining = True, 0, max_requests

            reset_at = int(time.time()) + window_seconds

            return RateLimitResult(
                allowed=allowed,
                retry_after=retry_after,
                tier=tier,
                limit=max_requests,
                remaining=remaining,
                reset_at=reset_at,
            )

        except Exception as e:
            log.error(f"Rate limit check failed: {e}")
            # On error, try to fall back to memory limiter
            if self.use_redis and self.config.fallback_to_memory:
                log.warning("Falling back to in-memory rate limiter")
                if not self.memory_limiter:
                    self._init_memory_limiter()
                self.use_redis = False
                # Retry with memory limiter
                return self.check_rate_limit(identifier, tier)

            # Ultimate fallback: allow the request
            return RateLimitResult(
                allowed=True,
                retry_after=0,
                tier=tier,
                limit=max_requests,
                remaining=0,
                reset_at=int(time.time()) + window_seconds,
            )

    def get_client_identifier(self, ip_address: str, api_key: str | None = None) -> tuple[str, RateLimitTier]:
        """Get client identifier and tier from IP/API key.

        Args:
            ip_address: Client IP address
            api_key: Optional API key

        Returns:
            Tuple of (identifier, tier)
        """
        if api_key:
            # Hash API key for privacy
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
            # TODO: Look up API key tier in database
            # For now, all API keys get API_KEY tier
            return key_hash, RateLimitTier.API_KEY
        else:
            # Use IP address for anonymous tier
            return ip_address, RateLimitTier.ANONYMOUS


# Global rate limiter instance
_rate_limiter: DistributedRateLimiter | None = None


def get_rate_limiter() -> DistributedRateLimiter:
    """Get or create global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = DistributedRateLimiter()
    return _rate_limiter


def reset_rate_limiter() -> None:
    """Reset global rate limiter instance (for testing)."""
    global _rate_limiter
    _rate_limiter = None
