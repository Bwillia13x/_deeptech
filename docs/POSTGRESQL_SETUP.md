# PostgreSQL Setup Guide

This guide walks you through setting up PostgreSQL for Signal Harvester development and production use.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
  - [macOS (Homebrew)](#macos-homebrew)
  - [Ubuntu/Debian](#ubuntudebian)
  - [Windows](#windows)
  - [Docker](#docker)
- [Database Configuration](#database-configuration)
- [Connection String Setup](#connection-string-setup)
- [Running Migrations](#running-migrations)
- [Data Migration from SQLite](#data-migration-from-sqlite)
- [Testing Connection](#testing-connection)
- [Troubleshooting](#troubleshooting)
- [Production Considerations](#production-considerations)

## Prerequisites

- Python 3.10+ with Signal Harvester installed
- PostgreSQL 13+ (recommended: 15 or 16)
- At least 2GB free disk space for development
- Admin/sudo access for installation

## Installation

### macOS (Homebrew)

```bash
# Install PostgreSQL
brew install postgresql@16

# Start PostgreSQL service
brew services start postgresql@16

# Add to PATH (if not already)
echo 'export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

# Verify installation
psql --version
# Should output: psql (PostgreSQL) 16.x
```

### Ubuntu/Debian

```bash
# Add PostgreSQL APT repository
sudo sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
wget -qO- https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo tee /etc/apt/trusted.gpg.d/pgdg.asc

# Install PostgreSQL
sudo apt update
sudo apt install -y postgresql-16 postgresql-contrib-16

# Start PostgreSQL service
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Verify installation
psql --version
```

### Windows

**Option 1: PostgreSQL Installer**

1. Download installer from https://www.postgresql.org/download/windows/
2. Run installer and follow wizard (default settings recommended)
3. Remember the password you set for the `postgres` user
4. Add PostgreSQL bin directory to PATH: `C:\Program Files\PostgreSQL\16\bin`

**Option 2: WSL2 + Ubuntu**

Follow the Ubuntu instructions above within WSL2.

### Docker

```bash
# Pull PostgreSQL image
docker pull postgres:16-alpine

# Run PostgreSQL container
docker run -d \
  --name signal-harvester-db \
  -e POSTGRES_PASSWORD=changeme \
  -e POSTGRES_USER=signal_harvester \
  -e POSTGRES_DB=signal_harvester \
  -p 5432:5432 \
  -v signal-harvester-data:/var/lib/postgresql/data \
  postgres:16-alpine

# Verify container is running
docker ps | grep signal-harvester-db
```

## Database Configuration

### Create Database and User

**macOS/Linux:**

```bash
# Connect as postgres superuser
psql postgres

# Or on Ubuntu:
sudo -u postgres psql
```

**SQL commands (run in psql):**

```sql
-- Create user
CREATE USER signal_harvester WITH PASSWORD 'your_secure_password_here';

-- Create database
CREATE DATABASE signal_harvester OWNER signal_harvester;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE signal_harvester TO signal_harvester;

-- Connect to database
\c signal_harvester

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO signal_harvester;

-- Exit psql
\q
```

### Configure Authentication (pg_hba.conf)

**macOS (Homebrew):**
- Location: `/opt/homebrew/var/postgresql@16/pg_hba.conf`

**Ubuntu/Debian:**
- Location: `/etc/postgresql/16/main/pg_hba.conf`

**Add this line for local development:**

```conf
# TYPE  DATABASE           USER              ADDRESS      METHOD
host    signal_harvester   signal_harvester  127.0.0.1/32 md5
```

**Reload PostgreSQL:**

```bash
# macOS
brew services restart postgresql@16

# Ubuntu/Debian
sudo systemctl restart postgresql

# Docker
docker restart signal-harvester-db
```

## Connection String Setup

### Format

```
postgresql://[user]:[password]@[host]:[port]/[database]
```

### Examples

**Local development:**
```bash
postgresql://signal_harvester:your_password@localhost:5432/signal_harvester
```

**Docker:**
```bash
postgresql://signal_harvester:changeme@localhost:5432/signal_harvester
```

**Production (AWS RDS):**
```bash
postgresql://signal_harvester:secure_pass@signal-harvester.abc123.us-east-1.rds.amazonaws.com:5432/signal_harvester
```

### Environment Variable

Add to your `.env` file:

```bash
DATABASE_URL=postgresql://signal_harvester:your_password@localhost:5432/signal_harvester
```

Or set temporarily:

```bash
export DATABASE_URL="postgresql://signal_harvester:your_password@localhost:5432/signal_harvester"
```

## Running Migrations

### Apply Database Schema

```bash
# Navigate to project directory
cd /path/to/signal-harvester

# Ensure you're using the correct Python environment
source venv/bin/activate  # or your virtualenv

# Set connection string
export DATABASE_URL="postgresql://signal_harvester:your_password@localhost:5432/signal_harvester"

# Run Alembic migrations
alembic upgrade head
```

### Verify Schema

```bash
# Connect to database
psql $DATABASE_URL

# List tables
\dt

# Expected output:
# artifacts, artifact_scores, artifact_topics, artifact_entities, 
# artifact_relationships, topics, topic_similarity, entities, 
# experiments, experiment_runs, discovery_labels, tweets, 
# snapshots, cursors
```

## Data Migration from SQLite

### Prerequisites

Install required packages:

```bash
pip install psycopg2-binary sqlalchemy
```

### Dry Run (Recommended First)

```bash
python scripts/migrate_to_postgresql.py \
  --source var/app.db \
  --target "postgresql://signal_harvester:your_password@localhost:5432/signal_harvester" \
  --dry-run
```

### Full Migration

```bash
python scripts/migrate_to_postgresql.py \
  --source var/app.db \
  --target "postgresql://signal_harvester:your_password@localhost:5432/signal_harvester" \
  --validate
```

### Migration Options

- `--source`: Path to SQLite database (default: `var/app.db`)
- `--target`: PostgreSQL connection string (required)
- `--dry-run`: Preview migration without making changes
- `--validate`: Compare row counts after migration
- `--batch-size`: Rows per insert batch (default: 1000)

### Expected Output

```
================================================================================
PostgreSQL Data Migration
================================================================================
Source: var/app.db
Target: localhost:5432/signal_harvester
Mode: LIVE MIGRATION
================================================================================

Migrating cursors: 5 rows
  ✓ Migrated 5 rows

Migrating tweets: 1,234 rows
  Progress: 1,000/1,234 rows (81%)
  ✓ Migrated 1,234 rows

Migrating artifacts: 567 rows
  ✓ Migrated 567 rows

...

================================================================================
Validating Migration
================================================================================
cursors                        SQLite:        5 | PostgreSQL:        5 [✓ MATCH]
tweets                         SQLite:    1,234 | PostgreSQL:    1,234 [✓ MATCH]
artifacts                      SQLite:      567 | PostgreSQL:      567 [✓ MATCH]
...
================================================================================
✅ Validation passed: All row counts match!
```

## Testing Connection

### Python Test Script

```python
#!/usr/bin/env python3
import os
from sqlalchemy import create_engine, text

# Get connection string from environment
db_url = os.environ.get("DATABASE_URL", 
    "postgresql://signal_harvester:your_password@localhost:5432/signal_harvester")

# Create engine
engine = create_engine(db_url)

# Test connection
with engine.connect() as conn:
    result = conn.execute(text("SELECT version()"))
    version = result.fetchone()[0]
    print(f"✅ Connected to PostgreSQL: {version}")
    
    # Check tables
    result = conn.execute(text("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
    """))
    tables = [row[0] for row in result]
    print(f"✅ Found {len(tables)} tables: {', '.join(tables)}")
```

### CLI Test

```bash
# Set environment variable
export DATABASE_URL="postgresql://signal_harvester:your_password@localhost:5432/signal_harvester"

# Test harvest commands
harvest db analyze-performance  # Should work with PostgreSQL
harvest discoveries --limit 10   # Fetch top discoveries
harvest topics                   # Show trending topics
```

## Troubleshooting

### Connection Refused

**Error:**
```
psycopg2.OperationalError: connection to server at "localhost" (127.0.0.1), port 5432 failed: Connection refused
```

**Solutions:**

1. Check if PostgreSQL is running:
   ```bash
   # macOS
   brew services list | grep postgresql
   
   # Ubuntu
   sudo systemctl status postgresql
   
   # Docker
   docker ps | grep signal-harvester-db
   ```

2. Verify port 5432 is listening:
   ```bash
   netstat -an | grep 5432
   # or
   lsof -i :5432
   ```

3. Check PostgreSQL logs:
   ```bash
   # macOS
   tail -f /opt/homebrew/var/log/postgresql@16.log
   
   # Ubuntu
   sudo tail -f /var/log/postgresql/postgresql-16-main.log
   
   # Docker
   docker logs signal-harvester-db
   ```

### Authentication Failed

**Error:**
```
psycopg2.OperationalError: FATAL: password authentication failed for user "signal_harvester"
```

**Solutions:**

1. Verify user exists:
   ```sql
   psql postgres -c "\du"
   ```

2. Reset password:
   ```sql
   psql postgres
   ALTER USER signal_harvester WITH PASSWORD 'new_password';
   ```

3. Check `pg_hba.conf` has correct authentication method (md5 or scram-sha-256)

4. Reload PostgreSQL configuration:
   ```bash
   psql postgres -c "SELECT pg_reload_conf();"
   ```

### Database Does Not Exist

**Error:**
```
psycopg2.OperationalError: FATAL: database "signal_harvester" does not exist
```

**Solution:**

```bash
psql postgres -c "CREATE DATABASE signal_harvester OWNER signal_harvester;"
```

### Permission Denied

**Error:**
```
psycopg2.ProgrammingError: permission denied for schema public
```

**Solution:**

```sql
psql signal_harvester
GRANT ALL ON SCHEMA public TO signal_harvester;
GRANT ALL ON ALL TABLES IN SCHEMA public TO signal_harvester;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO signal_harvester;
```

### Migration Errors

**Foreign Key Violations:**

Ensure tables are migrated in dependency order (the script handles this automatically). If you see FK violations, the migration script may need adjustment.

**JSON Decode Errors:**

Some SQLite JSON fields may have invalid JSON. The migration script handles this by setting invalid JSON to NULL. Check logs for affected rows.

**Timestamp Format Issues:**

The migration script converts SQLite timestamps to PostgreSQL format. If you see errors, check the `transform_row()` function in `migrate_to_postgresql.py`.

## Production Considerations

### Managed PostgreSQL Services

**AWS RDS:**
```bash
# Create RDS instance
aws rds create-db-instance \
  --db-instance-identifier signal-harvester-prod \
  --db-instance-class db.t3.medium \
  --engine postgres \
  --engine-version 16.1 \
  --master-username signal_harvester \
  --master-user-password SECURE_PASSWORD \
  --allocated-storage 100 \
  --storage-type gp3 \
  --backup-retention-period 7 \
  --multi-az
```

**Google Cloud SQL:**
```bash
gcloud sql instances create signal-harvester-prod \
  --database-version=POSTGRES_16 \
  --tier=db-custom-2-7680 \
  --region=us-central1 \
  --backup-start-time=03:00
```

**Azure Database for PostgreSQL:**
```bash
az postgres flexible-server create \
  --resource-group signal-harvester-rg \
  --name signal-harvester-prod \
  --location eastus \
  --admin-user signal_harvester \
  --admin-password SECURE_PASSWORD \
  --sku-name Standard_D2s_v3 \
  --version 16
```

### Connection Pooling

For production, use connection pooling (PgBouncer or built-in SQLAlchemy pooling):

```yaml
# config/settings.yaml
database:
  url: postgresql://signal_harvester:pass@localhost:5432/signal_harvester
  pool_size: 20
  max_overflow: 10
  pool_timeout: 30
  pool_recycle: 3600
```

### Performance Tuning

**Key PostgreSQL settings for production:**

```conf
# postgresql.conf
max_connections = 100
shared_buffers = 2GB              # 25% of RAM
effective_cache_size = 6GB        # 75% of RAM
maintenance_work_mem = 512MB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1            # For SSD
effective_io_concurrency = 200    # For SSD
work_mem = 10MB
min_wal_size = 1GB
max_wal_size = 4GB
```

### Backup Strategy

**Daily automated backups:**

```bash
#!/bin/bash
# /usr/local/bin/backup-postgres.sh

BACKUP_DIR=/var/backups/signal-harvester
DATE=$(date +%Y%m%d_%H%M%S)
DB_URL="postgresql://signal_harvester:pass@localhost:5432/signal_harvester"

pg_dump $DB_URL | gzip > $BACKUP_DIR/signal_harvester_$DATE.sql.gz

# Keep last 7 days
find $BACKUP_DIR -name "signal_harvester_*.sql.gz" -mtime +7 -delete
```

**Cron job:**

```cron
0 2 * * * /usr/local/bin/backup-postgres.sh
```

### Monitoring

**Key metrics to track:**

- Connection count (`SELECT count(*) FROM pg_stat_activity`)
- Query performance (`pg_stat_statements`)
- Cache hit rate (`pg_stat_database`)
- Table bloat (`pg_stat_user_tables`)
- Index usage (`pg_stat_user_indexes`)

See `docs/MONITORING.md` for full Prometheus/Grafana setup.

### Security Checklist

- ✅ Use strong passwords (20+ characters)
- ✅ Enable SSL/TLS for connections
- ✅ Restrict network access (security groups/firewall)
- ✅ Use separate user for application (not postgres superuser)
- ✅ Enable audit logging
- ✅ Regular security updates
- ✅ Encrypt backups
- ✅ Use secrets manager (AWS Secrets Manager, etc.)

## Next Steps

1. ✅ Complete this setup guide
2. Run migration with `--validate` flag
3. Update `config/settings.yaml` with PostgreSQL URL
4. Run end-to-end tests with `pytest tests/`
5. Monitor performance with `harvest db analyze-performance`
6. Review `docs/DEPLOYMENT.md` for production deployment

## References

- [PostgreSQL Documentation](https://www.postgresql.org/docs/16/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [SQLAlchemy PostgreSQL Dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html)
- [Signal Harvester Phase Three Plan](PHASE_THREE_SCALING.md)
