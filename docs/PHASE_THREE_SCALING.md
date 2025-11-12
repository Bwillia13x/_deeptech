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

## Monitoring & Next Steps

- Keep `docs/QUERY_PROFILING_REPORT.md` current; re-run `scripts/profile_queries.py` after schema changes and attach the resulting markdown to release notes.
- `make verify-all` now runs `harvest db analyze-performance`, so CI-level regressions are caught automatically.
- Maintain cache hit rate dashboards (via Prometheus or Grafana) and instrument SSE progress metrics as part of the `Phase Three` runbook.
- Once Postgres path is validated, update `ARCHITECTURE_AND_READINESS.md section 6.3` to mark the phase complete.
