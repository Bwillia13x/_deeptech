# Signal Harvester Troubleshooting Guide

> This document is part of the maintained documentation set for Signal Harvester.
> For canonical architecture, readiness status, and roadmap, see [`signal-harvester/ARCHITECTURE_AND_READINESS.md`](signal-harvester/ARCHITECTURE_AND_READINESS.md).
> For API error codes, see [`API.md`](API.md).
> For operations and monitoring, see [`OPERATIONS.md`](OPERATIONS.md).

## 📖 Overview

This guide provides solutions to common issues encountered when running Signal Harvester, covering database problems, API errors, pipeline failures, performance issues, and deployment challenges.

**Quick Diagnostic Commands:**

```bash
# Check overall health
harvest stats
curl http://localhost:8000/health

# Verify database
harvest verify

# Check logs
tail -f logs/app.log
grep ERROR logs/app.log | tail -20

# Check running processes
docker ps
ps aux | grep harvest
```

---

## 🗄️ Database Issues

### SQLite Database Locked

**Symptoms:**

- Error: `sqlite3.OperationalError: database is locked`
- API returns 503 Service Unavailable
- Pipeline commands hang or timeout

**Cause:** Multiple processes accessing SQLite database simultaneously, or abandoned connections.

**Solutions:**

1. **Check for concurrent processes:**

   ```bash
   # Find processes using database
   lsof var/app.db
   ps aux | grep harvest
   
   # Kill stuck processes (if safe)
   pkill -f "harvest pipeline"
   ```

2. **Increase busy timeout:**

   SQLite uses a busy timeout to wait for locks. Edit `src/signal_harvester/db.py`:

   ```python
   # Find the engine creation and add connect_args
   engine = create_engine(
       f"sqlite:///{db_path}",
       connect_args={"timeout": 30}  # 30 second timeout
   )
   ```

3. **Use WAL mode for better concurrency:**

   ```bash
   sqlite3 var/app.db "PRAGMA journal_mode=WAL;"
   ```

4. **Stop all services and restart:**

   ```bash
   docker-compose down
   docker-compose up -d
   ```

**Prevention:**

- Run only one pipeline process at a time
- Use API endpoints instead of direct CLI for concurrent operations
- Implement proper connection pooling
- Consider migrating to PostgreSQL for production (future roadmap)

---

### Database Corruption

**Symptoms:**

- Error: `sqlite3.DatabaseError: database disk image is malformed`
- Unexpected NULL values or missing records
- `harvest verify` reports integrity errors

**Cause:** Improper shutdown, disk errors, or SQLite bugs.

**Solutions:**

1. **Check database integrity:**

   ```bash
   sqlite3 var/app.db "PRAGMA integrity_check;"
   ```

2. **Attempt automatic repair:**

   ```bash
   # Dump and reload database
   sqlite3 var/app.db ".dump" > backup.sql
   mv var/app.db var/app.db.corrupt
   sqlite3 var/app.db < backup.sql
   ```

3. **Restore from backup:**

   ```bash
   # List available backups
   ls -lh data/backups/
   
   # Restore latest backup
   cp data/backups/app_2025-11-11.db var/app.db
   ```

4. **Reinitialize database (data loss):**

   ```bash
   # Backup current database first!
   mv var/app.db var/app.db.old
   
   # Reinitialize
   harvest init-db
   alembic upgrade head
   ```

**Prevention:**

- Regular backups: `harvest snapshot` (daily cron job)
- Graceful shutdowns: `docker-compose down` instead of `kill -9`
- Monitor disk health: `df -h`, SMART monitoring
- Use WAL mode: `PRAGMA journal_mode=WAL;`

---

### Migration Failures

**Symptoms:**

- Error: `alembic.util.exc.CommandError: Can't locate revision identified by 'XXXXX'`
- Database schema mismatch with code expectations
- `alembic current` shows unexpected version

**Cause:** Migration applied out of order, missing migration files, or database/code version mismatch.

**Solutions:**

1. **Check current migration version:**

   ```bash
   cd /Users/benjaminwilliams/_deeptech/signal-harvester
   alembic current
   alembic history
   ```

2. **Verify migration file integrity:**

   ```bash
   ls -lh migrations/versions/
   # Ensure all migration files are present
   # Check for Phase Two migrations (7-8)
   ```

3. **Downgrade and re-upgrade:**

   ```bash
   # Downgrade to specific version
   alembic downgrade <revision_id>
   
   # Upgrade to latest
   alembic upgrade head
   ```

