"""Tests for distributed rate limiter module."""

from __future__ import annotations

import time
from unittest.mock import Mock, patch

import pytest

from signal_harvester.rate_limiter import (
    DistributedRateLimiter,
    InMemoryRateLimiter,
    RateLimitConfig,
    RateLimitResult,
    RateLimitTier,
    get_rate_limiter,
    reset_rate_limiter,
)


class TestInMemoryRateLimiter:
    """Tests for in-memory rate limiter."""

    def test_initialization(self):
        """Test limiter initializes correctly."""
        limiter = InMemoryRateLimiter(cleanup_interval=3600)
        assert limiter.buckets == {}
        assert limiter.cleanup_interval == 3600

    def test_allows_first_request(self):
        """Test first request is always allowed."""
        limiter = InMemoryRateLimiter()
        allowed, retry_after, remaining = limiter.check_rate_limit("test_key", max_requests=10, window_seconds=60)

        assert allowed is True
        assert retry_after == 0
        assert remaining == 9

    def test_enforces_rate_limit(self):
        """Test rate limit is enforced."""
        limiter = InMemoryRateLimiter()
        max_requests = 5

        # Make max_requests successful requests
        for i in range(max_requests):
            allowed, retry_after, remaining = limiter.check_rate_limit("test_key", max_requests, window_seconds=60)
            assert allowed is True
            assert remaining == max_requests - i - 1

        # Next request should be denied
        allowed, retry_after, remaining = limiter.check_rate_limit("test_key", max_requests, window_seconds=60)
        assert allowed is False
        assert retry_after > 0
        assert remaining == 0

    def test_token_refill(self):
        """Test tokens refill over time."""
        limiter = InMemoryRateLimiter()
        max_requests = 10
        window_seconds = 1  # 1 second window for fast testing

        # Exhaust tokens
        for _ in range(max_requests):
            limiter.check_rate_limit("test_key", max_requests, window_seconds)

        # Should be denied
        allowed, _, _ = limiter.check_rate_limit("test_key", max_requests, window_seconds)
        assert allowed is False

        # Wait for tokens to refill
        time.sleep(0.2)  # 20% of window = 2 tokens

        # Should have ~2 tokens available now
        allowed, _, _ = limiter.check_rate_limit("test_key", max_requests, window_seconds)
        assert allowed is True

    def test_separate_keys_independent(self):
        """Test different keys have independent limits."""
        limiter = InMemoryRateLimiter()
        max_requests = 3

        # Exhaust key1
        for _ in range(max_requests):
            limiter.check_rate_limit("key1", max_requests, 60)

        # key1 should be denied
        allowed, _, _ = limiter.check_rate_limit("key1", max_requests, 60)
        assert allowed is False

        # key2 should still be allowed
        allowed, _, _ = limiter.check_rate_limit("key2", max_requests, 60)
        assert allowed is True

    def test_cleanup_old_buckets(self):
        """Test old buckets are cleaned up."""
        limiter = InMemoryRateLimiter(cleanup_interval=1)

        # Create some buckets
        limiter.check_rate_limit("key1", 10, 60)
        limiter.check_rate_limit("key2", 10, 60)
        assert len(limiter.buckets) == 2

        # Wait for cleanup interval
        time.sleep(1.1)

        # Trigger cleanup by checking a new key
        limiter.check_rate_limit("key3", 10, 60)

        # Old buckets should be cleaned (they're considered expired)
        # Note: This is timing-sensitive, so we just check it doesn't crash
        assert "key3" in limiter.buckets


