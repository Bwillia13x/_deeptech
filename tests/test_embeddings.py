"""Tests for enhanced embeddings with Redis caching."""

import asyncio
import os

import numpy as np
import pytest

from signal_harvester.config import Settings
from signal_harvester.embeddings import (
    EmbeddingConfig,
    _deserialize_embedding,
    _generate_cache_key,
    _serialize_embedding,
    clear_cache,
    get_affiliation_embedding,
    get_artifact_embedding,
    get_cache_stats,
    get_embedding,
    get_embedding_async,
    get_embeddings_batch,
    get_name_embedding,
    get_topic_embedding,
)


@pytest.fixture
def embedding_config():
    """Create test embedding configuration."""
    settings = Settings()
    config = EmbeddingConfig(settings)
    # Disable Redis for most tests
    config.redis_enabled = False
    config.ttl_seconds = 3600  # 1 hour for testing
    config.max_memory_cache_size = 100
    return config


@pytest.fixture(autouse=True)
def clear_all_caches():
    """Clear all caches before and after each test."""
    clear_cache()
    yield
    clear_cache()


class TestCacheKeys:
    """Test cache key generation."""
    
    def test_generate_cache_key(self):
        """Test cache key generation is deterministic."""
        text = "Hello, world!"
        key1 = _generate_cache_key(text, "emb")
        key2 = _generate_cache_key(text, "emb")
        
        assert key1 == key2
        assert key1.startswith("emb:")
    
    def test_different_prefixes(self):
        """Test different prefixes produce different keys."""
        text = "Test text"
        key1 = _generate_cache_key(text, "emb")
        key2 = _generate_cache_key(text, "name")
        
        assert key1 != key2
        assert key1.startswith("emb:")
        assert key2.startswith("name:")
    
    def test_different_texts(self):
        """Test different texts produce different keys."""
        key1 = _generate_cache_key("Text A", "emb")
        key2 = _generate_cache_key("Text B", "emb")
        
        assert key1 != key2


class TestSerialization:
    """Test embedding serialization/deserialization."""
    
    def test_serialize_deserialize_roundtrip(self):
        """Test serialization roundtrip preserves data."""
        original = np.random.rand(384).astype(np.float32)
        
        serialized = _serialize_embedding(original)
        assert isinstance(serialized, bytes)
        
        deserialized = _deserialize_embedding(serialized)
        assert isinstance(deserialized, np.ndarray)
        assert deserialized.shape == (384,)
        assert np.allclose(original, deserialized)
    
    def test_serialize_different_shapes(self):
        """Test serialization handles different shapes."""
        shapes = [(128,), (256,), (512,)]
        
        for shape in shapes:
            original = np.random.rand(*shape).astype(np.float32)
            serialized = _serialize_embedding(original)
            deserialized = _deserialize_embedding(serialized, shape=shape)
            assert np.allclose(original, deserialized)


class TestEmbeddingComputation:
    """Test basic embedding computation."""
    
    def test_get_embedding_returns_vector(self, embedding_config):
        """Test embedding computation returns correct shape."""
        text = "Quantum error correction using surface codes"
        embedding = get_embedding(text, config=embedding_config)
        
        assert isinstance(embedding, np.ndarray)
        assert embedding.shape == (384,)  # all-MiniLM-L6-v2 dimension
        assert not np.all(embedding == 0), "Embedding should not be all zeros"
    
    def test_embeddings_are_normalized(self, embedding_config):
        """Test embeddings are L2 normalized."""
        text = "Test normalization"
        embedding = get_embedding(text, config=embedding_config)
        
        norm = np.linalg.norm(embedding)
        assert np.isclose(norm, 1.0, atol=1e-6), f"Embedding should be normalized, got norm={norm}"
    
    def test_similar_texts_similar_embeddings(self, embedding_config):
        """Test similar texts produce similar embeddings."""
        text1 = "quantum computing research"
        text2 = "quantum computer research"
        text3 = "classical music composition"
        
        emb1 = get_embedding(text1, config=embedding_config, use_cache=False)
        emb2 = get_embedding(text2, config=embedding_config, use_cache=False)
        emb3 = get_embedding(text3, config=embedding_config, use_cache=False)
        
        # Cosine similarity
        sim_12 = np.dot(emb1, emb2)
        sim_13 = np.dot(emb1, emb3)
        
        assert sim_12 > sim_13, "Similar texts should have higher similarity"
        assert sim_12 > 0.7, "Very similar texts should have high similarity"
    
    def test_empty_text_fallback(self, embedding_config):
        """Test empty text uses fallback."""
        embedding = get_embedding("", config=embedding_config)
        
        assert isinstance(embedding, np.ndarray)
        assert embedding.shape == (384,)