4. **Manual schema fix (advanced):**

   ```bash
   # Compare expected vs actual schema
   sqlite3 var/app.db ".schema artifacts" > actual_schema.sql
   
   # Edit database manually (RISKY - backup first!)
   sqlite3 var/app.db
   > ALTER TABLE artifacts ADD COLUMN new_column TEXT;
   > .quit
   ```

5. **Fresh database with data preservation:**

   ```bash
   # Export data
   harvest export --format json > data_export.json
   
   # Reinitialize database
   mv var/app.db var/app.db.old
   harvest init-db
   alembic upgrade head
   
   # Import data (if import tool exists)
   # Otherwise, restore from snapshot
   ```

**Prevention:**

- Always run migrations before deploying code updates
- Keep migration files in version control
- Test migrations on staging environment first
- Document manual schema changes in migration comments

---

## 🔌 API Issues

### API Key Authentication Failures

**Symptoms:**

- 401 Unauthorized on all endpoints (except `/health`)
- Error: `Invalid or missing API key`

**Cause:** Missing, incorrect, or malformed API key.

**Solutions:**

1. **Verify environment variable is set:**

   ```bash
   echo $HARVEST_API_KEY
   
   # If empty, set it
   export HARVEST_API_KEY="your-secure-key-here"
   
   # For Docker
   docker-compose down
   # Edit .env file
   docker-compose up -d
   ```

2. **Check API key format:**

   ```bash
   # Should NOT have quotes or extra whitespace
   # Bad:  HARVEST_API_KEY="my-key  "
   # Good: HARVEST_API_KEY=my-key
   
   # Trim whitespace
   export HARVEST_API_KEY=$(echo $HARVEST_API_KEY | xargs)
   ```

3. **Test with correct header:**

   ```bash
   # Correct header name is X-API-Key (case-sensitive)
   curl -H "X-API-Key: $HARVEST_API_KEY" http://localhost:8000/top
   
   # NOT: Authorization, Api-Key, or X-Api-Key
   ```

4. **Restart API server after environment changes:**

   ```bash
   docker-compose restart signal-harvester
   # Or for development
   pkill -f "harvest api"
   harvest api
   ```

**Prevention:**

- Store API key in `.env` file (not in shell history)
- Use strong, random API keys: `openssl rand -hex 32`
- Rotate keys regularly (see OPERATIONS.md Security section)
- Never commit `.env` to version control

---

### Rate Limiting Issues

**Symptoms:**

- 429 Too Many Requests
- Error: `Rate limit exceeded. Please wait before retrying.`
- `X-RateLimit-Remaining: 0` header

**Cause:** Exceeded 10 requests per minute per client (IP + User-Agent).

**Solutions:**

1. **Check rate limit headers:**

   ```bash
   curl -v -H "X-API-Key: $API_KEY" http://localhost:8000/top 2>&1 | grep RateLimit
   # X-RateLimit-Limit: 10
   # X-RateLimit-Remaining: 9
   # X-RateLimit-Reset: 1699704125
   ```

2. **Wait for rate limit reset:**

   ```bash
   # Check Retry-After header for exact wait time
   curl -I -H "X-API-Key: $API_KEY" http://localhost:8000/top | grep Retry-After
   # Retry-After: 45
   ```

3. **Disable rate limiting for development:**

   ```bash
   # Edit .env
   echo "RATE_LIMITING_ENABLED=false" >> .env
   
   # Restart API
   docker-compose restart signal-harvester
   ```

4. **Implement client-side backoff:**

   ```python
   import time
   import requests
   
   def api_call_with_backoff(url, headers):
       response = requests.get(url, headers=headers)
       
       if response.status_code == 429:
           retry_after = int(response.headers.get('Retry-After', 60))
           time.sleep(retry_after)
           return api_call_with_backoff(url, headers)
       
       return response
   ```

**Prevention:**

- Monitor `X-RateLimit-Remaining` header
- Batch operations instead of individual calls
- Use webhooks/SSE for real-time updates instead of polling
- Request rate limit increase for production use cases

---

### CORS Errors (Frontend Integration)

**Symptoms:**

- Browser console: `Access to fetch at 'http://localhost:8000' has been blocked by CORS policy`
- API calls work in cURL but fail in browser

**Cause:** Missing CORS headers for cross-origin requests.

**Solutions:**

