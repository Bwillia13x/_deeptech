# PostgreSQL to SQLite Rollback Procedure

This document outlines the procedures for rolling back from PostgreSQL to SQLite in case of issues during or after the Phase Three migration.

## Table of Contents

- [When to Rollback](#when-to-rollback)
- [Decision Criteria](#decision-criteria)
- [Pre-Rollback Checklist](#pre-rollback-checklist)
- [Rollback Procedures](#rollback-procedures)
  - [Emergency Rollback (5-15 minutes)](#emergency-rollback-5-15-minutes)
  - [Planned Rollback (30-60 minutes)](#planned-rollback-30-60-minutes)
- [Data Synchronization](#data-synchronization)
- [Validation](#validation)
- [Post-Rollback Steps](#post-rollback-steps)
- [Recovery Time Objectives](#recovery-time-objectives)
- [Rollback Scenarios](#rollback-scenarios)
- [Troubleshooting](#troubleshooting)

## When to Rollback

### Critical Situations (Immediate Rollback)

- **Data Integrity Issues**: Missing or corrupted data after migration
- **Severe Performance Degradation**: Query latency >10x higher than SQLite baseline
- **Application Crashes**: Repeated failures or errors preventing normal operation
- **Security Breach**: Unauthorized access or data exposure
- **Connection Failures**: Inability to connect to PostgreSQL for >5 minutes
- **Migration Errors**: >5% data loss or corruption during migration

### Non-Critical Situations (Scheduled Rollback)

- **Minor Performance Issues**: Query latency 2-5x higher than expected
- **Feature Incompatibility**: Specific features not working correctly
- **Cost Concerns**: PostgreSQL costs exceeding budget
- **Testing Needs**: Reverting to baseline for comparison testing

## Decision Criteria

Use this decision tree to determine if rollback is necessary:

```
┌─────────────────────────────────────┐
│ Is there data loss or corruption?   │──Yes──> IMMEDIATE ROLLBACK
└─────────────────┬───────────────────┘
                  No
                  │
┌─────────────────▼───────────────────┐
│ Is application unavailable?         │──Yes──> IMMEDIATE ROLLBACK
└─────────────────┬───────────────────┘
                  No
                  │
┌─────────────────▼───────────────────┐
│ Are queries >10x slower?            │──Yes──> IMMEDIATE ROLLBACK
└─────────────────┬───────────────────┘
                  No
                  │
┌─────────────────▼───────────────────┐
│ Can issues be fixed in <4 hours?    │──No───> SCHEDULED ROLLBACK
└─────────────────┬───────────────────┘
                  Yes
                  │
              CONTINUE
          (Monitor & Tune)
```

## Pre-Rollback Checklist

Before initiating rollback, verify:

- [ ] SQLite backup exists and is recent (within last 24 hours)
- [ ] Backup integrity verified with `harvest db verify-backup`
- [ ] Recent PostgreSQL backup created (in case we need to retry)
- [ ] Stakeholders notified of rollback decision
- [ ] Maintenance window scheduled (if planned rollback)
- [ ] Rollback team assembled (on-call engineer, database admin)
- [ ] Monitoring dashboards ready to track rollback progress
- [ ] Rollback authorization obtained (if production system)

## Rollback Procedures

### Emergency Rollback (5-15 minutes)

Use this procedure when immediate restoration is required (data loss, application down).

**Step 1: Stop Application (2 minutes)**

```bash
# Stop API server
pkill -f "harvest api" || docker-compose down signal-harvester

# Stop scheduler if running
pkill -f "harvest daemon" || docker-compose down scheduler

# Verify all processes stopped
ps aux | grep harvest
```

**Step 2: Switch to SQLite (1 minute)**

```bash
# Backup current .env
cp .env .env.postgres.backup

# Remove PostgreSQL DATABASE_URL
sed -i.bak '/^DATABASE_URL=/d' .env

# Set SQLite path (or comment out DATABASE_URL to use default)
echo "HARVEST_DB_PATH=var/app.db" >> .env

# Or update config/settings.yaml
sed -i.bak 's|url: postgresql://.*|url: sqlite:///var/app.db|' config/settings.yaml
```

**Step 3: Restore SQLite Backup (5 minutes)**

```bash
# Find latest backup
LATEST_BACKUP=$(ls -t backups/*.db 2>/dev/null | head -1)

if [ -z "$LATEST_BACKUP" ]; then
    echo "ERROR: No backup found!"
    exit 1
fi

# Restore backup
cp "$LATEST_BACKUP" var/app.db

# Verify restore
sqlite3 var/app.db "SELECT COUNT(*) FROM artifacts;"
```

**Step 4: Restart Application (2 minutes)**

```bash
# Verify configuration
harvest config show | grep database

# Start API server
harvest api &

# Verify health
sleep 5
curl http://localhost:8000/health

# Expected: {"status":"ok"}
```

**Step 5: Validate (5 minutes)**

```bash
# Check top discoveries
harvest discoveries --limit 10

# Check API endpoints
curl http://localhost:8000/api/discoveries?limit=5

# Check error logs
tail -50 logs/signal-harvester.log | grep ERROR
```

**Total RTO: 15 minutes**

---

### Planned Rollback (30-60 minutes)

Use this procedure when rollback can be scheduled and data synchronization is needed.

**Step 1: Create Final PostgreSQL Backup (10 minutes)**

```bash
# Export current PostgreSQL data
pg_dump $DATABASE_URL > backups/postgres_final_$(date +%Y%m%d_%H%M%S).sql

# Or use harvest backup command
harvest db backup --compress --verify

# Verify backup
ls -lh backups/postgres_final_*.sql
```

**Step 2: Sync New Data to SQLite (15 minutes)**

If data was written to PostgreSQL since migration, export and merge:

```bash
# Export PostgreSQL data created since migration
python scripts/export_postgres_data.py \
  --source "$DATABASE_URL" \
  --output backups/postgres_delta.sql \
  --since "2025-11-13T00:00:00Z"  # Migration timestamp

# Import delta into SQLite
sqlite3 var/app.db < backups/postgres_delta.sql
```

Or use full re-migration:

```bash
# Run migration in reverse (PostgreSQL → SQLite)
python scripts/migrate_to_postgresql.py \
  --source "$DATABASE_URL" \
  --target "sqlite:///var/app.db" \
  --validate

# Note: This script would need reverse migration capability
```

**Step 3: Stop Application (2 minutes)**

Same as Emergency Rollback Step 1.

**Step 4: Switch Configuration (3 minutes)**

Same as Emergency Rollback Step 2, but also update settings.yaml:

```yaml
# config/settings.yaml
app:
  database:
    url: sqlite:///var/app.db
    pool:
      enabled: false  # Disable pooling for SQLite
  
  # Keep PostgreSQL config commented for future use
  # database:
  #   url: postgresql://signal_harvester:pass@localhost:5432/signal_harvester
  #   pool:
  #     enabled: true
  #     pool_size: 20
  #     max_overflow: 10
```

**Step 5: Verify Data Integrity (10 minutes)**

```bash
# Run comprehensive verification
harvest db verify --full

# Compare row counts
python scripts/compare_databases.py \
  --source "$DATABASE_URL" \
  --target "sqlite:///var/app.db"

# Expected output:
# artifacts:        MATCH (567 rows)
# topics:           MATCH (45 rows)
# entities:         MATCH (123 rows)
```

**Step 6: Run Alembic Downgrade (5 minutes)**

If PostgreSQL-specific migrations were applied:

```bash
# Check current migration version
alembic current

# Downgrade to last SQLite-compatible migration
alembic downgrade 0009  # Before PostgreSQL-specific migration 0010

# Verify schema
sqlite3 var/app.db ".schema" | grep -i index
```

**Step 7: Restart and Validate (5 minutes)**

Same as Emergency Rollback Steps 4-5, plus:

```bash
# Run test suite
pytest tests/ -v -k "not slow"

# Check performance
harvest db analyze-performance

# Expected: Similar to pre-migration baseline
```

**Step 8: Update Monitoring (5 minutes)**

```bash
# Update Grafana datasource back to SQLite metrics
kubectl patch configmap grafana-datasources \
  -p '{"data":{"datasources.yaml":"datasources:\n  - name: SQLite\n    type: sqlite\n    url: var/app.db"}}'

# Restart Grafana
kubectl rollout restart deployment/grafana
```

**Total RTO: 60 minutes**

---

## Data Synchronization

### Handling New Data Written to PostgreSQL

If data was created or modified in PostgreSQL after migration:

**Option 1: Export Recent Changes**

```sql
-- PostgreSQL: Export artifacts created since migration
COPY (
  SELECT * FROM artifacts 
  WHERE created_at > '2025-11-13T00:00:00Z'
) TO '/tmp/new_artifacts.csv' WITH CSV HEADER;

-- SQLite: Import CSV
.mode csv
.import /tmp/new_artifacts.csv artifacts
```

**Option 2: Bidirectional Sync Script**

```bash
# Create sync script that handles conflicts
python scripts/sync_databases.py \
  --from "$DATABASE_URL" \
  --to "sqlite:///var/app.db" \
  --since "2025-11-13T00:00:00Z" \
  --strategy "last_write_wins"
```

**Option 3: Accept Data Loss**

If acceptable (e.g., test environment):

```bash
# Document what will be lost
python scripts/data_loss_report.py \
  --postgres "$DATABASE_URL" \
  --sqlite "var/app.db" \
  --output reports/data_loss_analysis.txt

# Review and approve
cat reports/data_loss_analysis.txt

# Proceed with rollback (no sync)
```

## Validation

### Post-Rollback Validation Checklist

- [ ] **Health Check**: `/health` endpoint returns 200 OK
- [ ] **Row Counts**: All tables match expected counts
- [ ] **Key Queries**: Top discoveries, topics, entities return results
- [ ] **API Endpoints**: All REST endpoints functional
- [ ] **Error Logs**: No errors in last 100 log lines
- [ ] **Performance**: Query latency matches pre-migration baseline
- [ ] **Data Integrity**: Foreign keys, constraints intact
- [ ] **Scheduled Jobs**: Cron jobs, pipelines running
- [ ] **Monitoring**: Metrics dashboards showing data
- [ ] **User Access**: Frontend loads and displays data

### Validation Commands

```bash
# Health check
curl -f http://localhost:8000/health || echo "FAILED"

# Row count validation
sqlite3 var/app.db <<EOF
SELECT 'artifacts', COUNT(*) FROM artifacts
UNION ALL SELECT 'topics', COUNT(*) FROM topics
UNION ALL SELECT 'entities', COUNT(*) FROM entities;
EOF

# Query performance
time harvest discoveries --limit 100

# Error check
tail -100 logs/signal-harvester.log | grep -c ERROR

# Foreign key check
sqlite3 var/app.db "PRAGMA foreign_key_check;"
```

## Post-Rollback Steps

### Immediate Actions (< 1 hour)

1. **Notify Stakeholders**: Send rollback completion notification
2. **Update Status Page**: Mark service as operational
3. **Document Issues**: Create incident report with root cause
4. **Review Logs**: Analyze what went wrong with PostgreSQL
5. **Preserve Evidence**: Save PostgreSQL logs, metrics, error traces

### Short-term Actions (< 24 hours)

1. **Root Cause Analysis**: Deep dive into migration failures
2. **Fix Issues**: Address problems that caused rollback
3. **Update Migration Plan**: Revise Phase Three plan based on learnings
4. **Test Fixes**: Validate fixes in staging environment
5. **Schedule Retry**: Plan next migration attempt if desired

### Long-term Actions (< 1 week)

1. **Improve Tooling**: Enhance migration scripts based on issues
2. **Add Tests**: Create tests that would have caught the problems
3. **Update Documentation**: Improve migration and rollback guides
4. **Training**: Review rollback procedure with team
5. **Decision Point**: Decide whether to retry PostgreSQL or stay on SQLite

## Recovery Time Objectives

| Scenario | RTO | RPO | Notes |
|----------|-----|-----|-------|
| Emergency Rollback | 15 min | 1 hour | Uses latest backup |
| Planned Rollback | 60 min | 5 min | Full data sync |
| Emergency + Sync | 30 min | 5 min | Emergency with delta sync |
| Automated Rollback | 10 min | 1 hour | Triggered by monitoring |

**RTO (Recovery Time Objective)**: Maximum acceptable downtime  
**RPO (Recovery Point Objective)**: Maximum acceptable data loss

## Rollback Scenarios

### Scenario 1: Migration Failure

**Situation**: Migration script fails midway through data transfer.

**Action**:

1. Do NOT switch config to PostgreSQL
2. Keep using SQLite (no rollback needed)
3. Fix migration script issues
4. Retry migration

**Commands**:

```bash
# Check migration status
python scripts/migrate_to_postgresql.py \
  --source var/app.db \
  --target "$DATABASE_URL" \
  --validate

# If incomplete, clean PostgreSQL
psql $DATABASE_URL -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# Retry migration
python scripts/migrate_to_postgresql.py \
  --source var/app.db \
  --target "$DATABASE_URL" \
  --validate
```

### Scenario 2: Performance Issues

**Situation**: PostgreSQL queries 5x slower than SQLite after migration.

**Action**:

1. Check EXPLAIN plans and missing indexes
2. Run ANALYZE to update statistics
3. If unfixable within 4 hours → scheduled rollback

**Commands**:

```bash
# Check query plans
psql $DATABASE_URL -c "EXPLAIN ANALYZE SELECT * FROM artifacts ORDER BY discovery_score DESC LIMIT 100;"

# Update statistics
psql $DATABASE_URL -c "ANALYZE;"

# Check missing indexes
psql $DATABASE_URL -c "SELECT schemaname, tablename, indexname FROM pg_indexes WHERE schemaname = 'public';"
```

### Scenario 3: Data Corruption

**Situation**: Artifacts missing or have incorrect values after migration.

**Action**:

1. IMMEDIATE rollback
2. No data sync (PostgreSQL data suspect)
3. Investigate corruption cause before retry

**Commands**:

```bash
# Emergency rollback (Steps 1-5 from above)
# Skip data sync step

# Compare checksums
sqlite3 var/app.db "SELECT COUNT(*), SUM(id) FROM artifacts;"
psql $DATABASE_URL -c "SELECT COUNT(*), SUM(id) FROM artifacts;"
```

### Scenario 4: Connection Pool Exhaustion

**Situation**: PostgreSQL max_connections exceeded, application cannot connect.

**Action**:

1. Try increasing pool size first
2. If persistent → emergency rollback
3. Review connection pooling configuration

**Commands**:

```bash
# Check active connections
psql $DATABASE_URL -c "SELECT count(*) FROM pg_stat_activity;"

# Increase max_connections (requires PostgreSQL restart)
psql $DATABASE_URL -c "ALTER SYSTEM SET max_connections = 200;"
psql $DATABASE_URL -c "SELECT pg_reload_conf();"

# If still failing → emergency rollback
```

## Troubleshooting

### Issue: SQLite Backup Not Found

**Symptom**: `ERROR: No backup found!` during rollback

**Solution**:

```bash
# Check backup location
ls -lh backups/

# Check alternate locations
find . -name "*.db" -mtime -7

# If no backup exists, use PostgreSQL data
python scripts/migrate_to_postgresql.py \
  --source "$DATABASE_URL" \
  --target "sqlite:///var/app.db" \
  --validate

# (Requires reverse migration support)
```

### Issue: SQLite File Locked

**Symptom**: `database is locked` error when restoring

**Solution**:

```bash
# Kill all processes using database
lsof var/app.db | awk 'NR>1 {print $2}' | xargs kill -9

# Remove WAL files
rm -f var/app.db-wal var/app.db-shm

# Retry restore
cp backups/latest.db var/app.db
```

### Issue: Foreign Key Violations

**Symptom**: Foreign key constraint failures after rollback

**Solution**:

```bash
# Check violations
sqlite3 var/app.db "PRAGMA foreign_key_check;"

# Temporarily disable FK constraints
sqlite3 var/app.db "PRAGMA foreign_keys=OFF;"

# Re-import data
sqlite3 var/app.db < backups/clean_backup.sql

# Re-enable FK constraints
sqlite3 var/app.db "PRAGMA foreign_keys=ON;"
```

### Issue: Alembic Version Mismatch

**Symptom**: `alembic current` shows wrong version after rollback

**Solution**:

```bash
# Check current version
alembic current

# Manually set version to last SQLite migration
alembic stamp 0009

# Verify
alembic current
# Should show: 0009 (head)
```

### Issue: Missing PostgreSQL Backup

**Symptom**: Need to recover data but PostgreSQL backup missing

**Solution**:

```bash
# Create emergency backup from live PostgreSQL
pg_dump $DATABASE_URL > backups/emergency_$(date +%Y%m%d_%H%M%S).sql

# Export as CSV for analysis
psql $DATABASE_URL -c "\COPY artifacts TO 'backups/artifacts.csv' CSV HEADER;"

# Compress backup
gzip backups/emergency_*.sql
```

## Related Documentation

- [PostgreSQL Setup Guide](POSTGRESQL_SETUP.md)
- [Phase Three Execution Plan](PHASE_THREE_EXECUTION_PLAN.md)
- [Deployment Guide](DEPLOYMENT.md)
- [Operations Manual](OPERATIONS.md)
- [Backup and Recovery](BACKUP_RECOVERY.md)

## Lessons Learned Log

Document rollback incidents here for future reference:

### Rollback 2025-XX-XX: [Brief Description]

- **Reason**: [What caused the rollback]
- **Duration**: [How long it took]
- **Data Loss**: [What data was lost if any]
- **Root Cause**: [Why the issue occurred]
- **Prevention**: [How to prevent in future]

---

**Last Updated**: 2025-11-12  
**Owner**: Infrastructure Team  
**Review Frequency**: After each rollback or quarterly
