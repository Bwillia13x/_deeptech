"""Redis caching layer for API responses.

This module provides a caching decorator for expensive API operations:
- Discovery results (TTL 1h)
- Topic trends (TTL 1h)
- Entity profiles (TTL 24h)

Extends the existing Redis infrastructure from embeddings.py.
"""

from __future__ import annotations

import hashlib
import json
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional, TypeVar

from .config import Settings, load_settings
from .logger import get_logger

log = get_logger(__name__)

# Lazy-loaded Redis client
_redis_client: Optional[Any] = None

# In-memory fallback cache when Redis unavailable
_memory_cache: Dict[str, tuple[Any, float]] = {}  # key -> (value, timestamp)

# Cache statistics
_cache_stats = {
    "hits": 0,
    "misses": 0,
    "redis_hits": 0,
    "memory_hits": 0,
    "redis_errors": 0,
    "evictions": 0,
    "cache_sets": 0,
}

# Type variable for generic caching
T = TypeVar("T")


class CacheConfig:
    """Configuration for response caching."""
    
    def __init__(self, settings: Settings | None = None):
        settings = settings or load_settings()
        cache_config = getattr(settings.app, 'cache', {})
        if hasattr(cache_config, '__dict__'):
            cache_config = cache_config.__dict__
        
        # Redis configuration
        self.redis_enabled = cache_config.get("redis_enabled", False)
        self.redis_host = cache_config.get("redis_host", "localhost")
        self.redis_port = cache_config.get("redis_port", 6379)
        self.redis_db = cache_config.get("redis_db", 1)  # Different DB than embeddings
        self.redis_password = cache_config.get("redis_password", None)
        
        # Cache TTL configuration (in seconds)
        self.discovery_ttl = cache_config.get("discovery_ttl", 3600)  # 1 hour
        self.topic_ttl = cache_config.get("topic_ttl", 3600)  # 1 hour
        self.entity_ttl = cache_config.get("entity_ttl", 86400)  # 24 hours
        
        # Memory cache configuration
        self.max_memory_cache_size = cache_config.get("max_memory_cache_size", 1000)
        self.memory_cache_enabled = cache_config.get("memory_cache_enabled", True)


try:
    _default_cache_config = CacheConfig(Settings())
except Exception as exc:  # pragma: no cover - allows fallback if settings unavailable
    log.warning("Failed to initialize cache config from settings: %s", exc)
    _default_cache_config = CacheConfig(Settings())

_cache_config: CacheConfig = _default_cache_config


def _int_config_value(config: CacheConfig, name: str, default: int) -> int:
    value = getattr(config, name, default)
    return value if isinstance(value, int) else default


def _bool_config_value(config: CacheConfig, name: str, default: bool) -> bool:
    value = getattr(config, name, default)
    return value if isinstance(value, bool) else default


def get_redis_client(config: CacheConfig) -> Optional[Any]:
    """Get or create Redis client (lazy-loaded)."""
    global _redis_client
    
    if not config.redis_enabled:
        return None
    
    if _redis_client is None:
        try:
            import redis  # type: ignore[import-untyped]
            _redis_client = redis.Redis(
                host=config.redis_host,
                port=config.redis_port,
                db=config.redis_db,
                password=config.redis_password,
                decode_responses=True,  # We store JSON strings
            )
            # Test connection
            _redis_client.ping()
            log.info(
                "Redis cache connection established: "
                f"{config.redis_host}:{config.redis_port} (db={config.redis_db})"
            )
        except ImportError:
            log.warning("redis package not available, using in-memory cache only")
            _redis_client = None
        except Exception as e:
            log.error(f"Failed to connect to Redis cache: {e}, using in-memory cache only")
            _cache_stats["redis_errors"] += 1
            _redis_client = None
    
    return _redis_client