1. **Verify CORS configuration in FastAPI:**

   Edit `src/signal_harvester/api.py`:

   ```python
   from fastapi.middleware.cors import CORSMiddleware
   
   app.add_middleware(
       CORSMiddleware,
       allow_origins=["http://localhost:5173"],  # Vite dev server
       allow_credentials=True,
       allow_methods=["*"],
       allow_headers=["*"],
   )
   ```

2. **For production, set specific origins:**

   ```python
   allow_origins=[
       "https://yourdomain.com",
       "https://app.yourdomain.com"
   ]
   ```

3. **Check preflight OPTIONS requests:**

   ```bash
   curl -X OPTIONS -H "Origin: http://localhost:5173" \
     -H "Access-Control-Request-Method: GET" \
     -H "Access-Control-Request-Headers: X-API-Key" \
     http://localhost:8000/top -v
   ```

**Prevention:**

- Configure CORS early in development
- Use environment variables for allowed origins
- Test cross-origin requests before deployment

---

## 🔄 Pipeline Failures

### Fetch Stage Failures

**Symptoms:**

- Error: `X API request failed with status 429`
- Error: `Invalid bearer token`
- Zero tweets fetched despite active queries

**Cause:** X API rate limits, authentication issues, or invalid queries.

**Solutions:**

1. **Verify X API credentials:**

   ```bash
   # Test bearer token
   curl -H "Authorization: Bearer $X_BEARER_TOKEN" \
     "https://api.twitter.com/2/tweets/search/recent?query=test&max_results=10"
   
   # Should return tweet data, not authentication error
   ```

2. **Check X API rate limits:**

   ```bash
   # Monitor rate limit headers
   curl -I -H "Authorization: Bearer $X_BEARER_TOKEN" \
     "https://api.twitter.com/2/tweets/search/recent?query=test&max_results=10" \
     | grep x-rate-limit
   
   # x-rate-limit-limit: 450
   # x-rate-limit-remaining: 449
   # x-rate-limit-reset: 1699704125
   ```

3. **Validate search queries:**

   ```bash
   # Test query syntax in X Advanced Search UI first
   # https://twitter.com/search-advanced
   
   # Check settings.yaml for malformed queries
   cat config/settings.yaml | grep -A 5 "queries:"
   ```

4. **Reduce fetch frequency:**

   ```yaml
   # In config/settings.yaml
   app:
     fetch:
       max_results: 10  # Reduce from 50
   ```

5. **Check quota status:**

   ```bash
   harvest quota
   # Shows remaining X API quota
   ```

**Prevention:**

- Monitor X API quota: `harvest quota` in cron job
- Use webhooks instead of polling for real-time needs
- Implement exponential backoff in `x_client.py`
- Rotate API keys if approaching limits

---

### LLM Analysis Failures

**Symptoms:**

- Error: `OpenAI API error: insufficient_quota`
- Error: `Anthropic API error: rate_limit_exceeded`
- Tweets stuck in `fetched` status, never reaching `analyzed`

**Cause:** LLM API quota exceeded, invalid API keys, or network issues.

**Solutions:**

1. **Verify LLM API credentials:**

   ```bash
   # OpenAI
   curl https://api.openai.com/v1/models \
     -H "Authorization: Bearer $OPENAI_API_KEY"
   
   # Anthropic
   curl https://api.anthropic.com/v1/messages \
     -H "x-api-key: $ANTHROPIC_API_KEY" \
     -H "anthropic-version: 2023-06-01" \
     -d '{"model":"claude-3-haiku-20240307","max_tokens":10,"messages":[{"role":"user","content":"test"}]}'
   ```

2. **Check LLM quota:**

   OpenAI: <https://platform.openai.com/usage>
   Anthropic: <https://console.anthropic.com/settings/usage>

3. **Switch LLM provider:**

   ```yaml
   # In config/settings.yaml
   app:
     llm:
       provider: "anthropic"  # or "xai" or "openai"
       model: "claude-3-haiku-20240307"
   ```

4. **Reduce LLM usage:**

   ```bash
   # Analyze only high-engagement tweets
   harvest analyze --min-likes 10
   
   # Reduce batch size
   harvest analyze --limit 10
   ```

5. **Check for network issues:**

   ```bash
   # Test connectivity to LLM APIs
   ping api.openai.com
   ping api.anthropic.com
   
   # Check proxy settings if behind firewall
   echo $HTTP_PROXY
   ```

**Prevention:**