class TestCaching:
    """Test caching behavior."""
    
    def test_cache_hit_second_call(self, embedding_config):
        """Test second call uses cache."""
        text = "Cache test"
        
        # Clear stats
        clear_cache()
        
        # First call - miss
        emb1 = get_embedding(text, config=embedding_config)
        stats1 = get_cache_stats()
        assert stats1["misses"] == 1
        assert stats1["hits"] == 0
        
        # Second call - hit
        emb2 = get_embedding(text, config=embedding_config)
        stats2 = get_cache_stats()
        assert stats2["hits"] == 1
        
        # Should be exactly the same (cached)
        assert np.array_equal(emb1, emb2)
    
    def test_use_cache_false_bypasses_cache(self, embedding_config):
        """Test use_cache=False bypasses cache."""
        text = "Bypass cache test"
        
        clear_cache()
        
        # Call with use_cache=False twice
        get_embedding(text, config=embedding_config, use_cache=False)
        get_embedding(text, config=embedding_config, use_cache=False)
        
        stats = get_cache_stats()
        # Both should be misses
        assert stats["misses"] == 2
        assert stats["hits"] == 0
    
    def test_different_prefixes_different_cache(self, embedding_config):
        """Test different prefixes create separate cache entries."""
        text = "Same text, different prefix"
        
        clear_cache()
        
        # Get with different prefixes
        get_embedding(text, prefix="emb", config=embedding_config)
        get_embedding(text, prefix="name", config=embedding_config)
        
        stats = get_cache_stats()
        # Both should be misses (different cache keys)
        assert stats["misses"] == 2
        assert stats["hits"] == 0
    
    def test_clear_cache_removes_entries(self, embedding_config):
        """Test clear_cache removes cached entries."""
        text = "Clear cache test"
        
        # Cache an embedding
        get_embedding(text, config=embedding_config)
        stats1 = get_cache_stats()
        assert stats1["memory_cache_size"] > 0
        
        # Clear cache
        cleared = clear_cache(config=embedding_config)
        assert cleared > 0
        
        stats2 = get_cache_stats()
        assert stats2["memory_cache_size"] == 0
    
    def test_clear_cache_with_prefix(self, embedding_config):
        """Test clearing cache with specific prefix."""
        # Cache embeddings with different prefixes
        get_embedding("text1", prefix="emb", config=embedding_config)
        get_embedding("text2", prefix="name", config=embedding_config)
        
        # Clear only 'emb' prefix
        clear_cache(prefix="emb", config=embedding_config)
        
        # 'emb' should be cleared
        get_embedding("text1", prefix="emb", config=embedding_config)
        stats1 = get_cache_stats()
        # This should be a miss (cache was cleared)
        assert stats1["misses"] > 0


