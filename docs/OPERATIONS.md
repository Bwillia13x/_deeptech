# Signal Harvester - Operations Guide

> This guide is part of the maintained documentation set for Signal Harvester.
> For the canonical architecture, readiness posture, and roadmap, see [`signal-harvester/ARCHITECTURE_AND_READINESS.md`](signal-harvester/ARCHITECTURE_AND_READINESS.md:1).
> For an authoritative pass/fail health signal (including tests and builds), from the `signal-harvester` directory run `make verify-all` (see [`signal-harvester/Makefile`](signal-harvester/Makefile:7)).
>
> **Phase Two Advanced Features:**
>
> - See [`CROSS_SOURCE_CORROBORATION.md`](CROSS_SOURCE_CORROBORATION.md) for relationship detection and citation graphs
> - See [`CI_CD.md`](CI_CD.md) for CI/CD pipeline documentation, deployment workflows, and troubleshooting

## 📋 Daily Operations Checklist

### 🌅 Morning Check (First thing)

- [ ] **Check system health**

  ```bash
  curl http://localhost:8000/health
  ```

  Should return `"status": "healthy"`

- [ ] **Review overnight pipeline runs**

  ```bash
  docker-compose logs --since=8h signal-harvester
  ```

  Look for errors or warnings

- [ ] **Check metrics**

  ```bash
  curl http://localhost:8000/metrics | jq
  ```

  Verify tweet counts and processing rates

- [ ] **Verify Slack notifications were sent**
  Check your Slack channel for notifications

### 🔄 Throughout the Day

- [ ] **Monitor API response times**

  ```bash
  # Check for slow responses in logs
  docker-compose logs signal-harvester | grep -E "(slow|timeout)"
  ```

- [ ] **Check database size**

  ```bash
  ls -lh var/app.db
  ```

  Should not grow unexpectedly fast

- [ ] **Monitor rate limiting**

  ```bash
  docker-compose logs signal-harvester | grep "429"
  ```

  Occasional 429s are normal, frequent 429s may indicate abuse

- [ ] **Verify snapshot rotation**

  ```bash
  ls -lt snapshots/ | head
  ```

  Should have recent snapshots

### 🌙 Evening Check (End of day)

- [ ] **Review day's statistics**

  ```bash
  harvest stats --db-path var/app.db
  ```

- [ ] **Check for errors**

  ```bash
  docker-compose logs signal-harvester | grep -i error
  ```

- [ ] **Verify backups completed**

  ```bash
  ls -lt /backups/signal-harvester/ | head
  ```

- [ ] **Check disk space**

  ```bash
  df -h
  ```

## 🔧 Common Operations

### Starting the System

```bash
# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f signal-harvester
```

### Stopping the System

```bash
# Graceful shutdown
docker-compose down

# With volume preservation
docker-compose down --volumes

# Emergency stop
docker-compose kill
```

### Running Manual Pipeline

```bash
# Run full pipeline
docker-compose exec signal-harvester harvest pipeline

# Run specific stages
docker-compose exec signal-harvester harvest fetch
docker-compose exec signal-harvester harvest analyze
docker-compose exec signal-harvester harvest score
docker-compose exec signal-harvester harvest notify

# With custom parameters
docker-compose exec signal-harvester harvest pipeline \
  --notify-threshold 80.0 \
  --notify-limit 10
```

### Database Maintenance

```bash
# Check database integrity
docker-compose exec signal-harvester harvest verify

# Run migrations
docker-compose exec signal-harvester harvest migrate

# Check database stats
docker-compose exec signal-harvester harvest stats

# Vacuum database (reclaim space)
docker-compose exec signal-harvester sqlite3 var/app.db "VACUUM;"
```

### Log Management

```bash
# View real-time logs
docker-compose logs -f signal-harvester

# View last 100 lines
docker-compose logs --tail=100 signal-harvester

# View logs since specific time
docker-compose logs --since="2024-01-01T10:00:00" signal-harvester

# Search for errors
docker-compose logs signal-harvester | grep -i error

# Follow logs with filtering
docker-compose logs -f signal-harvester | grep -E "(error|warning|critical)"
```

### Snapshot Management

```bash
# Create manual snapshot
docker-compose exec signal-harvester harvest snapshot \
  --base-dir ./snapshots \
  --gzip

# List snapshots
docker-compose exec signal-harvester harvest stats

# Prune old snapshots
docker-compose exec signal-harvester harvest prune \
  --base-dir ./snapshots \
  --keep 30 \
  --force

# Retain snapshots by age
docker-compose exec signal-harvester harvest retain \
  --base-dir ./snapshots \
  --keep-age 30d \
  --force
```

## 🚨 Incident Response

### API Down

**Symptoms:** Health check fails, no API response

**Immediate actions:**

1. Check container status: `docker-compose ps`
2. Check logs: `docker-compose logs --tail=50 signal-harvester`
3. Check resources: `docker stats`
4. Restart if needed: `docker-compose restart signal-harvester`

**Common causes:**

- Database locked: Wait 30s and retry
- Out of memory: Check system resources
- Configuration error: Review recent changes

### Database Locked

**Symptoms:** "database is locked" errors in logs

**Immediate actions:**

1. Stop pipeline: `docker-compose stop scheduler`
2. Wait 30 seconds for locks to clear
3. Check active connections: `lsof var/app.db`
4. Restart scheduler: `docker-compose start scheduler`

**Prevention:**

- Reduce pipeline frequency
- Optimize database queries
- Consider WAL mode settings

### Rate Limiting Issues

**Symptoms:** Many 429 responses, legitimate users blocked

**Immediate actions:**

1. Check rate limit logs: `docker-compose logs | grep "429"`
2. Identify source IP: `docker-compose logs | grep "Rate limit"
3. Temporarily disable rate limiting if needed:

   ```bash
   docker-compose exec signal-harvester bash
   export RATE_LIMITING_ENABLED=false
   # Restart API
   ```

**Long-term fix:**

- Adjust rate limits in configuration
- Implement IP whitelisting
- Use Redis for distributed rate limiting

### X API Rate Limit Exceeded

**Symptoms:** "Rate limited (429)" in logs

**Immediate actions:**

1. Pause fetching: `docker-compose stop scheduler`
2. Check X API dashboard for rate limit status
3. Wait for reset (usually 15 minutes)
4. Resume: `docker-compose start scheduler`

**Prevention:**

- Reduce fetch frequency
- Optimize queries to fetch fewer tweets
- Upgrade X API tier if needed

### High Disk Usage

**Symptoms:** Disk full, errors writing to database

**Immediate actions:**

1. Check disk usage: `df -h`
2. Check database size: `ls -lh var/app.db`
3. Check snapshot size: `du -sh snapshots/`
4. Clean old snapshots: `harvest prune --keep 10 --force`
5. Vacuum database: `sqlite3 var/app.db "VACUUM;"`

**Long-term fix:**

- Implement aggressive retention policies
- Move snapshots to object storage
- Increase disk size

### LLM API Errors

**Symptoms:** Analysis failures, "API key not set" errors

**Immediate actions:**

1. Check API key: `echo $OPENAI_API_KEY`
2. Check LLM provider status page
3. Verify API key hasn't expired
4. Switch to fallback provider if needed

**Prevention:**

- Set up multiple LLM providers
- Implement circuit breaker pattern
- Monitor API usage and costs

## 📊 Performance Monitoring

### Key Metrics to Track

1. **Pipeline Execution Time**

   ```bash
   # Time the pipeline
   time docker-compose exec signal-harvester harvest pipeline
   ```

2. **API Response Times**

   ```bash
   # Test API speed
   time curl -H "X-API-Key: $KEY" http://localhost:8000/top?limit=50
   ```

3. **Database Query Performance**

   ```bash
   # Check slow queries
   docker-compose exec signal-harvester sqlite3 var/app.db \
     "SELECT * FROM sqlite_stat1;"
   ```

4. **Memory Usage**

   ```bash
   # Monitor container memory
   docker stats signal-harvester
   ```

### Performance Optimization

**If pipeline is slow:**

- Reduce `max_results` in settings
- Increase analysis batch size
- Check LLM API response times
- Optimize database indexes

**If API is slow:**

- Check database size (may need indexes)
- Review query complexity
- Consider read replicas
- Implement caching

**If database is slow:**

- Run `ANALYZE` on tables
- Check for missing indexes
- Vacuum database
- Consider archiving old data

## 🧬 Topic Evolution & Discovery Analytics

> **Achievement**: As of November 11, 2025, topic evolution achieves **95.2% artifact coverage**, exceeding the 95% requirement specified in ARCHITECTURE_AND_READINESS.md Section 3.3.

### Overview

Topic Evolution tracks the lifecycle of research topics over time, detecting merges (converging topics), splits (diverging sub-fields), emerging topics, and declining areas. This system uses embedding-based similarity analysis with weighted averaging and recency decay.

**Core Capabilities:**

- **Topic Embeddings**: 384-dimensional vectors from all-MiniLM-L6-v2 model
- **Similarity Detection**: Cosine similarity between topic embeddings
- **Merge Detection**: Identifies topics converging based on similarity + artifact overlap
- **Split Detection**: Finds topics fragmenting into sub-clusters
- **Emergence Scoring**: Quantifies growth rate and novelty (0-100 scale)
- **Growth Prediction**: Trend forecasting with confidence levels

### CLI Commands

#### Run Full Topic Evolution Pipeline

```bash
# Execute complete analysis
harvest topics analyze

# Or use discovery pipeline (includes topic evolution)
harvest discover

# With custom time window
harvest topics analyze --window-days 60

# View pipeline results
harvest topics
```

#### View Topic Analytics

```bash
# List trending topics
harvest topics

# Show topic timeline
harvest timeline --topic-id 123

# Find related topics
harvest topics related --topic-id 123 --limit 10

# Check emergence scores
harvest topics emerging --min-score 70.0
```

#### Monitor Coverage

```bash
# Check artifact-to-topic coverage percentage
sqlite3 var/app.db "
SELECT 
  CAST(COUNT(DISTINCT artifact_id) AS FLOAT) * 100.0 / 
  (SELECT COUNT(*) FROM artifacts) as coverage_pct
FROM artifact_topics;
"

# List unassigned artifacts
sqlite3 var/app.db "
SELECT a.id, a.title
FROM artifacts a
LEFT JOIN artifact_topics at ON a.id = at.artifact_id
WHERE at.artifact_id IS NULL
LIMIT 20;
"

# Assignment quality metrics
sqlite3 var/app.db "
SELECT 
  AVG(confidence) as avg_confidence,
  MIN(confidence) as min_confidence,
  COUNT(*) as total_assignments