- Monitor LLM API quotas daily
- Set up billing alerts in provider dashboards
- Use cheaper models for testing (gpt-3.5-turbo, claude-haiku)
- Cache LLM responses to avoid re-analysis
- Implement retry logic with exponential backoff

---

### Discovery Pipeline Failures

**Symptoms:**

- Error: `arXiv API returned 0 results`
- Error: `GitHub API rate limit exceeded`
- Artifacts fetched but not scored
- Topic evolution pipeline fails

**Cause:** External API issues, rate limits, or missing dependencies.

**Solutions:**

1. **Test each source independently:**

   ```bash
   # arXiv
   harvest discover fetch --sources arxiv --limit 5
   
   # GitHub
   harvest discover fetch --sources github --limit 5
   
   # X (Twitter)
   harvest discover fetch --sources x --limit 5
   
   # Facebook
   harvest discover fetch --sources facebook --limit 5
   
   # LinkedIn
   harvest discover fetch --sources linkedin --limit 5
   ```

2. **Check source configurations:**

   ```bash
   cat config/settings.yaml | grep -A 20 "sources:"
   
   # Verify enabled: true for each source
   # Check access tokens are set
   ```

3. **Verify Redis for embeddings:**

   ```bash
   redis-cli ping
   # Should return PONG
   
   # Check Redis config
   cat config/settings.yaml | grep -A 5 "embeddings:"
   ```

4. **Test embedding generation:**

   ```bash
   # Check embedding cache stats
   curl -H "X-API-Key: $API_KEY" \
     http://localhost:8000/embeddings/stats
   ```

5. **Run discovery pipeline in verbose mode:**

   ```bash
   # Enable debug logging
   export LOG_LEVEL=DEBUG
   harvest discover --verbose
   ```

6. **Check for entity resolution issues:**

   ```bash
   # Test identity resolution
   harvest researcher --limit 10
   
   # Check for high duplicate rates
   sqlite3 var/app.db "SELECT COUNT(*) FROM entities WHERE canonical_entity_id IS NOT NULL;"
   ```

**Prevention:**

- Monitor external API status pages
- Implement source-specific rate limiting
- Use fallback providers (e.g., Semantic Scholar if arXiv fails)
- Regular Redis maintenance and monitoring
- Test discovery pipeline in staging before production

---

## ⚡ Performance Issues

### Slow API Response Times

**Symptoms:**

- API requests taking >5 seconds
- Frontend shows loading spinners indefinitely
- Database queries timing out

**Cause:** Missing indexes, large result sets, or inefficient queries.

**Solutions:**

1. **Add database indexes:**

   ```bash
   sqlite3 var/app.db <<EOF
   CREATE INDEX IF NOT EXISTS idx_tweets_salience ON tweets(salience DESC);
   CREATE INDEX IF NOT EXISTS idx_tweets_created_at ON tweets(created_at DESC);
   CREATE INDEX IF NOT EXISTS idx_artifacts_score ON artifacts(discovery_score DESC);
   CREATE INDEX IF NOT EXISTS idx_artifacts_source ON artifacts(source, fetched_at DESC);
   EOF
   ```

2. **Analyze slow queries:**

   ```bash
   # Enable query logging in api.py
   # Add to engine creation:
   # echo_pool=True, echo=True
   
   # Check log for slow queries
   grep "SELECT" logs/app.log | grep -v "0.0[0-5]s"
   ```

3. **Optimize large result sets:**

   ```bash
   # Limit query results
   curl "http://localhost:8000/top?limit=50"  # Don't request 1000+
   
   # Use pagination
   curl "http://localhost:8000/discoveries?limit=50&offset=0"
   ```

4. **Check for N+1 query problems:**

   In code, use SQLAlchemy eager loading:

   ```python
   # Bad: N+1 queries
   tweets = session.query(Tweet).all()
   for tweet in tweets:
       user = tweet.user  # Separate query for each user
   
   # Good: Single query with join
   from sqlalchemy.orm import joinedload
   tweets = session.query(Tweet).options(joinedload(Tweet.user)).all()
   ```

5. **Monitor system resources:**

   ```bash
   docker stats signal-harvester
   # Check CPU, memory usage
   
   # Check disk I/O
   iostat -x 1
   ```

**Prevention:**

- Create indexes for all frequently queried columns
- Use `EXPLAIN QUERY PLAN` to analyze SQL performance
- Implement caching for expensive queries (Redis)
- Regular database VACUUM: `sqlite3 var/app.db "VACUUM;"`