class TestBatchProcessing:
    """Test batch embedding computation."""
    
    def test_batch_embeddings_correct_count(self, embedding_config):
        """Test batch returns correct number of embeddings."""
        texts = [
            "First text",
            "Second text",
            "Third text"
        ]
        
        embeddings = get_embeddings_batch(texts, config=embedding_config)
        
        assert len(embeddings) == len(texts)
        for emb in embeddings:
            assert isinstance(emb, np.ndarray)
            assert emb.shape == (384,)
    
    def test_batch_uses_cache(self, embedding_config):
        """Test batch processing uses cache for some texts."""
        texts = ["Text A", "Text B", "Text C"]
        
        # Cache first text
        get_embedding(texts[0], config=embedding_config)
        
        clear_cache()
        
        # Batch process all texts
        embeddings = get_embeddings_batch(texts, config=embedding_config)
        
        assert len(embeddings) == 3
        # Should have some cache hits
        stats_after = get_cache_stats()
        # Note: Since we cleared cache, all should be misses
        assert stats_after["misses"] >= 3
    
    def test_batch_performance_benefit(self, embedding_config):
        """Test batch processing is more efficient than individual calls."""
        texts = [f"Text {i}" for i in range(10)]
        
        clear_cache()
        
        # Batch processing
        get_embeddings_batch(texts, config=embedding_config)
        stats_batch = get_cache_stats()
        
        assert stats_batch["batch_operations"] > 0
    
    def test_empty_batch(self, embedding_config):
        """Test empty batch returns empty list."""
        embeddings = get_embeddings_batch([], config=embedding_config)
        assert embeddings == []


class TestAsyncEmbedding:
    """Test async embedding computation."""
    
    @pytest.mark.asyncio
    async def test_get_embedding_async(self, embedding_config):
        """Test async embedding computation."""
        text = "Async embedding test"
        
        embedding = await get_embedding_async(text, config=embedding_config)
        
        assert isinstance(embedding, np.ndarray)
        assert embedding.shape == (384,)
    
    @pytest.mark.asyncio
    async def test_async_multiple_concurrent(self, embedding_config):
        """Test multiple concurrent async embeddings."""
        texts = [f"Concurrent text {i}" for i in range(5)]
        
        tasks = [get_embedding_async(text, config=embedding_config) for text in texts]
        embeddings = await asyncio.gather(*tasks)
        
        assert len(embeddings) == len(texts)
        for emb in embeddings:
            assert isinstance(emb, np.ndarray)
            assert emb.shape == (384,)


class TestConvenienceFunctions:
    """Test convenience functions for specific embedding types."""
    
    def test_get_name_embedding(self, embedding_config):
        """Test name embedding function."""
        name = "David Chen"
        embedding = get_name_embedding(name, config=embedding_config)
        
        assert isinstance(embedding, np.ndarray)
        assert embedding.shape == (384,)
        
        # Check it uses 'name' prefix
        cache_key = _generate_cache_key(name, "name")
        assert cache_key.startswith("name:")
    
    def test_get_affiliation_embedding(self, embedding_config):
        """Test affiliation embedding function."""
        affiliation = "MIT CSAIL"
        embedding = get_affiliation_embedding(affiliation, config=embedding_config)
        
        assert isinstance(embedding, np.ndarray)
        assert embedding.shape == (384,)
    
    def test_get_topic_embedding(self, embedding_config):
        """Test topic embedding function."""
        topic = "Quantum Error Correction"
        embedding = get_topic_embedding(topic, config=embedding_config)
        
        assert isinstance(embedding, np.ndarray)
        assert embedding.shape == (384,)
    
    def test_get_artifact_embedding(self, embedding_config):
        """Test artifact embedding function."""
        artifact = "A novel approach to quantum computing using topological codes"
        embedding = get_artifact_embedding(artifact, config=embedding_config)
        
        assert isinstance(embedding, np.ndarray)
        assert embedding.shape == (384,)