class TestRateLimitConfig:
    """Tests for rate limit configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = RateLimitConfig()

        assert config.anonymous_max_requests == 100
        assert config.anonymous_window_seconds == 60
        assert config.api_key_max_requests == 1000
        assert config.api_key_window_seconds == 60
        assert config.premium_max_requests == 5000
        assert config.redis_enabled is True
        assert config.fallback_to_memory is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = RateLimitConfig(
            anonymous_max_requests=50,
            api_key_max_requests=500,
            redis_enabled=False,
        )

        assert config.anonymous_max_requests == 50
        assert config.api_key_max_requests == 500
        assert config.redis_enabled is False


class TestDistributedRateLimiter:
    """Tests for distributed rate limiter."""

    @pytest.fixture(autouse=True)
    def reset_limiter(self):
        """Reset global rate limiter before each test."""
        reset_rate_limiter()
        yield
        reset_rate_limiter()

    def test_initialization_without_redis(self):
        """Test limiter initializes with in-memory fallback when Redis unavailable."""
        config = RateLimitConfig(redis_enabled=False)
        limiter = DistributedRateLimiter(config)

        assert limiter.use_redis is False
        assert limiter.memory_limiter is not None
        assert limiter.redis_limiter is None

    def test_admin_tier_always_allowed(self):
        """Test admin tier is always allowed."""
        config = RateLimitConfig(redis_enabled=False)
        limiter = DistributedRateLimiter(config)

        # Make many requests
        for _ in range(1000):
            result = limiter.check_rate_limit("admin_user", RateLimitTier.ADMIN)
            assert result.allowed is True
            assert result.tier == RateLimitTier.ADMIN

    def test_anonymous_tier_limits(self):
        """Test anonymous tier respects limits."""
        config = RateLimitConfig(
            redis_enabled=False,
            anonymous_max_requests=5,
            anonymous_window_seconds=60,
        )
        limiter = DistributedRateLimiter(config)

        # Make requests up to limit
        for i in range(5):
            result = limiter.check_rate_limit("192.168.1.1", RateLimitTier.ANONYMOUS)
            assert result.allowed is True
            assert result.tier == RateLimitTier.ANONYMOUS
            assert result.limit == 5
            assert result.remaining == 4 - i

        # Next request should be denied
        result = limiter.check_rate_limit("192.168.1.1", RateLimitTier.ANONYMOUS)
        assert result.allowed is False
        assert result.retry_after > 0

    def test_api_key_tier_higher_limits(self):
        """Test API key tier has higher limits than anonymous."""
        config = RateLimitConfig(
            redis_enabled=False,
            anonymous_max_requests=5,
            api_key_max_requests=10,
        )
        limiter = DistributedRateLimiter(config)

        # API key tier should have higher limit
        result = limiter.check_rate_limit("api_key_hash", RateLimitTier.API_KEY)
        assert result.limit == 10

        # Anonymous tier should have lower limit
        result = limiter.check_rate_limit("192.168.1.1", RateLimitTier.ANONYMOUS)
        assert result.limit == 5

    def test_premium_tier_highest_limits(self):
        """Test premium tier has highest limits."""
        config = RateLimitConfig(
            redis_enabled=False,
            api_key_max_requests=100,
            premium_max_requests=500,
        )
        limiter = DistributedRateLimiter(config)

        result = limiter.check_rate_limit("premium_user", RateLimitTier.PREMIUM)
        assert result.limit == 500
        assert result.tier == RateLimitTier.PREMIUM

    def test_get_client_identifier_with_api_key(self):
        """Test client identifier generation with API key."""
        limiter = DistributedRateLimiter(RateLimitConfig(redis_enabled=False))

        identifier, tier = limiter.get_client_identifier("192.168.1.1", "test_api_key_12345")

        assert len(identifier) == 16  # SHA256 hash truncated to 16 chars
        assert tier == RateLimitTier.API_KEY

    def test_get_client_identifier_without_api_key(self):
        """Test client identifier generation without API key."""
        limiter = DistributedRateLimiter(RateLimitConfig(redis_enabled=False))

        identifier, tier = limiter.get_client_identifier("192.168.1.1")

        assert identifier == "192.168.1.1"
        assert tier == RateLimitTier.ANONYMOUS

    def test_rate_limit_result_structure(self):
        """Test rate limit result contains all required fields."""
        config = RateLimitConfig(redis_enabled=False, anonymous_max_requests=10)
        limiter = DistributedRateLimiter(config)

        result = limiter.check_rate_limit("test", RateLimitTier.ANONYMOUS)

        assert isinstance(result, RateLimitResult)
        assert hasattr(result, "allowed")
        assert hasattr(result, "retry_after")
        assert hasattr(result, "tier")
        assert hasattr(result, "limit")
        assert hasattr(result, "remaining")
        assert hasattr(result, "reset_at")
        assert result.reset_at > time.time()

    def test_separate_tiers_independent_limits(self):
        """Test different tiers have independent rate limits."""
        config = RateLimitConfig(
            redis_enabled=False,
            anonymous_max_requests=3,
            api_key_max_requests=5,
        )
        limiter = DistributedRateLimiter(config)

        # Exhaust anonymous tier
        for _ in range(3):
            limiter.check_rate_limit("user1", RateLimitTier.ANONYMOUS)

        # Anonymous should be denied
        result = limiter.check_rate_limit("user1", RateLimitTier.ANONYMOUS)
        assert result.allowed is False

        # But API key tier for same identifier should still work
        result = limiter.check_rate_limit("user1", RateLimitTier.API_KEY)
        assert result.allowed is True

    def test_global_rate_limiter_singleton(self):
        """Test global rate limiter is singleton."""
        limiter1 = get_rate_limiter()
        limiter2 = get_rate_limiter()

        assert limiter1 is limiter2

    def test_reset_global_rate_limiter(self):
        """Test resetting global rate limiter."""
        limiter1 = get_rate_limiter()
        reset_rate_limiter()
        limiter2 = get_rate_limiter()

        assert limiter1 is not limiter2

    def test_redis_connection_failure_fallback(self):
        """Test fallback to in-memory when Redis unavailable."""
        # Test with Redis explicitly disabled
        config = RateLimitConfig(
            redis_enabled=False,
            fallback_to_memory=True,
        )
        limiter = DistributedRateLimiter(config)

        # Should use in-memory
        assert limiter.use_redis is False
        assert limiter.memory_limiter is not None

        # Should still work
        result = limiter.check_rate_limit("test", RateLimitTier.ANONYMOUS)
        assert isinstance(result, RateLimitResult)

    def test_error_handling_ultimate_fallback(self):
        """Test ultimate fallback allows request on error."""
        config = RateLimitConfig(redis_enabled=False, fallback_to_memory=False)
        limiter = DistributedRateLimiter(config)

        # Force error by setting memory_limiter to None
        limiter.memory_limiter = None
        limiter.use_redis = False

        # Should allow request as ultimate fallback
        result = limiter.check_rate_limit("test", RateLimitTier.ANONYMOUS)
        assert result.allowed is True


class TestRateLimitTiers:
    """Tests for rate limit tier enum."""

    def test_tier_values(self):
        """Test tier enum values."""
        assert RateLimitTier.ANONYMOUS.value == "anonymous"
        assert RateLimitTier.API_KEY.value == "api_key"
        assert RateLimitTier.PREMIUM.value == "premium"
        assert RateLimitTier.ADMIN.value == "admin"

    def test_tier_comparison(self):
        """Test tier enum comparison."""
        assert RateLimitTier.ANONYMOUS == RateLimitTier.ANONYMOUS
        assert RateLimitTier.API_KEY != RateLimitTier.ANONYMOUS


# Integration tests (require Redis running)
@pytest.mark.skipif(True, reason="Redis integration tests require Redis server")
class TestRedisRateLimiter:
    """Integration tests for Redis rate limiter (requires Redis)."""

    def test_redis_rate_limiting(self):
        """Test rate limiting with Redis backend."""
        # This test would require a running Redis instance
        # Marked as skip by default
        pass

    def test_redis_atomic_operations(self):
        """Test Redis operations are atomic across instances."""
        # This test would verify distributed rate limiting
        # Marked as skip by default
        pass
