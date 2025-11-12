# End-to-End Migration Testing Guide

This guide provides procedures for testing the PostgreSQL migration comprehensively before production deployment.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Test Environment Setup](#test-environment-setup)
- [Test Execution](#test-execution)
  - [Quick Validation](#quick-validation)
  - [Full Test Suite](#full-test-suite)
  - [Performance Testing](#performance-testing)
- [Test Scenarios](#test-scenarios)
- [Interpreting Results](#interpreting-results)
- [Troubleshooting Failed Tests](#troubleshooting-failed-tests)
- [Sign-off Checklist](#sign-off-checklist)

## Overview

The end-to-end testing validates:

1. **Data Integrity**: All data migrated correctly with matching row counts
2. **Schema Correctness**: Foreign keys, indexes, and constraints intact
3. **API Functionality**: All REST endpoints work with PostgreSQL backend
4. **Performance**: Query performance within acceptable limits (<10x SQLite)
5. **Application Health**: Full system operates without errors

## Prerequisites

### Required Software

```bash
# Python dependencies
pip install psycopg2-binary requests

# PostgreSQL client tools
brew install postgresql@16  # macOS
# or
sudo apt install postgresql-client-16  # Ubuntu
```

### Test Data

Ensure you have:
- Recent SQLite backup at `var/app.db`
- PostgreSQL instance running and accessible
- API server stopped (will be started with PostgreSQL config)

### Environment Setup

```bash
# Set PostgreSQL connection string
export DATABASE_URL="postgresql://signal_harvester:your_password@localhost:5432/signal_harvester"

# Set API authentication (if required)
export HARVEST_API_KEY="your_api_key"
```

## Test Environment Setup

### Step 1: Provision PostgreSQL Instance

**Local Development:**
```bash
# Start PostgreSQL
brew services start postgresql@16

# Create database and user
psql postgres <<EOF
CREATE USER signal_harvester WITH PASSWORD 'test_password';
CREATE DATABASE signal_harvester_test OWNER signal_harvester;
GRANT ALL PRIVILEGES ON DATABASE signal_harvester_test TO signal_harvester;
\c signal_harvester_test
GRANT ALL ON SCHEMA public TO signal_harvester;
EOF
```

**Docker:**
```bash
docker run -d \
  --name signal-harvester-test-db \
  -e POSTGRES_PASSWORD=test_password \
  -e POSTGRES_USER=signal_harvester \
  -e POSTGRES_DB=signal_harvester_test \
  -p 5433:5432 \
  postgres:16-alpine
```

### Step 2: Apply Schema Migrations

```bash
export DATABASE_URL="postgresql://signal_harvester:test_password@localhost:5432/signal_harvester_test"

# Run Alembic migrations
alembic upgrade head

# Verify schema
psql $DATABASE_URL -c "\dt"
# Should show all 14 tables
```

### Step 3: Migrate Test Data

```bash
# Run migration
python scripts/migrate_to_postgresql.py \
  --source var/app.db \
  --target "$DATABASE_URL" \
  --validate

# Expected output: All tables migrated, validation passed
```

### Step 4: Configure API for PostgreSQL

```bash
# Update config to use PostgreSQL
cat > config/settings.test.yaml <<EOF
app:
  database:
    url: postgresql://signal_harvester:test_password@localhost:5432/signal_harvester_test
    pool:
      enabled: true
      pool_size: 10
      max_overflow: 5
EOF

# Or use environment variable
export DATABASE_URL="postgresql://signal_harvester:test_password@localhost:5432/signal_harvester_test"
```

### Step 5: Start API Server

```bash
# Start API with PostgreSQL config
HARVEST_CONFIG=config/settings.test.yaml harvest api &

# Wait for startup
sleep 5

# Verify health
curl http://localhost:8000/health
# Expected: {"status":"ok"}
```

## Test Execution

### Quick Validation

Fast smoke tests to verify basic functionality (2-3 minutes):

```bash
python scripts/test_migration.py \
  --sqlite var/app.db \
  --postgres "$DATABASE_URL" \
  --quick
```

**Tests Included:**
- Row count validation (all tables)
- Data checksum validation (sample data)
- Foreign key constraints
- Index validation

**Expected Output:**
```
================================================================================
Test Suite: Data Integrity
================================================================================
  Running: Row Count Validation... ✓ PASS (125.3ms)
  Running: Data Checksum Validation... ✓ PASS (89.7ms)
  Running: Foreign Key Constraints... ✓ PASS (45.2ms)
  Running: Index Validation... ✓ PASS (32.1ms)

Suite Results: 4 passed, 0 failed
Duration: 0.29s

================================================================================
Migration Test Summary
================================================================================
Total Tests: 4
Passed: 4
Failed: 0
Success Rate: 100%
================================================================================

✅ All tests passed!
```

### Full Test Suite

Comprehensive testing including API and performance checks (5-10 minutes):

```bash
python scripts/test_migration.py \
  --sqlite var/app.db \
  --postgres "$DATABASE_URL" \
  --api-url http://localhost:8000 \
  --report reports/migration_test_$(date +%Y%m%d_%H%M%S).html
```

**Tests Included:**
- All data integrity tests
- Query performance comparison
- API health check
- Discoveries endpoint
- Topics endpoint
- Entities endpoint (if implemented)

**Expected Output:**
```
================================================================================
Test Suite: Data Integrity
================================================================================
  Running: Row Count Validation... ✓ PASS (125.3ms)
  Running: Data Checksum Validation... ✓ PASS (89.7ms)
  Running: Foreign Key Constraints... ✓ PASS (45.2ms)
  Running: Index Validation... ✓ PASS (32.1ms)

Suite Results: 4 passed, 0 failed
Duration: 0.29s

================================================================================
Test Suite: Performance
================================================================================
  Running: Query Performance Comparison... ✓ PASS (1854.2ms)

Suite Results: 1 passed, 0 failed
Duration: 1.85s

================================================================================
Test Suite: API Functionality
================================================================================
  Running: API Health Check... ✓ PASS (23.4ms)
  Running: Discoveries Endpoint... ✓ PASS (156.7ms)
  Running: Topics Endpoint... ✓ PASS (98.3ms)

Suite Results: 3 passed, 0 failed
Duration: 0.28s

================================================================================
Migration Test Summary
================================================================================
Total Tests: 8
Passed: 8
Failed: 0
Success Rate: 100%

Suite Breakdown:
  ✓ PASS Data Integrity: 4/4 passed
  ✓ PASS Performance: 1/1 passed
  ✓ PASS API Functionality: 3/3 passed
================================================================================

✓ Report generated: reports/migration_test_20251112_143022.html

✅ All tests passed!
```

### Performance Testing

Focused performance validation (3-5 minutes):

```bash
python scripts/test_migration.py \
  --sqlite var/app.db \
  --postgres "$DATABASE_URL" \
  --performance
```

**Performance Criteria:**
- Discovery queries: <100ms p95 (PostgreSQL)
- Topic queries: <50ms p95 (PostgreSQL)
- PostgreSQL queries <10x SQLite baseline
- Cache hit rate >70%

**Expected Output:**
```
================================================================================
Test Suite: Performance
================================================================================
  Running: Query Performance Comparison... ✓ PASS (1854.2ms)

Suite Results: 1 passed, 0 failed
Duration: 1.85s

Performance Details:
  discoveries: SQLite 8.23ms, PostgreSQL 42.15ms (5.1x)
  topics: SQLite 0.67ms, PostgreSQL 3.42ms (5.1x)
  recent: SQLite 12.34ms, PostgreSQL 58.76ms (4.8x)

✅ All queries within 10x performance target
```

## Test Scenarios

### Scenario 1: Fresh Migration

Test a complete migration from scratch.

```bash
# Drop PostgreSQL database
psql postgres -c "DROP DATABASE signal_harvester_test;"
psql postgres -c "CREATE DATABASE signal_harvester_test OWNER signal_harvester;"

# Apply migrations
alembic upgrade head

# Migrate data
python scripts/migrate_to_postgresql.py \
  --source var/app.db \
  --target "$DATABASE_URL" \
  --validate

# Run tests
python scripts/test_migration.py \
  --sqlite var/app.db \
  --postgres "$DATABASE_URL" \
  --report reports/fresh_migration_test.html
```

### Scenario 2: Data Update Validation

Test that new data can be written to PostgreSQL.

```bash
# Start API with PostgreSQL
HARVEST_CONFIG=config/settings.test.yaml harvest api &

# Create test data via API
curl -X POST http://localhost:8000/api/artifacts \
  -H "Content-Type: application/json" \
  -d '{
    "source": "test",
    "external_id": "test_001",
    "title": "Test Artifact",
    "url": "https://example.com/test"
  }'

# Verify data in PostgreSQL
psql $DATABASE_URL -c "SELECT * FROM artifacts WHERE source = 'test';"

# Should show the test artifact
```

### Scenario 3: Load Testing

Test PostgreSQL under load.

```bash
# Install k6 (if not already)
brew install k6

# Run load test
k6 run scripts/load_test_k6.js

# Check for errors
psql $DATABASE_URL -c "SELECT count(*) FROM pg_stat_activity;"

# Should be within connection limits
```

### Scenario 4: Rollback Testing

Verify rollback procedure works.

```bash
# Test rollback (non-destructive)
cp var/app.db var/app.db.backup

# Stop API
pkill -f "harvest api"

# Switch to SQLite
unset DATABASE_URL
export HARVEST_DB_PATH="var/app.db"

# Start API
harvest api &

# Verify health
curl http://localhost:8000/health

# Verify discoveries work
curl http://localhost:8000/api/discoveries?limit=10

# Switch back to PostgreSQL for continued testing
```

## Interpreting Results

### Success Criteria

**Data Integrity:**
- ✅ All table row counts match between SQLite and PostgreSQL
- ✅ Sample data checksums match
- ✅ All foreign key constraints valid
- ✅ All indexes exist (30+ expected)

**Performance:**
- ✅ Discovery queries <100ms p95
- ✅ Topic queries <50ms p95
- ✅ All queries <10x SQLite baseline

**API Functionality:**
- ✅ Health endpoint returns 200 OK
- ✅ Discoveries endpoint returns results
- ✅ Topics endpoint returns results
- ✅ No 500 errors in API logs

### Warning Signs

**Performance Issues:**
- ⚠️ Queries 5-10x slower than SQLite → Investigate indexes
- ⚠️ Queries >10x slower → Consider rollback
- ⚠️ Increasing latency over time → Check connection pool

**Data Issues:**
- ⚠️ Row count mismatch <1% → Investigate specific rows
- ⚠️ Row count mismatch >1% → Migration failed, rollback
- ⚠️ Foreign key violations → Schema migration issue

**API Issues:**
- ⚠️ 500 errors → Check error logs, database connections
- ⚠️ Timeouts → Increase query timeout or check performance
- ⚠️ Connection refused → Check PostgreSQL is running

## Troubleshooting Failed Tests

### Test: Row Count Validation

**Failure:** Row counts don't match

**Diagnosis:**
```bash
# Compare counts
python -c "
import sqlite3
import psycopg2
from os import environ

sqlite_conn = sqlite3.connect('var/app.db')
pg_conn = psycopg2.connect(environ['DATABASE_URL'])

for table in ['artifacts', 'topics', 'entities']:
    sqlite_cursor = sqlite_conn.cursor()
    sqlite_cursor.execute(f'SELECT COUNT(*) FROM {table}')
    sqlite_count = sqlite_cursor.fetchone()[0]
    
    pg_cursor = pg_conn.cursor()
    pg_cursor.execute(f'SELECT COUNT(*) FROM {table}')
    pg_count = pg_cursor.fetchone()[0]
    
    print(f'{table}: SQLite={sqlite_count}, PostgreSQL={pg_count}')
"
```

**Solution:**
- If PostgreSQL has fewer rows: Re-run migration
- If PostgreSQL has more rows: Check for duplicate data
- If specific table mismatch: Check migration logs for that table

### Test: Query Performance Comparison

**Failure:** Queries >10x slower on PostgreSQL

**Diagnosis:**
```bash
# Check query plans
psql $DATABASE_URL -c "EXPLAIN ANALYZE SELECT * FROM artifacts ORDER BY discovery_score DESC LIMIT 100;"

# Check for missing indexes
psql $DATABASE_URL -c "SELECT schemaname, tablename, indexname FROM pg_indexes WHERE schemaname = 'public';"

# Update statistics
psql $DATABASE_URL -c "ANALYZE;"
```

**Solution:**
- Run `ANALYZE` to update statistics
- Check if indexes exist (should be 30+)
- If still slow, review `EXPLAIN ANALYZE` output
- Consider PostgreSQL tuning (shared_buffers, work_mem)

### Test: API Endpoints

**Failure:** API returns 500 errors

**Diagnosis:**
```bash
# Check API logs
tail -50 logs/signal-harvester.log | grep ERROR

# Check PostgreSQL connection
psql $DATABASE_URL -c "SELECT 1;"

# Check connection pool
psql $DATABASE_URL -c "SELECT count(*) FROM pg_stat_activity WHERE datname = 'signal_harvester_test';"
```

**Solution:**
- Review error logs for specific issues
- Check DATABASE_URL is set correctly
- Verify connection pool not exhausted
- Restart API server

## Sign-off Checklist

Before approving PostgreSQL for production:

### Data Integrity
- [ ] All table row counts match (100%)
- [ ] Sample data checksums match
- [ ] Foreign key constraints valid
- [ ] All 30+ indexes exist
- [ ] No data corruption detected

### Performance
- [ ] Discovery queries <100ms p95
- [ ] Topic queries <50ms p95
- [ ] Timeline queries <200ms p95
- [ ] All queries <10x SQLite baseline
- [ ] Connection pool handling concurrent requests

### API Functionality
- [ ] Health endpoint returns 200 OK
- [ ] All GET endpoints return results
- [ ] All POST endpoints accept data
- [ ] No 500 errors in logs (last 1000 lines)
- [ ] Frontend loads and displays data

### Operational Readiness
- [ ] Backup procedure tested and documented
- [ ] Rollback procedure tested and documented
- [ ] Monitoring dashboards configured
- [ ] Alert thresholds set
- [ ] On-call team trained on PostgreSQL troubleshooting

### Load Testing
- [ ] 100 concurrent users handled
- [ ] No connection pool exhaustion
- [ ] No query timeouts under load
- [ ] Error rate <0.1% under load
- [ ] Cache hit rate >70%

### Documentation
- [ ] Migration procedure documented
- [ ] Rollback procedure documented
- [ ] PostgreSQL setup guide complete
- [ ] Troubleshooting guide complete
- [ ] Test results archived

**Sign-off:**

- Tested by: _______________  Date: ___________
- Reviewed by: ______________  Date: ___________
- Approved by: ______________  Date: ___________

## Next Steps

After successful testing:

1. **Schedule Production Migration**: Pick maintenance window
2. **Notify Stakeholders**: Send migration announcement
3. **Prepare Rollback**: Ensure rollback plan ready
4. **Execute Migration**: Follow production migration checklist
5. **Monitor Closely**: Watch dashboards for 24 hours post-migration
6. **Gather Feedback**: Collect user feedback on performance
7. **Document Lessons**: Update documentation with any findings

## Related Documentation

- [PostgreSQL Setup Guide](POSTGRESQL_SETUP.md)
- [PostgreSQL Migration Script](../scripts/migrate_to_postgresql.py)
- [Rollback Procedure](ROLLBACK.md)
- [Phase Three Execution Plan](PHASE_THREE_EXECUTION_PLAN.md)
- [Operations Manual](OPERATIONS.md)

---

**Last Updated**: 2025-11-12  
**Owner**: Engineering Team  
**Review Frequency**: Before each migration
