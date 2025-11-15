# PostgreSQL Migration Guide

**Audience**: Operators migrating Signal Harvester from the legacy SQLite database to PostgreSQL.  
**Last Updated**: November 13, 2025

This runbook captures the exact steps used during Phase Three to cut the production dataset over to PostgreSQL 15. Follow the sections in order; every step is mandatory unless explicitly marked optional.

---

## 1. Scope & Success Criteria

- All tables listed in `scripts/migrate_sqlite_to_postgresql.py::MIGRATION_ORDER` exist in PostgreSQL with matching row counts.  
- Application services read/write exclusively from PostgreSQL (`DATABASE_URL` references the new DSN everywhere).  
- Validation via `harvest verify-postgres --database-url "$DATABASE_URL"` (or the legacy `scripts/validate_postgresql.py`) reports success and Alembic head version matches the repository.  
- SQLite database remains untouched so it can be used for rollback until the cutover is fully verified.

---

## 2. Prerequisites

| Requirement | Details |
|-------------|---------|
| Database Access | Ability to create/delete databases and run `psql` against the target PostgreSQL instance. |
| Python Env | `python3.12` with project dependencies installed (`pip install -e .[dev]`). |
| Scripts | `scripts/migrate_sqlite_to_postgresql.py`, `harvest verify-postgres` (or `scripts/validate_postgresql.py`), and `scripts/migrate_to_postgresql.py` (advanced resume/dry-run) available locally. |
| Source Data | Canonical SQLite database at `var/app.db` (or override via `--sqlite-path`). |
| Connectivity | Application services temporarily paused to prevent concurrent writes while migrating. |
| Backups | Verified filesystem backup of the SQLite DB plus any existing PostgreSQL data (if re-running). |

---

## 3. Pre-Migration Checklist

1. **Freeze Writes**: Stop the FastAPI API, scheduler, and any cron jobs (`harvest daemon`, `harvest pipeline`) so no new rows land in SQLite during the cutover window.  
2. **Snapshot SQLite**:

   ```bash
   mkdir -p backups
   cp var/app.db backups/app.db.$(date +%F-%H%M%S)
   ```

3. **Document Current Alembic Head**:

   ```bash
   sqlite3 var/app.db "SELECT version_num FROM alembic_version;"
   ```

4. **Prepare .env/.secrets**: Ensure the target `DATABASE_URL` is present in `.env`, `.env.staging`, and any CI secrets but do **not** flip the application yet.  
5. **Provision PostgreSQL**: Create the empty database (example uses `signal_harvester`):

   ```bash
   createdb -h <host> -U <user> signal_harvester
   ```

6. **Apply Schema**: Run Alembic against the new DSN so every table/index exists prior to the data copy:

   ```bash
   export DATABASE_URL=postgresql://user:pass@host:5432/signal_harvester
   alembic upgrade head
   ```

---

## 4. Running the Migration Script

1. **Set Environment Variables**:

   ```bash
   export DATABASE_URL=postgresql://user:pass@host:5432/signal_harvester
   ```

2. **Execute Migration** using the canonical script (auto-validates timestamps + JSON columns):

   ```bash
   python scripts/migrate_sqlite_to_postgresql.py \
     --sqlite-path var/app.db \
     --batch-size 250
   ```

   - `--database-url` can override `DATABASE_URL`.  
   - Lower `--batch-size` if you encounter transaction timeouts.  
   - Add `--skip-validation` only if you will run manual validation afterward.
3. **(Optional) Advanced Flows**: The older `scripts/migrate_to_postgresql.py` supports `--dry-run`, `--resume`, and per-table stats. Use it if you need to restart after correcting bad rows; otherwise prefer the streamlined script above.

Expected output: each table prints `✓ (N rows)` and the script ends with `✅ Validation passed`.

---

## 5. Post-Migration Validation

1. **Row Count + Schema Audit**:

   ```bash
   harvest verify-postgres --database-url "$DATABASE_URL"
   # Fallback: python scripts/validate_postgresql.py
   ```

   Confirms connectivity, lists tables, prints type checks (JSONB/TIMESTAMP), and dumps Alembic version.
