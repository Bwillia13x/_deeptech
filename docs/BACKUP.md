# Signal Harvester - Backup and Restore Procedures

> This guide is part of the maintained documentation set for Signal Harvester.
> For overall architecture, readiness status, and roadmap, refer to [`signal-harvester/ARCHITECTURE_AND_READINESS.md`](signal-harvester/ARCHITECTURE_AND_READINESS.md:1).
> To verify system health and consistency (including migrations and tests), from the `signal-harvester` directory run `make verify-all` (see [`signal-harvester/Makefile`](signal-harvester/Makefile:7)).

## 📋 Overview

This document describes backup and restore procedures for the Signal Harvester system, including database, snapshots, and configuration files.

## 💾 What to Backup

### 1. Database (`var/app.db`)
- **Location**: `var/app.db`
- **Content**: All harvested tweets, analysis results, and metadata
- **Size**: Typically 10MB-1GB depending on volume
- **Criticality**: **HIGH** - Core application data

### 2. Configuration Files
- **Location**: `config/settings.yaml`
- **Content**: Query definitions, LLM settings, scoring weights
- **Criticality**: **HIGH** - Application configuration

### 3. Snapshots (Optional)
- **Location**: `snapshots/`
- **Content**: Historical data exports (JSON, CSV, HTML)
- **Size**: Varies based on retention policy
- **Criticality**: **MEDIUM** - Historical analysis data

### 4. Environment Variables
- **Location**: `.env` file
- **Content**: API keys, database path, secrets
- **Criticality**: **HIGH** - Required for operation
- **Security**: Contains secrets, handle with care

## 🔧 Automated Backup Setup

### Option 1: Built-in Snapshot System

The Signal Harvester includes an automated snapshot system:

```bash
# Create snapshot manually
harvest snapshot --base-dir ./snapshots

# Create snapshot with all formats
harvest snapshot \
  --base-dir ./snapshots \
  --write-ndjson \
  --write-csv \
  --write-checksums \
  --gzip
```

### Option 2: Cron Job Backup

Create a backup script (`scripts/backup.sh`):

```bash
#!/bin/bash
# Signal Harvester Backup Script

set -e

BACKUP_DIR="/backups/signal-harvester/$(date +%Y-%m-%d)"
RETENTION_DAYS=7

# Create backup directory
mkdir -p "$BACKUP_DIR"

echo "Starting backup at $(date)"

# Backup database
echo "Backing up database..."
cp var/app.db "$BACKUP_DIR/app.db.$(date +%H%M%S)"

# Backup configuration
echo "Backing up configuration..."
cp config/settings.yaml "$BACKUP_DIR/"
cp .env "$BACKUP_DIR/env.backup" 2>/dev/null || echo "No .env file found"

# Create snapshots if requested
if [ "$1" = "--with-snapshots" ]; then
    echo "Creating snapshots..."
    harvest snapshot --base-dir "$BACKUP_DIR/snapshots" --gzip
fi

# Compress backup
echo "Compressing backup..."
tar -czf "$BACKUP_DIR.tar.gz" -C /backups/signal-harvester "$(basename "$BACKUP_DIR")"
rm -rf "$BACKUP_DIR"

# Cleanup old backups (older than RETENTION_DAYS)
echo "Cleaning up old backups..."
find /backups/signal-harvester -name "*.tar.gz" -type f -mtime +$RETENTION_DAYS -delete

echo "Backup completed: $BACKUP_DIR.tar.gz"
```

Make it executable and schedule:

```bash
chmod +x scripts/backup.sh

# Add to crontab (run daily at 2 AM)
(crontab -l 2>/dev/null; echo "0 2 * * * /path/to/signal-harvester/scripts/backup.sh") | crontab -

# Or with snapshots (run daily at 2 AM, weekly on Sunday)
(crontab -l 2>/dev/null; echo "0 2 * * * /path/to/signal-harvester/scripts/backup.sh") | crontab -
(crontab -l 2>/dev/null; echo "0 3 * * 0 /path/to/signal-harvester/scripts/backup.sh --with-snapshots") | crontab -
```

### Option 3: Docker Volume Backup

If using Docker, backup the volume:

```bash
#!/bin/bash
# Docker volume backup

BACKUP_NAME="signal-harvester-backup-$(date +%Y%m%d-%H%M%S)"

# Stop containers
docker-compose down

# Backup volumes
tar -czf "/backups/${BACKUP_NAME}.tar.gz" \
  -C /var/lib/docker/volumes \
  signal-harvester_var \
  signal-harvester_data

# Restart containers
docker-compose up -d

echo "Backup created: /backups/${BACKUP_NAME}.tar.gz"
```

## ☁️ Cloud Backup Options

### AWS S3 Backup

```bash
#!/bin/bash
# Backup to AWS S3

BACKUP_NAME="signal-harvester-$(date +%Y%m%d-%H%M%S).tar.gz"

# Create local backup
tar -czf "/tmp/${BACKUP_NAME}" \
  -C /path/to/signal-harvester \
  var/app.db \
  config/settings.yaml

# Upload to S3
aws s3 cp "/tmp/${BACKUP_NAME}" s3://your-bucket/signal-harvester/backups/

# Cleanup local file
rm "/tmp/${BACKUP_NAME}"

# Set S3 lifecycle policy for automatic cleanup
# Or manually delete old backups:
# aws s3 ls s3://your-bucket/signal-harvester/backups/ | head -n -30 | awk '{print $4}' | xargs -I {} aws s3 rm s3://your-bucket/{}
```

### Google Cloud Storage

```bash
#!/bin/bash
# Backup to Google Cloud Storage

BACKUP_NAME="signal-harvester-$(date +%Y%m%d-%H%M%S).tar.gz"

# Create local backup
tar -czf "/tmp/${BACKUP_NAME}" \
  -C /path/to/signal-harvester \
  var/app.db \
  config/settings.yaml

# Upload to GCS
gsutil cp "/tmp/${BACKUP_NAME}" gs://your-bucket/signal-harvester/backups/

# Cleanup local file
rm "/tmp/${BACKUP_NAME}"

# Set GCS lifecycle policy for automatic cleanup
```

## 🔄 Restore Procedures

### Database Restore

#### Option 1: From SQLite Backup

```bash
# Stop the application
docker-compose down

# Restore database
cp /backups/signal-harvester/2024-01-01/app.db.120000 var/app.db

# Fix permissions (if needed)
chown 1000:1000 var/app.db

# Restart application
docker-compose up -d

# Verify restoration
docker-compose exec signal-harvester harvest stats
```

#### Option 2: From Snapshot

```bash
# Restore from latest snapshot
LATEST_SNAPSHOT=$(ls -t snapshots/2024-*/data.json.gz | head -n1)

# Extract and load
gunzip -c "$LATEST_SNAPSHOT" > /tmp/snapshot.json

# Use the CLI to restore (you may need to create a restore command)
# Or manually import:
sqlite3 var/app.db ".read /tmp/restore_script.sql"
```

### Full System Restore

```bash
#!/bin/bash
# Full system restore from backup

BACKUP_FILE="$1"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup-file.tar.gz>"
    exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "Backup file not found: $BACKUP_FILE"
    exit 1
fi

# Stop application
docker-compose down

echo "Restoring from $BACKUP_FILE..."

# Extract backup
tar -xzf "$BACKUP_FILE" -C /tmp/restore

# Restore database
cp /tmp/restore/var/app.db* var/ 2>/dev/null || echo "No database in backup"

# Restore configuration
cp /tmp/restore/config/settings.yaml config/ 2>/dev/null || echo "No config in backup"

# Restore snapshots (if they exist)
if [ -d "/tmp/restore/snapshots" ]; then
    cp -r /tmp/restore/snapshots/* snapshots/ 2>/dev/null || echo "No snapshots in backup"
fi

# Cleanup
rm -rf /tmp/restore

# Fix permissions
chown -R 1000:1000 var/ data/ snapshots/

# Restart application
docker-compose up -d

echo "Restore completed!"
echo "Verify with: docker-compose exec signal-harvester harvest stats"
```

## 📊 Backup Verification

### Automated Verification Script

