# Production Deployment Guide

**Document Version**: 1.0  
**Last Updated**: November 12, 2025  
**Target Audience**: DevOps, SREs, Platform Engineers

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Environment Configuration](#environment-configuration)
4. [Docker Deployment](#docker-deployment)
5. [Kubernetes Deployment](#kubernetes-deployment)
6. [Monitoring Setup](#monitoring-setup)
7. [Database Configuration](#database-configuration)
8. [Redis Configuration](#redis-configuration)
9. [Health Checks](#health-checks)
10. [Rate Limiting](#rate-limiting)
11. [Security Hardening](#security-hardening)
12. [Scaling Guidelines](#scaling-guidelines)
13. [Troubleshooting](#troubleshooting)

---

## Overview

Signal Harvester is a production-ready intelligence platform that can be deployed in multiple configurations:

- **Single Node**: Docker Compose for small-medium workloads
- **Distributed**: Kubernetes for high availability and horizontal scaling
- **Hybrid**: Mix of managed services (RDS, ElastiCache) with containerized API

### Architecture Components

```
┌─────────────────┐
│   Load Balancer │
│   (Ingress/ALB) │
└────────┬────────┘
         │
    ┌────▼────────────────┐
    │  API Instances (3+) │
    │  (FastAPI + Uvicorn)│
    └──┬────┬─────────┬───┘
       │    │         │
   ┌───▼─┐ ┌▼─────┐ ┌▼──────┐
   │Redis│ │ DB   │ │Prometheus│
   │     │ │(PG)  │ │/Grafana  │
   └─────┘ └──────┘ └─────────┘
```

---

## Prerequisites

### Required Software

- **Docker**: >= 20.10
- **Docker Compose**: >= 2.0 (for single-node deployment)
- **Kubernetes**: >= 1.24 (for distributed deployment)
- **kubectl**: >= 1.24
- **Helm**: >= 3.10 (optional, for monitoring stack)

### Recommended Infrastructure

- **API Instances**: 2-4 vCPUs, 4-8 GB RAM per instance
- **Database**: PostgreSQL 14+ with 4 vCPUs, 16 GB RAM, 100 GB SSD
- **Redis**: Redis 7+ with 2 vCPUs, 8 GB RAM
- **Storage**: 100+ GB for database, 20 GB for logs

---

## Environment Configuration

### Required Environment Variables

Create a `.env` file with the following variables:

```bash
# Application
HARVEST_API_KEY=your-secure-api-key-here
HARVEST_ENV=production
HARVEST_VERSION=0.1.0

# Database (PostgreSQL recommended for production)
DATABASE_URL=postgresql://user:password@db-host:5432/signal_harvester
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10
DATABASE_POOL_TIMEOUT=30
DATABASE_POOL_RECYCLE=3600

# Redis (for rate limiting & caching)
REDIS_HOST=redis-host
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your-redis-password

# LLM Providers (choose one or more)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
XAI_API_KEY=xai-...

# External APIs
X_BEARER_TOKEN=your-twitter-bearer-token
GITHUB_TOKEN=ghp_...
FACEBOOK_ACCESS_TOKEN=...
LINKEDIN_ACCESS_TOKEN=...

# Monitoring (optional)
SENTRY_DSN=https://...@sentry.io/...
PROMETHEUS_ENABLED=true

# Notifications (optional)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

### Configuration File

Copy and customize `config/settings.yaml`:

```bash
cp config/settings.yaml config/settings.production.yaml
```

Key settings to configure:

```yaml
database:
  url: ${DATABASE_URL}
  pool:
    size: 20
    max_overflow: 10
    timeout: 30
    recycle: 3600

embeddings:
  redis_enabled: true
  redis_host: ${REDIS_HOST}
  redis_port: 6379
  cache_ttl: 604800  # 7 days

discovery:
  schedule_interval: 3600  # 1 hour
  max_concurrent_sources: 5

topic_evolution:
  schedule_interval: 86400  # 24 hours
  min_artifacts_per_topic: 3
```

---

## Docker Deployment

### Single-Node Deployment with Docker Compose

1. **Create production docker-compose.yml**:

```yaml
version: '3.8'

services:
  api:
    image: signal-harvester:latest
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:password@db:5432/signal_harvester
      - REDIS_HOST=redis
    env_file:
      - .env
    depends_on:
      - db
      - redis
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health/ready"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    restart: unless-stopped
    volumes:
      - ./config:/app/config:ro
      - ./logs:/app/logs
      - ./data:/app/data

  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: signal_harvester
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    restart: unless-stopped

  scheduler:
    image: signal-harvester:latest
    command: harvest daemon
    environment:
      - DATABASE_URL=postgresql://postgres:password@db:5432/signal_harvester
      - REDIS_HOST=redis
    env_file:
      - .env
    depends_on:
      - db
      - redis
      - api
    restart: unless-stopped
    volumes:
      - ./config:/app/config:ro
      - ./logs:/app/logs

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus:/etc/prometheus
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=30d'
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
      - GF_INSTALL_PLUGINS=redis-datasource
    volumes:
      - ./monitoring/grafana:/etc/grafana/provisioning
      - grafana_data:/var/lib/grafana
    depends_on:
      - prometheus
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
  prometheus_data:
  grafana_data:
```

2. **Build and deploy**:

```bash
# Build image
docker-compose build

# Start all services
docker-compose up -d

# Check logs
docker-compose logs -f api

# Verify health
curl http://localhost:8000/health/ready
```

3. **Initialize database**:

```bash
docker-compose exec api harvest init-db
docker-compose exec api alembic upgrade head
```

---

## Kubernetes Deployment

### Prerequisites

1. **Kubernetes cluster** (GKE, EKS, AKS, or self-hosted)
2. **kubectl configured** to access cluster
3. **Container registry** for images (GCR, ECR, ACR, or Docker Hub)

### Deployment Steps

1. **Build and push Docker image**:

```bash
# Tag image
docker build -t gcr.io/your-project/signal-harvester:v0.1.0 .

# Push to registry
docker push gcr.io/your-project/signal-harvester:v0.1.0
```

2. **Create namespace**:

```bash
kubectl create namespace signal-harvester
kubectl config set-context --current --namespace=signal-harvester
```

3. **Create secrets**:

```bash
# API secrets
kubectl create secret generic signal-harvester-secrets \
  --from-env-file=.env

# Database credentials
kubectl create secret generic postgres-secrets \
  --from-literal=password=your-secure-password

# Redis credentials
kubectl create secret generic redis-secrets \
  --from-literal=password=your-redis-password
```

4. **Deploy using Kubernetes manifests**:

```bash
# Apply all manifests
kubectl apply -f k8s/base/

# Check deployment status
kubectl get pods -w
kubectl get deployments
kubectl get services
```

5. **Access the application**:

```bash
# Get load balancer IP
kubectl get service signal-harvester-api

# Or use port forwarding for testing
kubectl port-forward service/signal-harvester-api 8000:8000
```

### Kubernetes Manifest Example (k8s/base/deployment.yaml)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: signal-harvester-api
  labels:
    app: signal-harvester
    component: api
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: signal-harvester
      component: api
  template:
    metadata:
      labels:
        app: signal-harvester
        component: api
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8000"
        prometheus.io/path: "/metrics"
    spec:
      containers:
      - name: api
        image: gcr.io/your-project/signal-harvester:v0.1.0
        imagePullPolicy: Always
        ports:
        - name: http
          containerPort: 8000
          protocol: TCP
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: signal-harvester-secrets
              key: DATABASE_URL
        - name: REDIS_HOST
          value: "redis-service"
        - name: REDIS_PASSWORD
          valueFrom:
            secretKeyRef:
              name: redis-secrets
              key: password
        resources:
          requests:
            memory: "2Gi"
            cpu: "1000m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 3
        startupProbe:
          httpGet:
            path: /health/startup
            port: 8000
          initialDelaySeconds: 0
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 30
      terminationGracePeriodSeconds: 30
```

---

## Monitoring Setup

### Prometheus Metrics

Signal Harvester exports comprehensive metrics at `/metrics` endpoint:

```bash
# Test metrics endpoint
curl http://localhost:8000/metrics
```

**Available Metrics**:

- `http_requests_total` - Total HTTP requests by method, endpoint, status
- `http_request_duration_seconds` - Request latency histogram
- `db_query_duration_seconds` - Database query latency
- `cache_hits_total` / `cache_misses_total` - Cache performance
- `rate_limit_denials_total` - Rate limiting statistics
- `discoveries_fetched_total` - Discovery pipeline metrics
- `errors_total` - Error rates by type and severity

### Grafana Dashboards

Pre-configured dashboards available in `monitoring/grafana/dashboards/`:

1. **API Performance Dashboard**: Request rates, latencies, error rates
2. **Database Dashboard**: Query performance, connection pool, slow queries
3. **Discovery Pipeline Dashboard**: Fetch rates, scoring, topic evolution
4. **Rate Limiting Dashboard**: Limit enforcement, denials by tier

Import dashboards:

```bash
# Copy dashboards to Grafana provisioning
cp monitoring/grafana/dashboards/* /etc/grafana/provisioning/dashboards/
```

### Alert Rules

Configure alerts in `monitoring/prometheus/alerts.yml`:

```yaml
groups:
  - name: signal_harvester_alerts
    rules:
      - alert: HighErrorRate
        expr: rate(errors_total[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected"
          
      - alert: SlowDatabaseQueries
        expr: histogram_quantile(0.95, db_query_duration_seconds_bucket) > 0.5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Database queries are slow (p95 > 500ms)"
```

---

## Database Configuration

### PostgreSQL Setup (Recommended for Production)

1. **Provision PostgreSQL**:
   - AWS RDS PostgreSQL
   - Google Cloud SQL
   - Azure Database for PostgreSQL
   - Self-hosted with streaming replication

2. **Create database**:

```sql
CREATE DATABASE signal_harvester;
CREATE USER harvest_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE signal_harvester TO harvest_user;
```

3. **Run migrations**:

```bash
# Set connection string
export DATABASE_URL=postgresql://harvest_user:password@db-host:5432/signal_harvester

# Apply migrations
alembic upgrade head
```

4. **Configure connection pooling**:

```yaml
# config/settings.production.yaml
database:
  url: ${DATABASE_URL}
  pool:
    size: 20               # Connections per API instance
    max_overflow: 10       # Extra connections allowed
    timeout: 30            # Connection acquisition timeout
    recycle: 3600          # Recycle connections after 1 hour
  query_timeout: 30.0      # Query timeout in seconds
```

### Performance Tuning

```sql
-- PostgreSQL settings (postgresql.conf)
shared_buffers = 4GB
effective_cache_size = 12GB
maintenance_work_mem = 1GB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1  -- For SSD
work_mem = 32MB
```

---

## Redis Configuration

### Redis Setup

1. **Provision Redis**:
   - AWS ElastiCache
   - Google Cloud Memorystore
   - Azure Cache for Redis
   - Self-hosted Redis cluster

2. **Configure Signal Harvester**:

```yaml
# config/settings.production.yaml
embeddings:
  redis_enabled: true
  redis_host: redis.example.com
  redis_port: 6379
  redis_db: 0
  redis_password: ${REDIS_PASSWORD}
  cache_ttl: 604800  # 7 days

rate_limiting:
  redis_enabled: true
  redis_host: redis.example.com
  redis_port: 6379
  redis_db: 1  # Separate database for rate limiting
```

3. **Redis performance settings** (`redis.conf`):

```conf
maxmemory 8gb
maxmemory-policy allkeys-lru
appendonly yes
appendfsync everysec
```

---

## Health Checks

Signal Harvester provides three health check endpoints for Kubernetes probes:

### Liveness Probe (`/health/live`)

- **Purpose**: Verify application process is running
- **Response Time**: < 100ms
- **Checks**: Process responsiveness only
- **Failure Action**: Restart container

### Readiness Probe (`/health/ready`)

- **Purpose**: Verify application can serve traffic
- **Response Time**: < 5s
- **Checks**:
  - Database connectivity and performance
  - Redis availability (non-critical)
  - Disk space (>10% free)
  - Memory usage (<85%)
- **Failure Action**: Remove from load balancer

### Startup Probe (`/health/startup`)

- **Purpose**: Verify application initialization complete
- **Response Time**: < 30s
- **Checks**: Same as readiness
- **Failure Action**: Restart container if startup fails

### Example Health Check Response

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "uptime_seconds": 3600.5,
  "components": [
    {
      "name": "database",
      "status": "healthy",
      "message": "Database is healthy",
      "last_check": "2025-11-12T10:00:00Z",
      "check_duration_ms": 15.3
    },
    {
      "name": "redis",
      "status": "healthy",
      "message": "Redis is healthy",
      "last_check": "2025-11-12T10:00:00Z",
      "check_duration_ms": 8.1
    }
  ],
  "timestamp": "2025-11-12T10:00:00Z"
}
```

---

## Rate Limiting

### Distributed Rate Limiting Architecture

Signal Harvester uses Redis-backed distributed rate limiting for horizontal scaling:

**Rate Limit Tiers**:

| Tier | Max Requests | Window | Use Case |
|------|-------------|--------|----------|
| Anonymous | 100 req/min | 60s | IP-based, no auth |
| API Key | 1000 req/min | 60s | Authenticated users |
| Premium | 5000 req/min | 60s | Premium tier customers |
| Admin | Unlimited | N/A | Internal/admin access |

### Configuration

```yaml
# config/settings.production.yaml
rate_limiting:
  redis_enabled: true
  redis_host: ${REDIS_HOST}
  redis_port: 6379
  redis_db: 1
  anonymous_max_requests: 100
  api_key_max_requests: 1000
  premium_max_requests: 5000
  fallback_to_memory: true  # Fallback if Redis unavailable
```

### Rate Limit Headers

Responses include rate limit headers:

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 998
X-RateLimit-Reset: 1699876543
Retry-After: 42  # (on 429 errors)
```

---

## Security Hardening

### Production Security Checklist

- [ ] **API Key Rotation**: Implement 90-day rotation schedule
- [ ] **TLS/HTTPS**: Enable TLS 1.3 for all endpoints
- [ ] **Security Headers**: Enforce HSTS, CSP, X-Frame-Options
- [ ] **Network Policies**: Restrict pod-to-pod communication
- [ ] **Secrets Management**: Use Kubernetes secrets or vault
- [ ] **Vulnerability Scanning**: Run `harvest security scan` weekly
- [ ] **Access Logging**: Enable and monitor access logs
- [ ] **Database Encryption**: Enable encryption at rest
- [ ] **Redis Authentication**: Require password for Redis access
- [ ] **Rate Limiting**: Enforce rate limits on all endpoints

### Security Scanning

```bash
# Run security scan
harvest security scan --output security-report.json

# Check for critical vulnerabilities
harvest security scan --fail-on-critical

# Review recommendations
harvest security recommendations
```

---

## Scaling Guidelines

### Horizontal Scaling

**API Instances**:

```bash
# Kubernetes
kubectl scale deployment signal-harvester-api --replicas=5

# Docker Compose (manual)
docker-compose up -d --scale api=5
```

**Autoscaling** (Kubernetes HPA):

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: signal-harvester-api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: signal-harvester-api
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

### Vertical Scaling

**Database**:
- Scale to 8-16 vCPUs, 32-64 GB RAM for high load
- Add read replicas for read-heavy workloads

**Redis**:
- Scale to 4-8 vCPUs, 16-32 GB RAM for large caches
- Consider Redis Cluster for >50 GB data

---

## Troubleshooting

### Common Issues

**1. Database Connection Pool Exhausted**

```bash
# Check pool status
curl http://localhost:8000/metrics | grep db_connections

# Increase pool size
# In config/settings.yaml:
database:
  pool:
    size: 30
    max_overflow: 20
```

**2. Redis Connection Failures**

```bash
# Test Redis connectivity
docker exec -it redis redis-cli ping

# Check rate limiter fallback
curl http://localhost:8000/health/ready | jq '.components[] | select(.name=="redis")'
```

**3. Slow API Responses**

```bash
# Check query performance
harvest db profile-slow-queries --threshold 100

# Analyze slow queries
harvest db recommend-indexes
```

**4. High Memory Usage**

```bash
# Check memory metrics
curl http://localhost:8000/metrics | grep process_resident_memory

# Review cache sizes
curl http://localhost:8000/api/embeddings/stats
```

### Debug Mode

Enable debug logging:

```bash
# Set log level
export LOG_LEVEL=DEBUG

# Or in config/settings.yaml:
logging:
  level: DEBUG
  format: detailed
```

### Support Resources

- **Documentation**: `docs/` directory
- **Operations Guide**: `docs/OPERATIONS.md`
- **Security Audit**: `docs/SECURITY_AUDIT.md`
- **GitHub Issues**: https://github.com/your-org/signal-harvester/issues

---

## Production Readiness Checklist

- [ ] Environment variables configured
- [ ] Database migrations applied
- [ ] Redis connection tested
- [ ] Health checks passing
- [ ] Prometheus metrics exported
- [ ] Grafana dashboards imported
- [ ] Alert rules configured
- [ ] TLS certificates installed
- [ ] API keys rotated
- [ ] Security scan clean
- [ ] Backup procedures tested
- [ ] Disaster recovery plan documented
- [ ] Load testing completed
- [ ] Monitoring dashboards reviewed
- [ ] On-call rotation established

---

**Document Maintained By**: DevOps Team  
**Next Review**: 2025-12-12  
**Questions**: devops@example.com