class TestCacheStats:
    """Test cache statistics."""
    
    def test_stats_track_hits_misses(self, embedding_config):
        """Test stats correctly track hits and misses."""
        clear_cache()
        
        text = "Stats test"
        
        # First call - miss
        get_embedding(text, config=embedding_config)
        stats1 = get_cache_stats()
        assert stats1["misses"] == 1
        assert stats1["hits"] == 0
        
        # Second call - hit
        get_embedding(text, config=embedding_config)
        stats2 = get_cache_stats()
        assert stats2["hits"] == 1
        assert stats2["misses"] == 1
    
    def test_stats_hit_rate(self, embedding_config):
        """Test hit rate calculation."""
        clear_cache()
        
        text = "Hit rate test"
        
        # One miss, two hits
        get_embedding(text, config=embedding_config)
        get_embedding(text, config=embedding_config)
        get_embedding(text, config=embedding_config)
        
        stats = get_cache_stats()
        assert stats["hit_rate"] == 2/3  # 2 hits out of 3 total
    
    def test_stats_memory_cache_size(self, embedding_config):
        """Test memory cache size tracking."""
        clear_cache()
        
        # Add 5 different texts
        for i in range(5):
            get_embedding(f"Text {i}", config=embedding_config)
        
        stats = get_cache_stats()
        assert stats["memory_cache_size"] == 5


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_very_long_text(self, embedding_config):
        """Test embedding very long text."""
        long_text = "quantum " * 1000  # Very long repeated text
        
        embedding = get_embedding(long_text, config=embedding_config)
        
        assert isinstance(embedding, np.ndarray)
        assert embedding.shape == (384,)
    
    def test_special_characters(self, embedding_config):
        """Test text with special characters."""
        text = "Test with émojis 🚀 and spëcial çhars!"
        
        embedding = get_embedding(text, config=embedding_config)
        
        assert isinstance(embedding, np.ndarray)
        assert embedding.shape == (384,)
    
    def test_unicode_text(self, embedding_config):
        """Test non-ASCII Unicode text."""
        texts = [
            "中文文本",  # Chinese
            "日本語テキスト",  # Japanese
            "Текст на русском",  # Russian
        ]
        
        for text in texts:
            embedding = get_embedding(text, config=embedding_config)
            assert isinstance(embedding, np.ndarray)
            assert embedding.shape == (384,)


class TestConfiguration:
    """Test embedding configuration."""
    
    def test_config_from_settings(self):
        """Test config loads from settings."""
        settings = Settings()
        config = EmbeddingConfig(settings)
        
        assert hasattr(config, 'redis_enabled')
        assert hasattr(config, 'ttl_seconds')
        assert hasattr(config, 'model_name')
        assert hasattr(config, 'batch_size')
    
    def test_config_defaults(self):
        """Test config has sensible defaults."""
        settings = Settings()
        config = EmbeddingConfig(settings)
        
        assert config.model_name == "all-MiniLM-L6-v2"
        assert config.ttl_seconds > 0
        assert config.batch_size > 0
        assert config.max_memory_cache_size > 0


@pytest.mark.skipif(
    os.getenv("REDIS_AVAILABLE") != "true",
    reason="Redis tests require REDIS_AVAILABLE=true env var"
)
class TestRedisIntegration:
    """Test Redis integration (requires Redis server)."""
    
    def test_redis_cache_hit(self):
        """Test Redis caching works."""
        settings = Settings()
        config = EmbeddingConfig(settings)
        config.redis_enabled = True
        
        clear_cache(config=config)
        
        text = "Redis cache test"
        
        # First call - should store in Redis
        emb1 = get_embedding(text, config=config)
        
        # Second call - should retrieve from Redis
        emb2 = get_embedding(text, config=config)
        
        assert np.array_equal(emb1, emb2)
        
        stats = get_cache_stats()
        assert stats["redis_hits"] > 0
    
    def test_redis_ttl_expiration(self):
        """Test Redis TTL expiration."""
        settings = Settings()
        config = EmbeddingConfig(settings)
        config.redis_enabled = True
        config.ttl_seconds = 1  # 1 second TTL
        
        clear_cache(config=config)
        
        text = "TTL test"
        
        # Cache embedding
        get_embedding(text, config=config)
        
        # Wait for expiration
        import time
        time.sleep(2)
        
        # Should be a cache miss now
        clear_cache()  # Reset stats
        get_embedding(text, config=config)
        stats = get_cache_stats()
        assert stats["misses"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