---

### High Memory Usage

**Symptoms:**

- Container OOM killed
- Error: `MemoryError` in Python
- System becomes unresponsive

**Cause:** Large batch operations, memory leaks, or insufficient container limits.

**Solutions:**

1. **Check current memory usage:**

   ```bash
   docker stats signal-harvester --no-stream
   
   # Inside container
   docker exec signal-harvester ps aux
   ```

2. **Increase Docker memory limits:**

   Edit `docker-compose.yml`:

   ```yaml
   services:
     signal-harvester:
       deploy:
         resources:
           limits:
             memory: 2G  # Increase from 1G
   ```

3. **Reduce batch sizes:**

   ```bash
   # Fetch in smaller batches
   harvest fetch --limit 10  # Instead of 100
   
   # Analyze in smaller batches
   harvest analyze --limit 20
   ```

4. **Check for memory leaks:**

   ```python
   # Add memory profiling
   pip install memory_profiler
   
   # Profile memory-intensive functions
   @profile
   def expensive_function():
       pass
   
   # Run with: python -m memory_profiler script.py
   ```

5. **Clear caches periodically:**

   ```bash
   # Clear Redis cache
   redis-cli FLUSHDB
   
   # Clear in-memory embedding cache
   # Restart API server
   docker-compose restart signal-harvester
   ```

**Prevention:**

- Use generators instead of loading all data into memory
- Implement streaming for large datasets
- Regular monitoring: `docker stats` in cron job
- Set proper container limits based on workload

---

### Slow Embedding Generation

**Symptoms:**

- Discovery pipeline takes hours
- Embeddings endpoint times out
- Topic evolution fails with timeout

**Cause:** Large number of artifacts, Redis connection issues, or model loading delays.

**Solutions:**

1. **Verify Redis connectivity:**

   ```bash
   redis-cli ping
   
   # Check Redis performance
   redis-cli --latency
   ```

2. **Check embedding cache hit rate:**

   ```bash
   curl -H "X-API-Key: $API_KEY" \
     http://localhost:8000/embeddings/stats
   
   # Look for:
   # hit_rate > 0.80 (80%+)
   # If low, cache isn't working
   ```

3. **Increase batch size:**

   ```yaml
   # In config/settings.yaml
   embeddings:
     batch_size: 64  # Increase from 32
   ```

4. **Use GPU acceleration (if available):**

   ```yaml
   # In config/settings.yaml
   embeddings:
     device: "cuda"  # Instead of "cpu"
   ```

5. **Pre-compute embeddings:**

   ```bash
   # Generate embeddings for all artifacts
   harvest embeddings --refresh-all
   
   # Run before topic evolution
   ```

6. **Monitor embedding generation:**

   ```bash
   # Enable debug logging
   export LOG_LEVEL=DEBUG
   harvest discover score
   
   # Watch for embedding cache misses
   grep "embedding" logs/app.log
   ```

**Prevention:**

- Run embedding refresh during off-peak hours
- Monitor Redis memory usage and eviction rate
- Use smaller embedding models for testing (all-MiniLM-L6-v2 is good balance)
- Regular cache cleanup: remove stale embeddings (>90 days)

---

## 🐳 Docker & Deployment Issues

### Container Won't Start

**Symptoms:**

- `docker-compose up` exits immediately
- Error: `Container exited with code 1`
- No logs in `docker logs signal-harvester`

**Cause:** Missing environment variables, invalid configuration, or port conflicts.

**Solutions:**

1. **Check container logs:**

   ```bash
   docker-compose logs signal-harvester
   docker logs signal-harvester -f
   ```

2. **Verify environment variables:**

   ```bash
   # Check .env file exists
   ls -la .env
   
   # Verify required variables
   grep -E "X_BEARER_TOKEN|OPENAI_API_KEY|HARVEST_API_KEY" .env
   ```

3. **Test configuration syntax:**

   ```bash
   # Validate settings.yaml
   python -c "import yaml; yaml.safe_load(open('config/settings.yaml'))"
   
   # Should return without errors
   ```

4. **Check port conflicts:**

   ```bash
   # See if port 8000 is already in use
   lsof -i :8000
   
   # Kill conflicting process or change port
   docker-compose down
   # Edit docker-compose.yml: "8001:8000"
   docker-compose up -d
   ```

5. **Rebuild container:**

   ```bash
   docker-compose down
   docker-compose build --no-cache
   docker-compose up -d
   ```