```bash
#!/bin/bash
# Verify backup integrity

BACKUP_FILE="$1"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup-file.tar.gz>"
    exit 1
fi

echo "Verifying backup: $BACKUP_FILE"

# Check if file exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file not found"
    exit 1
fi

# Check if file is readable
if ! tar -tzf "$BACKUP_FILE" >/dev/null 2>&1; then
    echo "ERROR: Backup file is corrupted or not a valid tar.gz"
    exit 1
fi

# List contents
echo "Backup contents:"
tar -tzf "$BACKUP_FILE"

# Check for critical files
echo "Checking for critical files..."
CRITICAL_FILES=("var/app.db" "config/settings.yaml")
for file in "${CRITICAL_FILES[@]}"; do
    if tar -tzf "$BACKUP_FILE" | grep -q "^${file}$"; then
        echo "✓ $file found"
    else
        echo "✗ $file MISSING"
    fi
done

echo "Backup verification completed"
```

## 🚨 Disaster Recovery Scenarios

### Scenario 1: Database Corruption

```bash
# 1. Stop application
docker-compose down

# 2. Restore from latest backup
LATEST_BACKUP=$(ls -t /backups/signal-harvester/*.tar.gz | head -n1)
./scripts/restore.sh "$LATEST_BACKUP"

# 3. Verify data integrity
docker-compose exec signal-harvester harvest verify

# 4. Check for data loss
./scripts/check_data_loss.sh
```

### Scenario 2: Complete System Loss

```bash
# 1. Set up new server with Docker and dependencies

# 2. Clone repository
git clone <repository-url>
cd signal-harvester

# 3. Restore from backup
./scripts/restore.sh /path/to/latest/backup.tar.gz

# 4. Configure environment
cp .env.example .env
# Edit .env with API keys

# 5. Start application
docker-compose up -d

# 6. Verify operation
curl http://localhost:8000/health
```

### Scenario 3: Accidental Data Deletion

```bash
# If recent deletion and using WAL mode:

# 1. Stop writes immediately
docker-compose stop scheduler

# 2. Copy database files
cp var/app.db var/app.db.emergency
cp var/app.db-wal var/app.db-wal.emergency 2>/dev/null

# 3. Try to extract deleted rows (requires forensic tools)
# This is complex - better to restore from backup if available

# 4. If no backup, use snapshot to recover most recent data
LATEST_SNAPSHOT=$(ls -t snapshots/2024-*/data.json.gz | head -n1)
# Manually extract important data and re-insert
```

## 📅 Backup Schedule Recommendations

### Small Scale (< 10k tweets/day)
- **Database**: Daily at 2 AM
- **Snapshots**: Weekly
- **Retention**: 30 days

### Medium Scale (10k-100k tweets/day)
- **Database**: Daily at 2 AM and 2 PM
- **Snapshots**: Daily
- **Retention**: 14 days

### Large Scale (> 100k tweets/day)
- **Database**: Every 6 hours
- **Snapshots**: Every 6 hours
- **Retention**: 7 days
- **Consider**: Streaming backups, read replicas

## 🔐 Security Considerations

### Backup Encryption

```bash
# Encrypt backup with GPG
tar -czf - var/app.db config/settings.yaml | \
  gpg --cipher-algo AES256 --compress-algo 1 --symmetric --output backup.tar.gz.gpg

# Decrypt
gpg --decrypt backup.tar.gz.gpg | tar -xzf -
```

### Secure Storage

- Store backups in encrypted storage
- Keep .env files separate and encrypted
- Use separate backup credentials
- Implement least-privilege access
- Regularly test backup restoration

### Offsite Backups

Always maintain offsite backups:

```bash
# Sync to remote server
rsync -avz /backups/signal-harvester/ user@backup-server:/backups/harvester/

# Or use rclone for cloud storage
rclone sync /backups/signal-harvester/ remote:backups/harvester/
```

## 📝 Maintenance Tasks

### Daily
- [ ] Check backup completion
- [ ] Verify backup file sizes are reasonable
- [ ] Monitor backup storage space

### Weekly
- [ ] Test restore from backup (staging environment)
- [ ] Review backup logs
- [ ] Clean up old backups

### Monthly
- [ ] Full disaster recovery drill
- [ ] Review and update backup procedures
- [ ] Verify offsite backup integrity
- [ ] Update encryption keys if needed

## 📞 Support

If you encounter issues with backups or restoration:

1. Check the troubleshooting guide in DEPLOYMENT.md
2. Verify backup integrity with verification script
3. Test restoration in staging environment
4. Check available disk space
5. Review application logs for errors

For critical data loss, contact the development team immediately.