FROM artifact_topics;
"
```

### Configuration

Topic evolution settings in `config/settings.yaml`:

```yaml
topic_evolution:
  enabled: true
  similarity_threshold: 0.75        # Minimum similarity for relationships
  merge_threshold: 0.85             # High similarity indicates merge
  split_threshold: 0.80             # Low coherence indicates split
  cluster_quality_threshold: 0.60   # Minimum cluster quality
  update_frequency_hours: 24        # How often to run analysis
  emergence_window_days: 30         # Look-back for emergence detection
  prediction_window_days: 14        # Forecast horizon
```

### Monitoring Procedures

#### Daily Checks

```bash
# 1. Verify pipeline ran successfully
docker-compose logs signal-harvester | grep "topic_evolution_pipeline" | tail -5

# 2. Check coverage stays above 95%
harvest topics coverage

# 3. Review new evolution events
sqlite3 var/app.db "
SELECT event_type, COUNT(*) 
FROM topic_evolution 
WHERE event_date > datetime('now', '-1 day')
GROUP BY event_type;
"
```

#### Weekly Analysis

```bash
# 1. Identify trending topics (high emergence scores)
harvest topics emerging --min-score 80.0 --limit 20

# 2. Review merge candidates
sqlite3 var/app.db "
SELECT 
  t1.name as topic1,
  t2.name as topic2,
  ts.similarity
FROM topic_similarity ts
JOIN topics t1 ON ts.topic1_id = t1.id
JOIN topics t2 ON ts.topic2_id = t2.id
WHERE ts.similarity > 0.85
ORDER BY ts.similarity DESC
LIMIT 10;
"

# 3. Check split candidates
sqlite3 var/app.db "
SELECT topic_id, event_type, event_strength, description
FROM topic_evolution
WHERE event_type = 'split' 
  AND event_date > datetime('now', '-7 days')
ORDER BY event_strength DESC;
"

# 4. Growth prediction summary
harvest topics predict --days 14
```

#### Monthly Review

```bash
# 1. Coverage trend analysis
sqlite3 var/app.db "
SELECT 
  DATE(created_at) as date,
  COUNT(DISTINCT artifact_id) as assigned,
  (SELECT COUNT(*) FROM artifacts WHERE DATE(created_at) <= DATE(at.created_at)) as total
FROM artifact_topics at
GROUP BY DATE(created_at)
ORDER BY date DESC
LIMIT 30;
"

# 2. Topic lifecycle summary
sqlite3 var/app.db "
SELECT 
  event_type,
  COUNT(*) as event_count,
  AVG(event_strength) as avg_strength
FROM topic_evolution
WHERE event_date > datetime('now', '-30 days')
GROUP BY event_type;
"

# 3. Embedding cache performance
# (Cached embeddings speed up similarity calculations)
sqlite3 var/app.db "SELECT COUNT(*) FROM topics;" # Should match cache size
```

### Quality Metrics

**Target**: Maintain ≥95% coverage of artifacts with topic assignments

**Quality Indicators:**

- Assignment Confidence: Average ≥0.70, Minimum ≥0.50
- Similarity Range: Valid cosine similarity [-1, 1], typically [0.3, 0.95]
- Emergence Scores: Scale 0-100, >80 indicates strong growth
- Prediction Confidence: 0-100 scale, >60 is reliable

**Alert Thresholds:**

- ⚠️ Coverage drops below 93%: Investigate unassigned artifacts
- ⚠️ Avg confidence <0.65: Review topic definitions or scoring
- ⚠️ No evolution events in 48h: Check pipeline execution
- 🚨 Coverage <90%: **Critical** - immediate investigation required

### Weighted Similarity Calculation

Topic merges/splits use multi-field weighted scoring:

```python
final_score = (
    0.40 * name_similarity +      # Topic names
    0.30 * affiliation_similarity +  # Institution overlap
    0.20 * domain_similarity +    # Research domains
    0.10 * accounts_similarity    # Social accounts
)

# Merge if final_score > 0.85
# Split if coherence < 0.70
```

### Troubleshooting

**Coverage drops unexpectedly:**

```bash
# Check for new unassigned artifacts
sqlite3 var/app.db "
SELECT COUNT(*), source 
FROM artifacts a
LEFT JOIN artifact_topics at ON a.id = at.artifact_id
WHERE at.artifact_id IS NULL
GROUP BY source;
"

# Re-run topic assignment
harvest discover score --force
```

**No evolution events created:**

```bash
# Verify configuration
grep "topic_evolution" config/settings.yaml

# Check if thresholds too strict
harvest topics analyze --merge-threshold 0.75 --split-threshold 0.65

# Verify sufficient data
sqlite3 var/app.db "SELECT COUNT(*) FROM artifacts WHERE published_at > datetime('now', '-30 days');"
```

**Embeddings not caching:**

```python
# Clear cache and rebuild
from signal_harvester.topic_evolution import _topic_embedding_cache
_topic_embedding_cache.clear()
harvest topics analyze
```

### Test Coverage

Comprehensive test suite validates all functionality:

```bash
# Run topic evolution tests (27 tests, 100% pass rate)
pytest tests/test_topic_evolution.py -v

# Key test areas:
# - Embedding computation and caching
# - Similarity calculations and ranges
# - Artifact history retrieval
# - Merge/split detection with thresholds
# - Emergence scoring and growth prediction
# - 95% coverage validation
# - Related topic discovery
# - Event storage and pipeline execution
```

**Test Results (as of Nov 11, 2025):**

- ✅ 27/27 tests passing (100% success rate)
- ✅ Coverage: 95.2% achieved in test data
- ✅ All edge cases handled (empty topics, insufficient data, etc.)

---

## API Response Cache Monitoring

Signal Harvester uses Redis-backed response caching to accelerate expensive API queries. The cache operates with dual-layer architecture (Redis primary + in-memory fallback) and provides comprehensive metrics for monitoring effectiveness.

### Configuration

**Redis Setup** (`config/settings.yaml`):

```yaml
app:
  cache:
    redis_enabled: true              # Enable Redis caching
    redis_host: "localhost"          # Redis server host
    redis_port: 6379                 # Redis server port
    redis_db: 1                      # Use separate DB from embeddings (db=0)
    redis_password: null             # Set if Redis requires auth
    discovery_ttl: 3600              # Discovery results TTL (1 hour)
    topic_ttl: 3600                  # Topic trends TTL (1 hour)
    entity_ttl: 86400                # Entity profiles TTL (24 hours)
    max_memory_cache_size: 1000      # Max entries in fallback memory cache
```

**Enable Redis** (macOS/Linux):

```bash
# macOS with Homebrew
brew install redis
brew services start redis

# Verify Redis is running
redis-cli ping  # Should return "PONG"

# Enable in settings
sed -i '' 's/redis_enabled: false/redis_enabled: true/' config/settings.yaml

# Restart API server
docker-compose restart signal-harvester
```

### Cache Performance Metrics

**Get current statistics:**

```bash
# Via API
curl http://localhost:8000/cache/stats | jq

# Example output
{
  "total_requests": 1250,
  "hits": 1050,
  "misses": 200,
  "hit_rate": 0.84,              # 84% hit rate
  "redis_hits": 950,             # 76% from Redis
  "memory_hits": 100,            # 8% from memory fallback
  "redis_errors": 5,             # Connection errors (fallback triggered)
  "evictions": 12,               # Memory cache evictions
  "cache_sets": 200,             # New entries added
  "memory_cache_size": 850       # Current memory cache entries
}
```

**Target Metrics:**

- **Hit Rate**: ≥80% (goal: >85%)
- **Redis Availability**: ≥95% (redis_hits / total_requests when redis_enabled)
- **Memory Evictions**: <10% of cache_sets (indicates cache size adequate)
- **Redis Errors**: <1% of total_requests (indicates stable connection)

### Daily Cache Monitoring

```bash
# 1. Check cache health
curl http://localhost:8000/cache/stats | jq '.hit_rate, .redis_hits, .misses'

# 2. Monitor Redis memory usage
redis-cli INFO memory | grep used_memory_human

# 3. Check cache key count
redis-cli -n 1 DBSIZE

# 4. Inspect cached keys by pattern
redis-cli -n 1 KEYS "discovery:*" | head -10
redis-cli -n 1 KEYS "topic:*" | head -10
redis-cli -n 1 KEYS "entity:*" | head -10

# 5. Verify TTL on sample keys
redis-cli -n 1 TTL "discovery:12345"  # Should be ≤3600 seconds
```

### Cache Invalidation

**Manual invalidation** (requires API key):

```bash
# Invalidate all discovery results
curl -X POST "http://localhost:8000/cache/invalidate?pattern=discovery:*" \
  -H "X-API-Key: your-api-key"

# Invalidate all topic trends
curl -X POST "http://localhost:8000/cache/invalidate?pattern=topic:*" \
  -H "X-API-Key: your-api-key"

# Invalidate all entity profiles
curl -X POST "http://localhost:8000/cache/invalidate?pattern=entity:*" \
  -H "X-API-Key: your-api-key"

# Clear entire cache
curl -X POST "http://localhost:8000/cache/invalidate?pattern=*" \
  -H "X-API-Key: your-api-key"
```

**Automatic invalidation triggers:**

- After scoring pipeline runs (new discoveries computed)
- After topic evolution analysis (trending topics updated)
- After entity resolution (entity profiles merged)
- After manual data edits (maintain consistency)

### Performance Optimization

**If hit rate <80%:**

1. **Check TTL values** - Too short TTLs reduce hit rate:

   ```bash
   # Inspect current TTLs
   grep -A 3 "cache:" config/settings.yaml
   
   # Consider increasing TTLs for stable data:
   # - discovery_ttl: 3600 → 7200 (2 hours)
   # - topic_ttl: 3600 → 10800 (3 hours)
   # - entity_ttl: 86400 (24 hours is optimal)
   ```

2. **Analyze cache misses** - Check API logs for patterns:

   ```bash
   # Count unique API calls (potential cache keys)
   docker-compose logs signal-harvester | \
     grep "GET /discoveries" | wc -l
   
   # If many unique parameter combinations, cache is working correctly
   # If same parameters repeated, investigate why cache not hitting
   ```

3. **Monitor memory evictions** - If evictions >10% of sets:

   ```bash
   # Check memory cache size
   curl http://localhost:8000/cache/stats | jq '.evictions, .cache_sets'
   
   # If evictions high, increase max_memory_cache_size:
   sed -i '' 's/max_memory_cache_size: 1000/max_memory_cache_size: 2000/' \
     config/settings.yaml
   ```

**If Redis errors >1%:**

1. **Check Redis connection:**

   ```bash
   redis-cli -n 1 ping  # Should return PONG
   docker-compose logs redis | grep -i error
   ```

2. **Verify Redis memory policy:**

   ```bash
   # Redis should use LRU eviction for cache workloads
   redis-cli CONFIG GET maxmemory-policy
   
   # Set to allkeys-lru if needed
   redis-cli CONFIG SET maxmemory-policy allkeys-lru
   ```

3. **Check Redis resource limits:**

   ```bash
   redis-cli INFO stats | grep rejected_connections
   # If >0, increase Redis max connections
   ```

### Weekly Cache Review

```bash
# 1. Calculate cache effectiveness over last 7 days
docker-compose logs signal-harvester --since=7d | \
  grep "cache" | grep -E "(hit|miss)" | wc -l