2. **Manual Spot Checks**:

   ```bash
   psql "$DATABASE_URL" -c "SELECT COUNT(*) FROM artifacts;"
   psql "$DATABASE_URL" -c "SELECT external_id, source FROM artifacts ORDER BY created_at DESC LIMIT 5;"
   ```

3. **Application Smoke Test**:

   ```bash
   DATABASE_URL="$DATABASE_URL" harvest api --host 0.0.0.0 --port 9000
   curl http://localhost:9000/health/ready
   ```

   (Run locally in a tmux pane to confirm the API boots against PostgreSQL.)

If any row counts mismatch, drop the affected table in PostgreSQL (`TRUNCATE table_name RESTART IDENTITY`) and re-run the migration script with the same settings.

---

## 6. Cutover Steps

1. **Update Configuration**: Point all environment files (`.env`, `.env.staging`, deployment secrets, Kubernetes ConfigMaps) to the PostgreSQL DSN.  
2. **Redeploy Services**: Restart the API, scheduler, and background workers so they pick up the new env vars.  
3. **Monitor Logs**: Tail `signal-harvester` container logs (or `uvicorn` stdout) for connection errors.  
4. **Verify Rate Limiter + Cache**: Ensure Redis still responds; PostgreSQL migration does not affect Redis but verifying prevents dual-issue debugging later.  
5. **Observe Metrics**: Confirm Prometheus `db_query_duration_seconds` and Grafana dashboards show traffic against PostgreSQL.

Once satisfied, archive the SQLite backup in cold storage but retain it until the next release in case forensic comparisons are needed.

---

## 7. Rollback & Recovery

| Scenario | Action |
|----------|--------|
| Migration script failed mid-way | Drop partially-filled tables: `psql -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"`, re-run `alembic upgrade head`, then re-run the migration. |
| Application errors after cutover | Stop services, revert `DATABASE_URL` to SQLite (legacy), restart services, investigate PostgreSQL logs before attempting the migration again. |
| Corrupted target data detected later | Restore from the saved SQLite backup or from a PostgreSQL physical backup if one has been taken post-cutover. |

Always keep the SQLite snapshot until the PostgreSQL instance has at least one verified nightly backup.

---

## 8. Troubleshooting

| Symptom | Likely Cause | Resolution |
|---------|--------------|-----------|
| `❌ PostgreSQL DATABASE_URL not set` | Missing env var or typo in `--database-url`. | Export `DATABASE_URL` or pass `--database-url postgresql://...` on the CLI. |
| Script logs `Table does not exist in PostgreSQL, skipping` | Alembic not run before migration. | Re-run `alembic upgrade head` against the PostgreSQL DSN, then rerun the migration. |
| Duplicate key errors on insert | Pre-existing data in PostgreSQL. | Drop conflicting rows/table or rerun with the advanced migrator (`scripts/migrate_to_postgresql.py --resume`) to UPSERT and skip duplicates. |
| Validation mismatches row counts | Migration interrupted or batch insert failed. | Identify tables flagged in the output, truncate them, rerun the migration script for those tables. |
| API fails to start after cutover (`psycopg2.OperationalError`) | Network/SSL/security group issue. | Verify the host/port from the machine running the API; ensure the PostgreSQL firewall allows the app nodes. |

---

## 9. Quick Command Reference

```bash
# 1. Backup SQLite
cp var/app.db backups/app.db.$(date +%F-%H%M%S)

# 2. Prepare PostgreSQL schema
export DATABASE_URL=postgresql://user:pass@host:5432/signal_harvester
alembic upgrade head

# 3. Run migration
python scripts/migrate_sqlite_to_postgresql.py --sqlite-path var/app.db --batch-size 250

# 4. Validate
harvest verify-postgres --database-url "$DATABASE_URL"

# 5. Smoke test API against PostgreSQL
DATABASE_URL=$DATABASE_URL harvest api --host 0.0.0.0 --port 9000
```

Document each run (timestamp, operator, command flags, row counts) in the operations log so future audits can trace the migration history.
