# Database Index Optimization Report

**Date**: November 11, 2025  
**Migration**: 9 (Schema Version 9)  
**Status**: ✅ Complete

## Executive Summary

Added 9 composite indexes to optimize critical query patterns across the discovery pipeline, topic evolution analytics, cross-source corroboration, and backtesting workflows. All indexes successfully created and verified.

## Composite Indexes Added

### 1. Top Discoveries Query Optimization ⭐ **CRITICAL**

**Index**: `idx_scores_discovery_artifact` on `scores(discovery_score DESC, artifact_id)`

**Query Pattern**:

```sql
SELECT a.*, s.discovery_score 
FROM artifacts a
JOIN scores s ON s.artifact_id = a.id
ORDER BY s.discovery_score DESC, a.published_at DESC
LIMIT 50;
```

**Impact**: Eliminates full table scan for most frequently accessed API endpoint (`/discoveries`). Enables index-only scan for TOP-N queries.

**Usage**: `db.py:1170` - `get_top_discoveries()`

---

### 2. Topic Timeline Query Optimization ⭐ **HIGH PRIORITY**

**Index**: `idx_artifact_topics_topic_artifact` on `artifact_topics(topic_id, artifact_id)`

**Query Pattern**:

```sql
SELECT a.* 
FROM artifacts a
JOIN artifact_topics at ON at.artifact_id = a.id
WHERE at.topic_id = ?
ORDER BY a.published_at DESC
LIMIT 100;
```

**Impact**: Critical for Phase Two topic evolution analytics. Speeds up topic timeline queries from full table scan to index seek + artifact lookup.

**Usage**: `topic_evolution.py:161-162` - `compute_topic_embedding()`

---

### 3. Citation Graph Source Lookups ⭐ **HIGH PRIORITY**

**Index**: `idx_relationships_source_confidence` on `artifact_relationships(source_artifact_id, confidence DESC)`

**Query Pattern**:

```sql
SELECT ar.*, target_artifact.*
FROM artifact_relationships ar
JOIN artifacts target_artifact ON ar.target_artifact_id = target_artifact.id
WHERE ar.source_artifact_id = ? 
  AND ar.confidence >= 0.80
ORDER BY ar.confidence DESC;
```

**Impact**: Optimizes cross-source corroboration citation graph traversal. Enables confidence-filtered relationships without full table scan.

**Usage**: `db.py:2001-2002` - `get_artifact_relationships(direction='outgoing')`

---

### 4. Citation Graph Target Lookups ⭐ **HIGH PRIORITY**

**Index**: `idx_relationships_target_confidence` on `artifact_relationships(target_artifact_id, confidence DESC)`

**Query Pattern**:

```sql
SELECT ar.*, source_artifact.*
FROM artifact_relationships ar
JOIN artifacts source_artifact ON ar.source_artifact_id = source_artifact.id
WHERE ar.target_artifact_id = ?
  AND ar.confidence >= 0.80
ORDER BY ar.confidence DESC;
```

**Impact**: Optimizes reverse citation lookups (which artifacts cite this one). Critical for citation impact analysis.

**Usage**: `db.py:2008-2011` - `get_artifact_relationships(direction='incoming')`

---

### 5. Time-Filtered Discovery Queries

**Index**: `idx_artifacts_published_source` on `artifacts(published_at DESC, source)`

**Query Pattern**:

```sql
SELECT * FROM artifacts
WHERE published_at >= date('now', '-7 days')
  AND source IN ('arxiv', 'github')
ORDER BY published_at DESC
LIMIT 100;
```

**Impact**: Efficient range scans for time-filtered queries with source filtering. Common in dashboard and recent discoveries endpoints.

**Usage**: `db.py:1144` - `get_top_discoveries()` with time filters

---

### 6. Topic Similarity Forward Lookups

**Index**: `idx_topic_similarity_topic1_score` on `topic_similarity(topic_id_1, similarity DESC)`

**Query Pattern**:

```sql
SELECT topic_id_2, similarity
FROM topic_similarity
WHERE topic_id_1 = ?
ORDER BY similarity DESC
LIMIT 10;
```

**Impact**: Speeds up related topics queries and topic merge detection (similarity >0.85 threshold).

**Usage**: `topic_evolution.py:618` - topic merge/split detection

---

### 7. Topic Similarity Bidirectional Lookups

**Index**: `idx_topic_similarity_topic2_score` on `topic_similarity(topic_id_2, similarity DESC)`

**Query Pattern**:

```sql
SELECT topic_id_1, similarity
FROM topic_similarity
WHERE topic_id_2 = ?
ORDER BY similarity DESC
LIMIT 10;
```

**Impact**: Enables symmetric topic similarity lookups without duplicate storage. Critical for topic clustering.

**Usage**: `topic_evolution.py:687` - topic cluster analysis

---

### 8. Entity Influence Ranking

**Index**: `idx_entities_activity_influence` on `entities(last_activity_date DESC, influence_score DESC)`

**Query Pattern**:

```sql
SELECT * FROM entities
WHERE last_activity_date >= date('now', '-30 days')
ORDER BY influence_score DESC
LIMIT 50;
```

**Impact**: Optimizes researcher profile analytics and "trending researchers" queries with recency filtering.

**Usage**: Researcher ranking API endpoints (Phase Two analytics)

---

### 9. Experiment Run History

**Index**: `idx_experiment_runs_experiment_started` on `experiment_runs(experiment_id, started_at DESC)`

**Query Pattern**:

```sql
SELECT * FROM experiment_runs
WHERE experiment_id = ?
ORDER BY started_at DESC
LIMIT 20;
```

**Impact**: Speeds up backtesting history retrieval and A/B testing trend analysis.

**Usage**: Experiments API (`GET /experiments/{id}/runs`)

---

## Performance Impact Estimates

### Before Optimization

- **Top Discoveries Query**: ~150-300ms (full table scan on artifacts + scores JOIN)
- **Topic Timeline Query**: ~200-400ms (full artifact_topics + artifacts JOIN)
- **Citation Graph Traversal**: ~100-250ms per level (full artifact_relationships scan)
- **Time-Filtered Queries**: ~80-150ms (sequential scan with date filtering)

### After Optimization (Expected)

- **Top Discoveries Query**: ~10-30ms (index-only scan + artifact lookup by ID)
- **Topic Timeline Query**: ~15-40ms (index seek on topic_id + artifact fetch)
- **Citation Graph Traversal**: ~5-15ms per level (index seek + confidence filter)
- **Time-Filtered Queries**: ~8-20ms (index range scan + source filter)

### Overall Improvement

- **p95 API Latency**: ~60-75% reduction for discovery endpoints
- **Database Query Performance**: 5-20x faster for indexed queries
- **Throughput**: 3-5x more concurrent requests supported

---

## Verification Commands

### Check All Composite Indexes Created

```bash
sqlite3 var/signal_harvester.db "
SELECT name, tbl_name 
FROM sqlite_master 
WHERE type='index' 
  AND (name LIKE '%topic_artifact%' 
    OR name LIKE '%source_confidence%' 
    OR name LIKE '%target_confidence%'
    OR name LIKE '%published_source%'
    OR name LIKE '%topic1_score%'
    OR name LIKE '%topic2_score%'
    OR name LIKE '%activity_influence%'
    OR name LIKE '%experiment_started%'
    OR name LIKE '%discovery_artifact%')
ORDER BY tbl_name, name;
"
```

**Expected Output** (9 indexes):

```
idx_relationships_source_confidence|artifact_relationships
idx_relationships_target_confidence|artifact_relationships
idx_artifact_topics_topic_artifact|artifact_topics
idx_artifacts_published_source|artifacts
idx_entities_activity_influence|entities
idx_experiment_runs_experiment_started|experiment_runs
idx_scores_discovery_artifact|scores
idx_topic_similarity_topic1_score|topic_similarity
idx_topic_similarity_topic2_score|topic_similarity
```

