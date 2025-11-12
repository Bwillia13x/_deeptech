# Phase Three Execution Plan - Production Hardening & Scale

**Document Version**: 1.0  
**Created**: November 12, 2025  
**Status**: In Progress  
**Target Completion**: 6 weeks from start

---

## Executive Summary

Phase Three focuses on production readiness, performance optimization, and scaling Signal Harvester to handle enterprise workloads. This phase builds on the complete Phase Two implementation (entity resolution, topic evolution, embeddings, corroboration, social media ingestion, and backtesting).

**Key Objectives**:

- PostgreSQL migration for production-grade durability and scale
- Performance optimization to meet <500ms p95 latency SLA
- Kubernetes deployment with autoscaling and high availability
- Comprehensive monitoring and alerting infrastructure
- Load testing validation for 100+ concurrent users
- Production security hardening and compliance

---

## Current Status

### ✅ Completed (Nov 12, 2025)

1. **Database Performance Baseline**
   - Ran `harvest db analyze-performance` showing all queries well under SLA
   - Current p95 latency: <10ms for most queries (SQLite baseline)
   - 9 composite indexes optimized and validated
   - Query profiling report generated

2. **PostgreSQL Migration Created**
   - Alembic migration `20251112_0010_postgresql_schema.py` complete
   - Converts all SQLite tables to PostgreSQL with proper types
   - Includes all 14 tables with indexes and foreign keys
   - Uses JSONB for JSON fields, DateTime for timestamps
   - Dialect-aware (only runs on PostgreSQL)

3. **Load Testing Infrastructure**
   - Created Locust load test script (`scripts/load_test.py`)
   - Created k6 load test script (`scripts/load_test_k6.js`)
   - Both simulate realistic user behavior patterns
   - Validates <500ms p95, <1000ms p99 latency targets
   - Tests 100+ concurrent users with ramp-up scenarios

4. **Monitoring Configuration**
   - Prometheus configs in `monitoring/prometheus/`
   - Grafana dashboards in `monitoring/grafana/`
   - Kubernetes manifests in `monitoring/k8s/`
   - Alert rules defined for SLA violations

### 🔄 In Progress

1. **Monitoring Stack Deployment**
   - Review and validate Prometheus configuration
   - Deploy Grafana dashboards
   - Configure alert routing

### ⚪ Not Started

1. **PostgreSQL Data Migration**
2. **Kubernetes Production Deployment**
3. **Security Hardening**
4. **Production Load Testing**
5. **Documentation Updates**

---

## Detailed Timeline (6 Weeks)

### Week 1: PostgreSQL Migration & Testing

#### Days 1-2: PostgreSQL Setup

- [ ] Provision PostgreSQL instance (RDS, Cloud SQL, or self-hosted)
- [ ] Configure connection pooling (PgBouncer or SQLAlchemy pool)
- [ ] Update `config/settings.yaml` with PostgreSQL connection string
- [ ] Test database connectivity and authentication

#### Days 3-4: Schema Migration

- [ ] Run Alembic migration on PostgreSQL: `alembic upgrade head`
- [ ] Validate all 14 tables created with correct schema
- [ ] Verify all 30+ indexes created successfully
- [ ] Run database performance analysis on PostgreSQL

#### Day 5: Data Migration

- [ ] Export SQLite data using `sqlite3 .dump` or custom script
- [ ] Transform data formats (timestamps, JSON, etc.)
- [ ] Import data into PostgreSQL using `psql` or `COPY`
- [ ] Validate data integrity with row counts and checksums
- [ ] Run `harvest verify` to validate relationships

#### Days 6-7: Performance Validation

- [ ] Run `harvest db analyze-performance` on PostgreSQL
- [ ] Compare latencies to SQLite baseline
- [ ] Optimize PostgreSQL configuration (shared_buffers, work_mem, etc.)
- [ ] Run discovery pipeline end-to-end on PostgreSQL
- [ ] Document rollback procedure

**Success Criteria**:

- PostgreSQL p95 latency < 100ms for all queries
- All data migrated with 100% integrity
- Zero errors in discovery pipeline
- Rollback procedure tested and documented

---

### Week 2: Load Testing & Performance Tuning

#### Days 1-2: Load Test Setup

- [ ] Install k6: `brew install k6` (macOS) or equivalent
- [ ] Configure API for load testing (seed data, API keys)
- [ ] Run baseline load test: `k6 run scripts/load_test_k6.js`
- [ ] Document baseline performance metrics

#### Days 3-4: Performance Optimization

- [ ] Identify slow queries from load test results
- [ ] Add query-specific indexes if needed
- [ ] Optimize cache configuration (Redis TTLs, eviction policies)
- [ ] Tune PostgreSQL connection pool settings
- [ ] Enable query plan caching

#### Day 5: Stress Testing

- [ ] Run stress test: 200 VUs, 10-minute duration
- [ ] Monitor resource utilization (CPU, memory, I/O)
- [ ] Identify bottlenecks (database, API, cache, network)
- [ ] Document maximum sustainable load

#### Days 6-7: Optimization Iteration