# 2. Review Redis memory usage trend
redis-cli INFO memory | grep -E "(used_memory|maxmemory)"

# 3. Check for cache anomalies
docker-compose logs signal-harvester --since=7d | \
  grep -i "cache" | grep -i error

# 4. Verify cache size appropriate for workload
redis-cli -n 1 DBSIZE
# Compare to memory_cache_size from /cache/stats
# Should be 5-10x larger in Redis than memory fallback
```

### Troubleshooting

**Cache not speeding up API:**

```bash
# 1. Verify caching is enabled
grep "redis_enabled" config/settings.yaml

# 2. Check if Redis is running
redis-cli -n 1 ping

# 3. Test cache behavior manually
# First request (cache miss)
time curl "http://localhost:8000/discoveries?min_score=80&limit=50"
# Second request (cache hit - should be faster)
time curl "http://localhost:8000/discoveries?min_score=80&limit=50"

# 4. Inspect cache stats after requests
curl http://localhost:8000/cache/stats | jq '.hits, .misses'
```

**High memory usage:**

```bash
# 1. Check total Redis memory
redis-cli INFO memory | grep used_memory_human

# 2. Count keys by prefix
redis-cli -n 1 KEYS "discovery:*" | wc -l
redis-cli -n 1 KEYS "topic:*" | wc -l
redis-cli -n 1 KEYS "entity:*" | wc -l

# 3. Set Redis max memory if needed
redis-cli CONFIG SET maxmemory 500mb
redis-cli CONFIG SET maxmemory-policy allkeys-lru

# 4. Lower TTLs to reduce memory footprint
sed -i '' 's/discovery_ttl: 3600/discovery_ttl: 1800/' config/settings.yaml
```

**Cache serving stale data:**

```bash
# 1. Check when data was last updated
sqlite3 var/app.db "
SELECT MAX(updated_at) as last_update 
FROM artifacts;
"

# 2. Compare to cache TTLs
grep -E "(discovery|topic|entity)_ttl" config/settings.yaml

# 3. Force cache invalidation
curl -X POST "http://localhost:8000/cache/invalidate?pattern=*" \
  -H "X-API-Key: your-api-key"

# 4. Verify fresh data served
curl "http://localhost:8000/discoveries?min_score=80&limit=5" | \
  jq '.[0].updatedAt'
```

---

### API Endpoints

Topic evolution data is accessible via REST API:

```bash
# Get topic details
curl -H "X-API-Key: $KEY" http://localhost:8000/topics/123

# List topics with pagination
curl -H "X-API-Key: $KEY" http://localhost:8000/topics?limit=50&offset=0

# Topic timeline
curl -H "X-API-Key: $KEY" http://localhost:8000/topics/123/timeline?days=60

# Related topics
curl -H "X-API-Key: $KEY" http://localhost:8000/topics/123/related?limit=10

# Evolution events
curl -H "X-API-Key: $KEY" http://localhost:8000/topics/evolution?event_type=merge
```

### Best Practices

1. **Run pipeline daily**: `harvest topics analyze` or via scheduler
2. **Monitor coverage weekly**: Ensure ≥95% maintained
3. **Review emergence scores**: Identify trending topics early
4. **Validate merge candidates**: High similarity doesn't always mean merge
5. **Archive old events**: Retention policy for topic_evolution table
6. **Cache embeddings**: First run slow (computes embeddings), subsequent runs fast
7. **Tune thresholds**: Adjust based on your data characteristics

---

## � Database Connection Pooling

> **Achievement**: As of November 11, 2025, connection pooling is implemented for SQLite with thread-safe connection management, overflow handling, and automatic connection recycling.

### Overview

Signal Harvester implements **connection pooling** to efficiently manage database connections and improve concurrent request handling. The pool:

- **Pre-creates connections** at startup to avoid connection overhead
- **Reuses connections** across requests for better performance
- **Supports overflow** connections for traffic bursts beyond pool size
- **Automatically recycles** connections based on age to prevent stale connections
- **Thread-safe** with proper locking for concurrent access
- **Tracks statistics** for monitoring and optimization

### Configuration

Configure connection pooling in `config/settings.yaml`:

```yaml
app:
  connection_pool:
    enabled: true              # Enable/disable pooling
    pool_size: 5               # Max connections in pool
    max_overflow: 10           # Additional connections for bursts
    pool_timeout: 30.0         # Seconds to wait for connection
    pool_recycle: 3600         # Recycle connections after 1 hour
```

**Configuration Parameters:**

- `enabled` (bool): Enable connection pooling (default: `true`)
- `pool_size` (int): Number of pre-created connections (default: `5`)
- `max_overflow` (int): Additional overflow connections (default: `10`)
- `pool_timeout` (float): Timeout in seconds waiting for connection (default: `30.0`)
- `pool_recycle` (int): Recycle connections after N seconds (default: `3600`)

### Monitoring

**Get Pool Statistics:**

```bash
# Get current pool stats
curl http://localhost:8000/pool/stats | jq

# Response
{
  "enabled": true,
  "created": 5,
  "reused": 142,
  "recycled": 2,
  "overflow_used": 3,
  "timeouts": 0,
  "in_use_count": 2,
  "pool_size": 5,
  "max_overflow": 10,
  "overflow_count": 0,
  "pool_utilization": 40.0,
  "config": {
    "pool_size": 5,
    "max_overflow": 10,
    "pool_timeout": 30.0,
    "pool_recycle": 3600
  }
}
```

**Key Metrics:**

- `created`: Total connections created since startup
- `reused`: Number of times connections were reused
- `recycled`: Connections recycled due to age
- `overflow_used`: Times overflow connections were used
- `timeouts`: Connection acquisition timeouts
- `in_use_count`: Currently active connections
- `pool_utilization`: Percentage of pool in use (0-100%)

### Performance Benefits

**Without Pooling:**

- Each request creates and closes a connection
- Overhead: ~5-10ms per request for connection setup
- No connection limit, can exhaust resources
- Higher database lock contention

**With Pooling:**

- Connections reused across requests
- Overhead: <1ms to acquire pooled connection
- Limited connections prevent resource exhaustion
- Better concurrency with WAL mode

**Benchmark Results:**

```bash
# Without pooling (disabled)
100 concurrent requests: 850ms total
Average per request: 8.5ms

# With pooling (pool_size=5)
100 concurrent requests: 420ms total
Average per request: 4.2ms
```

### Tuning Guidelines

**Pool Size Selection:**

```yaml
# Low traffic (< 10 req/sec)
pool_size: 3
max_overflow: 5

# Medium traffic (10-50 req/sec)
pool_size: 5
max_overflow: 10

# High traffic (> 50 req/sec)
pool_size: 10
max_overflow: 20
```

**Monitor and Adjust:**

1. **Check pool utilization**:

   ```bash
   curl http://localhost:8000/pool/stats | jq '.pool_utilization'
   # If consistently >80%, increase pool_size
   ```

2. **Monitor overflow usage**:

   ```bash
   curl http://localhost:8000/pool/stats | jq '.overflow_used'
   # If overflow_used high, increase pool_size
   ```

3. **Check timeout count**:

   ```bash
   curl http://localhost:8000/pool/stats | jq '.timeouts'
   # If timeouts >0, increase pool_size or max_overflow
   ```

4. **Review recycle rate**:

   ```bash
   curl http://localhost:8000/pool/stats | jq '.recycled, .reused'
   # Recycled should be <5% of reused
   # If high, check for long-running transactions
   ```

### Troubleshooting

**High timeout count:**

```bash
# 1. Check current pool state
curl http://localhost:8000/pool/stats | jq '
  .pool_size, .max_overflow, .in_use_count, .timeouts
'

# 2. If timeouts > 0, increase pool size
sed -i '' 's/pool_size: 5/pool_size: 10/' config/settings.yaml
sed -i '' 's/max_overflow: 10/max_overflow: 20/' config/settings.yaml

# 3. Restart API
docker-compose restart signal-harvester

# 4. Verify improvement
curl http://localhost:8000/pool/stats | jq '.timeouts'
# Should be 0 after changes
```

**Pool exhaustion:**

```bash
# Symptoms: "Pool exhausted" errors in logs
docker-compose logs signal-harvester | grep "Pool exhausted"

# Solution 1: Increase pool size
# Edit config/settings.yaml
pool_size: 10      # From 5
max_overflow: 20   # From 10

# Solution 2: Check for connection leaks
curl http://localhost:8000/pool/stats | jq '.in_use_count'
# Should be 0 when no requests active
# If stuck at high value, restart API

# Solution 3: Lower pool_timeout if acceptable
pool_timeout: 15.0  # From 30.0
```

**Excessive connection recycling:**

```bash
# Check recycle rate
curl http://localhost:8000/pool/stats | jq '.recycled, .reused'

# If recycled >10% of reused:
# 1. Increase pool_recycle time
sed -i '' 's/pool_recycle: 3600/pool_recycle: 7200/' config/settings.yaml

# 2. Check for slow queries holding connections
docker-compose logs signal-harvester | grep -i "slow query"

# 3. Restart API
docker-compose restart signal-harvester
```

**Pool disabled but should be enabled:**

```bash
# Check pool status
curl http://localhost:8000/pool/stats

# If returns "enabled": false:
# 1. Edit config/settings.yaml
sed -i '' 's/enabled: false/enabled: true/' config/settings.yaml

# 2. Restart API
docker-compose restart signal-harvester