6. **Check file permissions:**

   ```bash
   # Ensure var/ directory is writable
   chmod 755 var/
   ls -la var/
   ```

**Prevention:**

- Use `.env.example` as template
- Validate configuration in CI/CD
- Document all required environment variables
- Use health checks in docker-compose.yml

---

### Volume Mount Issues

**Symptoms:**

- Database changes don't persist after container restart
- Configuration changes not reflected in container
- Error: `Permission denied` when writing to volume

**Cause:** Incorrect volume paths, permission issues, or SELinux conflicts.

**Solutions:**

1. **Verify volume mounts:**

   ```bash
   docker inspect signal-harvester | grep Mounts -A 20
   ```

2. **Check volume permissions:**

   ```bash
   # On host
   ls -la var/
   ls -la config/
   
   # Should be readable by container user (UID 1000)
   sudo chown -R 1000:1000 var/
   ```

3. **Test with explicit paths:**

   Edit `docker-compose.yml`:

   ```yaml
   volumes:
     - /Users/benjaminwilliams/_deeptech/signal-harvester/var:/app/var
     - /Users/benjaminwilliams/_deeptech/signal-harvester/config:/app/config:ro
   ```

4. **Check SELinux (Linux only):**

   ```bash
   # Check SELinux status
   getenforce
   
   # Add SELinux label to volumes
   chcon -Rt svirt_sandbox_file_t var/
   
   # Or disable SELinux (not recommended)
   setenforce 0
   ```

5. **Use named volumes instead:**

   ```yaml
   volumes:
     - signal_harvester_db:/app/var
   
   volumes:
     signal_harvester_db:
   ```

**Prevention:**

- Use consistent UID/GID in Dockerfile
- Document volume requirements
- Test volume mounts on target deployment platform
- Use named volumes for production

---

### Build Failures

**Symptoms:**

- `docker build` fails
- Error: `pip install failed with exit code 1`
- Error: `COPY failed: no such file or directory`

**Cause:** Missing dependencies, network issues, or incorrect Dockerfile paths.

**Solutions:**

1. **Check build context:**

   ```bash
   # Ensure building from correct directory
   cd /Users/benjaminwilliams/_deeptech/signal-harvester
   docker build -t signal-harvester .
   ```

2. **Verify Dockerfile paths:**

   ```dockerfile
   # Ensure files exist
   COPY pyproject.toml README.md ./
   COPY src/ src/
   
   # Check files are in context
   ls pyproject.toml README.md src/
   ```

3. **Clear build cache:**

   ```bash
   docker build --no-cache -t signal-harvester .
   ```

4. **Check network connectivity:**

   ```bash
   # Test PyPI access
   docker run --rm python:3.12-slim pip install --index-url https://pypi.org/simple/ httpx
   ```

5. **Use multi-stage build debugging:**

   ```bash
   # Build only first stage
   docker build --target builder -t signal-harvester-builder .
   
   # Inspect builder stage
   docker run --rm -it signal-harvester-builder sh
   ```

6. **Check for dependency conflicts:**

   ```bash
   # Test installation locally
   python -m venv test_env
   source test_env/bin/activate
   pip install -e ".[dev]"
   ```

**Prevention:**

- Pin dependency versions in pyproject.toml
- Use requirements.txt for reproducible builds
- Test builds in CI/CD before deploying
- Keep base images updated

---

## 📊 Data Quality Issues

### Duplicate Signals

**Symptoms:**

- Same tweet appears multiple times in top signals
- Duplicate discoveries with different IDs
- Entity resolution not merging duplicates

**Cause:** Missing deduplication logic, fetch interval too short, or identity resolution disabled.

**Solutions:**

1. **Check for duplicate tweets:**

   ```bash
   sqlite3 var/app.db <<EOF
   SELECT tweet_id, COUNT(*) as count
   FROM tweets
   GROUP BY tweet_id
   HAVING count > 1;
   EOF
   ```

2. **Remove duplicates:**

   ```bash
   sqlite3 var/app.db <<EOF
   DELETE FROM tweets
   WHERE rowid NOT IN (
     SELECT MIN(rowid)
     FROM tweets
     GROUP BY tweet_id
   );
   EOF
   ```

3. **Add unique constraint:**

   ```bash
   # Create migration
   alembic revision -m "add_unique_constraint_tweet_id"
   
   # Edit migration file to add:
   # op.create_unique_constraint('uq_tweets_tweet_id', 'tweets', ['tweet_id'])
   
   alembic upgrade head
   ```