- [ ] Implement optimizations based on stress test findings
- [ ] Re-run load tests to validate improvements
- [ ] Achieve <500ms p95, <1000ms p99 targets consistently
- [ ] Document performance tuning guide

**Success Criteria**:

- p95 latency < 500ms for all endpoints under 100 VUs
- p99 latency < 1000ms for critical endpoints
- Cache hit rate > 80%
- Zero errors at 100 concurrent users
- System remains stable at 200 VUs

---

### Week 3: Monitoring & Observability

#### Days 1-2: Prometheus Deployment

- [ ] Deploy Prometheus to Kubernetes: `kubectl apply -f monitoring/k8s/prometheus.yaml`
- [ ] Verify scrape targets discovered (API pods, Redis, nodes)
- [ ] Test alert rules firing correctly
- [ ] Configure persistent storage for metrics

#### Days 3-4: Grafana Dashboards

- [ ] Deploy Grafana: `kubectl apply -f monitoring/k8s/grafana.yaml`
- [ ] Import dashboards from `monitoring/grafana/`
- [ ] Configure data sources (Prometheus, PostgreSQL)
- [ ] Create custom dashboards for Phase Two features
- [ ] Set up user access controls

#### Day 5: Alerting Configuration

- [ ] Configure Alertmanager for Prometheus
- [ ] Set up notification channels (Slack, PagerDuty, email)
- [ ] Define alert routing rules by severity
- [ ] Test alert firing and routing end-to-end

#### Days 6-7: Logging & Tracing

- [ ] Configure structured logging to stdout
- [ ] Set up log aggregation (Loki, CloudWatch, or Elasticsearch)
- [ ] Enable Sentry for error tracking
- [ ] Add distributed tracing if needed (Jaeger, Zipkin)
- [ ] Create runbook for common alerts

**Success Criteria**:

- All API metrics scraped and visible in Prometheus
- 4+ Grafana dashboards operational
- Critical alerts firing and routing to Slack
- Logs aggregated and searchable
- Runbook covers 10+ common scenarios

---

### Week 4: Kubernetes Production Deployment

#### Days 1-2: Kubernetes Cluster Setup

- [ ] Provision production Kubernetes cluster (GKE, EKS, AKS, or self-hosted)
- [ ] Configure kubectl context for production
- [ ] Set up RBAC and service accounts
- [ ] Configure network policies and ingress

#### Days 3-4: Application Deployment

- [ ] Create namespace: `kubectl create namespace signal-harvester-production`
- [ ] Apply base manifests: `kubectl apply -k k8s/overlays/production`
- [ ] Deploy Redis StatefulSet with persistence
- [ ] Deploy Signal Harvester API Deployment
- [ ] Configure HorizontalPodAutoscaler (HPA)

#### Day 5: Ingress & TLS

- [ ] Configure Ingress resource with production domain
- [ ] Set up TLS certificates (cert-manager or manual)
- [ ] Configure DNS records
- [ ] Enable HTTPS redirect
- [ ] Test external access

#### Days 6-7: Validation & Rollback

- [ ] Run smoke tests against production API
- [ ] Execute load test against production: `k6 run --vus 50 scripts/load_test_k6.js`
- [ ] Monitor metrics and logs during load test
- [ ] Document rollback procedure
- [ ] Create backup/restore runbook

**Success Criteria**:

- Application accessible at production domain over HTTPS
- HPA scales pods from 2 to 10 based on CPU/memory
- Load test passes with <500ms p95 latency
- Zero downtime during deployment
- Rollback procedure tested and documented

---

### Week 5: Security Hardening & Compliance

#### Days 1-2: Security Audit

- [ ] Run security scan on Docker images (Trivy, Snyk, or Clair)
- [ ] Audit dependencies for vulnerabilities: `pip audit`
- [ ] Review secrets management (use Kubernetes Secrets or external vault)
- [ ] Enable network policies to restrict pod communication
- [ ] Configure security contexts (non-root user, read-only filesystem)

#### Days 3-4: API Security

- [ ] Implement rate limiting per IP and API key
- [ ] Add request validation and input sanitization
- [ ] Enable CORS with strict origin whitelist
- [ ] Configure API key rotation schedule (90 days)
- [ ] Add request signing for sensitive endpoints

#### Day 5: Compliance

- [ ] Document data retention policies (90-day default)
- [ ] Implement GDPR data export endpoint
- [ ] Implement GDPR data deletion endpoint
- [ ] Create compliance audit checklist
- [ ] Document X API compliance requirements

#### Days 6-7: Penetration Testing

- [ ] Run automated security tests (OWASP ZAP, Burp Suite)
- [ ] Test authentication bypass attempts
- [ ] Test SQL injection, XSS, CSRF protections
- [ ] Review and fix any security findings
- [ ] Document security posture and controls

**Success Criteria**:

- Zero critical/high vulnerabilities in images
- All secrets managed securely (no hardcoded keys)
- Rate limiting prevents abuse
- GDPR endpoints functional
- Penetration test finds no critical issues

---

### Week 6: Production Launch & Validation

#### Days 1-2: Pre-Launch Checklist