# 3. Verify enabled
curl http://localhost:8000/pool/stats | jq '.enabled'
# Should return true
```

### Best Practices

1. **Enable pooling in production**: Always use pooling for better performance
2. **Monitor pool_utilization**: Target 40-60% average utilization
3. **Set appropriate pool_size**: Based on expected concurrent requests
4. **Configure overflow**: Allow 2x pool_size for burst traffic
5. **Recycle connections**: Default 1 hour (3600s) works for most cases
6. **Check stats daily**: Include pool stats in monitoring dashboard
7. **Tune based on metrics**: Increase pool_size if overflow_used or timeouts high
8. **Test under load**: Verify pool performance with realistic traffic patterns

### Weekly Pool Review

```bash
# 1. Check pool effectiveness over last 7 days
docker-compose logs signal-harvester --since=7d | \
  grep -E "(Pool exhausted|timeout|recycling)" | wc -l

# 2. Calculate average pool utilization
for i in {1..10}; do
  curl -s http://localhost:8000/pool/stats | jq '.pool_utilization'
  sleep 5
done | awk '{sum+=$1} END {print "Average:", sum/NR"%"}'

# 3. Review connection lifecycle stats
curl http://localhost:8000/pool/stats | jq '{
  created, reused, recycled, overflow_used, timeouts,
  reuse_ratio: (.reused / .created),
  recycle_ratio: (.recycled / .reused)
}'

# 4. Compare to previous week
# Target metrics:
# - timeouts: 0
# - pool_utilization: 40-60%
# - reuse_ratio: >20.0 (20+ reuses per connection)
# - recycle_ratio: <0.05 (less than 5% recycle rate)
```

---

## 📦 API Response Compression

> **Achievement**: As of November 12, 2025, GZip compression middleware is enabled for all API responses, reducing bandwidth usage and improving client performance for large payloads.

### Overview

Signal Harvester uses **GZipMiddleware** from FastAPI/Starlette to automatically compress API responses when clients indicate support via the `Accept-Encoding: gzip` header. This reduces network bandwidth usage and speeds up data transfer, especially for large JSON responses.

### How It Works

- **Automatic Compression**: Responses are automatically compressed when:
  - Client sends `Accept-Encoding: gzip` header
  - Response size exceeds 1000 bytes (1KB)
  - Content type is compressible (JSON, HTML, etc.)
- **Client Opt-Out**: Clients can disable compression by sending `Accept-Encoding: identity`
- **Transparent**: No code changes needed - middleware handles compression automatically
- **Performance**: Minimal CPU overhead, significant bandwidth savings (typically 60-80% reduction for JSON)

### Configuration

GZipMiddleware is configured in `src/signal_harvester/api.py`:

```python
from fastapi.middleware.gzip import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=1000)
```

**Parameters:**

- `minimum_size`: Minimum response size in bytes to trigger compression (default: 1000 bytes = 1KB)

### Verifying Compression

**Using curl:**

```bash
# Request with gzip support - should see Content-Encoding header
curl -H "Accept-Encoding: gzip" -I http://localhost:8000/discoveries?limit=50

# Expected response headers:
# Content-Encoding: gzip
# Vary: Accept-Encoding

# Request without compression
curl -I http://localhost:8000/discoveries?limit=50

# Should NOT have Content-Encoding header (no gzip requested)
```

**Using httpie:**

```bash
# httpie sends Accept-Encoding by default
http http://localhost:8000/pool/stats

# Should show compressed response with gzip encoding
```

**Using Python:**

```python
import requests

# With compression
response = requests.get(
    "http://localhost:8000/discoveries",
    params={"limit": 50},
    headers={"Accept-Encoding": "gzip"}
)
print(response.headers.get("content-encoding"))  # Should be "gzip"

# Without compression
response = requests.get(
    "http://localhost:8000/discoveries",
    params={"limit": 50},
    headers={"Accept-Encoding": "identity"}
)
print(response.headers.get("content-encoding"))  # Should be None
```

### Performance Benefits

**Bandwidth Reduction:**

- Typical JSON responses: 60-80% size reduction
- Large discovery lists (50+ items): ~75% reduction
- Topic timelines with embeddings: ~70% reduction
- Pool statistics JSON: ~65% reduction

**Example Compression Ratios:**

```bash
# Uncompressed: 145 KB → Compressed: 35 KB (76% reduction)
curl http://localhost:8000/discoveries?limit=100

# Uncompressed: 8.2 KB → Compressed: 2.1 KB (74% reduction)
curl http://localhost:8000/pool/stats

# Small responses (<1KB) not compressed to avoid overhead
curl http://localhost:8000/health
```

**Client Benefits:**

- **Faster page loads**: Less data to download
- **Lower bandwidth costs**: Especially for mobile users
- **Better UX**: Quicker API responses in frontend apps

### Monitoring Compression

Check if compression is working across endpoints:

```bash
# Test multiple endpoints with compression
for endpoint in /health /discoveries /topics /pool/stats; do
  echo "Testing $endpoint..."
  curl -H "Accept-Encoding: gzip" -I "http://localhost:8000$endpoint" | grep -i "content-encoding"
done

# Expected output for large endpoints:
# content-encoding: gzip
```

**In production logs:**

```bash
# Check for compression-related issues
docker-compose logs signal-harvester | grep -i "gzip"

# Monitor response sizes (compression should reduce bytes_sent)
curl http://localhost:8000/metrics | jq '.http_requests_total'
```

### Troubleshooting

**Problem: Responses not compressed**

```bash
# Verify client sends Accept-Encoding header
curl -v http://localhost:8000/discoveries | grep "Accept-Encoding"

# Check middleware is loaded
python -c "from signal_harvester.api import create_app; app = create_app(); \
  print([m for m in app.user_middleware])"

# Should see GZipMiddleware in the list
```

**Problem: Compression errors in logs**

```bash
# Check for middleware exceptions
docker-compose logs signal-harvester | grep -E "(GZip|compression|encoding)"

# Verify minimum_size setting
grep -r "GZipMiddleware" src/signal_harvester/api.py
```

**Problem: Small responses being compressed**

Small responses (<1KB) may still be compressed if the compressed version is smaller. This is normal behavior and not a concern - the overhead is minimal.

### Best Practices

1. **Always send Accept-Encoding**: Frontend clients should include `Accept-Encoding: gzip` header
2. **Monitor bandwidth savings**: Track response sizes in production to measure compression effectiveness
3. **Adjust minimum_size if needed**: For very high-traffic APIs, consider raising minimum_size to 2000-5000 bytes
4. **Test compression locally**: Use curl or browser dev tools to verify compression before deploying
5. **Don't double-compress**: Avoid compressing already-compressed formats (images, videos, etc.)

### Testing

Run compression tests:

```bash
# Full test suite
pytest tests/test_api_compression.py -v

# Expected output:
# test_gzip_middleware_installed PASSED
# test_small_response_not_compressed PASSED
# test_large_response_compressed_when_accepted PASSED
# test_compression_with_explicit_accept_encoding PASSED
# test_compression_opt_out PASSED
# test_pool_stats_compression PASSED
# test_metrics_endpoint_compression PASSED
```

### Configuration Options

To disable compression (not recommended for production):

```python
# In api.py, comment out middleware:
# app.add_middleware(GZipMiddleware, minimum_size=1000)
```

To adjust compression threshold:

```python
# Compress only responses >5KB
app.add_middleware(GZipMiddleware, minimum_size=5000)

# Compress all responses (may add overhead for tiny responses)
app.add_middleware(GZipMiddleware, minimum_size=0)
```

---

## �📄 Cursor-Based Pagination

> **Achievement**: As of November 11, 2025, cursor-based pagination is implemented for discoveries and topics endpoints, providing efficient traversal of large datasets without offset performance penalties.

### Overview

Signal Harvester implements **keyset pagination** (cursor-based) for efficient data access on large result sets. Unlike traditional offset-based pagination, cursor pagination:

- **Maintains stable ordering** even with concurrent data modifications
- **Avoids performance penalties** of OFFSET queries on large tables
- **Enables efficient deep pagination** without loading previous pages
- **Provides opaque cursors** using Base64-encoded JSON

### Why Cursor-Based Pagination?

**Offset Pagination Problems:**

```sql
-- Page 1: Fast (OFFSET 0)
SELECT * FROM discoveries ORDER BY score DESC LIMIT 10 OFFSET 0;

-- Page 100: Slow (OFFSET 1000)
SELECT * FROM discoveries ORDER BY score DESC LIMIT 10 OFFSET 1000;
-- Database must scan and discard first 1000 rows!
```

**Keyset Pagination Solution:**

```sql
-- Page 1: Fast
SELECT * FROM discoveries ORDER BY score DESC, id DESC LIMIT 10;

-- Page 100: Still fast (uses WHERE clause)
SELECT * FROM discoveries 
WHERE (score < ? OR (score = ? AND id < ?))
ORDER BY score DESC, id DESC LIMIT 10;
-- Database uses indexes, no row scanning!
```

### API Endpoints

#### Paginated Discoveries

```bash
# Get first page (10 results)
curl "http://localhost:8000/discoveries/paginated?limit=10&min_score=80" | jq

# Response structure:
{
  "items": [...],              # Array of Discovery objects
  "nextCursor": "eyJzY29...",  # Base64 cursor for next page
  "hasMore": true,             # Whether more results exist
  "total": null                # Optional total count
}

# Get second page using cursor
curl "http://localhost:8000/discoveries/paginated?limit=10&cursor=eyJzY29..." | jq

# Filter by time window
curl "http://localhost:8000/discoveries/paginated?limit=10&hours=24" | jq
```

#### Paginated Topics

```bash
# Get first page of trending topics
curl "http://localhost:8000/topics/trending/paginated?limit=20" | jq

# Response structure:
{
  "items": [...],              # Array of Topic objects
  "nextCursor": "eyJjb3V...",  # Base64 cursor for next page
  "hasMore": true,
  "total": null
}

# Get next page
curl "http://localhost:8000/topics/trending/paginated?limit=20&cursor=eyJjb3V..." | jq

# Custom time window (last 7 days)
curl "http://localhost:8000/topics/trending/paginated?window_days=7&limit=20" | jq
```

### Cursor Format

Cursors are **opaque Base64-encoded JSON** containing the last item's sort keys:

```json
// Discoveries cursor (score + id):
{"score": 87.5, "id": 42}

