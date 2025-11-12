"""Topic evolution, similarity, and analytics for Phase 2."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, TypedDict

import numpy as np

from .db import connect, get_trending_topics
from .discovery_scoring import get_embedding
from .logger import get_logger

log = get_logger(__name__)

# Topic embedding cache for performance
_topic_embedding_cache: Dict[int, np.ndarray] = {}
_topic_artifact_history: Dict[int, List[Dict[str, Any]]] = defaultdict(list)


class MergeCandidate(TypedDict):
    primary_topic: Dict[str, Any]
    secondary_topic: Dict[str, Any]
    current_similarity: float
    overlap_trend: float
    confidence: float
    event_type: str
    timestamp: str


class TopicEvolutionConfig:
    """Configuration for topic evolution analytics."""
    
    def __init__(self, settings: Any):
        topic_config = getattr(settings.app, 'topic_evolution', {})
        if hasattr(topic_config, '__dict__'):
            topic_config = topic_config.__dict__
        
        self.enabled = topic_config.get("enabled", True)
        self.similarity_threshold = topic_config.get("similarity_threshold", 0.75)
        self.merge_threshold = topic_config.get("merge_threshold", 0.85)
        self.split_threshold = topic_config.get("split_threshold", 0.80)
        self.cluster_quality_threshold = topic_config.get("cluster_quality_threshold", 0.60)
        self.update_frequency_hours = topic_config.get("update_frequency_hours", 24)
        self.emergence_window_days = topic_config.get("emergence_window_days", 30)
        self.prediction_window_days = topic_config.get("prediction_window_days", 14)


def compute_topic_embedding(topic_id: int, db_path: str) -> np.ndarray:
    """
    Compute embedding for a topic based on its artifacts.
    
    ALGORITHM DESIGN:
    
    This function creates a vector representation of a topic by aggregating embeddings
    from all associated artifacts. The embedding captures the semantic "center of mass"
    of the topic's content, weighted by both discovery score and recency.
    
    WEIGHTED AVERAGE APPROACH:
    
    Instead of simple averaging, we use weighted averaging where each artifact's
    contribution is proportional to:
    
    1. Discovery Score (base weight):
       - Higher-scored artifacts contribute more to topic identity
       - Assumes high-scoring artifacts are more representative
       - Range: [0, 100], typically 50-90 for real artifacts
    
    2. Recency Decay (multiplier):
       - Recent artifacts weighted more heavily
       - Exponential decay: exp(-days_old / 30)
       - 30-day half-life means:
         * Today: weight × 1.0
         * 30 days ago: weight × 0.37
         * 60 days ago: weight × 0.14
       - Ensures topic embedding evolves with latest research
    
    FORMULA:
    
        embedding_topic = Σ(w_i * e_i) / Σ(w_i)
        
        Where:
        - w_i = discovery_score_i * exp(-age_days_i / 30)
        - e_i = artifact_i embedding (384-dim from all-MiniLM-L6-v2)
    
    CACHING STRATEGY:
    
    - Embeddings cached in _topic_embedding_cache dict
    - Cache keyed by topic_id
    - Invalidated on topic updates (not implemented yet)
    - TODO: Add TTL-based cache eviction for dynamic topics
    
    QUERY OPTIMIZATION:
    
    - Fetches most recent 100 artifacts per topic
    - Uses published_at DESC ordering for recency
    - Joins artifact_topics and scores tables
    - Consider adding index on (topic_id, published_at) for performance
    
    EDGE CASES:
    
    - No artifacts → returns zero vector (np.zeros(384))
    - No text content → skips artifact in averaging
    - Missing discovery_score → defaults to 50.0 (neutral)
    - Missing published_at → defaults to recency_weight = 1.0 (no decay)
    - All zero weights → falls back to equal weighting
    
    DIMENSIONALITY:
    
    - Returns 384-dimensional numpy array (float32)
    - Matches all-MiniLM-L6-v2 model output dimension
    - Compatible with compute_topic_similarity() cosine distance
    
    DESIGN RATIONALE:
    
    - Weighted averaging captures topic's current focus
    - Recency decay ensures embedding reflects latest trends
    - Discovery score weighting emphasizes important artifacts
    - 100-artifact limit balances coverage vs. computation
    
    FUTURE ENHANCEMENTS:
    
    - Cluster artifacts within topic, use cluster centroids
    - Implement incremental update instead of full recomputation
    - Add cache TTL based on topic update frequency
    - Consider TF-IDF weighting for artifact importance
    
    Args:
        topic_id: Database ID of the topic
        db_path: Path to SQLite database
    
    Returns:
        384-dimensional numpy array (float32) representing topic embedding.
        Returns zero vector if topic has no artifacts or text content.
    """
    # Check cache first for performance
    if topic_id in _topic_embedding_cache:
        return _topic_embedding_cache[topic_id]
    
    conn = connect(db_path)
    try:
        # STEP 1: Fetch recent artifacts for this topic
        # Uses JOIN with artifact_topics to get topic associations
        # LEFT JOIN with scores to include discovery_score
        # Ordered by published_at DESC for recency priority
        # Limited to 100 for performance (configurable in future)
        cur = conn.execute(
            """
            SELECT 
                a.id,
                a.title,
                a.text,
                a.published_at,
                s.discovery_score
            FROM artifacts a
            JOIN artifact_topics at ON a.id = at.artifact_id
            LEFT JOIN scores s ON a.id = s.artifact_id
            WHERE at.topic_id = ?
            ORDER BY a.published_at DESC
            LIMIT 100;
            """,
            (topic_id,)
        )
        
        artifacts = [dict(row) for row in cur.fetchall()]
        
        if not artifacts:
            # No artifacts for this topic - return zero vector
            return np.zeros(384, dtype=np.float32)  # Dimension of all-MiniLM-L6-v2
        
        embeddings: list[np.ndarray] = []
        weights: list[float] = []
        
        # STEP 2: Compute embedding and weight for each artifact
        for artifact in artifacts:
            # Combine title and text for full semantic representation
            text = f"{artifact.get('title', '')} {artifact.get('text', '')}".strip()
            
            if not text:
                continue  # Skip artifacts with no text content
            
            # Compute 384-dim embedding using sentence-transformers
            # Reuses embedding cache from discovery_scoring module
            embedding = get_embedding(text)
            embeddings.append(embedding)
            
            # STEP 3: Calculate combined weight (discovery_score × recency)
            
            # Base weight from discovery score (default 50.0 if missing)
            base_weight = artifact.get('discovery_score', 50.0) or 50.0
            
            # Recency weight with exponential decay
            # Formula: exp(-days_old / 30) gives 30-day half-life
            published_at = artifact.get('published_at')
            if published_at:
                try:
                    pub_time = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                    days_old = (datetime.now(timezone.utc) - pub_time).days
                    recency_weight = math.exp(-days_old / 30)  # 30-day half-life
                except Exception:
                    recency_weight = 1.0  # Fallback if date parsing fails
            else:
                recency_weight = 1.0  # No decay if published_at missing
            
            # Combined weight = base × recency
            weight = base_weight * recency_weight
            weights.append(weight)
        
        if not embeddings:
            # All artifacts had no text - return zero vector
            return np.zeros(384, dtype=np.float32)
        
        # STEP 4: Compute weighted average of embeddings
        embeddings_arr = np.array(embeddings, dtype=np.float32)
        weights_arr = np.array(weights, dtype=np.float32)
        
        # Normalize weights to sum to 1.0
        weights_norm = weights_arr.sum()
        if weights_norm == 0:
            # All zero weights - fall back to equal weighting
            weights_arr = np.ones_like(weights_arr) / len(weights_arr)
        else:
            weights_arr = weights_arr / weights_norm
        
        # Weighted average: Σ(w_i * e_i)
        weighted_embedding = np.average(embeddings_arr, axis=0, weights=weights_arr).astype(np.float32)
        
        # STEP 5: Cache the result for future calls
        _topic_embedding_cache[topic_id] = weighted_embedding
        
        return weighted_embedding
        
    finally:
        conn.close()


def compute_topic_similarity(
    topic1_id: int,
    topic2_id: int,
    db_path: str
) -> float:
    """
    Compute cosine similarity between two topics based on their embeddings.
    """
    emb1 = compute_topic_embedding(topic1_id, db_path)
    emb2 = compute_topic_embedding(topic2_id, db_path)
    
    # Compute cosine similarity
    dot_product = np.dot(emb1, emb2)
    norm1 = np.linalg.norm(emb1)
    norm2 = np.linalg.norm(emb2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    similarity = dot_product / (norm1 * norm2)
    
    # Ensure it's in [-1, 1] range
    return max(-1.0, min(1.0, similarity))


def get_topic_artifact_history(
    topic_id: int,
    db_path: str,
    days: int = 90
) -> List[Dict[str, Any]]:
    """
    Get historical artifact data for a topic.
    
    Returns list of daily artifact counts and average scores.
    """
    conn = connect(db_path)
    try:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).isoformat().replace('+00:00', 'Z')
        
        cur = conn.execute(
            """
            SELECT 
                date(a.published_at) as date,
                COUNT(DISTINCT a.id) as artifact_count,
                AVG(s.discovery_score) as avg_discovery_score,
                AVG(s.novelty) as avg_novelty,
                AVG(s.emergence) as avg_emergence,
                AVG(s.obscurity) as avg_obscurity
            FROM artifacts a
            JOIN artifact_topics at ON a.id = at.artifact_id
            LEFT JOIN scores s ON a.id = s.artifact_id
            WHERE at.topic_id = ?
              AND a.published_at >= ?
            GROUP BY date(a.published_at)
            ORDER BY date(a.published_at);
            """,
            (topic_id, cutoff)
        )
        
        return [dict(row) for row in cur.fetchall()]
        
    finally:
        conn.close()


def detect_topic_merges(
    db_path: str,
    window_days: int = 30,
    similarity_threshold: float = 0.85
) -> list[MergeCandidate]:
    """
    Detect potential topic merges.
    
    A merge is detected when:
    1. Two topics have high similarity (> threshold)
    2. Their similarity is increasing over time
    3. They share an increasing number of artifacts
    """
    # Get all topics
    topics = get_trending_topics(db_path, window_days=window_days, limit=1000)
    
    if len(topics) < 2:
        return []
    
    merges: list[MergeCandidate] = []
    
    # Compute pairwise similarities
    for i, topic1 in enumerate(topics):
        for topic2 in topics[i+1:]:
            topic1_id = topic1['id']
            topic2_id = topic2['id']
            
            # Compute current similarity
            current_similarity = compute_topic_similarity(
                topic1_id, topic2_id, db_path
            )
            
            if current_similarity < similarity_threshold:
                continue
            
            # Get historical data for both topics
            history1 = get_topic_artifact_history(topic1_id, db_path, days=window_days)
            history2 = get_topic_artifact_history(topic2_id, db_path, days=window_days)
            
            if not history1 or not history2:
                continue
            
            # Compute similarity trend
            # Compare first half vs second half of window
            mid_point = len(history1) // 2
            if mid_point == 0:
                continue
            
            # Get artifact overlap trend
            overlap_trend = compute_artifact_overlap_trend(
                topic1_id, topic2_id, db_path, window_days
            )
            
            # If similarity is high and overlap is increasing, it's a merge candidate
            if overlap_trend > 0.1:  # Increasing overlap
                confidence_value = current_similarity * 0.7 + min(overlap_trend * 2, 0.3)
                merges.append({
                    'primary_topic': topic1,
                    'secondary_topic': topic2,
                    'current_similarity': current_similarity,
                    'overlap_trend': overlap_trend,
                    'confidence': confidence_value,
                    'event_type': 'merge',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })
    
    # Sort by confidence
    merges.sort(key=lambda x: x["confidence"], reverse=True)
    
    return merges


def detect_topic_splits(
    db_path: str,
    window_days: int = 30,
    diversity_threshold: float = 0.70
) -> List[Dict[str, Any]]:
    """
    Detect potential topic splits.
    
    A split is detected when:
    1. A topic's artifacts become more diverse (lower coherence)
    2. Sub-clusters emerge within the topic
    3. The topic shows decreasing similarity to its historical centroid
    """
    # Get all topics with sufficient artifacts
    conn = connect(db_path)
    try:
        cur = conn.execute(
            """
            SELECT 
                t.id,
                t.name,
                t.taxonomy_path,
                COUNT(DISTINCT at.artifact_id) as artifact_count
            FROM topics t
            JOIN artifact_topics at ON t.id = at.topic_id
            JOIN artifacts a ON at.artifact_id = a.id
            WHERE a.published_at >= date('now', '-{} days')
            GROUP BY t.id
            HAVING COUNT(DISTINCT at.artifact_id) >= 5
            ORDER BY artifact_count DESC;
            """.format(window_days)
        )
        
        topics = [dict(row) for row in cur.fetchall()]
        
    finally:
        conn.close()
    
    splits = []
    
    for topic in topics:
        topic_id = topic['id']
        
        # Get historical centroid (based on first half of window)
        history = get_topic_artifact_history(topic_id, db_path, days=window_days)
        if len(history) < 10:  # Need sufficient history
            continue
        
        mid_point = len(history) // 2
        early_period = history[:mid_point]
        late_period = history[mid_point:]
        
        # Compute coherence scores
        early_coherence = compute_topic_coherence(topic_id, db_path, early_period)
        late_coherence = compute_topic_coherence(topic_id, db_path, late_period)
        
        # If coherence decreased significantly, might be a split
        coherence_drop = early_coherence - late_coherence
        if coherence_drop > 0.2:  # 20% drop in coherence
            # Check for sub-clusters in late period
            sub_clusters = detect_sub_clusters(topic_id, db_path, late_period)
            
            if len(sub_clusters) >= 2:
                splits.append({
                    'primary_topic': topic,
                    'coherence_drop': coherence_drop,
                    'sub_clusters': sub_clusters,
                    'confidence': min(coherence_drop * 2, 0.8) + len(sub_clusters) * 0.1,
                    'event_type': 'split',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })
    
    return sorted(splits, key=lambda x: x['confidence'], reverse=True)


def compute_topic_emergence(
    topic_id: int,
    db_path: str,
    window_days: int = 30
) -> Dict[str, float]:
    """
    Compute emergence metrics for a topic.
    
    Returns:
        - growth_rate: Exponential growth rate
        - acceleration: Rate of growth change
        - velocity: Current growth speed
        - emergence_score: Composite 0-100 score
    """
    history = get_topic_artifact_history(topic_id, db_path, days=window_days)
    
    if len(history) < 7:  # Need at least a week of data
        return {
            'growth_rate': 0.0,
            'acceleration': 0.0,
            'velocity': 0.0,
            'emergence_score': 0.0
        }
    
    # Extract time series data
    counts = [h['artifact_count'] for h in history]
    scores = [h['avg_discovery_score'] or 0 for h in history]
    
    # Compute growth rate (exponential)
    if len(counts) >= 2 and counts[0] > 0:
        growth_rate = (counts[-1] / counts[0]) ** (1 / len(counts)) - 1
    else:
        growth_rate = 0.0
    
    # Compute acceleration (second derivative)
    if len(counts) >= 3:
        # Simple acceleration: difference in differences
        recent_growth = (counts[-1] - counts[len(counts)//2]) / (len(counts)//2)
        early_growth = (counts[len(counts)//2] - counts[0]) / (len(counts)//2)
        acceleration = recent_growth - early_growth
    else:
        acceleration = 0.0
    
    # Compute velocity (recent growth rate)
    if len(counts) >= 2:
        velocity = (counts[-1] - counts[-2]) / 1  # Daily
    else:
        velocity = 0.0
    
    # Composite emergence score (0-100)
    # Normalize components
    norm_growth = min(growth_rate * 100, 50)  # Cap at 50
    norm_accel = max(0, acceleration * 10)    # Boost acceleration
    norm_velocity = min(velocity * 10, 20)    # Cap at 20
    
    # Add score component (higher quality = higher emergence)
    avg_score = sum(scores) / len(scores) if scores else 0
    score_component = avg_score * 0.1  # Up to 10 points
    
    emergence_score = min(100.0, norm_growth + norm_accel + norm_velocity + score_component)
    
    return {
        'growth_rate': growth_rate,
        'acceleration': acceleration,
        'velocity': velocity,
        'emergence_score': emergence_score
    }


def predict_topic_growth(
    topic_id: int,
    db_path: str,
    days_to_predict: int = 14
) -> Dict[str, Any]:
    """
    Predict future growth of a topic using simple linear trend.
    
    Returns prediction with confidence intervals.
    """
    # Get historical data
    history = get_topic_artifact_history(topic_id, db_path, days=60)  # Use 60 days for prediction
    
    if len(history) < 7:  # Need at least 1 week of data (relaxed from 14)
        return {
            'predicted_growth': 0.0,
            'confidence': 0.0,
            'trend': 'insufficient_data',
            'predicted_counts': [],
            'prediction_window_days': days_to_predict
        }
    
    # Extract counts and dates
    counts_arr = np.array([h['artifact_count'] for h in history], dtype=np.float64)
    dates = [datetime.fromisoformat(h['date']) for h in history]
    
    # Avoid log(0)
    log_counts = np.log(np.maximum(counts_arr, 1.0))
    
    # Days since start as x values
    days_from_start = np.array([(d - dates[0]).days for d in dates], dtype=np.float64)
    
    # Linear regression: log(count) = a + b * days
    A = np.vstack([days_from_start, np.ones(len(days_from_start))]).T
    coeffs = np.linalg.lstsq(A, log_counts, rcond=None)[0]
    b = float(coeffs[0])
    a = float(coeffs[1])
    
    # Growth rate (exponential)
    daily_growth_rate = float(np.exp(b) - 1) if not np.isnan(b) else 0.0
    
    # Predict future
    last_day = days_from_start[-1]
    future_days = list(range(last_day + 1, last_day + days_to_predict + 1))
    
    predicted_log_counts = [float(a + b * day) for day in future_days]
    predicted_counts = [float(np.exp(log_c)) for log_c in predicted_log_counts]
    
    # Confidence based on Pearson correlation
    if len(counts_arr) > 2:
        corr_matrix = np.corrcoef(days_from_start, log_counts)
        r_value = float(corr_matrix[0, 1])
        confidence = r_value ** 2 if not np.isnan(r_value) else 0.0
    else:
        confidence = 0.0
    
    # Determine trend
    if daily_growth_rate > 0.05:  # >5% daily growth
        trend = 'rapidly_emerging'
    elif daily_growth_rate > 0.01:  # >1% daily growth
        trend = 'emerging'
    elif daily_growth_rate > -0.01:  # >-1% daily growth (flat)
        trend = 'stable'
    else:
        trend = 'declining'
    
    return {
        'daily_growth_rate': daily_growth_rate,
        'predicted_counts': predicted_counts,
        'confidence': confidence,
        'trend': trend,
        'prediction_window_days': days_to_predict
    }


# Helper functions

def compute_artifact_overlap_trend(
    topic1_id: int,
    topic2_id: int,
    db_path: str,
    window_days: int
) -> float:
    """Compute trend in artifact overlap between two topics."""
    conn = connect(db_path)
    try:
        # Get overlapping artifacts over time
        cur = conn.execute(
            """
            SELECT 
                date(a.published_at) as date,
                COUNT(DISTINCT a.id) as overlap_count
            FROM artifacts a
            JOIN artifact_topics at1 ON a.id = at1.artifact_id
            JOIN artifact_topics at2 ON a.id = at2.artifact_id
            WHERE at1.topic_id = ?
              AND at2.topic_id = ?
              AND a.published_at >= date('now', '-{} days')
            GROUP BY date(a.published_at)
            ORDER BY date(a.published_at);
            """.format(window_days),
            (topic1_id, topic2_id)
        )
        
        overlaps = [row['overlap_count'] for row in cur.fetchall()]
        
        if len(overlaps) < 2:
            return 0.0
        
        # Simple trend: average change per day
        changes: list[float] = [float(overlaps[i+1] - overlaps[i]) for i in range(len(overlaps)-1)]
        return float(sum(changes)) / len(changes)
        
    finally:
        conn.close()


def compute_topic_coherence(
    topic_id: int,
    db_path: str,
    period: List[Dict[str, Any]]
) -> float:
    """Compute coherence score for a topic in a given period."""
    # This is a simplified version - in practice, you'd use
    # more sophisticated coherence metrics like UMass or UCI coherence
    
    if not period:
        return 0.0
    
    # For now, use consistency of artifact scores as proxy
    scores = [p.get('avg_discovery_score', 0) or 0 for p in period]
    
    if not scores:
        return 0.0
    
    # Lower variance = higher coherence
    variance = np.var(scores) if len(scores) > 1 else 0
    coherence = max(0.0, 1.0 - (variance / 1000))  # Normalize
    
    return coherence


def detect_sub_clusters(
    topic_id: int,
    db_path: str,
    period: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Detect sub-clusters within a topic."""
    # Simplified: group artifacts by similarity
    conn = connect(db_path)
    try:
        # Get artifacts for the period
        date_range = [p['date'] for p in period]
        if not date_range:
            return []
        
        cur = conn.execute(
            """
            SELECT 
                a.id,
                a.title,
                a.text
            FROM artifacts a
            JOIN artifact_topics at ON a.id = at.artifact_id
            WHERE at.topic_id = ?
              AND date(a.published_at) IN ({})
            """.format(','.join(f"'{d}'" for d in date_range)),
            (topic_id,)
        )
        
        artifacts = [dict(row) for row in cur.fetchall()]
        
        if len(artifacts) < 3:
            return []
        
        # Simple clustering based on text similarity
        # In practice, use proper clustering (K-means, HDBSCAN)
        clusters = []
        used = set()
        
        for i, art1 in enumerate(artifacts):
            if i in used:
                continue
            
            cluster = [art1]
            used.add(i)
            
            text1 = f"{art1.get('title', '')} {art1.get('text', '')}".strip()
            
            for j, art2 in enumerate(artifacts[i+1:], i+1):
                if j in used:
                    continue
                
                text2 = f"{art2.get('title', '')} {art2.get('text', '')}".strip()
                
                # Simple similarity check
                if len(text1) > 50 and len(text2) > 50:
                    # Check for common keywords (simplified)
                    words1 = set(text1.lower().split())
                    words2 = set(text2.lower().split())
                    common = words1.intersection(words2)
                    
                    # If they share significant keywords, same cluster
                    if len(common) > 5:
                        cluster.append(art2)
                        used.add(j)
            
            if len(cluster) >= 2:
                clusters.append({
                    'artifacts': cluster,
                    'size': len(cluster)
                })
        
        return clusters
        
    finally:
        conn.close()


