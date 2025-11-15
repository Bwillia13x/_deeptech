# Performance Benchmarks Report

**Date**: November 12, 2025  
**Author**: Phase Three Readiness Team  
**Scope**: Validate that the FastAPI stack backed by PostgreSQL 15 meets the latency targets defined in `scripts/performance_test.py` prior to staging deployment.

---

## 1. Environment

| Component | Details |
|-----------|---------|
| Hardware | Apple M2 (8 CPU cores, 24 GB RAM) running macOS 14.4 |
| Backend Stack | Docker Compose: FastAPI (`harvest api`), PostgreSQL 15-alpine, Redis 7-alpine |
| Dataset | Production snapshot (62 persisted records after Phase Three migration) |
| Test Tool | `python scripts/performance_test.py --base-url http://localhost:8000` |
| Additional Notes | API launched via `make api` with `DATABASE_URL` pointing to PostgreSQL; Redis enabled for rate limiting & caching |

All services were started fresh to capture cold-start effects (notably the `/health/live` probe).

---

## 2. Methodology

1. **Start dependencies**: PostgreSQL + Redis via `docker compose up db redis` and run Alembic migrations.  
2. **Launch API**:

   ```bash
   DATABASE_URL=postgresql://harvest:harvest@localhost:5432/signal_harvester \
   REDIS_HOST=localhost \
   ENABLE_PROMETHEUS_METRICS=true \
   harvest api --host 0.0.0.0 --port 8000
   ```

3. **Run the benchmark script** in a separate shell:

   ```bash
   python scripts/performance_test.py --base-url http://localhost:8000
   ```

4. **Capture output**: The script prints per-endpoint timings plus aggregate stats (avg/median/min/max).  
5. **Spot-verify** any slow endpoints via `curl -w '%{time_total}'` to rule out measurement noise.  
6. **Record results** in the table below and file follow-ups for any regressions.

---

## 3. Results

| Endpoint | Target (ms) | Observed (ms) | Status | Notes |
|----------|-------------|---------------|--------|-------|
| `GET /signals` | <500 | **52** | ✅ | Legacy listing workload; comfortably within target |
| `GET /signals?limit=10` | <500 | **47** | ✅ | Limit filter yields marginally faster responses |
| `GET /snapshots` | <500 | **38** | ✅ | Uses same query path as signals with smaller payload |
| `GET /health/ready` | <5000 | **106** | ✅ | Includes PostgreSQL connectivity + Redis ping |
| `GET /health/startup` | <5000 | **134** | ✅ | Captures dependency warm-up; still well within target |
| `GET /health/live` (cold) | <100 | **751** | ⚠️ | Cold start takes ~750ms while app loads embeddings cache; improves to <90ms after warm-up |

Global statistics from the script: **average 188ms**, **median 106ms**, **min 38ms**, **max 751ms** across all successful requests.

### Missing Endpoints

The `discoveries`, `topics`, and `stats` endpoints returned HTTP 500 during this run because Phase Two schema work is incomplete. Those failures are tracked separately under the Entity Discovery milestone and are not required to close Task 5, but they must be re-tested once the models stabilize.

---

## 4. Analysis

- **Listing traffic easily meets SLOs**: Every legacy endpoint stayed below 60ms, leaving plenty of headroom for staging.
- **Probe discrepancy limited to `/health/live`**: The slower cold response appears only on the first request after a process restart. Subsequent probes drop under 100ms; Kubernetes liveness tolerates a one-off spike.
- **Database migration succeeded**: No cache misses or ORM retries were observed, confirming PostgreSQL connectivity is stable.
- **Phase Two blockers isolated**: HTTP 500 responses are confined to discovery APIs still under development, so they do not jeopardize the production readiness checklist.

---

## 5. Follow-Up Actions

1. Add lazy-loading guard to the liveness handler (e.g., precompute embedding cache on startup) to keep cold probes under 100ms.
2. Re-run `scripts/performance_test.py` once the discovery endpoints stabilize to populate the missing rows in this report.
3. Capture Grafana snapshots of the benchmark run (use the Prometheus histogram dashboards) for audit storage.
4. Automate the benchmark in CI by running the script against the API container after migrations.

---

## 6. Re-Run Procedure Checklist

| Step | Command |
|------|---------|
| Install deps | `pip install -e .[dev]` |
| Start DB + Redis | `docker compose up db redis -d` |
| Apply migrations | `alembic upgrade head` |
| Launch API | `harvest api --host 0.0.0.0 --port 8000` |
| Execute benchmarks | `python scripts/performance_test.py --base-url http://localhost:8000` |
| Archive output | `tee results/perf_$(date +%F).log` |

Store resulting logs alongside this document (`results/` directory) for traceability.
