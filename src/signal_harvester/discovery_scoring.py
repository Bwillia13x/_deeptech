"""Discovery scoring algorithms for deep tech research artifacts."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import numpy as np

from .db import (
    get_entity_with_accounts,
    list_artifacts_for_scoring,
    update_discovery_scores,
)
from .logger import get_logger

log = get_logger(__name__)

# Simple embedding cache to avoid recomputation
_embedding_cache: dict[str, np.ndarray] = {}
_topic_centroids: dict[str, np.ndarray] = {}
_topic_artifact_counts: dict[str, int] = defaultdict(int)

# Lazy-loaded sentence transformer model
_sentence_model = None


def get_sentence_model():  # type: ignore[no-untyped-def]
    """Get or create the sentence transformer model."""
    global _sentence_model
    if _sentence_model is None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]
            # Use a fast, efficient model
            model_name = "all-MiniLM-L6-v2"
            log.info(f"Loading sentence transformer model: {model_name}")
            _sentence_model = SentenceTransformer(model_name)
            log.info(f"Model loaded successfully. Dimension: {_sentence_model.get_sentence_embedding_dimension()}")
        except ImportError:
            log.warning("sentence-transformers not available, using fallback embeddings")
            _sentence_model = None
    return _sentence_model


def get_embedding(text: str) -> np.ndarray:
    """Get sentence embedding for text using sentence-transformers."""
    cache_key = hashlib.md5(text.encode()).hexdigest()[:16]
    
    if cache_key in _embedding_cache:
        return _embedding_cache[cache_key]
    
    model = get_sentence_model()
    
    if model is not None:
        # Use real sentence embeddings
        try:
            embedding = model.encode(text, convert_to_numpy=True)
            # Ensure it's float32 and normalized
            embedding = embedding.astype(np.float32)
            embedding = embedding / (np.linalg.norm(embedding) + 1e-8)
        except Exception as e:
            log.error(f"Error computing embedding: {e}, using fallback")
            embedding = _get_fallback_embedding(text)
    else:
        # Fallback to hash-based pseudo-embeddings
        embedding = _get_fallback_embedding(text)
    
    _embedding_cache[cache_key] = embedding
    return embedding


def _get_fallback_embedding(text: str) -> np.ndarray:
    """Fallback hash-based embedding when sentence-transformers is unavailable."""
    hash_obj = hashlib.sha256(text.encode())
    hash_bytes = hash_obj.digest()
    
    # Convert to numpy array of floats
    embedding = np.frombuffer(hash_bytes[:32], dtype=np.float32)
    embedding = embedding / (np.linalg.norm(embedding) + 1e-8)  # Normalize
    return embedding


async def get_embedding_async(text: str) -> np.ndarray:
    """Async version of get_embedding for batch processing."""
    # Run in thread pool to avoid blocking
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_embedding, text)


def compute_novelty(artifact: dict[str, Any], topic: str | None = None) -> float:
    """
    Compute novelty score (0-100) for an artifact.
    
    ALGORITHM DESIGN:
    
    Novelty measures how different an artifact is from existing knowledge in its topic area.
    The score combines three orthogonal signals:
    
    1. Embedding Distance (50% weight):
       - Uses all-MiniLM-L6-v2 embeddings (384-dim) to capture semantic content
       - Computes L2 distance from topic centroid (mean of historical artifacts)
       - Larger distance = more novel
       - Scaled by 50.0 to map to 0-100 range
       - Default 50.0 if no centroid (first artifact in topic)
    
    2. Rare Terms (30% weight):
       - Counts technical terms (words >5 chars, alphanumeric only)
       - Assumes longer words are more domain-specific
       - Each rare term adds 2.0 points, capped at 30.0
       - Proxy for specialized vocabulary
    
    3. Unique Combinations (20% weight):
       - Detects unusual word pairings (bigrams)
       - Hash-based pseudo-check for rarity (10% threshold)
       - Each unique pair adds 2.0 points, capped at 20.0
       - Identifies novel conceptual connections
    
    MATHEMATICAL FORMULATION:
    
        novelty = 0.5 * D(e, c) * 50 + 0.3 * min(30, R * 2) + 0.2 * min(20, P * 2)
    
        Where:
        - D(e, c) = ||e - c||₂ (L2 distance between embedding e and centroid c)
        - R = count of rare terms (len > 5, alphanumeric)
        - P = count of unique bigram pairs (hash % 10 == 0)
    
    RANGE: [0.0, 100.0]
    
    DESIGN RATIONALE:
    
    - Embedding distance captures semantic novelty at scale
    - Rare terms compensate for embedding limitations (out-of-vocabulary)
    - Bigram pairs detect novel idea combinations not captured by individual terms
    - Weights prioritize embedding distance (most robust signal)
    
    Args:
        artifact: Artifact dict with 'title' and 'text' fields
        topic: Optional topic string for centroid lookup
    
    Returns:
        Novelty score in range [0.0, 100.0]
    """
    try:
        text = f"{artifact.get('title', '')} {artifact.get('text', '')}".strip()
        if not text:
            return 0.0
        
        # STEP 1: Compute semantic embedding for artifact text
        # Uses sentence-transformers with L2 normalization
        embedding: np.ndarray = get_embedding(text)
        
        # STEP 2: Calculate distance from topic centroid
        if topic and topic in _topic_centroids:
            # Distance from topic centroid (L2 norm)
            centroid = _topic_centroids[topic]
            distance = float(np.linalg.norm(embedding - centroid))
            # Convert distance to novelty (0-100)
            # Scaling factor 50.0 empirically chosen to map typical distances to 0-100
            novelty_from_distance = float(min(100.0, distance * 50.0))
        else:
            # Default if no centroid available (e.g., first artifact in topic)
            novelty_from_distance = 50.0
        
        # STEP 3: Compute rare term score
        # Rare terms = technical vocabulary indicator
        words = text.lower().split()
        rare_terms = [w for w in words if len(w) > 5 and w.isalnum()]  # Longer words are often technical
        # 2.0 points per rare term, capped at 30.0
        rare_term_score = float(min(30.0, len(rare_terms) * 2.0))
        
        # STEP 4: Compute unique combination score
        # Detects novel bigram pairings (conceptual connections)
        unique_pairs = 0
        for i in range(len(words) - 1):
            pair = f"{words[i]}_{words[i+1]}"
            # In production: check against historical bigram frequency table
            # For now: pseudo-check using hash (10% rarity threshold)
            if hash(pair) % 10 == 0:  # Simulates 1-in-10 rarity
                unique_pairs += 1
        
        # 2.0 points per unique pair, capped at 20.0
        combination_score = float(min(20.0, unique_pairs * 2.0))
        
        # STEP 5: Weighted combination of all signals
        # Weights: embedding distance (0.5), rare terms (0.3), combinations (0.2)
        novelty = float(
            novelty_from_distance * 0.5 + rare_term_score * 0.3 + combination_score * 0.2
        )
        
        # Clamp to valid range [0.0, 100.0]
        return min(100.0, max(0.0, novelty))
        
    except Exception as e:
        log.error("Error computing novelty: %s", e)
        return 0.0


def compute_emergence(artifact: dict[str, Any], topic: str | None = None) -> float:
    """
    Compute emergence score (0-100) for an artifact.
    
    ALGORITHM DESIGN:
    
    Emergence measures whether a topic/idea is gaining traction in the research community.
    Combines four signals to detect growing trends and accelerating interest:
    
    1. Cross-Source Corroboration (15 points):
       - Boost for artifacts from credible sources (arXiv, GitHub)
       - Multi-source appearance indicates broader adoption
       - arXiv/GitHub get +15 points (research + implementation)
    
    2. Recency Boost (25 points max):
       - Exponential decay with 168-hour (1-week) half-life
       - Formula: 25.0 * exp(-hours_old / 168)
       - Captures "hot off the press" momentum
       - Decays to ~12.5 after 1 week, ~6.25 after 2 weeks
    
    3. Topic Growth Rate (30 points max):
       - Based on artifact count within topic
       - More artifacts = more emergent topic
       - Formula: min(30.0, artifact_count * 3.0)
       - Caps at 10 artifacts for maximum emergence
    
    4. Acceleration Detection (10 points):
       - Detects increasing rate of activity
       - In production: fit time series, compute d²/dt² (second derivative)
       - Current: default 10.0 (placeholder for full implementation)
    
    MATHEMATICAL FORMULATION:
    
        emergence = C + R * exp(-t/168) + min(30, N * 3) + A
    
        Where:
        - C = cross_source_boost (15 for arXiv/GitHub, 0 otherwise)
        - R = recency_coefficient (25.0)
        - t = hours since publication
        - N = artifact count in topic
        - A = acceleration score (10.0 default)
    
    RANGE: [0.0, 100.0]
    
    DESIGN RATIONALE:
    
    - Recency heavily weighted (25 points) to catch breaking trends
    - Topic growth captures sustained interest over time
    - Cross-source validates emergence across platforms
    - Acceleration detects inflection points (future enhancement)
    
    FUTURE ENHANCEMENTS:
    
    - Real acceleration via ARIMA time series forecasting
    - Citation velocity (papers citing per day)
    - GitHub star/fork velocity for code repos
    - Social media mention velocity (X, LinkedIn)
    
    Args:
        artifact: Artifact dict with 'source' and 'published_at' fields
        topic: Optional topic string for growth rate lookup
    
    Returns:
        Emergence score in range [0.0, 100.0]
    """
    try:
        score = 0.0
        
        # STEP 1: Cross-source boost
        # Artifacts from research+code sources indicate broader adoption
        source = artifact.get("source", "")
        if topic:
            # In production: query if same topic appears across arXiv, GitHub, X, etc.
            # For now: boost arXiv and GitHub as high-quality sources
            if source in ["arxiv", "github"]:
                score += 15.0
        
        # STEP 2: Recency boost with exponential decay
        # Recent artifacts score higher (captures momentum)
        published_at = artifact.get("published_at")
        if published_at:
            try:
                pub_time = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                hours_old = (now - pub_time).total_seconds() / 3600
                
                # Exponential decay with 1-week half-life
                # At t=0: 25.0, t=168h: 12.5, t=336h: 6.25
                recency_boost = 25.0 * math.exp(-hours_old / 168)
                score += recency_boost
            except Exception:
                # Fallback if published_at parsing fails
                pass
        
        # STEP 3: Topic growth rate
        # More artifacts in topic = more emergent
        if topic:
            # In production: compute actual growth rate via linear regression on artifact counts
            # For now: use current artifact count as proxy
            count = _topic_artifact_counts.get(topic, 0)
            # 3.0 points per artifact, capped at 30.0 (10 artifacts)
            growth_score = min(30.0, count * 3.0)
            score += growth_score
        
        # STEP 4: Acceleration detection
        # In production: fit time series and compute d²/dt² (concavity)
        # Positive acceleration = exponential growth phase
        # Implementation requires historical time series:
        #   1. Group artifacts by day
        #   2. Fit polynomial or exponential curve
        #   3. Compute second derivative
        #   4. Positive d²/dt² indicates acceleration
        # Current: default placeholder
        acceleration_score = 10.0
        score += acceleration_score
        
        # Clamp to valid range [0.0, 100.0]
        return min(100.0, max(0.0, score))
        
    except Exception as e:
        log.error("Error computing emergence: %s", e)
        return 0.0


def compute_obscurity(artifact: dict[str, Any], author_entities: list[dict[str, Any]] | None = None) -> float:
    """
    Compute obscurity score (0-100) for an artifact.
    
    Higher obscurity means:
    - Low mainstream engagement/coverage
    - High expert ratio (credible authors, quality sources)
    - Niche topic with specialized audience
    """
    try:
        score = 0.0
        source = artifact.get("source", "")
        
        # Source-based obscurity
        source_obscurity = {
            "arxiv": 80.0,      # Academic preprints are obscure
            "github": 60.0,     # Code repos moderately obscure
            "x": 20.0,          # Twitter is mainstream
            "crossref": 70.0,   # Academic papers are obscure
            "semantic": 70.0    # Academic papers are obscure
        }
        score += source_obscurity.get(source, 50.0)
        
        # Author credibility boost
        if author_entities:
            for entity in author_entities:
                # Check if author has credibility indicators
                accounts = entity.get("accounts", [])
                for account in accounts:
                    platform = account.get("platform", "")
                    confidence = account.get("confidence", 0.0)
                    
                    # High confidence links increase obscurity (credible experts)
                    if confidence > 0.8:
                        score += 10.0
                    
                    # Academic platforms boost obscurity
                    if platform in ["arxiv", "crossref", "semantic"]:
                        score += 5.0
        
        # Content-based obscurity
        text = f"{artifact.get('title', '')} {artifact.get('text', '')}".lower()
        
        # Technical terms increase obscurity
        technical_terms = [
            "theorem", "proof", "algorithm", "optimization", "convergence",
            "embedding", "latent", "differentiable", "gradient", "backpropagation",
            "hamiltonian", "tensor", "manifold", "isomorphism", "homomorphism"
        ]
        
        tech_term_count = sum(1 for term in technical_terms if term in text)
        score += min(20.0, tech_term_count * 2.0)
        
        # Penalize viral/general terms
        general_terms = ["amazing", "incredible", "game-changer", "revolutionary", "blow", "mind"]
        general_count = sum(1 for term in general_terms if term in text)
        score -= general_count * 5.0
        
        return min(100.0, max(0.0, score))
        
    except Exception as e:
        log.error("Error computing obscurity: %s", e)
        return 0.0


def compute_discovery_score(
    artifact: dict[str, Any],
    novelty: float,
    emergence: float,
    obscurity: float,
    config: dict[str, Any]
) -> float:
    """
    Compute final discovery score (0-100) from components.
    
    Uses configurable weights from settings.
    """
    try:
        weights = config.get("weights", {}).get("discovery", {})
        
        novelty_weight = weights.get("novelty", 0.35)
        emergence_weight = weights.get("emergence", 0.30)
        obscurity_weight = weights.get("obscurity", 0.20)
        cross_source_weight = weights.get("cross_source", 0.10)
        expert_signal_weight = weights.get("expert_signal", 0.05)
        
        # Base score from components
        base_score = (
            novelty * novelty_weight +
            emergence * emergence_weight +
            obscurity * obscurity_weight
        )
        
        # Cross-source boost
        source = artifact.get("source", "")
        cross_source_boost = 0.0
        if source in ["arxiv", "github"]:
            cross_source_boost = 10.0 * cross_source_weight
        
        # Expert signal boost
        expert_boost = 0.0
        author_entities_json = artifact.get("author_entity_ids")
        if author_entities_json:
            try:
                author_ids = json.loads(author_entities_json)
                if author_ids and len(author_ids) > 0:
                    expert_boost = 5.0 * expert_signal_weight
            except Exception:
                pass
        
        # Recency decay (slower than salience)
        half_life = weights.get("recency_half_life_hours", 336)  # 14 days default
        published_at = artifact.get("published_at")
        recency_multiplier = 1.0
        
        if published_at:
            try:
                pub_time = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                hours_old = (now - pub_time).total_seconds() / 3600
                
                # Exponential decay
                recency_multiplier = math.exp(-hours_old / half_life)
            except Exception:
                pass
        
        # Combine all components
        discovery_score = (base_score + cross_source_boost + expert_boost) * recency_multiplier
        
        return min(100.0, max(0.0, discovery_score))
        
    except Exception as e:
        log.error("Error computing discovery score: %s", e)
        return 0.0


async def score_artifact(
    artifact: dict[str, Any],
    db_path: str,
    config: dict[str, Any]
) -> dict[str, float] | None:
    """
    Compute all scores for an artifact and return them.
    """
    try:
        artifact_id = artifact.get("id")
        if not artifact_id:
            log.error("Artifact missing ID")
            return None
        
        # Get author entities if available
        author_entities = None
        author_entities_json = artifact.get("author_entity_ids")
        if author_entities_json:
            try:
                author_ids = json.loads(author_entities_json)
                author_entities = []
                for entity_id in author_ids:
                    entity = get_entity_with_accounts(db_path, entity_id)
                    if entity:
                        author_entities.append(entity)
            except Exception as e:
                log.warning("Error parsing author entities: %s", e)
        
        # Get topics for this artifact
        # In real implementation, query artifact_topics table
        topics: list[str] = []  # Would fetch from DB
        primary_topic = topics[0] if topics else None
        
        # Compute component scores
        novelty = compute_novelty(artifact, primary_topic)
        emergence = compute_emergence(artifact, primary_topic)
        obscurity = compute_obscurity(artifact, author_entities)
        
        # Compute final discovery score
        discovery_score = compute_discovery_score(
            artifact, novelty, emergence, obscurity, config
        )
        
        return {
            "novelty": novelty,
            "emergence": emergence,
            "obscurity": obscurity,
            "discovery_score": discovery_score
        }
        
    except Exception as e:
        log.error("Error scoring artifact %s: %s", artifact.get("id"), e)
        return None


async def run_discovery_scoring(db_path: str, config: dict[str, Any], limit: int = 500) -> int:
    """
    Run discovery scoring on un-scored artifacts.
    
    Returns number of artifacts scored.
    """
    try:
        # Get artifacts that need scoring
        artifacts = list_artifacts_for_scoring(db_path, limit)
        log.info("Found %d artifacts to score", len(artifacts))
        
        scored_count = 0
        
        for artifact in artifacts:
            try:
                scores = await score_artifact(artifact, db_path, config)
                if scores:
                    # Update database
                    update_discovery_scores(
                        db_path,
                        artifact["id"],
                        scores["novelty"],
                        scores["emergence"],
                        scores["obscurity"],
                        scores["discovery_score"]
                    )
                    scored_count += 1
                    
                    log.debug("Scored artifact %s: discovery_score=%.2f", 
                             artifact.get("source_id"), scores["discovery_score"])
                
            except Exception as e:
                log.error("Error scoring artifact %s: %s", artifact.get("id"), e)
                continue
        
        log.info("Discovery scoring complete: %d artifacts scored", scored_count)
        return scored_count
        
    except Exception as e:
        log.error("Error in discovery scoring: %s", e)
        return 0


def update_topic_stats(db_path: str) -> None:
    """
    Update topic statistics for scoring.
    
    This should be called periodically to maintain accurate topic centroids
    and artifact counts.
    """
    try:
        # In real implementation:
        # 1. Compute topic centroids from artifact embeddings
        # 2. Update artifact counts per topic
        # 3. Compute time series for emergence detection
        
        log.info("Topic stats update would happen here")
        
    except Exception as e:
        log.error("Error updating topic stats: %s", e)