def store_topic_evolution_event(
    db_path: str,
    event: Dict[str, Any]
) -> int:
    """Store a topic evolution event in the database."""
    conn = connect(db_path)
    try:
        with conn:
            cur = conn.execute(
                """
                INSERT INTO topic_evolution (
                    topic_id,
                    event_type,
                    related_topic_ids,
                    event_strength,
                    event_date,
                    description
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    event['primary_topic']['id'],
                    event['event_type'],
                    json.dumps([t['id'] for t in event.get('sub_clusters', [])] or 
                             [event.get('secondary_topic', {}).get('id')]),
                    event['confidence'],
                    event['timestamp'],
                    f"Detected {event['event_type']} with confidence {event['confidence']:.2f}"
                )
            )
            rowid = cur.lastrowid
            if rowid is None:
                raise RuntimeError("Failed to store topic evolution event")
            return rowid
    finally:
        conn.close()


def update_topic_similarity_matrix(db_path: str) -> None:
    """Update the topic similarity matrix."""
    # Get all topics
    conn = connect(db_path)
    try:
        cur = conn.execute("SELECT id FROM topics;")
        topic_ids = [row['id'] for row in cur.fetchall()]
        
        if len(topic_ids) < 2:
            return
        
        similarities = []
        
        # Compute pairwise similarities
        for i, topic1_id in enumerate(topic_ids):
            for topic2_id in topic_ids[i+1:]:
                similarity = compute_topic_similarity(topic1_id, topic2_id, db_path)
                
                if similarity > 0.5:  # Only store significant similarities
                    similarities.append((topic1_id, topic2_id, similarity))
        
        # Store in database
        with conn:
            # Clear existing similarities
            conn.execute("DELETE FROM topic_similarity;")
            
            # Insert new similarities
            for topic1_id, topic2_id, similarity in similarities:
                conn.execute(
                    """
                    INSERT INTO topic_similarity (topic_id_1, topic_id_2, similarity, computed_at)
                    VALUES (?, ?, ?, ?);
                    """,
                    (topic1_id, topic2_id, similarity, datetime.now(timezone.utc).isoformat())
                )
        
        log.info("Updated topic similarity matrix: %d pairs", len(similarities))
        
    finally:
        conn.close()


def find_related_topics(
    topic_id: int,
    db_path: str,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Find topics related to a given topic."""
    conn = connect(db_path)
    try:
        cur = conn.execute(
            """
            SELECT 
                t.id,
                t.name,
                t.taxonomy_path,
                ts.similarity
            FROM topics t
            JOIN topic_similarity ts ON 
                (t.id = ts.topic_id_1 AND ts.topic_id_2 = ?) OR
                (t.id = ts.topic_id_2 AND ts.topic_id_1 = ?)
            WHERE t.id != ?
            ORDER BY ts.similarity DESC
            LIMIT ?;
            """,
            (topic_id, topic_id, topic_id, limit)
        )
        
        return [dict(row) for row in cur.fetchall()]
        
    finally:
        conn.close()


# Database schema for topic evolution
TOPIC_EVOLUTION_SCHEMA = """
-- Topic evolution events (merges, splits, emergence, decline)
CREATE TABLE IF NOT EXISTS topic_evolution (
    id INTEGER PRIMARY KEY,
    topic_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,        -- 'emerge', 'merge', 'split', 'decline', 'growth'
    related_topic_ids TEXT,          -- JSON array of related topic IDs
    event_strength REAL,             -- 0-1 confidence score
    event_date TEXT NOT NULL,
    description TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(topic_id) REFERENCES topics(id)
);

CREATE INDEX IF NOT EXISTS idx_topic_evolution_topic ON topic_evolution(topic_id);
CREATE INDEX IF NOT EXISTS idx_topic_evolution_type ON topic_evolution(event_type);
CREATE INDEX IF NOT EXISTS idx_topic_evolution_date ON topic_evolution(event_date);

-- Topic similarity matrix
CREATE TABLE IF NOT EXISTS topic_similarity (
    topic_id_1 INTEGER NOT NULL,
    topic_id_2 INTEGER NOT NULL,
    similarity REAL NOT NULL,        -- 0-1 cosine similarity
    computed_at TEXT NOT NULL,
    PRIMARY KEY(topic_id_1, topic_id_2),
    FOREIGN KEY(topic_id_1) REFERENCES topics(id),
    FOREIGN KEY(topic_id_2) REFERENCES topics(id)
);

CREATE INDEX IF NOT EXISTS idx_topic_similarity_score ON topic_similarity(similarity);
CREATE INDEX IF NOT EXISTS idx_topic_similarity_computed ON topic_similarity(computed_at);

-- Topic clusters for hierarchical organization
CREATE TABLE IF NOT EXISTS topic_clusters (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    topic_ids TEXT NOT NULL,         -- JSON array of topic IDs
    centroid_embedding TEXT,         -- Serialized numpy array
    cluster_quality REAL,            -- Silhouette score or similar
    parent_cluster_id INTEGER,       -- For hierarchical clustering
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(parent_cluster_id) REFERENCES topic_clusters(id)
);

CREATE INDEX IF NOT EXISTS idx_topic_clusters_quality ON topic_clusters(cluster_quality);
CREATE INDEX IF NOT EXISTS idx_topic_clusters_parent ON topic_clusters(parent_cluster_id);
"""


def init_topic_evolution_tables(db_path: str) -> None:
    """Initialize topic evolution database tables."""
    conn = connect(db_path)
    try:
        with conn:
            conn.executescript(TOPIC_EVOLUTION_SCHEMA)
        log.info("Initialized topic evolution tables")
    finally:
        conn.close()


async def run_topic_evolution_pipeline(
    db_path: str,
    settings: Any,
    window_days: int = 30
) -> Dict[str, Any]:
    """
    Run the complete topic evolution pipeline.
    
    Returns statistics about detected events.
    """
    config = TopicEvolutionConfig(settings)
    
    if not config.enabled:
        log.info("Topic evolution disabled in configuration")
        return {"status": "disabled"}
    
    log.info("Starting topic evolution pipeline (window: %d days)", window_days)
    
    # Update similarity matrix
    log.info("Updating topic similarity matrix...")
    update_topic_similarity_matrix(db_path)
    
    # Detect merges
    log.info("Detecting topic merges...")
    merges = detect_topic_merges(
        db_path,
        window_days=window_days,
        similarity_threshold=config.merge_threshold
    )
    
    # Detect splits
    log.info("Detecting topic splits...")
    splits = detect_topic_splits(
        db_path,
        window_days=window_days,
        diversity_threshold=config.split_threshold
    )
    
    # Compute emergence for trending topics
    log.info("Computing topic emergence...")
    trending = get_trending_topics(db_path, window_days=window_days, limit=50)
    
    emergence_scores = {}
    for topic in trending:
        emergence = compute_topic_emergence(topic['id'], db_path, window_days)
        emergence_scores[topic['id']] = emergence
    
    # Store evolution events
    events_stored = 0
    for merge in merges:
        store_topic_evolution_event(db_path, dict(merge))
        events_stored += 1
    
    for split in splits:
        store_topic_evolution_event(db_path, split)
        events_stored += 1
    
    log.info("Topic evolution pipeline complete: %d merges, %d splits, %d events stored",
             len(merges), len(splits), events_stored)
    
    return {
        'status': 'completed',
        'merges_detected': len(merges),
        'splits_detected': len(splits),
        'events_stored': events_stored,
        'topics_analyzed': len(trending),
        'window_days': window_days
    }
