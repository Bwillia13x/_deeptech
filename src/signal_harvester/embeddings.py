"""Unified embedding service with Redis-backed caching and refresh pipeline.

This module replaces the scattered in-memory embedding caches across:
- discovery_scoring.py (_embedding_cache)
- identity_resolution.py (_name_embedding_cache, _affiliation_embedding_cache)
- topic_evolution.py (_topic_embedding_cache)

Features:
- Redis-backed persistent caching (fallback to in-memory if Redis unavailable)
- Automatic cache invalidation with configurable TTL
- Batch embedding computation for performance
- Async refresh pipeline for stale embeddings
- Metrics and monitoring hooks
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .config import Settings
from .logger import get_logger

log = get_logger(__name__)

# Lazy-loaded dependencies
_sentence_model = None
_redis_client: Optional[Any] = None

# In-memory fallback cache when Redis is unavailable
_memory_cache: Dict[str, Tuple[np.ndarray, float]] = {}  # key -> (embedding, timestamp)

# Cache statistics
_cache_stats = {
    "hits": 0,
    "misses": 0,
    "redis_hits": 0,
    "memory_hits": 0,
    "redis_errors": 0,
    "embeddings_computed": 0,
    "batch_operations": 0,
}


class EmbeddingConfig:
    """Configuration for embedding service."""
    
    def __init__(self, settings: Settings):
        embedding_config = getattr(settings.app, 'embeddings', {})
        if hasattr(embedding_config, '__dict__'):
            embedding_config = embedding_config.__dict__
        
        # Redis configuration
        self.redis_enabled = embedding_config.get("redis_enabled", False)
        self.redis_host = embedding_config.get("redis_host", "localhost")
        self.redis_port = embedding_config.get("redis_port", 6379)
        self.redis_db = embedding_config.get("redis_db", 0)
        self.redis_password = embedding_config.get("redis_password", None)
        
        # Cache configuration
        self.ttl_seconds = embedding_config.get("ttl_seconds", 86400 * 7)  # 7 days default
        self.max_memory_cache_size = embedding_config.get("max_memory_cache_size", 10000)
        
        # Model configuration
        self.model_name = embedding_config.get("model_name", "all-MiniLM-L6-v2")
        self.batch_size = embedding_config.get("batch_size", 32)
        
        # Refresh pipeline configuration
        self.refresh_enabled = embedding_config.get("refresh_enabled", True)
        self.refresh_interval_hours = embedding_config.get("refresh_interval_hours", 24)
        self.refresh_stale_threshold_days = embedding_config.get("refresh_stale_threshold_days", 3)


def get_sentence_model():  # type: ignore[no-untyped-def]
    """Get or create the sentence transformer model (lazy-loaded)."""
    global _sentence_model
    if _sentence_model is None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]
            config = EmbeddingConfig(Settings())
            log.info(f"Loading sentence transformer model: {config.model_name}")
            _sentence_model = SentenceTransformer(config.model_name)
            log.info(f"Model loaded. Dimension: {_sentence_model.get_sentence_embedding_dimension()}")
        except ImportError:
            log.warning("sentence-transformers not available, using fallback embeddings")
            _sentence_model = None
    return _sentence_model


def get_redis_client(config: EmbeddingConfig) -> Optional[Any]:
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
                decode_responses=False,  # We store binary data
            )
            # Test connection
            _redis_client.ping()
            log.info(f"Redis connection established: {config.redis_host}:{config.redis_port}")
        except ImportError:
            log.warning("redis package not available, using in-memory cache")
            _redis_client = None
        except Exception as e:
            log.error(f"Failed to connect to Redis: {e}, using in-memory cache")
            _cache_stats["redis_errors"] += 1
            _redis_client = None
    
    return _redis_client


def _generate_cache_key(text: str, prefix: str = "emb") -> str:
    """Generate cache key for text."""
    text_hash = hashlib.md5(text.encode()).hexdigest()[:16]
    return f"{prefix}:{text_hash}"


def _serialize_embedding(embedding: np.ndarray) -> bytes:
    """Serialize numpy array to bytes for Redis storage."""
    return embedding.tobytes()


def _deserialize_embedding(data: bytes, dtype: np.dtype = np.float32, shape: Tuple[int, ...] = (384,)) -> np.ndarray:
    """Deserialize bytes to numpy array."""
    return np.frombuffer(data, dtype=dtype).reshape(shape)


def _get_fallback_embedding(text: str) -> np.ndarray:
    """Fallback hash-based embedding when sentence-transformers is unavailable."""
    hash_obj = hashlib.sha256(text.encode())
    hash_bytes = hash_obj.digest()
    
    # Convert to numpy array of floats
    embedding = np.frombuffer(hash_bytes[:32], dtype=np.float32)
    embedding = embedding / (np.linalg.norm(embedding) + 1e-8)  # Normalize
    return embedding


def get_embedding(
    text: str,
    prefix: str = "emb",
    config: Optional[EmbeddingConfig] = None,
    use_cache: bool = True
) -> np.ndarray:
    """
    Get embedding for text with Redis-backed caching.
    
    Args:
        text: Text to embed
        prefix: Cache key prefix (e.g., 'emb', 'name', 'affiliation', 'topic')
        config: Optional config (loaded from Settings if not provided)
        use_cache: Whether to use cache (set False to force recomputation)
    
    Returns:
        384-dimensional normalized embedding vector
    """
    if config is None:
        config = EmbeddingConfig(Settings())
    
    cache_key = _generate_cache_key(text, prefix)
    
    # Try cache first
    if use_cache:
        cached = _get_from_cache(cache_key, config)
        if cached is not None:
            _cache_stats["hits"] += 1
            return cached
    
    _cache_stats["misses"] += 1
    
    # Compute embedding
    model = get_sentence_model()
    
    if model is not None:
        try:
            embedding = model.encode(text, convert_to_numpy=True, show_progress_bar=False)
            embedding = embedding.astype(np.float32)
            embedding = embedding / (np.linalg.norm(embedding) + 1e-8)
            _cache_stats["embeddings_computed"] += 1
        except Exception as e:
            log.error(f"Error computing embedding: {e}, using fallback")
            embedding = _get_fallback_embedding(text)
    else:
        embedding = _get_fallback_embedding(text)
    
    # Store in cache
    if use_cache:
        _set_in_cache(cache_key, embedding, config)
    
    return embedding


async def get_embedding_async(
    text: str,
    prefix: str = "emb",
    config: Optional[EmbeddingConfig] = None
) -> np.ndarray:
    """Async version of get_embedding."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_embedding, text, prefix, config)


