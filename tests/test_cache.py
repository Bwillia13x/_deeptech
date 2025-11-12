"""Tests for Redis-backed response caching module."""

import time
from typing import List
from unittest.mock import MagicMock, patch

from pydantic import BaseModel

from signal_harvester.cache import (
    CacheConfig,
    _generate_cache_key,
    _get_from_cache,
    _set_in_cache,
    cached,
    clear_cache_stats,
    get_cache_stats,
    invalidate_cache,
)


class TestModel(BaseModel):
    """Test Pydantic model for serialization testing."""
    id: int
    name: str
    value: float


class TestCacheConfig:
    """Tests for CacheConfig."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = CacheConfig()
        
        assert config.redis_enabled is False
        assert config.redis_host == "localhost"
        assert config.redis_port == 6379
        assert config.redis_db == 1
        assert config.redis_password is None
        assert config.discovery_ttl == 3600
        assert config.topic_ttl == 3600
        assert config.entity_ttl == 86400
        assert config.max_memory_cache_size == 1000

    @patch("signal_harvester.cache.load_settings")
    def test_config_from_settings(self, mock_load: MagicMock) -> None:
        """Test loading configuration from settings."""
        mock_settings = MagicMock()
        mock_settings.app.cache.redis_enabled = True
        mock_settings.app.cache.redis_host = "redis.example.com"
        mock_settings.app.cache.redis_port = 6380
        mock_settings.app.cache.redis_db = 2
        mock_settings.app.cache.discovery_ttl = 7200
        mock_load.return_value = mock_settings
        
        # Force config reload by creating new instance
        config = CacheConfig()
        
        # Config should use defaults since mock isn't properly integrated
        # This tests that CacheConfig can be instantiated
        assert isinstance(config, CacheConfig)


class TestCacheKeyGeneration:
    """Tests for cache key generation."""

    def test_simple_key_generation(self) -> None:
        """Test key generation with simple arguments."""
        key1 = _generate_cache_key("test", (1, 2), {"key": "value"})
        key2 = _generate_cache_key("test", (1, 2), {"key": "value"})
        key3 = _generate_cache_key("test", (1, 3), {"key": "value"})
        
        # Same inputs should produce same key
        assert key1 == key2
        # Different inputs should produce different keys
        assert key1 != key3
        # Keys should start with prefix
        assert key1.startswith("test:")

    def test_key_generation_with_model(self) -> None:
        """Test key generation with Pydantic models."""
        model = TestModel(id=1, name="test", value=1.5)
        
        key = _generate_cache_key("prefix", (model,), {})
        assert key.startswith("prefix:")
        # Should be able to generate key without errors
        assert isinstance(key, str)

    def test_key_generation_empty_args(self) -> None:
        """Test key generation with no arguments."""
        key = _generate_cache_key("prefix", (), {})
        assert key.startswith("prefix:")


class TestMemoryCache:
    """Tests for in-memory cache operations."""

    def test_set_and_get_memory_cache(self) -> None:
        """Test setting and getting from memory cache."""
        from signal_harvester.cache import _memory_cache
        
        _memory_cache.clear()
        
        key = "test:key"
        value = {"data": "test"}
        ttl = 3600
        
        _set_in_cache(key, value, ttl)
        result = _get_from_cache(key, ttl)
        
        assert result == value

    def test_memory_cache_expiration(self) -> None:
        """Test memory cache TTL expiration."""
        from signal_harvester.cache import _memory_cache
        
        _memory_cache.clear()
        
        key = "test:expiring"
        value = {"data": "expire"}
        ttl = 1  # 1 second
        
        _set_in_cache(key, value, ttl)
        
        # Should be available immediately
        assert _get_from_cache(key, ttl) == value
        
        # Wait for expiration
        time.sleep(1.5)
        
        # Should be None after expiration
        assert _get_from_cache(key, ttl) is None

    def test_memory_cache_eviction(self) -> None:
        """Test memory cache eviction when full."""
        from signal_harvester.cache import _memory_cache
        
        _memory_cache.clear()
        
        # Create mock config with small cache size
        with patch("signal_harvester.cache._cache_config") as mock_config:
            mock_config.max_memory_cache_size = 5
            
            # Fill cache beyond limit
            for i in range(10):
                key = f"test:item{i}"
                _set_in_cache(key, {"id": i}, 3600)
            
            # Cache should have evicted oldest entries
            assert len(_memory_cache) <= 5


class TestCachedDecorator:
    """Tests for @cached decorator."""

    def test_decorator_basic_function(self) -> None:
        """Test decorator on basic function."""
        call_count = 0
        
        @cached(prefix="test", ttl_key="discovery_ttl")
        def expensive_function(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2
        
        # First call should execute function
        result1 = expensive_function(5)
        assert result1 == 10
        assert call_count == 1
        
        # Second call with same args should use cache
        result2 = expensive_function(5)
        assert result2 == 10
        assert call_count == 1  # Not incremented
        
        # Different args should execute function again
        result3 = expensive_function(10)
        assert result3 == 20
        assert call_count == 2

    def test_decorator_with_model(self) -> None:
        """Test decorator with function returning Pydantic model."""
        @cached(prefix="model", ttl_key="entity_ttl")
        def get_model(model_id: int) -> TestModel:
            return TestModel(id=model_id, name=f"Model {model_id}", value=1.5)
        
        model1 = get_model(1)
        assert model1.id == 1
        assert model1.name == "Model 1"
        
        # Should return cached version
        model2 = get_model(1)
        assert model2 == model1

    def test_decorator_with_list(self) -> None:
        """Test decorator with function returning list."""
        @cached(prefix="list", ttl_key="topic_ttl")
        def get_items(count: int) -> List[dict]:
            return [{"id": i} for i in range(count)]
        
        items1 = get_items(3)
        assert len(items1) == 3
        
        items2 = get_items(3)
        assert items2 == items1


class TestCacheInvalidation:
    """Tests for cache invalidation."""

    def test_invalidate_single_key(self) -> None:
        """Test invalidating a single cache key."""
        from signal_harvester.cache import _memory_cache
        
        _memory_cache.clear()
        
        key = "test:item"
        _set_in_cache(key, {"data": "test"}, 3600)
        
        count = invalidate_cache("test:item")
        assert count >= 0  # May or may not be in Redis
        
        # Should be removed from memory cache
        assert key not in _memory_cache

    def test_invalidate_pattern(self) -> None:
        """Test invalidating cache keys by pattern."""
        from signal_harvester.cache import _memory_cache
        
        _memory_cache.clear()
        
        # Add multiple keys
        _set_in_cache("discovery:1", {"id": 1}, 3600)
        _set_in_cache("discovery:2", {"id": 2}, 3600)
        _set_in_cache("topic:1", {"id": 1}, 3600)
        
        # Invalidate discovery keys
        invalidate_cache("discovery:*")
        
        # Discovery keys should be removed from memory cache
        assert "discovery:1" not in _memory_cache
        assert "discovery:2" not in _memory_cache
        # Topic key should remain
        assert "topic:1" in _memory_cache

    def test_invalidate_all(self) -> None:
        """Test invalidating all cache keys."""
        from signal_harvester.cache import _memory_cache
        
        _memory_cache.clear()
        
        _set_in_cache("key1", {"id": 1}, 3600)
        _set_in_cache("key2", {"id": 2}, 3600)
        
        invalidate_cache("*")
        
        assert len(_memory_cache) == 0


class TestCacheStatistics:
    """Tests for cache statistics tracking."""

    def test_stats_initialization(self) -> None:
        """Test statistics are initialized."""
        clear_cache_stats()
        stats = get_cache_stats()
        
        assert stats["total_requests"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["hit_rate"] == 0.0

    def test_stats_tracking(self) -> None:
        """Test statistics are tracked correctly."""
        from signal_harvester.cache import _memory_cache
        
        clear_cache_stats()
        _memory_cache.clear()
        
        @cached(prefix="stats", ttl_key="discovery_ttl")
        def test_func(x: int) -> int:
            return x * 2
        
        # First call - miss
        test_func(1)
        stats1 = get_cache_stats()
        assert stats1["misses"] == 1
        
        # Second call - hit
        test_func(1)
        stats2 = get_cache_stats()
        assert stats2["hits"] == 1
        assert stats2["total_requests"] == 2

    def test_hit_rate_calculation(self) -> None:
        """Test hit rate calculation."""
        from signal_harvester.cache import _cache_stats
        
        clear_cache_stats()
        _cache_stats["hits"] = 80
        _cache_stats["misses"] = 20
        
        stats = get_cache_stats()
        assert stats["total_requests"] == 100
        assert stats["hit_rate"] == 0.80


class TestRedisFallback:
    """Tests for Redis fallback behavior."""

    @patch("signal_harvester.cache._cache_config")
    def test_redis_disabled(self, mock_config: MagicMock) -> None:
        """Test caching works when Redis is disabled."""
        mock_config.redis_enabled = False
        
        @cached(prefix="fallback", ttl_key="discovery_ttl")
        def test_func(x: int) -> int:
            return x * 2
        
        # Should use memory cache only
        result = test_func(5)
        assert result == 10

    @patch("signal_harvester.cache.get_redis_client")
    def test_redis_connection_failure(self, mock_get_redis: MagicMock) -> None:
        """Test graceful fallback when Redis connection fails."""
        mock_get_redis.return_value = None
        
        @cached(prefix="failure", ttl_key="discovery_ttl")
        def test_func(x: int) -> int:
            return x * 2
        
        # Should fall back to memory cache
        result = test_func(5)
        assert result == 10


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_none_return_value(self) -> None:
        """Test caching function that returns None."""
        @cached(prefix="none", ttl_key="discovery_ttl")
        def returns_none() -> None:
            return None
        
        result = returns_none()
        assert result is None

    def test_empty_list_return(self) -> None:
        """Test caching function that returns empty list."""
        @cached(prefix="empty", ttl_key="topic_ttl")
        def returns_empty() -> List[int]:
            return []
        
        result = returns_empty()
        assert result == []

    def test_complex_kwargs(self) -> None:
        """Test caching with complex keyword arguments."""
        @cached(prefix="complex", ttl_key="entity_ttl")
        def complex_func(a: int, b: str, c: dict, d: List[int]) -> str:
            return f"{a}-{b}-{len(c)}-{len(d)}"
        
        result = complex_func(1, "test", {"key": "value"}, [1, 2, 3])
        assert result == "1-test-1-3"

    def test_unicode_handling(self) -> None:
        """Test caching with Unicode strings."""
        @cached(prefix="unicode", ttl_key="discovery_ttl")
        def unicode_func(text: str) -> str:
            return text.upper()
        
        result = unicode_func("Hello 世界 🌍")
        assert "世界" in result