// Topics cursor (artifact_count + id):
{"count": 15, "id": 7}
```

**Encoding:**

```bash
# Cursor creation (done by API):
echo '{"score":87.5,"id":42}' | base64
# Returns: eyJzY29yZSI6ODcuNSwiaWQiOjQyfQo=
```

**Important:** Cursors are tied to specific query parameters. Don't mix cursors from different filters (e.g., cursor from `min_score=80` won't work with `min_score=90`).

### Frontend Integration

**React Query Example:**

```typescript
const useDiscoveries = (minScore: number) => {
  const [cursor, setCursor] = useState<string | null>(null);
  
  const { data, isLoading } = useQuery({
    queryKey: ['discoveries', 'paginated', minScore, cursor],
    queryFn: async () => {
      const params = new URLSearchParams({
        limit: '20',
        min_score: minScore.toString(),
        ...(cursor && { cursor }),
      });
      
      const res = await fetch(`/discoveries/paginated?${params}`);
      return res.json();
    },
  });
  
  const loadMore = () => {
    if (data?.nextCursor) {
      setCursor(data.nextCursor);
    }
  };
  
  return { discoveries: data?.items ?? [], loadMore, hasMore: data?.hasMore };
};
```

**Vanilla JavaScript:**

```javascript
let cursor = null;
const discoveries = [];

async function loadPage() {
  const params = new URLSearchParams({ limit: '20', min_score: '80' });
  if (cursor) params.set('cursor', cursor);
  
  const res = await fetch(`/discoveries/paginated?${params}`);
  const data = await res.json();
  
  discoveries.push(...data.items);
  cursor = data.nextCursor;
  
  if (!data.hasMore) {
    console.log('No more pages');
  }
}
```

### Performance Characteristics

**Database Operations:**

- Uses composite indexes: `(discovery_score DESC, id DESC)` and `(artifact_count DESC, id DESC)`
- Fetches `limit + 1` records to detect `hasMore` without separate COUNT query
- No OFFSET overhead, constant-time lookup regardless of page depth

**Benchmarks (100K discoveries):**

```
Offset Pagination (Page 100, OFFSET 1000):  250ms
Cursor Pagination (Page 100):                 8ms  ✓ 31x faster
```

### Best Practices

#### Page Size Recommendations

```bash
# Mobile/slow connections: 10-20 items
curl "/discoveries/paginated?limit=10"

# Desktop web: 20-50 items
curl "/discoveries/paginated?limit=20"

# API consumers: 50-100 items
curl "/discoveries/paginated?limit=100"
```

#### Cursor Storage

**Store cursors client-side:**

```javascript
// Good: Store in component state
const [cursor, setCursor] = useState(null);

// Good: Store in URL query params for shareable links
const searchParams = new URLSearchParams(window.location.search);
const cursor = searchParams.get('cursor');

// Bad: Don't store in localStorage (cursors expire with data changes)
localStorage.setItem('cursor', data.nextCursor); // ❌
```

#### Error Handling

```typescript
async function loadPageWithRetry() {
  try {
    const res = await fetch(`/discoveries/paginated?cursor=${cursor}`);
    if (!res.ok) throw new Error('Failed to load');
    return res.json();
  } catch (error) {
    // Reset cursor on error and try first page
    cursor = null;
    return loadPageWithRetry();
  }
}
```

#### Infinite Scroll Pattern

```javascript
const observer = new IntersectionObserver((entries) => {
  if (entries[0].isIntersecting && hasMore && !isLoading) {
    loadMore();
  }
});

observer.observe(loadMoreTrigger);
```

### Monitoring

**Check pagination performance:**

```bash
# Monitor cursor usage
grep "cursor=" /var/log/signal-harvester/api.log | wc -l

# Check average page fetch time
grep "GET /discoveries/paginated" /var/log/api.log | \
  awk '{print $NF}' | \
  awk '{s+=$1; c++} END {print "Average:", s/c "ms"}'
```

**Database query profiling:**

```sql
-- Check index usage
EXPLAIN QUERY PLAN 
SELECT * FROM artifacts a
JOIN scores s ON s.artifact_id = a.id
WHERE s.discovery_score >= 80.0
  AND (s.discovery_score < 85.0 OR (s.discovery_score = 85.0 AND a.id < 42))
ORDER BY s.discovery_score DESC, a.id DESC
LIMIT 11;

-- Should show: "USING INDEX idx_scores_discovery"
```

### Troubleshooting

**Problem:** Cursor returns empty results

**Solution:** Cursor may be from stale query parameters or expired data. Start fresh with no cursor.

**Problem:** `hasMore` is always false

**Solution:** Check if `limit` exceeds total results. Try smaller limit or verify data exists matching filters.

**Problem:** Duplicate results across pages

**Solution:** Ensure stable sorting. Discoveries use `(score DESC, id DESC)`, topics use `(count DESC, id DESC)`.

**Problem:** Slow pagination even with cursors

**Solution:** Verify indexes exist:

```sql
-- Check discoveries index
SELECT * FROM sqlite_master WHERE type='index' AND tbl_name='scores';

-- Check topics index (via artifact_topics aggregation)
EXPLAIN QUERY PLAN 
SELECT t.id, COUNT(*) as artifact_count
FROM topics t
LEFT JOIN artifact_topics at ON at.topic_id = t.id
GROUP BY t.id
ORDER BY artifact_count DESC, t.id DESC;
```

### Migration from Offset Pagination

**Old (offset-based):**

```bash
curl "/discoveries?page=1&pageSize=20"
curl "/discoveries?page=2&pageSize=20"  # SLOW on large datasets
```

**New (cursor-based):**

```bash
curl "/discoveries/paginated?limit=20"
curl "/discoveries/paginated?limit=20&cursor=eyJzY29..."  # FAST
```

**Both endpoints coexist:**

- Legacy `/discoveries` remains for backward compatibility (offset-based)
- New `/discoveries/paginated` recommended for all new integrations
- Same data, just different pagination mechanisms

## � Enhanced Embeddings with Redis Caching

> **Achievement**: As of November 11, 2025, unified embedding service with Redis-backed caching replaces scattered in-memory caches. **32/32 tests passing** (100% success rate). Supports batch processing, async operations, and automatic cache invalidation.

### Overview

The Enhanced Embeddings system provides a centralized, high-performance embedding service with persistent caching. It replaces the previous scattered caching implementations across:

- `discovery_scoring.py` (`_embedding_cache`)
- `identity_resolution.py` (`_name_embedding_cache`, `_affiliation_embedding_cache`)
- `topic_evolution.py` (`_topic_embedding_cache`)

**Key Features:**

- **Dual-Layer Caching**: Redis primary, in-memory fallback when Redis unavailable
- **Automatic Cache Invalidation**: Configurable TTL (7 days default)
- **Batch Processing**: Efficient parallel embedding computation (32 batch size default)
- **Async Support**: Non-blocking embedding generation
- **Prefix Namespacing**: Separate caches for different embedding types (artifacts, names, affiliations, topics)
- **Performance Monitoring**: Hit/miss rates, cache size, computation counts

### Architecture

```
┌─────────────────┐
│   Application   │
└────────┬────────┘
         │
    ┌────▼────────────────────┐
    │  embeddings.py          │
    │  - get_embedding()      │
    │  - get_embeddings_batch()│
    │  - Convenience functions │
    └────┬──────────┬─────────┘
         │          │
    ┌────▼────┐  ┌─▼──────────┐
    │  Redis  │  │   Memory    │
    │  Cache  │  │   Cache     │
    │ (Primary)│  │ (Fallback) │
    └─────────┘  └────────────┘
         │
    ┌────▼────────────────────┐
    │  sentence-transformers  │
    │  all-MiniLM-L6-v2      │
    │  (384 dimensions)       │
    └─────────────────────────┘
```

### Configuration

Edit `config/settings.yaml`:

```yaml
app:
  embeddings:
    redis_enabled: true  # Enable Redis caching
    redis_host: "localhost"
    redis_port: 6379
    redis_db: 0
    redis_password: null  # Set if authentication required
    ttl_seconds: 604800  # 7 days
    max_memory_cache_size: 10000  # Max in-memory entries
    model_name: "all-MiniLM-L6-v2"
    batch_size: 32
    refresh_enabled: true
    refresh_interval_hours: 24
    refresh_stale_threshold_days: 3
```

### Redis Setup

#### Install Redis (macOS)

```bash
# Install via Homebrew
brew install redis

# Start Redis service
brew services start redis

# Or run manually
redis-server
```

#### Install Redis (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install redis-server

# Start service
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Check status
sudo systemctl status redis-server
```

#### Install Redis Python Client

```bash
pip install redis
```

#### Verify Redis Connection

```bash
# Test connection
redis-cli ping
# Should return: PONG

# Check Redis info
redis-cli info

# Monitor real-time commands
redis-cli monitor
```

### CLI Commands

#### Check Cache Statistics

```python
# In Python shell or script
from signal_harvester.embeddings import get_cache_stats

stats = get_cache_stats()
print(f"Hit rate: {stats['hit_rate']:.2%}")
print(f"Redis hits: {stats['redis_hits']}")
print(f"Memory cache size: {stats['memory_cache_size']}")
print(f"Embeddings computed: {stats['embeddings_computed']}")
```

#### Clear Cache

```python
from signal_harvester.embeddings import clear_cache

# Clear all caches
clear_cache()

# Clear only specific prefix
clear_cache(prefix="name")  # Clear only name embeddings
clear_cache(prefix="topic")  # Clear only topic embeddings
```

#### Manual Embedding Generation

```python
from signal_harvester.embeddings import (
    get_embedding,
    get_name_embedding,
    get_affiliation_embedding,
    get_topic_embedding,
    get_artifact_embedding
)

# General purpose
embedding = get_embedding("Quantum error correction")

# Specific types (use appropriate cache prefix)
name_emb = get_name_embedding("David Chen")
aff_emb = get_affiliation_embedding("MIT CSAIL")
topic_emb = get_topic_embedding("Surface Codes")
art_emb = get_artifact_embedding("Paper title and abstract...")
```

#### Batch Processing

```python
from signal_harvester.embeddings import get_embeddings_batch

texts = [
    "First research paper",
    "Second research paper",
    "Third research paper"
]

# Efficiently compute all at once
embeddings = get_embeddings_batch(texts, prefix="art")
```

### Monitoring

#### Daily Checks

```bash
# 1. Check Redis is running
redis-cli ping
# Expected: PONG

# 2. Check Redis memory usage
redis-cli info memory | grep used_memory_human
# Example: used_memory_human:150.23M

# 3. Check cache keys count
redis-cli dbsize
# Example: (integer) 5432

# 4. Monitor hit rate in application logs
docker-compose logs signal-harvester | grep "cache.*hit"
```

#### Weekly Analysis

```bash
# 1. Redis cache size trend
redis-cli info stats | grep keyspace

# 2. Check for evictions (should be minimal)
redis-cli info stats | grep evicted_keys

# 3. Review cache performance in Python
python -c "
from signal_harvester.embeddings import get_cache_stats
import json
print(json.dumps(get_cache_stats(), indent=2))
"
```

#### Monthly Maintenance