def get_embeddings_batch(
    texts: List[str],
    prefix: str = "emb",
    config: Optional[EmbeddingConfig] = None
) -> List[np.ndarray]:
    """
    Get embeddings for multiple texts efficiently using batch processing.
    
    Args:
        texts: List of texts to embed
        prefix: Cache key prefix
        config: Optional config
    
    Returns:
        List of embedding vectors in same order as input texts
    """
    if config is None:
        config = EmbeddingConfig(Settings())
    
    results: List[Optional[np.ndarray]] = [None] * len(texts)
    uncached_indices: List[int] = []
    uncached_texts: List[str] = []
    
    # Check cache for each text
    for i, text in enumerate(texts):
        cache_key = _generate_cache_key(text, prefix)
        cached = _get_from_cache(cache_key, config)
        if cached is not None:
            results[i] = cached
            _cache_stats["hits"] += 1
        else:
            uncached_indices.append(i)
            uncached_texts.append(text)
            _cache_stats["misses"] += 1
    
    # Compute uncached embeddings in batch
    if uncached_texts:
        model = get_sentence_model()
        
        if model is not None:
            try:
                embeddings = model.encode(
                    uncached_texts,
                    convert_to_numpy=True,
                    show_progress_bar=False,
                    batch_size=config.batch_size
                )
                embeddings = embeddings.astype(np.float32)
                # Normalize each embedding
                for i in range(len(embeddings)):
                    embeddings[i] = embeddings[i] / (np.linalg.norm(embeddings[i]) + 1e-8)
                
                _cache_stats["embeddings_computed"] += len(uncached_texts)
                _cache_stats["batch_operations"] += 1
            except Exception as e:
                log.error(f"Error computing batch embeddings: {e}, using fallback")
                embeddings = [_get_fallback_embedding(t) for t in uncached_texts]
        else:
            embeddings = [_get_fallback_embedding(t) for t in uncached_texts]
        
        # Store in results and cache
        for idx, embedding in zip(uncached_indices, embeddings):
            results[idx] = embedding
            cache_key = _generate_cache_key(texts[idx], prefix)
            _set_in_cache(cache_key, embedding, config)
    
    return [r for r in results if r is not None]  # type: ignore[misc]


