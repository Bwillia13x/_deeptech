# Phase Three: Performance Optimization & Scaling Playbook

This document captures the outstanding Phase Three work and the path to release-grade stability for Signal Harvester.
It ties together the index work, caching, profiling, and the new PostgreSQL migration planning that guard the <500 ms p95 target.

## Objectives

1. Keep all discovery, topic, and citation queries below 100 ms with repeatable verification.
2. Ensure caching (Redis + in-memory fallback) covers high-traffic endpoints (discoveries, topics, entity profiles).
3. Prepare for >1 million artifacts by documenting a PostgreSQL migration plan, connection pooling, and index audit.

## Current State

- **Indexes & profiling:** Migration 9 put the nine composite indexes in production and the `docs/DATABASE_INDEX_OPTIMIZATION.md` report documents their usage; the profiling report (`docs/QUERY_PROFILING_REPORT.md`) shows all critical queries hitting the expected indexes and staying under 100 ms.
- **Caching:** `src/signal_harvester/cache.py` decorates `/discoveries`, `/topics/trending`, and `/entities/{id}`. Cache stats are exposed through `GET /cache/stats` and invalidatable via `POST /cache/invalidate`; hit rates are currently targeted >80%.
- **Connection pooling:** `src/signal_harvester/db_pool.py` is wired through `Settings.app.connection_pool` and enabled in `api.py` for production deployments, keeping SQLite concurrency under control until Postgres is live.
- **Profiling tooling:** `scripts/profile_queries.py` (which uses the shared query definitions in `src/signal_harvester/performance.py`) and the new CLI command `harvest db analyze-performance` both exercise and log latency + EXPLAIN plans so regressions are easy to spot.

## Tooling & Verification

- **`harvest db analyze-performance`** (CLI command in `src/signal_harvester/cli/db_commands.py`): runs the curated query set, prints latency tables, and optionally shows `EXPLAIN QUERY PLAN` output for each query.
- **`scripts/profile_queries.py`**: generates the markdown `docs/QUERY_PROFILING_REPORT.md` using the same query definitions, ideal for CI artifacts or release notes.
- **Cache observability:** `GET /cache/stats` surfaces hit/miss counts; the Phase Three goal is to keep the discovery cache hit rate ≥80% and to invalidate with `POST /cache/invalidate` whenever relevant ingestion completes.
- **Metrics:** monitor Prometheus metrics emitted by `src/signal_harvester/prometheus_metrics.py` (included via middleware) plus `GET /metrics/prometheus` to compare measured p95 latencies against the 500 ms SLA.

## PostgreSQL Migration Plan

The SQLite database works for local testing, but production must move to PostgreSQL for durability, indexing, and concurrency. The steps below build a safe migration path.

| Step | Description | Status |
| --- | --- | --- |
| 1. Schema audit | Map the current SQLite schema (tables, indexes, constraints) documented across migrations and `docs/DATABASE_INDEX_OPTIMIZATION.md` and capture any SQLite-specific PRAGMAs that need translating. | ✅ Complete |
| 2. Alembic Postgres migration | Create a PostgreSQL-only Alembic revision that re-creates tables/indexes for Postgres (including `idx_scores_discovery_artifact`, `idx_artifact_topics_topic_artifact`, and the confidence indexes) and run it against a staging PG instance. | 🔄 In progress |
| 3. Data migration & transformation | Use `sqlite3` exports or `sqlalchemy` ETL jobs to copy artifacts, scores, relationships, and topic tables into PostgreSQL; validate counts and referential integrity via `harvest verify`. | ⚪ Planned |
| 4. Runtime wiring | Point `config/settings.yaml` at `postgresql://` URLs, ensure `db_pool` (or SQLAlchemy engine) uses pooling parameters, and confirm Redis caching + SSE still work. | ⚪ Planned |
| 5. Validation | Run `harvest db analyze-performance`, the query profiling script, and API p95 measurements to verify <500 ms latency with the new database; capture logs in `docs/QUERY_PROFILING_REPORT.md`. | ⚪ Planned |
| 6. Rollback & monitoring | Document rollback steps (point back to SQLite, run migrations `downgrade`, flush cache) and update `docs/DEPLOYMENT.md` with Health Check steps. | ⚪ Planned |

### Discovery Route Validation

- `src/signal_harvester/db.py` now normalizes legacy database paths, reuses the shared `DatabaseConnection`, and emits dialect-aware aggregations (`string_agg` when `DATABASE_URL` points at Postgres, `GROUP_CONCAT` otherwise) so `/discoveries`, cursor pagination, and topic analytics no longer hit HTTP 500 errors after switching to PostgreSQL.
- Regression coverage is provided by `tests/test_db.py` (Postgres-aware connection helper) and `tests/test_config.py` (config loading with Postgres URLs), keeping the contract layer green regardless of the backend.
- After the remote staging credentials are available, execute:

  ```bash
  DATABASE_URL=postgresql://harness:secret@staging-db:5432/signal_harvester \
    scripts/migrate_sqlite_to_postgresql.py --sqlite-path var/app.db
  harvest verify-postgres --database-url postgresql://harness:secret@staging-db:5432/signal_harvester
  python scripts/performance_test.py --base-url http://localhost:8000
  ```

  Capture the row counts and latency table output and append them to `docs/QUERY_PROFILING_REPORT.md` along with screenshots of the Grafana/Postgres dashboards before releasing the discovery UI.

### Command Shortcuts

- `make migrate-postgres-dry-run` — exercise `scripts/migrate_to_postgresql.py` without writing to PostgreSQL (great for CI smoke). Override `PG_URL` to point at staging: `PG_URL=postgresql://harvest:secret@staging-db:5432/signal_harvester make migrate-postgres-dry-run`.
- `make migrate-postgres` — run the live migration from the default SQLite file (`$(SQLITE_DB)` → `var/app.db`) into `$(PG_URL)`. Emit per-table stats plus a markdown-friendly summary.
- `make validate-postgres` — execute `harvest verify-postgres --database-url $(PG_URL)` to confirm schema, indexes, and row counts after the migration lands (the target falls back to the legacy script if Typer isn't available).

These targets encode the environment-variable plumbing (SQLite path, Postgres DSN) so Phase Three verification can run with a single command and be wired into `make verify-all` once the Postgres cutover date is locked.

## Monitoring & Next Steps

- Keep `docs/QUERY_PROFILING_REPORT.md` current; re-run `scripts/profile_queries.py` after schema changes and attach the resulting markdown to release notes.
- `docker-compose.staging.yml` + `deploy/staging/Caddyfile` spin up the API, scheduler, PostgreSQL, Redis, and the monitoring trio (Prometheus/Grafana/Alertmanager) behind HTTPS so staging drills use the same topology (see `docs/PRODUCTION_DEPLOYMENT.md`).
- `make verify-all` now runs `harvest db analyze-performance`, so CI-level regressions are caught automatically.
- Maintain cache hit rate dashboards (via Prometheus or Grafana) and instrument SSE progress metrics as part of the `Phase Three` runbook.
- Once Postgres path is validated, update `ARCHITECTURE_AND_READINESS.md section 6.3` to mark the phase complete.