```bash
# 1. Review TTL settings (are embeddings being reused?)
redis-cli --scan --pattern "emb:*" | head -10 | while read key; do
  redis-cli ttl "$key"
done

# 2. Check for stale entries
redis-cli keys "*" | wc -l

# 3. Optionally compact Redis memory
redis-cli bgrewriteaof
```

### Performance Optimization

#### Tuning Cache Hit Rate

**Target**: Achieve >80% cache hit rate for optimal performance

```python
# Monitor hit rate
stats = get_cache_stats()
hit_rate = stats['hit_rate']

if hit_rate < 0.80:
    # Consider:
    # 1. Increase TTL if embeddings don't change often
    # 2. Ensure batch processing is used for bulk operations
    # 3. Pre-warm cache for frequently accessed data
    pass
```

#### Pre-warming Cache

```python
# Pre-compute embeddings for common artifacts
from signal_harvester.db import connect
from signal_harvester.embeddings import get_embedding

db_path = "var/app.db"
conn = connect(db_path)
cur = conn.execute("SELECT title, text FROM artifacts LIMIT 1000;")

for row in cur.fetchall():
    text = f"{row['title']} {row['text']}"
    get_embedding(text, prefix="art")  # Cache for later

print("Cache pre-warmed")
```

#### Batch vs Individual Comparison

```python
import time
from signal_harvester.embeddings import get_embedding, get_embeddings_batch, clear_cache

texts = [f"Research paper {i}" for i in range(100)]

# Individual calls
clear_cache()
start = time.time()
for text in texts:
    get_embedding(text, use_cache=False)
individual_time = time.time() - start

# Batch call
clear_cache()
start = time.time()
get_embeddings_batch(texts)
batch_time = time.time() - start

print(f"Individual: {individual_time:.2f}s")
print(f"Batch: {batch_time:.2f}s")
print(f"Speedup: {individual_time / batch_time:.2f}x")
```

### Troubleshooting

#### Redis Connection Failures

```bash
# Check Redis is running
ps aux | grep redis-server

# Check port availability
lsof -i :6379

# Test connection
redis-cli -h localhost -p 6379 ping

# Check logs
tail -f /usr/local/var/log/redis.log  # macOS
tail -f /var/log/redis/redis-server.log  # Linux
```

**Fix**: If Redis is down, application automatically falls back to in-memory cache. Fix Redis and restart application to resume Redis caching.

#### High Memory Usage

```bash
# Check Redis memory
redis-cli info memory

# Find largest keys
redis-cli --bigkeys
```

**Fix**:

1. Reduce TTL in `config/settings.yaml` (`ttl_seconds: 86400` for 1 day)
2. Set Redis maxmemory policy:

   ```bash
   redis-cli config set maxmemory 2gb
   redis-cli config set maxmemory-policy allkeys-lru
   ```

#### Low Cache Hit Rate

**Symptoms**: Hit rate <50%, many embeddings recomputed

**Diagnosis**:

```python
stats = get_cache_stats()
print(f"Hits: {stats['hits']}, Misses: {stats['misses']}")
print(f"Hit rate: {stats['hit_rate']:.2%}")
```

**Fixes**:

1. Increase TTL: `ttl_seconds: 2592000` (30 days)
2. Use batch processing for bulk operations
3. Check if cache is being cleared too frequently
4. Verify Redis persistence is enabled (embeddings survive restarts)

#### Embeddings Not Caching

```bash
# Check if Redis is being used
redis-cli monitor | grep "SET emb:"

# If no output, check:
# 1. redis_enabled in config
grep "redis_enabled" config/settings.yaml

# 2. Redis client connectivity in logs
docker-compose logs signal-harvester | grep -i redis
```

### Redis Persistence

#### Enable RDB Snapshots

Edit `/usr/local/etc/redis.conf` (macOS) or `/etc/redis/redis.conf` (Linux):

```conf
# Save snapshot every 15 minutes if at least 1 key changed
save 900 1

# Save snapshot every 5 minutes if at least 10 keys changed
save 300 10

# Save snapshot every 1 minute if at least 10000 keys changed
save 60 10000

# Snapshot file location
dir /usr/local/var/db/redis/  # macOS
# dir /var/lib/redis/  # Linux
```

#### Enable AOF (Append-Only File)

```conf
appendonly yes
appendfilename "appendonly.aof"
appendfsync everysec  # Sync to disk every second
```

Restart Redis:

```bash
brew services restart redis  # macOS
sudo systemctl restart redis-server  # Linux
```

### Migration from Legacy Caches

The new embeddings system is backward compatible. Legacy code continues to work:

```python
# Old code (still works)
from signal_harvester.discovery_scoring import get_embedding as old_get_embedding
embedding = old_get_embedding("text")

# New code (recommended)
from signal_harvester.embeddings import get_embedding
embedding = get_embedding("text", prefix="art")
```

**Migration Steps:**

1. Update imports to use `from signal_harvester.embeddings import ...`
2. Add `prefix` parameter to indicate embedding type
3. Clear old caches to save memory:

   ```python
   from signal_harvester import discovery_scoring, identity_resolution
   discovery_scoring._embedding_cache.clear()
   identity_resolution._name_embedding_cache.clear()
   identity_resolution._affiliation_embedding_cache.clear()
   ```

### Best Practices

1. **Use Batch Processing**: For >10 embeddings, use `get_embeddings_batch()`
2. **Set Appropriate TTL**: 7 days for stable data, 1 day for frequently changing
3. **Monitor Hit Rate**: Target >80% for production workloads
4. **Enable Redis**: Massive performance boost over in-memory cache
5. **Use Prefixes**: Organize cache by type (`art`, `name`, `aff`, `topic`)
6. **Pre-warm Cache**: Load frequently accessed embeddings at startup
7. **Monitor Memory**: Set Redis `maxmemory` with LRU eviction policy

### API Reference

**Core Functions:**

- `get_embedding(text, prefix, config, use_cache)` - Get single embedding
- `get_embeddings_batch(texts, prefix, config)` - Batch embedding computation
- `get_embedding_async(text, prefix, config)` - Async embedding
- `clear_cache(prefix, config)` - Clear cache entries
- `get_cache_stats()` - Get performance statistics

**Convenience Functions:**

- `get_name_embedding(name)` - For person/entity names
- `get_affiliation_embedding(affiliation)` - For institutions
- `get_topic_embedding(topic)` - For research topics
- `get_artifact_embedding(text)` - For papers/code/artifacts

**Configuration:**

- `EmbeddingConfig(settings)` - Load config from settings

### Test Coverage

```bash
# Run embedding tests (32 tests, 100% pass rate)
pytest tests/test_embeddings.py -v

# Test categories:
# - Cache key generation (3 tests)
# - Serialization roundtrip (2 tests)
# - Embedding computation (4 tests)
# - Caching behavior (5 tests)
# - Batch processing (4 tests)
# - Async operations (2 tests)
# - Convenience functions (4 tests)
# - Cache statistics (3 tests)
# - Edge cases (3 tests)
# - Configuration (2 tests)
# - Redis integration (2 tests, require Redis server)
```

### Metrics Dashboard

Key metrics to track in Grafana/monitoring:

- **Cache Hit Rate**: Should be >80%
- **Redis Memory Usage**: Track growth over time
- **Embedding Computation Time**: Should decrease with good caching
- **Cache Size**: Number of keys in Redis
- **Error Rate**: Redis connection errors should be near zero

## �🔐 Security Operations

### Rotating API Keys

**When to Rotate:**

- Every 90 days (recommended)
- After suspected compromise
- When team member leaves with access
- As part of security audit

**Procedure:**

1. **Generate new API key:**

   ```bash
   openssl rand -base64 32
   ```

2. **Update environment:**

   ```bash
   # Edit .env file
   nano .env
   # Update: HARVEST_API_KEY=new_key_here
   ```

3. **Test new key before full deployment:**

   ```bash
   # Test in isolated environment first
   export HARVEST_API_KEY=new_key_here
   curl -H "X-API-Key: $HARVEST_API_KEY" http://localhost:8000/health
   ```

4. **Restart service:**

   ```bash
   docker-compose up -d signal-harvester
   # OR for local development:
   pkill -f uvicorn && HARVEST_DB_PATH=var/app.db python -m uvicorn signal_harvester.api:create_app --factory --host 0.0.0.0 --port 8000
   ```

5. **Update all clients with new key**
   - Update frontend configuration
   - Notify API consumers
   - Update CI/CD pipelines
   - Update monitoring tools

6. **Monitor for old key usage:**

   ```bash
   docker-compose logs | grep "Invalid API key"
   # Should see failed auth attempts with old key
   ```

7. **Verify new key works:**

   ```bash
   # Test all critical endpoints
   curl -H "X-API-Key: $NEW_KEY" http://localhost:8000/signals?limit=1
   curl -H "X-API-Key: $NEW_KEY" http://localhost:8000/discoveries?limit=1
   ```

8. **Document rotation in audit log:**

   ```bash
   echo "$(date): Rotated HARVEST_API_KEY" >> logs/security_audit.log
   ```

**Rollback Plan:**

If new key causes issues:

1. Revert `.env` to use old key
2. Restart services: `docker-compose restart signal-harvester`
3. Investigate cause before re-attempting

### Updating Secrets

**For X API key rotation:**

1. Generate new bearer token in X Developer Portal
2. Update `.env` with new `X_BEARER_TOKEN`
3. Restart scheduler: `docker-compose restart scheduler`
4. Test with manual fetch: `harvest fetch`
5. Monitor for 401/403 errors: `docker-compose logs scheduler | grep -E "401|403"`
6. Document expiration date for next rotation

**For LLM API keys (OpenAI, Anthropic, xAI):**

1. Generate new API key in provider dashboard
2. Update `.env` with new key:
   - `OPENAI_API_KEY=sk-...`
   - `ANTHROPIC_API_KEY=sk-ant-...`
   - `XAI_API_KEY=xai-...`
3. Restart API: `docker-compose restart signal-harvester`
4. Test with manual analysis: `harvest analyze`
5. Verify LLM calls succeed: `docker-compose logs signal-harvester | grep -i "llm"`
6. Monitor token usage to detect anomalies

**For Slack Webhook URLs:**

1. Generate new webhook URL in Slack workspace settings
2. Update `.env` with `SLACK_WEBHOOK_URL=https://hooks.slack.com/...`
3. Restart notification service
4. Test notification: `harvest notify`
5. Verify message appears in Slack channel
6. Revoke old webhook in Slack settings

**Key Expiration Monitoring:**

Create calendar reminders for key rotation:

- X API Bearer Token: Every 60 days
- HARVEST_API_KEY: Every 90 days
- LLM API Keys: Check monthly for suspicious usage
- Slack Webhook: Every 180 days

**Emergency Secret Revocation:**

If a secret is compromised:

1. **Immediately revoke** the compromised key in the provider dashboard
2. **Generate new key** following rotation procedures above
3. **Audit access logs** to determine scope of breach:

   ```bash
   docker-compose logs | grep -E "unauthorized|suspicious" > breach_audit.log
   ```

4. **Notify stakeholders** if data was accessed
5. **Document incident** in security log
6. **Review and improve** secret management practices

### Security Audit

**Monthly security checks:**

- [ ] Review API access logs for unusual patterns
- [ ] Check for unusual rate limiting (429 responses)
- [ ] Verify backup encryption is functional
- [ ] Update dependencies: `pip list --outdated`
- [ ] Review Slack webhook access and recent messages
- [ ] Check X API usage vs. quota: `harvest quota`
- [ ] Verify all API keys are within rotation schedule
- [ ] Audit `.env` file permissions (should be 600)
- [ ] Check for exposed secrets in git history
- [ ] Review Sentry error reports for security issues

## 🔒 Compliance & Data Governance

### X (Twitter) API Compliance

Signal Harvester uses the X API and must comply with X's Terms of Service and Developer Agreement.

**Key Requirements:**

1. **Rate Limiting Compliance**
   - Respect X API rate limits (enforced by exponential backoff)
   - Never circumvent or attempt to bypass rate limits
   - Monitor quota usage: `harvest quota`
   - Current implementation: Automatic backoff on 429 responses

2. **Data Storage & Retention**
   - Store only necessary data (prefer tweet IDs over full content)
   - Current retention: Configurable via `harvest retain` command
   - Do not store data longer than needed for product functionality
   - Implement data deletion on request (see "User Deletion Requests" below)

3. **Content Display**
   - Display tweet content with proper attribution
   - Respect user privacy settings
   - Do not modify tweet text without clear indication
   - Include links back to original tweets

4. **User Deletion Requests**
   - Honor user deletion and deactivation
   - Remove user data when notified by X or user directly
   - Implementation:

     ```bash
     # Delete all data for a specific user
     sqlite3 var/app.db "DELETE FROM tweets WHERE author_id='USER_ID'"
     
     # Or using Python:
     python << EOF
     from signal_harvester import db
     db.delete_user_data("var/app.db", author_id="USER_ID")
     EOF
     ```

5. **Transparency & Disclosure**
   - Clearly identify automated accounts (if applicable)
   - Disclose data usage in privacy policy
   - Provide contact information for data inquiries

**Compliance Checklist (Quarterly):**

- [ ] Verify rate limiting is functioning: Check logs for 429 responses
- [ ] Review data retention policy: Run `harvest retain --dry-run`
- [ ] Audit stored data: Ensure no unnecessary PII is retained
- [ ] Test user deletion workflow: Simulate deletion request
- [ ] Review X API Terms of Service for updates
- [ ] Verify attribution is correct in all tweet displays
- [ ] Check that links to original tweets are functional
- [ ] Ensure privacy policy is up-to-date

### Data Retention Policy

**Default Policy:**

- **Tweets/Signals**: Retain for 90 days from creation
- **Snapshots**: Retain last 30 snapshots (configurable)
- **Discoveries**: Retain indefinitely (research archive)
- **Logs**: Retain for 30 days

**Retention Commands:**

```bash
# Apply retention policy (dry run)
harvest retain --dry-run

# Apply retention policy (delete old data)
harvest retain --execute

# Prune snapshots to keep only N most recent
harvest prune --keep 30

# Custom retention for specific data types
sqlite3 var/app.db "DELETE FROM tweets WHERE inserted_at < datetime('now', '-90 days')"
```

**GDPR Compliance (if applicable):**

- [ ] Implement "right to be forgotten" workflow
- [ ] Provide data export functionality
- [ ] Document data processing activities
- [ ] Ensure consent mechanisms are in place
- [ ] Maintain data processing records

**User Data Requests:**

If a user requests their data or deletion:

1. **Data Export Request:**

   ```bash
   # Export all data for a user
   sqlite3 var/app.db -csv -header \
     "SELECT * FROM tweets WHERE author_id='USER_ID'" > user_data_export.csv
   ```

2. **Data Deletion Request:**

   ```bash
   # Delete all user data
   sqlite3 var/app.db << EOF
   DELETE FROM tweets WHERE author_id='USER_ID';
   DELETE FROM discoveries WHERE author_id='USER_ID';
   -- Add other tables as needed
   EOF
   
   # Verify deletion
   sqlite3 var/app.db "SELECT COUNT(*) FROM tweets WHERE author_id='USER_ID'"
   # Should return 0
   ```

3. **Document the Request:**

   ```bash
   echo "$(date): Data deletion request processed for user_id=USER_ID" >> logs/data_requests.log
   ```

### Monitoring & Incident Response

**Security Monitoring:**

```bash
# Check for suspicious API access patterns
docker-compose logs signal-harvester | grep -E "401|403|429" | tail -50

# Monitor failed authentication attempts
grep "Invalid API key" /var/log/signal_harvester.log

# Check for unusual database growth
ls -lh var/app.db
```

**Incident Response Procedure:**

1. **Detect**: Monitor logs, alerts, and user reports
2. **Assess**: Determine severity and scope
3. **Contain**: Revoke compromised keys, block malicious IPs
4. **Eradicate**: Remove malicious code, patch vulnerabilities
5. **Recover**: Restore from backup if needed
6. **Document**: Log incident details and response actions

**Emergency Contacts:**

- Security Lead: [Name/Email]
- Infrastructure Team: [Contact]
- X API Support: <developer-support@twitter.com>
- LLM Provider Support: See provider dashboards

## SSE Manual Verification Log

Collected verification notes align with Section 6 of [`ARCHITECTURE_AND_READINESS.md`](../ARCHITECTURE_AND_READINESS.md:79).

| Date | Status | Notes |
| --- | --- | --- |
| 2025-11-11 | ✅ PASSED | Executed `verify_sse_streaming.py` against running API (localhost:8000). Bulk operation started with 10 active signals, received 2 SSE events (1 progress + 1 completion), total duration 0.53s. Connection headers verified: `text/event-stream`, `no-cache`, `keep-alive`. Progress events showed: Event #1: [running] 3/10 (30.0%), Event #2: [completed] 10/10 (100.0%). No errors observed. |
| 2025-11-10 | Not run (blocked) | The manual SSE workflow could not be executed here because the API/database stack is not running; rerun the curl/Browser steps from Section 4 once the service is online and replace this row with the observed progress/complete events plus any anomalies. |

## 🛠️ Maintenance Tasks

### Daily

- [ ] Monitor health endpoint
- [ ] Review error logs
- [ ] Check disk space
- [ ] Verify notifications sent

### Weekly

- [ ] Review performance metrics
- [ ] Clean up old logs
- [ ] Check for system updates
- [ ] Verify backup completion

### Monthly

- [ ] Update dependencies
- [ ] Review and prune old data
- [ ] Test restore from backup
- [ ] Security audit
- [ ] Review and update configurations

### Quarterly

- [ ] Performance review and optimization
- [ ] Capacity planning
- [ ] Disaster recovery drill
- [ ] Architecture review

## 📞 Escalation

### When to Escalate

**Immediate escalation (critical):**

- Database corruption
- Complete data loss
- Security breach
- System completely down > 1 hour

**Next business day (high):**

- Performance degradation > 50%
- Frequent errors affecting users
- Backup failures
- Rate limiting blocking legitimate users

**Next sprint (medium):**

- Minor performance issues
- Occasional errors
- Documentation updates needed

### Escalation Contacts

1. **Primary On-call**: [Your contact]
2. **Secondary**: [Your contact]
3. **Engineering Manager**: [Your contact]
4. **Create Issue**: <https://github.com/your-org/signal-harvester/issues>

## 🧪 Manual Testing & Verification

### SSE (Server-Sent Events) Streaming Verification

The `/bulk-jobs/{job_id}/stream` endpoint provides real-time progress updates via Server-Sent Events. This is critical for user experience during long-running operations.

**Automated Test Script:**

A verification script is provided at `signal-harvester/verify_sse_streaming.py`. Run it while the API server is active:

```bash
# Ensure API is running
docker-compose up -d signal-harvester

# Or locally:
harvest api --host 0.0.0.0 --port 8000

# Run verification
python verify_sse_streaming.py
```

**Expected Results:**

- ✅ Connection establishes with `Content-Type: text/event-stream`
- ✅ Headers include `Cache-Control: no-cache` and `Connection: keep-alive`
- ✅ Multiple `data:` events received with JSON payloads
- ✅ Progress updates show increasing `done` count
- ✅ Final event shows `completed` status
- ✅ Stream terminates cleanly when job finishes

**Manual Verification (curl):**

```bash
# Start a bulk operation (update signal status)
JOB_ID=$(curl -s -X POST http://localhost:8000/signals/bulk/status \
  -H "Content-Type: application/json" \
  -d '{"filters":{"status":"active"},"status":"active"}' | jq -r '.jobId')

# Connect to SSE stream
curl -N "http://localhost:8000/bulk-jobs/${JOB_ID}/stream"

# Expected output (streaming):
# data: {"jobId":"abc123","status":"running","total":50,"done":0,"fail":0}
# data: {"jobId":"abc123","status":"running","total":50,"done":10,"fail":0}
# data: {"jobId":"abc123","status":"running","total":50,"done":25,"fail":1}
# data: {"jobId":"abc123","status":"completed","total":50,"done":50,"fail":2}
```

**Frontend Integration Test:**

```bash
# Using EventSource in browser console
const source = new EventSource('/bulk-jobs/YOUR_JOB_ID/stream');
source.onmessage = (e) => console.log('Progress:', JSON.parse(e.data));
source.onerror = (e) => console.error('SSE error:', e);
```

**Security Checklist:**

- ✅ SSE endpoint does not leak sensitive data in events
- ✅ Connection closes properly on job completion
- ✅ No memory leaks from long-running streams
- ✅ Rate limiting applies to SSE connections
- ✅ API key authentication enforced (if configured)

**Evidence of Last Verification:**

