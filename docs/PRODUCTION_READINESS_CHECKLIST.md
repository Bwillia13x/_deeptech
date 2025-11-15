# Production Readiness Checklist

**Date**: November 13, 2025  
**Owner**: Platform & DevOps Team  
**Purpose**: Provide a single-source checklist to confirm Signal Harvester is ready for Phase Three staging and production deployment. This document supersedes ad-hoc notes in prior status reports.

---

## 1. Configuration & Secrets

- [ ] `.env`, `.env.staging`, and Kubernetes/Compose secrets updated with the PostgreSQL `DATABASE_URL` and Redis credentials.  
- [ ] API keys for X, GitHub, Facebook, LinkedIn, OpenAI, Anthropic, xAI stored in the secrets manager (no plaintext on disk).  
- [ ] `TLS_EMAIL`, `TLS_CERT_MODE`, `ACME_CA`, and basic auth hashes populated in `.env.staging` (see `docs/STAGING_DEPLOYMENT_RUNBOOK.md`).

## 2. Database & Migrations

- [ ] Alembic `upgrade head` applied against PostgreSQL staging/production.  
- [ ] `scripts/migrate_sqlite_to_postgresql.py` executed (or confirmed not needed) with validation successful.  
- [ ] `harvest verify-postgres --database-url "$DATABASE_URL"` (or the legacy `scripts/validate_postgresql.py`) reports correct schema/types and Alembic version.  
- [ ] SQLite backup archived with timestamp (rollback safety).

## 3. Application Health

- [ ] API boots with `DATABASE_URL` pointing to PostgreSQL, Redis rate limiting enabled.  
- [ ] `/health/live`, `/health/ready`, `/health/startup` all 200 OK; cold `/health/live` spike documented (<1s).  
- [ ] `/signals`, `/snapshots`, `/stats` respond within <500 ms (see `docs/PERFORMANCE_BENCHMARKS.md`).  
- [ ] Known HTTP 500s on discovery endpoints tracked with follow-up issue IDs.

## 4. Observability

- [ ] Prometheus scraping API metrics (`/metrics/prometheus` endpoint reachable from Prometheus container).  
- [ ] Grafana datasource connected and dashboards imported (`monitoring/grafana`).  
- [ ] Alertmanager routes configured with Slack/email receivers.  
- [ ] Logs forwarded (or collected locally) with retention ≥14 days.

## 5. Security & Compliance

- [ ] Latest `docs/SECURITY_AUDIT.md` tasks closed or assigned.  
- [ ] Secrets rotated within last 90 days (X API, LLM keys, Redis password).  
- [ ] TLS certificates issued/renewed (Let’s Encrypt or internal) and HSTS enabled via Caddy.  
- [ ] Basic auth hashes for Grafana/Prometheus/Alertmanager regenerated (bcrypt) and stored securely.  
- [ ] GDPR export/delete workflows tested (per `docs/OPERATIONS.md`).

## 6. Backups & Recovery

- [ ] Automated PostgreSQL backups scheduled (pg_dump or managed service snapshots).  
- [ ] Redis persistence enabled or data considered ephemeral.  
- [ ] Restore drill performed in staging within last 30 days (documented in `docs/BACKUP_RECOVERY.md`).

## 7. Deployment & Runbook Readiness

- [ ] `docs/STAGING_DEPLOYMENT_RUNBOOK.md` reviewed and updated after each dry run.  
- [ ] Staging compose stack rehearsed locally with `TLS_CERT_MODE=internal`; curl verification screenshots/commands captured.  
- [ ] Production deployment plan (Kubernetes or Docker Compose) updated in `docs/PRODUCTION_DEPLOYMENT.md`.  
- [ ] Operator hand-off completed (on-call rotation defined, contact list in `AGENTS.md`).

## 8. Testing & Benchmarks

- [ ] `make lint`, `make test`, frontend build, and contract tests passing.  
- [ ] `scripts/performance_test.py` run with latest code; results logged in `docs/PERFORMANCE_BENCHMARKS.md`.  
- [ ] Load testing (Locust or equivalent) executed or documented as not required for initial staging.  
- [ ] Manual discovery pipeline spot-check (Phase Two) performed or blocked with a written exception.

## 9. Sign-Off

| Role | Name | Date | Notes |
|------|------|------|-------|
| Platform Lead | | | |
| Backend Lead | | | |
| Security Lead | | | |
| Product Owner | | | |

Sign-off requires all boxes checked or documented risk waivers approved by the Product Owner.