def _generate_cache_key(*args: Any, prefix: str = "cache", **kwargs: Any) -> str:
    """Generate cache key from function arguments."""
    func_args = args
    func_kwargs = kwargs
    if (
        len(args) == 3
        and not kwargs
        and isinstance(args[0], str)
        and isinstance(args[1], (tuple, list))
        and isinstance(args[2], dict)
    ):
        prefix, func_args, func_kwargs = args[0], args[1], args[2]
    # Create deterministic string from args and kwargs
    key_data = {
        "args": [str(arg) for arg in func_args],
        "kwargs": {k: str(v) for k, v in sorted(func_kwargs.items())},
    }
    key_str = json.dumps(key_data, sort_keys=True)
    key_hash = hashlib.md5(key_str.encode()).hexdigest()[:16]
    return f"{prefix}:{key_hash}"


def _get_from_cache(
    key: str,
    config_or_ttl: CacheConfig | int | None = None,
) -> Optional[Any]:
    """Get value from cache (Redis first, then memory fallback)."""
    if isinstance(config_or_ttl, int):
        ttl_override = config_or_ttl
        config = _cache_config
    else:
        ttl_override = None
        config = config_or_ttl or _cache_config

    redis_client = get_redis_client(config)
    
    # Try Redis first
    if redis_client is not None:
        try:
            value = redis_client.get(key)
            if value is not None:
                _cache_stats["hits"] += 1
                _cache_stats["redis_hits"] += 1
                return json.loads(value)
        except Exception as e:
            log.error(f"Redis get error: {e}")
            _cache_stats["redis_errors"] += 1
    
    # Fallback to memory cache
    memory_cache_enabled = _bool_config_value(
        config, "memory_cache_enabled", _default_cache_config.memory_cache_enabled
    )
    if memory_cache_enabled and key in _memory_cache:
        cached_value, cached_time = _memory_cache[key]
        # Simple TTL check (use discovery_ttl as default)
        discovery_ttl = _int_config_value(
            config, "discovery_ttl", _default_cache_config.discovery_ttl
        )
        if ttl_override is not None:
            discovery_ttl = ttl_override
        if time.time() - cached_time < discovery_ttl:
            _cache_stats["hits"] += 1
            _cache_stats["memory_hits"] += 1
            return cached_value
        else:
            # Expired, remove from memory
            del _memory_cache[key]
    
    _cache_stats["misses"] += 1
    return None


def _set_in_cache(
    key: str,
    value: Any,
    ttl: int,
    config: CacheConfig | None = None,
    raw_value: Any | None = None,
) -> None:
    """Set value in cache (Redis and memory)."""
    config = config or _cache_config
    _cache_stats["cache_sets"] += 1
    redis_client = get_redis_client(config)
    
    # Try Redis first
    if redis_client is not None:
        try:
            redis_client.setex(key, ttl, json.dumps(value))
        except Exception as e:
            log.error(f"Redis set error: {e}")
            _cache_stats["redis_errors"] += 1
    
    # Also set in memory cache as fallback
    memory_cache_enabled = _bool_config_value(
        config, "memory_cache_enabled", _default_cache_config.memory_cache_enabled
    )
    if memory_cache_enabled:
        # Evict oldest entries if cache is full
        max_memory_cache_size = _int_config_value(
            config, "max_memory_cache_size", _default_cache_config.max_memory_cache_size
        )
        if len(_memory_cache) >= max_memory_cache_size:
            oldest_key = min(_memory_cache.items(), key=lambda x: x[1][1])[0]
            del _memory_cache[oldest_key]
            _cache_stats["evictions"] += 1
        
        memory_value = raw_value if raw_value is not None else value
        _memory_cache[key] = (memory_value, time.time())


