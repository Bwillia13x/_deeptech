# Database Backup & Disaster Recovery Guide

**Last Updated:** November 11, 2025  
**Version:** 1.0  
**Audience:** DevOps, SRE, Database Administrators

---

## Table of Contents

1. [Overview](#overview)
2. [Backup Types](#backup-types)
3. [Configuration](#configuration)
4. [Backup Operations](#backup-operations)
5. [Restore Procedures](#restore-procedures)
6. [Disaster Recovery](#disaster-recovery)
7. [RTO & RPO](#rto--rpo)
8. [Testing & Validation](#testing--validation)
9. [Monitoring & Alerts](#monitoring--alerts)
10. [Troubleshooting](#troubleshooting)
11. [Best Practices](#best-practices)

---

## Overview

Signal Harvester uses SQLite for data storage with comprehensive backup and recovery capabilities. The backup system supports:

- **Automated scheduled backups** (daily, weekly, monthly)
- **Multiple backup types** (full, incremental, WAL-based)
- **Compression** (gzip, zstd) for storage efficiency
- **Cloud storage integration** (S3, GCS, Azure)
- **Retention policies** with automatic pruning
- **Backup verification** and integrity checking
- **Point-in-time recovery** capabilities

### Architecture

```
┌─────────────────┐
│ SQLite Database │
│  (var/app.db)   │
└────────┬────────┘
         │
         ├─── Backup Engine ───┐
         │                     │
    ┌────▼──────┐       ┌──────▼───────┐
    │  Local    │       │   Cloud      │
    │  Storage  │──────▶│   Storage    │
    │ (backups/)│       │ (S3/GCS/Az)  │
    └───────────┘       └──────────────┘
         │
    ┌────▼──────────┐
    │  Retention    │
    │  Management   │
    └───────────────┘
```

---

## Backup Types

### 1. Full Backup

**Description:** Complete copy of the entire database using SQLite's backup API.

**Use Cases:**

- Initial baseline backups
- Pre-deployment safety snapshots
- Migration and archival

**Characteristics:**

- **Size:** Full database size (compressed)
- **Duration:** ~10-30 seconds for typical databases
- **Storage:** Largest backup type
- **Restore:** Fastest restore process

**Command:**

```bash
harvest backup create --type full --description "Pre-deployment backup"
```

**Output:**

```
✓ Created full backup: backup_20251111_020000_full.db.gz
  Size: 15.3 MB (compressed from 42.1 MB)
  Duration: 12.4 seconds
  Compression ratio: 2.75x
  Backup ID: bkp_20251111_020000_abc123
```

### 2. Incremental Backup

**Description:** Captures only changes since the last backup (currently implemented as full backup).

**Use Cases:**

- Frequent backups with minimal storage
- High-change databases
- Cost optimization

**Status:** 🚧 **Planned** - Currently creates full backups

**Future Implementation:**

- Track changed pages using WAL
- Store delta files
- Chain backups for point-in-time recovery

### 3. WAL (Write-Ahead Log) Backup

**Description:** Creates backup while database is actively being written to.

**Use Cases:**

- Zero-downtime backups
- Production environments
- High-availability systems

**Characteristics:**

- **Consistency:** Uses SQLite checkpoint mechanism
- **Impact:** Minimal performance impact
- **Safety:** No database locks required

**Command:**

```bash
harvest backup create --type wal --description "Production live backup"
```

---

## Configuration

### Backup Settings (`config/settings.yaml`)

```yaml
app:
  backup:
    # Basic configuration
    enabled: true
    backup_dir: "backups"
    compression: "gzip" # Options: none, gzip, zstd
    retention_days: 90

    # Automated scheduling
    schedule:
      daily_enabled: true
      daily_time: "02:00" # UTC
      weekly_enabled: true
      weekly_day: "sunday"
      weekly_time: "03:00" # UTC
      monthly_enabled: true
      monthly_day: 1 # 1st of month
      monthly_time: "04:00" # UTC

    # Retention policy
    retention:
      daily_keep: 7 # Last 7 days
      weekly_keep: 4 # Last 4 weeks
      monthly_keep: 12 # Last 12 months

    # S3 configuration
    s3:
      enabled: true
      bucket: "signal-harvester-backups"
      prefix: "production/backups"
      region: "us-east-1"
      upload_after_backup: true

    # Verification
    verification:
      verify_after_backup: true
      verify_before_restore: true
```

### Environment Variables

```bash
# AWS credentials for S3 uploads
export AWS_ACCESS_KEY_ID="AKIAIOSFODNN7EXAMPLE"
export AWS_SECRET_ACCESS_KEY="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
export AWS_DEFAULT_REGION="us-east-1"

# GCS credentials (alternative)
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"

# Azure credentials (alternative)
export AZURE_STORAGE_ACCOUNT="yourstorageaccount"
export AZURE_STORAGE_KEY="your-storage-key"
```

---

## Backup Operations

### Manual Backup Creation

#### Create Full Backup

```bash
# Basic backup
harvest backup create

# With custom description
harvest backup create --description "Before schema migration v2.5"

# Specific backup type
harvest backup create --type full

# With S3 upload
harvest backup create --upload-s3

# Skip verification (faster, not recommended)
harvest backup create --no-verify
```

#### Create Compressed Backup

```bash
# Gzip compression (default)
harvest backup create --compression gzip

# Zstandard compression (better ratio, requires zstandard package)
harvest backup create --compression zstd

# No compression (faster, larger files)
harvest backup create --compression none
```

### List Backups

```bash
# List all backups
harvest backup list

# Filter by type
harvest backup list --type full
harvest backup list --type incremental

# Show detailed information
harvest backup list --verbose
```

**Example Output:**

```
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┓
┃ Backup ID          ┃ Type   ┃ Size    ┃ Created            ┃ Description          ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━┩
│ bkp_20251111_02... │ full   │ 15.3 MB │ 2025-11-11 02:00   │ Daily backup         │
│ bkp_20251110_02... │ full   │ 14.8 MB │ 2025-11-10 02:00   │ Daily backup         │
│ bkp_20251109_03... │ full   │ 14.2 MB │ 2025-11-09 03:00   │ Weekly backup        │
└────────────────────┴────────┴─────────┴────────────────────┴──────────────────────┘

Total: 3 backups, 44.3 MB
```

### Verify Backups

```bash
# Verify specific backup
harvest backup verify <backup-id>

# Verify all backups
harvest backup verify --all

# Check specific backup file
harvest backup verify --file backups/backup_20251111_020000_full.db.gz
```

**Verification Process:**

1. ✓ File exists and is readable
2. ✓ Decompression successful (if compressed)
3. ✓ SQLite database integrity check
4. ✓ Schema validation
5. ✓ Table row counts match metadata

### Cloud Storage Operations

#### Upload to S3

```bash
# Upload specific backup
harvest backup upload <backup-id>

# Upload all local backups not in S3
harvest backup upload --all

# Custom S3 bucket
harvest backup upload <backup-id> --bucket my-other-bucket
```

#### Download from S3

```bash
# List available S3 backups
harvest backup list --s3

# Download specific backup
harvest backup download <backup-id>

# Download to custom location
harvest backup download <backup-id> --output /path/to/backup.db.gz
```

### Retention Management

```bash
# Preview what would be deleted
harvest backup prune --dry-run

# Apply retention policy
harvest backup prune

# Force prune (skip confirmation)
harvest backup prune --force
```

**Retention Logic:**

- **Daily backups:** Keep last 7 (default)
- **Weekly backups:** Keep last 4 (default)
- **Monthly backups:** Keep last 12 (default)
- Backups uploaded to S3 are preserved
- Manual backups (no schedule) never auto-pruned

---

## Restore Procedures

### Standard Restore Process

#### 1. List Available Backups

```bash
harvest backup list
```

#### 2. Verify Backup Before Restore

```bash
harvest backup verify <backup-id>
```

#### 3. Stop Application (Important!)

```bash
# Stop API server
pkill -f "harvest api"

# Or stop Docker containers
docker-compose down
```

#### 4. Create Pre-Restore Backup

```bash
harvest backup create --description "Before restore from backup <backup-id>"
```

#### 5. Restore Database

```bash
# Restore specific backup
harvest backup restore <backup-id>

# Restore with confirmation
harvest backup restore <backup-id> --confirm

# Restore to different location
harvest backup restore <backup-id> --output /path/to/restored.db
```

#### 6. Verify Restored Database

```bash
# Check database integrity
sqlite3 var/app.db "PRAGMA integrity_check;"

# Verify row counts
harvest stats
```

#### 7. Restart Application

```bash
# Start API server
harvest api

# Or start Docker containers
docker-compose up -d
```

### Restore Output Example

```
⚠ WARNING: This will overwrite the current database!
  Current database: var/app.db (42.1 MB, modified 2025-11-11 14:30)
  Restore from: backup_20251111_020000_full.db.gz
  Created: 2025-11-11 02:00
  Type: full
  Size: 15.3 MB (compressed)

Continue with restore? [y/N]: y

✓ Created safety backup: bkp_20251111_143245_pre_restore.db.gz
✓ Downloaded backup from S3 (if needed)
✓ Decompressed backup file
✓ Verified backup integrity
✓ Restored database to var/app.db
✓ Verified restored database

Database restored successfully!
  Restored from: backup_20251111_020000_full.db.gz
  Backup created: 2025-11-11 02:00
  Restoration time: 8.2 seconds
  Database size: 42.1 MB
```

### Emergency Restore from S3

If local backups are lost:

```bash
# 1. Download backup from S3
harvest backup download <backup-id>

# 2. Restore from downloaded backup
harvest backup restore <backup-id>
```

---

## Disaster Recovery

### Scenario 1: Database Corruption

**Symptoms:**

- SQLite error: "database disk image is malformed"
- Application crashes on database queries
- PRAGMA integrity_check fails

**Recovery Steps:**

```bash
# 1. Stop application immediately
docker-compose down

# 2. Verify corruption
sqlite3 var/app.db "PRAGMA integrity_check;"
# Output: "*** in database main ***"

# 3. List available backups
harvest backup list

# 4. Restore from most recent valid backup
harvest backup restore <latest-backup-id> --confirm

# 5. Restart application
docker-compose up -d

# 6. Verify service health
curl http://localhost:8000/health
```

**Prevention:**

- Enable WAL mode (enabled by default)
- Use backup verification
- Monitor disk space
- Regular integrity checks

### Scenario 2: Accidental Data Deletion

**Symptoms:**

- User reports missing signals/discoveries
- Row counts significantly decreased
- Audit logs show bulk delete operation

**Recovery Steps:**

```bash
# 1. Identify when deletion occurred
harvest backup list | grep "2025-11-10"

# 2. Find backup before deletion
# Look for backup created before the incident

# 3. Restore to temporary location
harvest backup restore <backup-id> --output /tmp/restored.db

# 4. Extract specific data
sqlite3 /tmp/restored.db <<EOF
.mode csv
.output /tmp/recovered_data.csv
SELECT * FROM signals WHERE created_at >= '2025-11-10';
.quit
EOF

# 5. Import recovered data
sqlite3 var/app.db <<EOF
.mode csv
.import /tmp/recovered_data.csv signals_temp
INSERT INTO signals SELECT * FROM signals_temp WHERE id NOT IN (SELECT id FROM signals);
DROP TABLE signals_temp;
.quit
EOF

# 6. Verify recovery
harvest stats
```

### Scenario 3: Complete Server Failure

**Symptoms:**

- Server hardware failure
- Disk failure
- Complete data loss on primary server

**Recovery Steps:**

```bash
# 1. Provision new server
# 2. Install Signal Harvester
git clone <repo>
cd signal-harvester
pip install -e .

# 3. Configure AWS credentials
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."

# 4. Initialize database structure
harvest init-db

# 5. List S3 backups
harvest backup list --s3

# 6. Download and restore latest backup
harvest backup download <latest-backup-id>
harvest backup restore <latest-backup-id> --confirm

# 7. Start application
docker-compose up -d

# 8. Verify recovery
curl http://localhost:8000/health
harvest stats
```

**Expected Recovery Time:** 30-60 minutes

### Scenario 4: Ransomware Attack

**Symptoms:**

- Files encrypted
- Database inaccessible
- Ransom note present

**Recovery Steps:**

```bash
# 1. Isolate affected server immediately
# 2. Do NOT pay ransom
# 3. Provision clean server
# 4. Follow "Complete Server Failure" recovery steps
# 5. Restore from S3 backups (attackers typically don't have cloud access)
# 6. Audit access logs
# 7. Rotate all credentials
# 8. Implement additional security measures
```

**Critical:** Never restore backups to infected server

---

## RTO & RPO

### Recovery Time Objective (RTO)

**Definition:** Maximum acceptable time to restore service after a disaster.

| Scenario | Target RTO | Actual RTO | Steps |
|----------|-----------|------------|-------|
| Database corruption | 15 minutes | 10-15 min | Stop → Restore → Start |
| Accidental deletion | 30 minutes | 20-40 min | Identify → Extract → Import |
| Server failure | 60 minutes | 30-60 min | Provision → Install → Restore |
| Ransomware | 120 minutes | 60-120 min | Isolate → Clean server → Restore |

### Recovery Point Objective (RPO)

**Definition:** Maximum acceptable data loss measured in time.

| Backup Type | Frequency | RPO | Data Loss |
|-------------|-----------|-----|-----------|
| Daily backup | 02:00 UTC | 24 hours | Up to 1 day |
| Weekly backup | Sunday 03:00 | 7 days | Up to 1 week |
| Monthly backup | 1st 04:00 | 30 days | Up to 1 month |
| Manual backup | On-demand | 0 | None (if recent) |

**Improving RPO:**

To achieve sub-hour RPO:

```yaml
# Enable hourly backups (requires custom schedule)
schedule:
  hourly_enabled: true
  hourly_interval: 1 # Every 1 hour
```

Or use WAL archiving for continuous backup:

```bash
# Archive WAL files continuously
harvest backup create --type wal --continuous
```

---

## Testing & Validation

### Monthly Restore Test

**Objective:** Validate backup and restore procedures work correctly.

**Schedule:** First Monday of each month

**Procedure:**

```bash
#!/bin/bash
# monthly_restore_test.sh

set -e

echo "=== Monthly Backup Restore Test ==="
echo "Date: $(date)"

# 1. Select most recent backup
BACKUP_ID=$(harvest backup list --json | jq -r '.[0].backup_id')
echo "Testing backup: $BACKUP_ID"

# 2. Create test directory
TEST_DIR="/tmp/backup_test_$(date +%Y%m%d)"
mkdir -p "$TEST_DIR"
cd "$TEST_DIR"

# 3. Restore to test location
echo "Restoring backup..."
harvest backup restore "$BACKUP_ID" --output "$TEST_DIR/test.db"

# 4. Verify database integrity
echo "Verifying integrity..."
sqlite3 "$TEST_DIR/test.db" "PRAGMA integrity_check;" | grep -q "ok"

# 5. Check row counts
echo "Checking row counts..."
SIGNALS=$(sqlite3 "$TEST_DIR/test.db" "SELECT COUNT(*) FROM signals;")
DISCOVERIES=$(sqlite3 "$TEST_DIR/test.db" "SELECT COUNT(*) FROM discoveries;")
echo "Signals: $SIGNALS"
echo "Discoveries: $DISCOVERIES"

# 6. Verify S3 access
echo "Verifying S3 access..."
harvest backup list --s3 > /dev/null

# 7. Cleanup
echo "Cleaning up..."
rm -rf "$TEST_DIR"

echo "✓ Backup restore test PASSED"
echo "=========================="
```

**Run Test:**

```bash
chmod +x monthly_restore_test.sh
./monthly_restore_test.sh
```

### Quarterly Disaster Recovery Drill

**Objective:** Validate complete disaster recovery process.

**Schedule:** Quarterly (January, April, July, October)

**Drill Scenario:**

1. Simulate complete server failure
2. Provision new server (or VM)
3. Perform full recovery from S3
4. Validate application functionality
5. Document recovery time
6. Update procedures based on findings

**Checklist:**

- [ ] Fresh server provisioned
- [ ] Dependencies installed
- [ ] AWS credentials configured
- [ ] Database restored from S3
- [ ] Application started
- [ ] Health checks passing
- [ ] Sample queries successful
- [ ] Recovery time documented
- [ ] Lessons learned recorded

---

## Monitoring & Alerts

### Prometheus Metrics

The backup system exposes comprehensive metrics:

```promql
# Backup operations
backup_runs_total{backup_type="full",status="success"}
backup_runs_total{backup_type="full",status="failure"}

# Backup duration
backup_duration_seconds{backup_type="full",operation="create"}
backup_duration_seconds{backup_type="full",operation="verify"}

# Backup size
backup_size_bytes{backup_type="full",compression="gzip"}

# Backup age
backup_oldest_age_seconds
backup_newest_age_seconds

# Backup count
backup_total_count{backup_type="full"}

# Upload operations
backup_uploads_total{destination="s3",status="success"}
backup_upload_duration_seconds{destination="s3"}

# Errors
backup_errors_total{operation="create",error_type="disk_full"}
```

### Alert Rules

Add to `monitoring/prometheus/alerts.yml`:

```yaml
groups:
  - name: backup_alerts
    interval: 5m
    rules:
      - alert: BackupFailure
        expr: increase(backup_runs_total{status="failure"}[1h]) > 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Backup operation failed"
          description: "{{ $labels.backup_type }} backup failed ({{ $value }} failures in last hour)"

      - alert: BackupTooOld
        expr: backup_newest_age_seconds > 86400 * 2 # 2 days
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "No recent backups"
          description: "Last backup is {{ $value | humanizeDuration }} old"

      - alert: BackupVerificationFailed
        expr: increase(backup_verifications_total{status="failed"}[1h]) > 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Backup verification failed"
          description: "Backup verification failed ({{ $value }} failures)"

      - alert: S3UploadFailure
        expr: increase(backup_uploads_total{status="failure"}[1h]) > 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "S3 upload failed"
          description: "Failed to upload backup to S3 ({{ $value }} failures)"

      - alert: LowBackupCount
        expr: backup_total_count < 3
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "Low backup count"
          description: "Only {{ $value }} backups available (expected >= 7)"
```

### Grafana Dashboard

Create a backup monitoring dashboard:

```json
{
  "dashboard": {
    "title": "Database Backups",
    "panels": [
      {
        "title": "Backup Success Rate",
        "targets": [{
          "expr": "rate(backup_runs_total{status=\"success\"}[1h]) / rate(backup_runs_total[1h])"
        }]
      },
      {
        "title": "Backup Age",
        "targets": [{
          "expr": "backup_newest_age_seconds / 3600",
          "legendFormat": "Hours since last backup"
        }]
      },
      {
        "title": "Backup Size Trend",
        "targets": [{
          "expr": "backup_size_bytes"
        }]
      },
      {
        "title": "Backup Duration",
        "targets": [{
          "expr": "backup_duration_seconds"
        }]
      }
    ]
  }
}
```

---

## Troubleshooting

### Issue: Backup Creation Fails

**Symptoms:**

```
Error: Failed to create backup
sqlite3.OperationalError: disk I/O error
```

**Diagnosis:**

```bash
# Check disk space
df -h

# Check file permissions
ls -la var/
ls -la backups/

# Check database status
sqlite3 var/app.db "PRAGMA integrity_check;"
```

**Solutions:**

1. **Disk Full:**

   ```bash
   # Free up space
   harvest backup prune --force
   
   # Or clean old snapshots
   rm -rf snapshots/2024-*
   ```

2. **Permission Issues:**

   ```bash
   # Fix permissions
   chmod 755 backups/
   chmod 644 var/app.db
   ```

3. **Database Locked:**

   ```bash
   # Stop application
   docker-compose down
   
   # Create backup
   harvest backup create
   
   # Restart
   docker-compose up -d
   ```

### Issue: Restore Fails

**Symptoms:**

```
Error: Failed to restore backup
ValueError: Backup verification failed
```

**Diagnosis:**

```bash
# Verify backup integrity
harvest backup verify <backup-id>

# Check backup file
file backups/backup_*.db.gz
gunzip -t backups/backup_*.db.gz
```

**Solutions:**

1. **Corrupted Backup:**

   ```bash
   # Try older backup
   harvest backup list
   harvest backup restore <older-backup-id>
   ```

2. **Compression Error:**

   ```bash
   # Download fresh copy from S3
   harvest backup download <backup-id>
   harvest backup restore <backup-id>
   ```

3. **Insufficient Space:**

   ```bash
   # Check space
   df -h
   
   # Free up space or use different location
   harvest backup restore <backup-id> --output /mnt/large-disk/restored.db
   ```

### Issue: S3 Upload Fails

**Symptoms:**

```
Error: Failed to upload to S3
botocore.exceptions.NoCredentialsError: Unable to locate credentials
```

**Diagnosis:**

```bash
# Check AWS credentials
aws sts get-caller-identity

# Test S3 access
aws s3 ls s3://signal-harvester-backups/
```

**Solutions:**

1. **Missing Credentials:**

   ```bash
   # Set credentials
   export AWS_ACCESS_KEY_ID="..."
   export AWS_SECRET_ACCESS_KEY="..."
   
   # Or use AWS CLI config
   aws configure
   ```

2. **Wrong Bucket:**

   ```yaml
   # Check config/settings.yaml
   s3:
     bucket: "correct-bucket-name"
     region: "correct-region"
   ```

3. **Permission Issues:**

   ```json
   // Ensure IAM policy includes:
   {
     "Effect": "Allow",
     "Action": [
       "s3:PutObject",
       "s3:GetObject",
       "s3:ListBucket"
     ],
     "Resource": [
       "arn:aws:s3:::signal-harvester-backups",
       "arn:aws:s3:::signal-harvester-backups/*"
     ]
   }
   ```

### Issue: Scheduler Not Running

**Symptoms:**

- No automated backups created
- Logs show: "Scheduler not started"

**Diagnosis:**

```bash
# Check scheduler status
ps aux | grep "backup.*scheduler"

# Check logs
tail -f logs/app.log | grep scheduler
```

**Solutions:**

1. **Start Scheduler:**

   ```bash
   # Start in background
   harvest backup scheduler start &
   
   # Or use systemd (recommended)
   sudo systemctl start signal-harvester-backup-scheduler
   ```

2. **Check Schedule Configuration:**

   ```yaml
   # Ensure at least one schedule enabled
   schedule:
     daily_enabled: true
     daily_time: "02:00"
   ```

3. **Verify Cron Triggers:**

   ```bash
   # Check scheduler logs
   tail -f logs/backup_scheduler.log
   ```

---

## Best Practices

### 1. The 3-2-1 Backup Rule

✓ **3 copies** of data:

- Original database
- Local backup
- S3 backup

✓ **2 different media types**:

- Local disk (SSD)
- Cloud storage (S3)

✓ **1 offsite copy**:

- S3 in different region
- Or GCS/Azure as secondary

### 2. Backup Verification

**Always verify backups:**

```bash
# Enable in config
verification:
  verify_after_backup: true
  verify_before_restore: true
```

**Manual verification:**

```bash
# Verify all backups monthly
harvest backup verify --all
```

### 3. Test Restores Regularly

**Schedule:**

- Monthly: Test restore of latest backup
- Quarterly: Full disaster recovery drill
- Annually: Complete environment rebuild

**Document results:**

```bash
# Create test log
echo "$(date): Restore test PASSED, RTO: 12 minutes" >> tests/restore_test_log.txt
```

### 4. Monitor Backup Health

**Key metrics to track:**

- Backup success rate (target: 100%)
- Backup age (target: < 24 hours)
- Backup size trend (detect anomalies)
- S3 upload success rate (target: 100%)

### 5. Secure Backups

**Encryption at rest:**

```bash
# S3 server-side encryption
aws s3 cp backup.db.gz s3://bucket/ --sse AES256
```

**Access control:**

```bash
# Restrict backup directory
chmod 700 backups/
chown app:app backups/
```

**Credential rotation:**

```bash
# Rotate AWS keys quarterly
aws iam create-access-key --user-name backup-user
# Update .env with new keys
# Delete old keys
aws iam delete-access-key --access-key-id OLD_KEY --user-name backup-user
```

### 6. Retention Policy

**Recommended retention:**

- Daily: 7 days (for recent incidents)
- Weekly: 4 weeks (for medium-term recovery)
- Monthly: 12 months (for long-term compliance)

**Adjust based on:**

- Compliance requirements
- Storage costs
- Data change rate
- Recovery scenarios

### 7. Documentation

**Maintain:**

- Recovery procedures (this document)
- Contact information (on-call rotation)
- Credential locations (password manager)
- Test results (restore test logs)
- Incident reports (lessons learned)

---

## Quick Reference

### Common Commands

```bash
# Create backup
harvest backup create

# List backups
harvest backup list

# Verify backup
harvest backup verify <backup-id>

# Restore backup
harvest backup restore <backup-id>

# Upload to S3
harvest backup upload <backup-id>

# Prune old backups
harvest backup prune

# Start scheduler
harvest backup scheduler start

# Stop scheduler
harvest backup scheduler stop
```

### Emergency Contacts

| Role | Contact | Availability |
|------|---------|--------------|
| Primary DBA | <ops-dba@company.com> | 24/7 |
| DevOps On-call | <ops-oncall@company.com> | 24/7 |
| AWS Support | <aws-support@company.com> | Business hours |
| Escalation | <cto@company.com> | Emergency only |

### Critical Files

| File | Purpose | Backup Frequency |
|------|---------|------------------|
| `var/app.db` | Main database | Hourly recommended |
| `config/settings.yaml` | Configuration | On change |
| `.env` | Secrets | On change (secure) |
| `backups/` | Local backups | N/A (source) |

---

## Appendix

### A. Backup File Naming Convention

```
backup_<timestamp>_<type>.<extension>

Examples:
- backup_20251111_020000_full.db.gz
- backup_20251111_143000_wal.db.zst
- backup_20251110_030000_weekly.db.gz
```

### B. Compression Comparison

| Type | Ratio | Speed | CPU | Recommendation |
|------|-------|-------|-----|----------------|
| none | 1.0x | Fast | None | Testing only |
| gzip | 2.5-3x | Medium | Low | Default choice |
| zstd | 3-4x | Fast | Medium | Best option (if available) |

### C. S3 Storage Classes

| Class | Use Case | Cost | Retrieval |
|-------|----------|------|-----------|
| Standard | Daily/weekly backups | $$$ | Immediate |
| IA | Monthly backups | $$ | Minutes |
| Glacier | Archival | $ | Hours |
| Deep Archive | Compliance | ¢ | 12+ hours |

**Recommendation:** Use Standard for all active backups, Glacier for archives >1 year old.

### D. SQLite Backup API vs File Copy

| Method | Pros | Cons |
|--------|------|------|
| SQLite Backup API | Consistent, handles WAL, safer | Requires app |
| File copy | Simple, fast | May be inconsistent, requires exclusive lock |

**Signal Harvester uses:** SQLite Backup API for safety and consistency.

---

**Document Version:** 1.0  
**Last Updated:** November 11, 2025  
**Next Review:** February 11, 2026  
**Maintained By:** DevOps Team