def _get_from_cache(cache_key: str, config: EmbeddingConfig) -> Optional[np.ndarray]:
    """Get embedding from cache (Redis or memory fallback)."""
    # Try Redis first
    redis_client = get_redis_client(config)
    if redis_client is not None:
        try:
            data = redis_client.get(cache_key)
            if data is not None:
                _cache_stats["redis_hits"] += 1
                return _deserialize_embedding(data)
        except Exception as e:
            log.error(f"Redis get error: {e}")
            _cache_stats["redis_errors"] += 1
    
    # Fallback to memory cache
    if cache_key in _memory_cache:
        embedding, timestamp = _memory_cache[cache_key]
        # Check if expired
        if time.time() - timestamp < config.ttl_seconds:
            _cache_stats["memory_hits"] += 1
            return embedding
        else:
            # Remove expired entry
            del _memory_cache[cache_key]
    
    return None


def _set_in_cache(cache_key: str, embedding: np.ndarray, config: EmbeddingConfig) -> None:
    """Store embedding in cache (Redis and/or memory)."""
    # Try Redis first
    redis_client = get_redis_client(config)
    if redis_client is not None:
        try:
            data = _serialize_embedding(embedding)
            redis_client.setex(cache_key, config.ttl_seconds, data)
        except Exception as e:
            log.error(f"Redis set error: {e}")
            _cache_stats["redis_errors"] += 1
    
    # Also store in memory cache as fallback
    _memory_cache[cache_key] = (embedding, time.time())
    
    # Evict old entries if memory cache too large
    if len(_memory_cache) > config.max_memory_cache_size:
        # Remove 10% oldest entries
        sorted_keys = sorted(_memory_cache.keys(), key=lambda k: _memory_cache[k][1])
        for key in sorted_keys[:config.max_memory_cache_size // 10]:
            del _memory_cache[key]


def clear_cache(prefix: Optional[str] = None, config: Optional[EmbeddingConfig] = None) -> int:
    """
    Clear embedding cache.
    
    Args:
        prefix: Optional prefix to clear only specific cache namespace
        config: Optional config
    
    Returns:
        Number of cache entries cleared
    """
    global _cache_stats
    
    if config is None:
        config = EmbeddingConfig(Settings())
    
    cleared = 0
    
    # Clear Redis
    redis_client = get_redis_client(config)
    if redis_client is not None:
        try:
            if prefix:
                # Clear keys matching prefix
                pattern = f"{prefix}:*"
                keys = redis_client.keys(pattern)
                if keys:
                    cleared += redis_client.delete(*keys)
            else:
                # Clear all embeddings
                redis_client.flushdb()
                cleared = -1  # Unknown count
        except Exception as e:
            log.error(f"Redis clear error: {e}")
            _cache_stats["redis_errors"] += 1
    
    # Clear memory cache
    if prefix:
        keys_to_remove = [k for k in _memory_cache.keys() if k.startswith(prefix)]
        for key in keys_to_remove:
            del _memory_cache[key]
        if cleared != -1:
            cleared += len(keys_to_remove)
    else:
        cleared_memory = len(_memory_cache)
        _memory_cache.clear()
        if cleared != -1:
            cleared += cleared_memory
        
        # Also reset stats when clearing all caches
        _cache_stats = {
            "hits": 0,
            "misses": 0,
            "redis_hits": 0,
            "memory_hits": 0,
            "redis_errors": 0,
            "embeddings_computed": 0,
            "batch_operations": 0,
        }
    
    log.info(f"Cleared {cleared if cleared != -1 else 'all'} cache entries (prefix={prefix})")
    return cleared


def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics."""
    hit_rate = _cache_stats["hits"] / max(1, _cache_stats["hits"] + _cache_stats["misses"])
    
    return {
        **_cache_stats,
        "hit_rate": hit_rate,
        "memory_cache_size": len(_memory_cache),
    }


async def refresh_stale_embeddings(
    db_path: str,
    config: Optional[EmbeddingConfig] = None,
    dry_run: bool = False
) -> Dict[str, int]:
    """
    Refresh stale embeddings in the background.
    
    This scans artifacts, topics, and entities for text that needs
    re-embedding (e.g., after TTL expiration or model updates).
    
    Args:
        db_path: Database path
        config: Optional config
        dry_run: If True, only count stale entries without refreshing
    
    Returns:
        Stats dict with counts
    """
    if config is None:
        config = EmbeddingConfig(Settings())
    
    if not config.refresh_enabled:
        log.info("Refresh pipeline disabled in config")
        return {"refreshed": 0, "skipped": 0}
    
    from .db import connect
    
    stats = {
        "artifacts_scanned": 0,
        "topics_scanned": 0,
        "entities_scanned": 0,
        "embeddings_refreshed": 0,
        "skipped": 0,
    }
    
    # Implement refresh logic
    # This queries stale artifacts/topics/entities and recomputes their embeddings
    
    staleness_days = config.refresh_stale_threshold_days
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=staleness_days)).isoformat()
    
    try:
        conn = connect(db_path)
        
        # 1. Refresh artifact embeddings (title + description)
        artifacts = conn.execute(
            """
            SELECT id, title, description 
            FROM artifacts 
            WHERE created_at < ? OR updated_at < ?
            LIMIT 1000
            """,
            (cutoff_date, cutoff_date),
        ).fetchall()
        
        stats["artifacts_scanned"] = len(artifacts)
        
        for artifact in artifacts:
            artifact_text = f"{artifact[1]} {artifact[2] or ''}"
            if artifact_text.strip():
                _ = get_embedding(artifact_text, prefix="artifact", config=config)
                stats["embeddings_refreshed"] += 1
        
        # 2. Refresh topic embeddings (name + description)
        topics = conn.execute(
            """
            SELECT name, description 
            FROM topics 
            WHERE created_at < ?
            LIMIT 500
            """,
            (cutoff_date,),
        ).fetchall()
        
        stats["topics_scanned"] = len(topics)
        
        for topic in topics:
            topic_text = f"{topic[0]} {topic[1] or ''}"
            if topic_text.strip():
                _ = get_embedding(topic_text, prefix="topic", config=config)
                stats["embeddings_refreshed"] += 1
        
        # 3. Refresh entity embeddings (name + description)
        entities = conn.execute(
            """
            SELECT name, description 
            FROM entities 
            WHERE created_at < ?
            LIMIT 500
            """,
            (cutoff_date,),
        ).fetchall()
        
        stats["entities_scanned"] = len(entities)
        
        for entity in entities:
            entity_text = f"{entity[0]} {entity[1] or ''}"
            if entity_text.strip():
                _ = get_embedding(entity_text, prefix="entity", config=config)
                stats["embeddings_refreshed"] += 1
        
        conn.close()
        
    except Exception as e:
        log.error(f"Refresh pipeline error: {e}")
        stats["skipped"] = -1  # Indicate error occurred
    
    log.info(f"Refresh pipeline stats: {stats}")
    return stats


# Convenience functions for specific embedding types

def get_name_embedding(name: str, config: Optional[EmbeddingConfig] = None) -> np.ndarray:
    """Get embedding for a person/entity name."""
    return get_embedding(name, prefix="name", config=config)


def get_affiliation_embedding(affiliation: str, config: Optional[EmbeddingConfig] = None) -> np.ndarray:
    """Get embedding for an affiliation/institution."""
    return get_embedding(affiliation, prefix="aff", config=config)


def get_topic_embedding(topic_text: str, config: Optional[EmbeddingConfig] = None) -> np.ndarray:
    """Get embedding for a topic description."""
    return get_embedding(topic_text, prefix="topic", config=config)


def get_artifact_embedding(artifact_text: str, config: Optional[EmbeddingConfig] = None) -> np.ndarray:
    """Get embedding for an artifact (paper, code, etc.)."""
    return get_embedding(artifact_text, prefix="art", config=config)