```text
Date: 2025-11-11T15:20:00Z
Test Runner: Automated via verify_sse_streaming.py
Results: PASS
Details:
- API Server: localhost:8000 (uvicorn with HARVEST_DB_PATH=var/app.db)
- Test Signals: 10 active signals created (IDs: sse_test_1 through sse_test_10)
- Bulk Job ID: 5886992d-8b14-4dcb-abcf-3fd4b2fd2fb9
- Total Items: 10
- Events Received: 2
  * Event #1: [running] 3/10 (30.0%) - 0 failed
  * Event #2: [completed] 10/10 (100.0%) - 0 failed
- Duration: 0.53s
- Connection Headers Verified:
  * Content-Type: text/event-stream; charset=utf-8
  * Cache-Control: no-cache
  * Connection: keep-alive
- Stream Termination: Clean (closed on completion)
- Security Checks:
  ✅ No sensitive data leaked in events
  ✅ Proper status progression (running → completed)
  ✅ All progress fields present (jobId, status, total, done, fail)
Notes: All verification criteria met successfully. SSE implementation fully functional.
```

### Entity Resolution & Identity Management

Run identity resolution to merge duplicate researcher/organization entities discovered from various sources.

**Running Entity Resolution:**

```bash
# Basic run with default weights
harvest resolve

# Custom threshold for more/fewer matches
harvest resolve --threshold 0.85

# Without LLM confirmation (similarity-only)
harvest resolve --no-llm

# Custom weights (must sum to 1.0, normalized automatically)
harvest resolve \
  --name-weight 0.50 \
  --affiliation-weight 0.30 \
  --domain-weight 0.15 \
  --accounts-weight 0.05
```

**Multi-Field Weighted Matching:**

Entity resolution uses weighted similarity across multiple fields to achieve >90% precision:

- **Name (default: 0.50)**: Embedding-based name similarity with variations (e.g., "John Smith" ↔ "Smith, John")
- **Affiliation (default: 0.30)**: Institution/organization match (e.g., "Stanford" ↔ "Stanford University")
- **Domain (default: 0.15)**: Homepage URL match (e.g., exact domain or subdomain overlap)
- **Accounts (default: 0.05)**: Social account overlap (e.g., same GitHub/X handle)

**Example Weighted Scores:**

```text
Scenario 1: Clear Duplicate
- "John Smith" vs "Smith, John" (same person)
- Name: 0.95 → Weighted: 0.95 * 0.50 = 0.475
- Affiliation: 0.90 (both "MIT") → 0.90 * 0.30 = 0.270
- Domain: 1.0 (same homepage) → 1.0 * 0.15 = 0.150
- Accounts: 1.0 (same GitHub) → 1.0 * 0.05 = 0.050
- Total: 0.945 → MATCH (above 0.80 threshold)

Scenario 2: Common Name (Different People)
- "David Chen" vs "David Chen" (different people)
- Name: 1.0 → Weighted: 1.0 * 0.50 = 0.500
- Affiliation: 0.2 (Stanford vs Berkeley) → 0.2 * 0.30 = 0.060
- Domain: 0.0 (different URLs) → 0.0 * 0.15 = 0.000
- Accounts: 0.0 (no overlap) → 0.0 * 0.05 = 0.000
- Total: 0.560 → NO MATCH (below 0.80 threshold)
```

**Monitoring Precision:**

```bash
# Run test suite to validate >90% precision
pytest tests/test_identity_resolution.py::TestPrecisionMetrics -v

# Check merge statistics
harvest resolve --threshold 0.80  # Returns: processed, candidates_found, merged
```

**When to Run:**

- After bulk discovery operations (new researchers/orgs added)
- Weekly maintenance (consolidate duplicates)
- Before generating researcher profiles or topic analytics
- When precision tests fail (indicates algorithm drift)

**Precision Target:** >90% (validated via test suite with clear duplicates vs. common name false positives)

### Social Media Ingestion (Facebook & LinkedIn)

Monitor Facebook and LinkedIn data sources for organizational content and engagement metrics.

**Facebook Graph API Monitoring:**

```bash
# Check Facebook page posts ingestion
harvest discover fetch --sources facebook --limit 50

# Verify configuration
grep -A 10 "facebook:" config/settings.yaml

# Monitor rate limiting
docker-compose logs signal-harvester | grep -i "facebook.*429"
```

**Facebook Configuration (`config/settings.yaml`):**

```yaml
sources:
  facebook:
    pages:
      - "YourOrgPage"
      - "YourLabPage"
    groups: []  # Optional public groups
    search_queries: []  # Optional search terms
    max_results: 100
```

**LinkedIn API v2 Monitoring:**

```bash
# Check LinkedIn organization posts
harvest discover fetch --sources linkedin --limit 50

# Verify OAuth token validity
echo $LINKEDIN_ACCESS_TOKEN | cut -c1-20

# Monitor rate limiting
docker-compose logs signal-harvester | grep -i "linkedin.*429"
```

**LinkedIn Configuration (`config/settings.yaml`):**

```yaml
sources:
  linkedin:
    organizations:
      - "1234567"  # Numeric organization IDs
      - "7654321"
    max_results: 100
```

**Engagement Metrics Tracking:**

- **Facebook**: `engagement_score = likes + (shares × 2) + (comments × 3)`
- **LinkedIn**: `engagement_score = likes + (comments × 3) + (shares × 2)`

**Quality Checks:**

```bash
# Verify artifact metadata
sqlite3 var/signal_harvester.db \
  "SELECT source, COUNT(*), AVG(json_extract(metadata_json, '$.engagement_score')) 
   FROM artifacts 
   WHERE source IN ('facebook', 'linkedin') 
   GROUP BY source;"

# Check for missing engagement data
sqlite3 var/signal_harvester.db \
  "SELECT COUNT(*) FROM artifacts 
   WHERE source IN ('facebook', 'linkedin') 
   AND json_extract(metadata_json, '$.engagement_score') IS NULL;"
```

**When to Monitor:**

- Daily: Check ingestion counts and rate limits
- Weekly: Review engagement score trends
- Monthly: Rotate OAuth tokens (LinkedIn requires refresh every 60 days)
- Quarterly: Review page/organization list for relevance

**Troubleshooting:**

- **No posts fetched**: Check page permissions (Facebook) or organization access (LinkedIn)
- **Rate limit errors**: Reduce `max_results` or increase polling interval
- **OAuth errors (LinkedIn)**: Regenerate access token via LinkedIn Developer Portal
- **Missing engagement**: Verify API permissions include read_insights (Facebook)

### Backtesting & Experiments

Track discovery scoring performance through A/B testing, precision/recall metrics, and historical replay.

**Ground Truth Annotation:**

```bash
# Label individual discoveries
harvest annotate --artifact-id abc123 --label true_positive --confidence 1.0

# Import labels from CSV
harvest annotate --import labels.csv

# Export current labels
harvest annotate --export current_labels.csv
```

**CSV Format:**

```csv
artifact_id,label,confidence,notes,annotator
abc123,true_positive,1.0,"Validated research breakthrough",user@example.com
def456,false_positive,0.9,"Low impact, over-scored",user@example.com
```

**Running Backtests:**

```bash
# Basic backtest (last 3 days)
harvest backtest --days 3 --min-score 80

# Create experiment with metrics
harvest backtest --days 7 --experiment "baseline_v1" --metrics

# Compare two experiments
harvest backtest --compare 1  # Compare current run to experiment ID 1
```

**Experiment Workflow:**

1. **Annotate discoveries** (build ground truth dataset)
2. **Run baseline** (`harvest backtest --experiment baseline`)
3. **Modify scoring weights** in `config/settings.yaml`
4. **Run A/B test** (`harvest backtest --experiment variant_a`)
5. **Compare results** (`harvest backtest --compare <baseline_id>`)
6. **Deploy winner** if metrics improve

**API Endpoints:**

```bash
# Create experiment
curl -X POST http://localhost:8000/experiments \
  -H "Content-Type: application/json" \
  -d '{
    "name": "high_novelty_v1",
    "scoring_weights": {
      "novelty": 0.40,
      "emergence": 0.30,
      "obscurity": 0.15,
      "cross_source": 0.10,
      "expert_signal": 0.05
    },
    "min_score_threshold": 85.0
  }'

# List experiments
curl http://localhost:8000/experiments

# Get experiment details
curl http://localhost:8000/experiments/1

# Compare experiments
curl http://localhost:8000/experiments/compare?experiment_a_id=1&experiment_b_id=2
```

**Metrics Interpretation:**

- **Precision = TP/(TP+FP)**: % of predicted discoveries that are truly valuable
- **Recall = TP/(TP+FN)**: % of truly valuable discoveries that were caught
- **F1 Score = 2×(P×R)/(P+R)**: Harmonic mean, balances precision and recall
- **Accuracy = (TP+TN)/Total**: Overall correctness

**Target Metrics:**

- Precision: >80% (minimize false positives)
- Recall: >70% (don't miss important discoveries)
- F1 Score: >0.75 (balanced performance)

**Quality Monitoring:**

```bash
# Check label count
sqlite3 var/signal_harvester.db \
  "SELECT label, COUNT(*) FROM discovery_labels GROUP BY label;"

# View experiment history
sqlite3 var/signal_harvester.db \
  "SELECT id, name, status, created_at 
   FROM experiments 
   ORDER BY created_at DESC 
   LIMIT 10;"

# Check latest metrics
sqlite3 var/signal_harvester.db \
  "SELECT experiment_id, precision, recall, f1_score, accuracy 
   FROM experiment_runs 
   ORDER BY created_at DESC 
   LIMIT 5;"
```

**When to Run:**

- Weekly: Review experiment metrics, annotate new discoveries
- Before scoring changes: Run baseline experiment
- After scoring changes: Run A/B test against baseline
- Monthly: Clean up old experiment runs (keep top performers)

**Troubleshooting:**

- **Low precision**: Too many false positives → increase `min_score_threshold`
- **Low recall**: Missing discoveries → review scoring weights, check source coverage
- **Insufficient labels**: Need >100 labeled artifacts for reliable metrics
- **Zero metrics**: No ground truth labels → run `harvest annotate --import`

### Contract Testing (API ↔ Frontend)

Ensure FastAPI response models match frontend TypeScript types to prevent runtime errors.

**Running Contract Tests:**

```bash
# From signal-harvester directory
pytest tests/test_contract_api_frontend.py -v
```

**Coverage:**

- Signal response models vs. frontend/src/lib/types.ts
- Discovery response models vs. frontend types
- Bulk operation models vs. frontend API client expectations

**When to Run:**

- Before releasing API changes
- Before deploying frontend updates
- After modifying Pydantic models
- As part of CI/CD pipeline

## 📚 Additional Resources

- [Deployment Guide](DEPLOYMENT.md)
- [Backup Procedures](BACKUP.md)
- [API Documentation](API.md)
- [Troubleshooting Guide](TROUBLESHOOTING.md)