def cached(
    prefix: str = "cache",
    ttl: Optional[int] = None,
    ttl_key: str = "discovery_ttl",
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator to cache function results in Redis with TTL.
    
    Args:
        prefix: Cache key prefix (e.g., 'discovery', 'topic', 'entity')
        ttl: Time-to-live in seconds (if None, uses config based on ttl_key)
        ttl_key: Config key to use for TTL (discovery_ttl, topic_ttl, entity_ttl)
    
    Example:
        @cached(prefix='discovery', ttl_key='discovery_ttl')
        def get_discoveries(min_score: float, limit: int) -> List[Dict]:
            # Expensive database query
            return results
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            # Get settings and config
            config = _cache_config or CacheConfig(Settings())
            
            # Generate cache key from function args
            cache_key = _generate_cache_key(*args, prefix=prefix, **kwargs)
            
            # Try to get from cache
            cached_value = _get_from_cache(cache_key, config)
            if cached_value is not None:
                log.debug(f"Cache hit for {prefix}: {cache_key}")
                return cached_value  # type: ignore[return-value]
            
            # Cache miss - compute value
            log.debug(f"Cache miss for {prefix}: {cache_key}")
            result = func(*args, **kwargs)
            
            # Determine TTL
            default_ttl = getattr(_default_cache_config, ttl_key, 3600)
            config_ttl = _int_config_value(config, ttl_key, default_ttl)
            actual_ttl = ttl if ttl is not None else config_ttl
            
            # Store in cache
            # Convert Pydantic models to dicts for JSON serialization
            if hasattr(result, '__iter__') and not isinstance(result, (str, bytes)):
                # List of Pydantic models
                try:
                    cache_value = [item.model_dump() if hasattr(item, 'model_dump') else item for item in result]  # type: ignore[union-attr]
                except (TypeError, AttributeError):
                    cache_value = result
            elif hasattr(result, 'model_dump'):
                # Single Pydantic model
                cache_value = result.model_dump()
            else:
                cache_value = result
            
            _set_in_cache(cache_key, cache_value, actual_ttl, config, raw_value=result)
            
            return result
        
        return wrapper
    
    return decorator


def invalidate_cache(pattern: str = "*") -> int:
    """Invalidate cache entries matching pattern.
    
    Args:
        pattern: Redis key pattern (e.g., 'discovery:*', 'topic:*', '*')
    
    Returns:
        Number of keys deleted
    """
    config = _cache_config or CacheConfig(Settings())
    redis_client = get_redis_client(config)
    
    deleted = 0
    
    # Invalidate Redis cache
    if redis_client is not None:
        try:
            keys = redis_client.keys(pattern)
            if keys:
                deleted = redis_client.delete(*keys)
                log.info(f"Invalidated {deleted} Redis cache entries matching '{pattern}'")
        except Exception as e:
            log.error(f"Redis invalidation error: {e}")
            _cache_stats["redis_errors"] += 1
    
    # Invalidate memory cache
    memory_cache_enabled = _bool_config_value(
        config, "memory_cache_enabled", _default_cache_config.memory_cache_enabled
    )
    if memory_cache_enabled:
        matching_keys = [k for k in _memory_cache.keys() if _matches_pattern(k, pattern)]
        for key in matching_keys:
            del _memory_cache[key]
        deleted += len(matching_keys)
    
    return deleted


def _matches_pattern(key: str, pattern: str) -> bool:
    """Simple pattern matching for cache invalidation."""
    if pattern == "*":
        return True
    if "*" not in pattern:
        return key == pattern
    # Simple prefix matching
    if pattern.endswith("*"):
        return key.startswith(pattern[:-1])
    return False


def get_cache_stats() -> Dict[str, Any]:
    """Get cache performance statistics.
    
    Returns:
        Dictionary with cache hit/miss rates and other metrics
    """
    total_requests = _cache_stats["hits"] + _cache_stats["misses"]
    hit_rate = _cache_stats["hits"] / total_requests if total_requests > 0 else 0.0
    
    return {
        "total_requests": total_requests,
        "hits": _cache_stats["hits"],
        "misses": _cache_stats["misses"],
        "hit_rate": hit_rate,
        "redis_hits": _cache_stats["redis_hits"],
        "memory_hits": _cache_stats["memory_hits"],
        "redis_errors": _cache_stats["redis_errors"],
        "evictions": _cache_stats["evictions"],
        "cache_sets": _cache_stats["cache_sets"],
        "memory_cache_size": len(_memory_cache),
    }


def clear_cache_stats() -> None:
    """Reset cache statistics counters."""
    _cache_stats.clear()
    _cache_stats.update(
        {
            "hits": 0,
            "misses": 0,
            "redis_hits": 0,
            "memory_hits": 0,
            "redis_errors": 0,
            "evictions": 0,
            "cache_sets": 0,
        }
    )