- [ ] Run full test suite: `pytest tests/ -v`
- [ ] Validate all Phase Two features working
- [ ] Run contract tests: `pytest tests/test_contract_api_frontend.py`
- [ ] Execute load test one final time
- [ ] Review monitoring dashboards and alerts

#### Days 3-4: Staged Rollout

- [ ] Deploy to staging environment first
- [ ] Run end-to-end tests in staging
- [ ] Perform canary deployment to production (10% traffic)
- [ ] Monitor error rates and latencies
- [ ] Gradually increase traffic to 100%

#### Day 5: Production Validation

- [ ] Run discovery pipeline in production
- [ ] Validate data quality and artifact coverage
- [ ] Test all API endpoints with real data
- [ ] Verify monitoring alerts working
- [ ] Test backup and restore procedures

#### Days 6-7: Documentation & Handoff

- [ ] Update OPERATIONS.md with production procedures
- [ ] Update DEPLOYMENT.md with K8s deployment guide
- [ ] Create incident response playbook
- [ ] Train operations team on monitoring and troubleshooting
- [ ] Document Phase Three completion in ARCHITECTURE_AND_READINESS.md

**Success Criteria**:

- Application running in production with real traffic
- All Phase One and Phase Two features operational
- Monitoring shows healthy metrics (p95 < 500ms)
- Operations team trained and confident
- Documentation complete and accurate

---

## Risk Mitigation

### High-Risk Areas

1. **PostgreSQL Migration Data Loss**
   - **Mitigation**: Full SQLite backup before migration
   - **Rollback**: Keep SQLite database and revert config
   - **Validation**: Automated row count and checksum verification

2. **Performance Degradation on PostgreSQL**
   - **Mitigation**: Extensive load testing before production
   - **Rollback**: Configuration flag to switch back to SQLite
   - **Monitoring**: Alert on p95 latency > 500ms

3. **Kubernetes Deployment Failures**
   - **Mitigation**: Deploy to staging first, canary rollouts
   - **Rollback**: Keep previous deployment in standby
   - **Validation**: Smoke tests after each deployment

4. **Security Vulnerabilities Discovered**
   - **Mitigation**: Continuous security scanning in CI/CD
   - **Response**: Hotfix deployment process < 2 hours
   - **Prevention**: Monthly security audits

### Medium-Risk Areas

1. **Cache Performance Issues**
   - Monitor cache hit rates, tune TTLs and eviction policies

2. **Third-Party API Rate Limits**
   - Implement exponential backoff, monitor quota usage

3. **Database Connection Pool Exhaustion**
   - Size pools appropriately, implement circuit breakers

---

## Success Metrics

### Performance

- ✅ p95 API latency < 500ms
- ✅ p99 API latency < 1000ms
- ✅ Cache hit rate > 80%
- ✅ Support 100+ concurrent users
- ✅ Database query latency < 100ms

### Reliability

- ✅ 99.9% uptime SLA
- ✅ Zero data loss during migrations
- ✅ < 1 minute recovery time objective (RTO)
- ✅ < 5 minutes recovery point objective (RPO)

### Security

- ✅ Zero critical security vulnerabilities
- ✅ All secrets managed securely
- ✅ GDPR compliance implemented
- ✅ API rate limiting functional

### Operational

- ✅ 100% monitoring coverage
- ✅ Alerts routing correctly
- ✅ Runbooks for 10+ scenarios
- ✅ Operations team trained

---

## Dependencies

### Infrastructure

- PostgreSQL instance (RDS, Cloud SQL, or self-hosted)
- Kubernetes cluster (GKE, EKS, AKS, or self-hosted)
- Redis instance for caching
- Domain name and TLS certificates

### Tools

- k6 for load testing
- Prometheus for metrics
- Grafana for dashboards
- Alertmanager for alerts
- kubectl for Kubernetes management

### Access

- Production database credentials
- Kubernetes cluster admin access
- Domain DNS management
- Cloud provider credentials (if applicable)

---

## Next Actions

**Immediate (This Week)**:

1. ✅ Review this execution plan
2. ⏳ Provision PostgreSQL instance
3. ⏳ Run PostgreSQL migration
4. ⏳ Deploy monitoring stack locally

**This Month**:

1. Complete PostgreSQL migration and validation
2. Complete load testing and optimization
3. Deploy monitoring to production

**Next Month**:

1. Complete Kubernetes production deployment
2. Complete security hardening
3. Production launch and validation

---

## Change Log

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2025-11-12 | 1.0 | Initial Phase Three execution plan | System |

---

## References

- [ARCHITECTURE_AND_READINESS.md](ARCHITECTURE_AND_READINESS.md) - Section 6: Phase Three
- [PHASE_THREE_SCALING.md](docs/PHASE_THREE_SCALING.md) - Performance optimization details
- [DATABASE_INDEX_OPTIMIZATION.md](docs/DATABASE_INDEX_OPTIMIZATION.md) - Index strategy
- [DEPLOYMENT.md](docs/DEPLOYMENT.md) - Deployment procedures
- [OPERATIONS.md](docs/OPERATIONS.md) - Daily operations guide

---

**Status Updates**: Update this document weekly with progress on each milestone.