### Verify Schema Version

```bash
sqlite3 var/signal_harvester.db "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1;"
# Expected: 9
```

### Analyze Query Plan (Example - Top Discoveries)

```bash
sqlite3 var/signal_harvester.db "
EXPLAIN QUERY PLAN
SELECT a.*, s.discovery_score 
FROM artifacts a
JOIN scores s ON s.artifact_id = a.id
ORDER BY s.discovery_score DESC
LIMIT 50;
"
```

**Expected Plan**:

```
SCAN s USING INDEX idx_scores_discovery_artifact
SEARCH a USING INTEGER PRIMARY KEY (rowid=?)
```

*(Index scan on scores, then direct primary key lookup on artifacts)*

---

## Migration Details

### Migration File

- **Path**: `src/signal_harvester/db.py` (Migration 9, lines 868-963)
- **Applied**: November 11, 2025
- **Schema Version**: 3 → 9

### Rollback Procedure

```python
# Not recommended, but if needed:
import sqlite3
conn = sqlite3.connect('var/signal_harvester.db')
cursor = conn.cursor()

# Drop all composite indexes
cursor.execute("DROP INDEX IF EXISTS idx_scores_discovery_artifact;")
cursor.execute("DROP INDEX IF EXISTS idx_artifact_topics_topic_artifact;")
cursor.execute("DROP INDEX IF EXISTS idx_relationships_source_confidence;")
cursor.execute("DROP INDEX IF EXISTS idx_relationships_target_confidence;")
cursor.execute("DROP INDEX IF EXISTS idx_artifacts_published_source;")
cursor.execute("DROP INDEX IF EXISTS idx_topic_similarity_topic1_score;")
cursor.execute("DROP INDEX IF EXISTS idx_topic_similarity_topic2_score;")
cursor.execute("DROP INDEX IF EXISTS idx_entities_activity_influence;")
cursor.execute("DROP INDEX IF EXISTS idx_experiment_runs_experiment_started;")

# Revert schema version
cursor.execute("UPDATE schema_version SET version = 8 WHERE version = 9;")
conn.commit()
conn.close()
```

---

## Next Steps

1. **Query Performance Profiling** (Section 6.3 Task 2)
   - Benchmark actual query performance with indexes
   - Measure p95 latencies for top 10 API endpoints
   - Validate 60-75% latency reduction estimate
   - Document findings in profiling report

2. **Redis Caching Layer** (Section 6.3 Task 3)
   - Cache discovery results (TTL 1h)
   - Cache topic trends (TTL 1h)
   - Cache entity profiles (TTL 24h)
   - Target >80% cache hit rate

3. **Connection Pooling** (Section 6.3 Task 5)
   - Configure SQLAlchemy pool_size and max_overflow
   - Test concurrent request handling
   - Monitor connection pool exhaustion

4. **Production Monitoring** (Section 6.1)
   - Add Prometheus metrics for query latencies
   - Track slow query log (queries >100ms)
   - Monitor index usage statistics
   - Set up alerts for p95 latency >500ms

---

## References

- **Architecture Document**: `ARCHITECTURE_AND_READINESS.md` Section 6.3 (Performance Optimization)
- **Database Module**: `src/signal_harvester/db.py`
- **Query Patterns**: Analyzed via `grep_search` across codebase
- **Index Design**: SQLite documentation on composite indexes and covering indexes
- **Performance Targets**: p95 API latency <500ms, database query performance <100ms for 95% of queries

---

## Approval & Sign-off

- ✅ **Migration Applied**: November 11, 2025
- ✅ **Indexes Verified**: All 9 composite indexes created successfully
- ✅ **Schema Version**: 9 (current)
- ✅ **Tests Passing**: No schema-related test failures
- ✅ **Production Ready**: Indexes use `IF NOT EXISTS` for idempotency

**Status**: Ready for profiling and production deployment.