4. **Enable entity resolution:**

   ```yaml
   # In config/settings.yaml
   identity_resolution:
     enabled: true
     threshold: 0.90
   ```

5. **Run deduplication:**

   ```bash
   harvest researcher --deduplicate
   ```

**Prevention:**

- Implement unique constraints at database level
- Enable entity resolution in settings
- Use `ON CONFLICT` clauses in INSERT statements
- Regular deduplication runs in cron

---

### Missing or Incorrect Scores

**Symptoms:**

- Signals have `null` or `0.0` salience scores
- Discoveries not ranked properly
- Topic evolution shows no trending topics

**Cause:** Scoring pipeline not run, LLM analysis failed, or scoring weights misconfigured.

**Solutions:**

1. **Check scoring status:**

   ```bash
   sqlite3 var/app.db <<EOF
   SELECT 
     COUNT(*) as total,
     COUNT(salience) as scored,
     AVG(salience) as avg_score
   FROM tweets;
   EOF
   ```

2. **Run scoring manually:**

   ```bash
   # Legacy mode (tweets)
   harvest score
   
   # Discovery mode (artifacts)
   harvest discover score
   ```

3. **Verify scoring weights:**

   ```bash
   cat config/settings.yaml | grep -A 10 "weights:"
   
   # Ensure weights are reasonable (not all 0.0)
   ```

4. **Check LLM analysis status:**

   ```bash
   sqlite3 var/app.db <<EOF
   SELECT status, COUNT(*) 
   FROM tweets 
   GROUP BY status;
   EOF
   
   # Should see 'analyzed' status for most tweets
   ```

5. **Test scoring algorithm:**

   ```bash
   # Enable debug logging
   export LOG_LEVEL=DEBUG
   harvest score --limit 10
   
   # Check logs for scoring calculations
   grep "score" logs/app.log
   ```

6. **Recalculate all scores:**

   ```bash
   # Force re-scoring
   harvest score --force-recalculate
   ```

**Prevention:**

- Always run full pipeline: fetch → analyze → score
- Validate scoring weights sum to reasonable total
- Monitor average scores over time for anomalies
- Test scoring changes on sample data first

---

## 🔍 Debugging Tools & Techniques

### Enabling Debug Logging

**Temporary (current session):**

```bash
export LOG_LEVEL=DEBUG
harvest pipeline
```

**Permanent (environment file):**

```bash
# Edit .env
echo "LOG_LEVEL=DEBUG" >> .env
docker-compose restart
```

**Per-module logging:**

Edit `src/signal_harvester/config.py`:

```python
import logging

logging.getLogger("signal_harvester.x_client").setLevel(logging.DEBUG)
logging.getLogger("signal_harvester.llm_client").setLevel(logging.DEBUG)
```

---

### Database Inspection

**Using SQLite CLI:**

```bash
sqlite3 var/app.db

# Common queries
.tables                                    # List all tables
.schema tweets                             # Show table schema
SELECT COUNT(*) FROM tweets;               # Count records
SELECT * FROM tweets ORDER BY salience DESC LIMIT 10;  # Top signals

# Analyze indexes
.indexes tweets                            # List indexes
EXPLAIN QUERY PLAN SELECT * FROM tweets WHERE salience > 80;

# Check for issues
PRAGMA integrity_check;                    # Database integrity
PRAGMA foreign_key_check;                  # Foreign key violations
```

**Using harvest CLI:**

```bash
harvest stats                              # Overall statistics
harvest verify                             # Data integrity check
harvest top                                # Top signals
harvest discoveries                        # Top discoveries
```

---

### API Testing

**Health Check:**

```bash
curl http://localhost:8000/health | jq
```

**Authenticated Endpoints:**

```bash
API_KEY="your-key-here"

# Test authentication
curl -H "X-API-Key: $API_KEY" http://localhost:8000/top

# Test rate limiting
for i in {1..15}; do
  curl -H "X-API-Key: $API_KEY" http://localhost:8000/top
  echo "Request $i"
done

# Test error handling
curl -H "X-API-Key: $API_KEY" "http://localhost:8000/top?limit=999"  # Should fail validation
```

**Load Testing:**

```bash
# Install Apache Bench
brew install httpd  # macOS
apt-get install apache2-utils  # Linux

# Run load test
ab -n 100 -c 10 -H "X-API-Key: $API_KEY" http://localhost:8000/top
```

---

### Log Analysis

**Find errors:**

```bash
# Last 50 errors
grep ERROR logs/app.log | tail -50

# Errors in last hour
grep ERROR logs/app.log | grep "$(date -u +%Y-%m-%dT%H)" | tail -20

# Count errors by type
grep ERROR logs/app.log | awk -F'ERROR - ' '{print $2}' | sort | uniq -c | sort -rn
```

**Track API performance:**

```bash
# Find slow requests (>1s)
grep "duration=" logs/app.log | awk -F'duration=' '{print $2}' | awk '{if ($1 > 1.0) print}'

# Average response time
grep "duration=" logs/app.log | awk -F'duration=' '{print $2}' | awk '{sum+=$1; count++} END {print sum/count}'
```

**Monitor real-time:**

```bash
# Tail logs with filtering
tail -f logs/app.log | grep --line-buffered ERROR

# Multi-file monitoring
tail -f logs/*.log
```

---

### Performance Profiling

**Python cProfile:**

```python
# Add to problematic function
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# Your code here
expensive_function()

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)  # Top 20 slowest functions
```

**Memory profiling:**

```bash
pip install memory_profiler

# Add @profile decorator to functions
# Run with:
python -m memory_profiler src/signal_harvester/pipeline.py
```

**Line profiling:**

```bash
pip install line_profiler

# Add @profile decorator
# Run with:
kernprof -l -v src/signal_harvester/pipeline.py
```

---

## 📞 Getting Help

### Before Opening an Issue

1. **Search existing issues:** [GitHub Issues](https://github.com/yourusername/signal-harvester/issues)
2. **Check documentation:**
   - [OPERATIONS.md](OPERATIONS.md) - Daily operations
   - [API.md](API.md) - API reference and error codes
   - [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment guide
   - [TEAM_GUIDE.md](TEAM_GUIDE.md) - Onboarding and workflows
3. **Run diagnostics:**

   ```bash
   harvest stats
   harvest verify
   curl http://localhost:8000/health
   ```

4. **Collect logs:**

   ```bash
   grep ERROR logs/app.log | tail -50 > error_log.txt
   docker-compose logs > docker_logs.txt
   ```

### Opening an Issue

**Include:**

- **Environment:** OS, Docker version, Python version
- **Version:** `harvest --version` or git commit hash
- **Error message:** Full error output (not screenshot)
- **Reproduction steps:** Minimal commands to reproduce
- **Logs:** Relevant log excerpts (use code blocks)
- **Configuration:** Sanitized settings.yaml (remove API keys!)

**Template:**

```markdown
## Environment
- OS: macOS 14.0
- Docker: 24.0.7
- Python: 3.12.1
- Version: commit abc123

## Issue
Brief description of problem

## Steps to Reproduce
1. Run `harvest fetch`
2. Error occurs

## Error Output
```

[paste error here]

```

## Logs
```

[paste relevant logs]

```

## Expected Behavior
What should happen

## Actual Behavior
What actually happens
```

### Community Resources

- **Documentation:** [docs/](.)
- **Examples:** [API_EXAMPLES.md](API_EXAMPLES.md)
- **Architecture:** [ARCHITECTURE_AND_READINESS.md](../ARCHITECTURE_AND_READINESS.md)

---

## ✅ Troubleshooting Checklist

When encountering issues, work through this checklist:

- [ ] Check service health: `curl http://localhost:8000/health`
- [ ] Review recent logs: `grep ERROR logs/app.log | tail -20`
- [ ] Verify environment variables: `env | grep -E "X_BEARER_TOKEN|OPENAI_API_KEY|HARVEST_API_KEY"`
- [ ] Test database connectivity: `harvest stats`
- [ ] Check external API connectivity: `curl https://api.twitter.com/2/tweets/search/recent`
- [ ] Verify configuration syntax: `python -c "import yaml; yaml.safe_load(open('config/settings.yaml'))"`
- [ ] Check for resource constraints: `docker stats signal-harvester`
- [ ] Test with minimal configuration (disable features one by one)
- [ ] Try with fresh database: `mv var/app.db var/app.db.backup && harvest init-db`
- [ ] Restart services: `docker-compose restart`
- [ ] Rebuild containers: `docker-compose build --no-cache`
- [ ] Review recent code/config changes: `git log -5`

If all else fails, collect diagnostics and open an issue with full details.
